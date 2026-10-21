import { test, expect, Page } from '@playwright/test';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';
import { readFile } from 'node:fs/promises';

async function signIn(page: Page, suffix = '-training') {
  const credentials = requireTestCredentials();
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username + suffix);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
}
async function open(page: Page, name: string) {
  await page.getByRole('button', { name: 'Training jobs for ' + name, exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Development training · ' + name })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Refresh jobs', exact: true })).toBeEnabled();
}
async function fill(page: Page, regression = false) {
  await page
    .getByLabel('Task', { exact: true })
    .selectOption(regression ? 'regression' : 'classification');
  await page.getByLabel('Target column', { exact: true }).fill('outcome');
  if (!regression) await page.getByLabel('Positive class label', { exact: true }).fill('bad');
  await page
    .getByLabel('Business objective', { exact: true })
    .fill('Estimate synthetic development outcomes');
  await page
    .getByLabel('Development population', { exact: true })
    .fill('Synthetic development applicants');
  await page.getByLabel('Prediction horizon', { exact: true }).fill('12 months');
  await page
    .getByLabel('Outcome definition', { exact: true })
    .fill('Synthetic recorded event or value');
  await page
    .getByLabel('Label maturity and follow-up', { exact: true })
    .fill('Complete synthetic follow-up');
  await page
    .getByLabel('Primary metric', { exact: true })
    .selectOption(regression ? 'rmse' : 'roc_auc');
  await page.getByLabel('Numeric predictor columns', { exact: true }).fill('x\nz');
  await page
    .getByLabel('Validation strategy', { exact: true })
    .selectOption(regression ? 'group' : 'random');
  if (regression) await page.getByLabel('Group column', { exact: true }).fill('entity');
  await page.getByLabel('I confirm all rows belong', { exact: false }).check();
  await page.getByLabel('I confirm every selected predictor', { exact: false }).check();
}
async function preview(page: Page) {
  const prepared = page.waitForResponse(
    (r) => r.url().includes('/training-input/') && r.request().method() === 'POST',
  );
  await expect(
    page.getByRole('button', { name: 'Prepare training preview', exact: true }),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Prepare training preview', exact: true }).focus();
  await expect(
    page.getByRole('button', { name: 'Prepare training preview', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  const response = await prepared;
  expect(response.status()).toBe(200);
  await expect(
    page.getByRole('heading', { name: '2. Review the exact plan', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Queue reviewed training search', exact: true }),
  ).toBeDisabled();
  return { receipt: await response.json(), options: response.request().postDataJSON() };
}
async function finish(page: Page, job: any, testInfo: any) {
  await expect
    .poll(
      async () => (await (await page.request.get(API_BASE_URL + `jobs/${job.id}/`)).json()).state,
      { timeout: 30000 },
    )
    .toBe('succeeded');
  await page.getByRole('button', { name: 'Refresh jobs', exact: true }).click();
  await expect(page.locator('app-package-jobs')).toContainText('Job state: succeeded');
  await expect(page.locator('app-package-jobs')).toContainText('Development search:');
  await expect(
    page.getByRole('button', { name: 'Use receipt for review action', exact: true }),
  ).toHaveCount(0);
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download job receipt', exact: true }).focus();
  await page.keyboard.press('Enter');
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe(`job-${job.id}.json`);
  const receipt = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(receipt.result.candidates).toHaveLength(2);
  expect(receipt.result.model_format).toBe('xgboost_json');
  expect(JSON.parse(receipt.result.model_json).learner).toBeDefined();
  expect(receipt.result.final_holdout_accessed).toBe(false);
  expect(receipt.result.model_adopted).toBe(false);
  expect(receipt.result.review_approved).toBe(false);
  expect(receipt.result.production_use_approved).toBe(false);
  await testInfo.attach('training-job-receipt', {
    body: JSON.stringify(receipt, null, 2),
    contentType: 'application/json',
  });
  return receipt;
}

test('developer downloads a revision-pinned read-only operational handoff by keyboard', async ({
  page,
}, testInfo) => {
  await signIn(page);
  await open(page, 'Operations binary.csv');
  await fill(page);
  await preview(page);
  await page.getByLabel('I reviewed this exact declaration', { exact: false }).check();
  const response = page.waitForResponse(
    (r) => /\/jobs\/datasets\/\d+\/\?/.test(r.url()) && r.request().method() === 'POST',
  );
  await expect(
    page.getByRole('button', { name: 'Queue reviewed training search', exact: true }),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Queue reviewed training search', exact: true }).focus();
  await page.keyboard.press('Enter');
  const submitted = await response;
  expect(submitted.status()).toBe(202);
  const job = await submitted.json();
  await finish(page, job, testInfo);
  await page.getByRole('button', { name: 'Inspect operational handoff', exact: true }).focus();
  await page.keyboard.press('Enter');
  const panel = page.getByRole('region', { name: 'Operational review handoff', exact: true });
  await expect(panel).toContainText('independent reviewer');
  await expect(panel).toContainText('0 unresolved');
  const downloadEvent = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Download operational handoff', exact: true }).focus();
  await page.keyboard.press('Enter');
  const download = await downloadEvent;
  const handoff = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(handoff.schema).toBe('native_operational_handoff_v1');
  expect(handoff.job_id).toBe(job.id);
  expect(handoff.read_only).toBe(true);
  expect(handoff.state).toBe('succeeded');
  expect(handoff.review_approved).toBe(false);
  expect(handoff.recovery_authorized).toBe(false);
  expect(handoff.production_use_approved).toBe(false);
  expect(handoff.model_json).toBeUndefined();
  await panel.screenshot({
    path: testInfo.outputPath('operational-handoff.png'),
    animations: 'disabled',
  });
  await testInfo.attach('operational-handoff', {
    body: JSON.stringify(handoff, null, 2),
    contentType: 'application/json',
  });
});
