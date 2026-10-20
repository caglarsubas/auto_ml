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

test('developer reviews and queues binary search by keyboard and downloads native evidence', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await signIn(page);
  await open(page, 'Training binary.csv');
  await fill(page);
  const { receipt, options } = await preview(page);
  expect(receipt.prediction_contract.positive_class).toBe('bad');
  await page.getByText('Exact declaration, row membership and runtime', { exact: true }).click();
  await expect(page.locator('app-training-launch pre')).toContainText(receipt.training_sha256);
  await page.getByText('Exact declaration, row membership and runtime', { exact: true }).click();
  await page.getByLabel('I reviewed this exact declaration', { exact: false }).check();
  await page.locator('app-training-launch .preview').screenshot({
    path: testInfo.outputPath('training-reviewed-preview.png'),
    animations: 'disabled',
  });
  const queued = page.waitForResponse(
    (r) => /\/jobs\/datasets\/\d+\/\?/.test(r.url()) && r.request().method() === 'POST',
  );
  await expect(
    page.getByRole('button', { name: 'Queue reviewed training search', exact: true }),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Queue reviewed training search', exact: true }).focus();
  await expect(
    page.getByRole('button', { name: 'Queue reviewed training search', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  const response = await queued;
  expect(response.status()).toBe(202);
  const submitted = response.request().postDataJSON();
  expect(submitted).toEqual({
    ...options,
    request_id: expect.any(String),
    kind: receipt.kind,
    input_sha256: receipt.input_sha256,
    training_sha256: receipt.training_sha256,
  });
  const result = await finish(page, await response.json(), testInfo);
  expect(result.result.metric.primary_metric).toBe('roc_auc');
  expect(result.result.prediction_contract.positive_class).toBe('bad');
  await page.getByRole('button', { name: 'Close training panel', exact: true }).click();
  await open(page, 'Training binary.csv');
  await page.getByRole('button', { name: 'Open job ' + result.id, exact: true }).click();
  await expect(page.locator('app-package-jobs')).toContainText('Job state: succeeded');
  expect(errors).toEqual([]);
});

test('regression edit invalidates approval and uncertain admission retries the identical request', async ({
  page,
}, testInfo) => {
  await signIn(page);
  await open(page, 'Training regression.csv');
  await fill(page, true);
  await preview(page);
  await page.getByLabel('I reviewed this exact declaration', { exact: false }).check();
  await page
    .getByLabel('Business objective', { exact: true })
    .fill('Changed explicit development regression objective');
  await expect(page.getByRole('heading', { name: '2. Review the exact plan' })).toHaveCount(0);
  const { receipt } = await preview(page);
  expect(receipt.prediction_contract.task).toBe('regression');
  await page.getByLabel('I reviewed this exact declaration', { exact: false }).check();
  let firstBody: any;
  let firstId = '';
  await page.route(
    '**/api/jobs/datasets/*/?*',
    async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      firstBody = route.request().postDataJSON();
      const actual = await route.fetch();
      expect(actual.status()).toBe(202);
      firstId = (await actual.json()).id;
      await route.abort('failed'); // Real admitted request; only its response is lost.
    },
    { times: 1 },
  );
  await page.getByRole('button', { name: 'Queue reviewed training search', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('unconfirmed');
  await expect(page.getByLabel('Numeric predictor columns', { exact: true })).toBeDisabled();
  const retried = page.waitForResponse(
    (r) => /\/jobs\/datasets\/\d+\/\?/.test(r.url()) && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Retry exact training request', exact: true }).click();
  const response = await retried;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toEqual(firstBody);
  const job = await response.json();
  expect(job.id).toBe(firstId);
  expect(job.replayed).toBe(true);
  const result = await finish(page, job, testInfo);
  expect(result.result.prediction_contract.task).toBe('regression');
  expect(result.result.metric.primary_metric).toBe('rmse');
  expect(result.result.candidates[0].folds).toHaveLength(2);
  await page.screenshot({
    path: testInfo.outputPath('training-durable-result.png'),
    animations: 'disabled',
  });
});

test('reviewer can inspect history while launch and forged preview remain denied', async ({
  page,
}) => {
  await signIn(page, '-training-reviewer');
  await open(page, 'Training binary.csv');
  await expect(page.locator('app-training-launch form')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Prepare training preview', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Durable job history', exact: true }),
  ).toBeVisible();
  const datasets = await (await page.request.get(API_BASE_URL + 'declaration/')).json();
  const dataset = datasets.find((d: any) => d.original_name === 'Training binary.csv');
  const csrf = (await (await page.request.get(API_BASE_URL + 'auth/session/')).json()).csrf_token;
  const denied = await page.request.post(
    API_BASE_URL +
      `jobs/datasets/${dataset.id}/training-input/?project_id=${await page.getByLabel('Current project').inputValue()}`,
    {
      data: { data_role: 'development_only' },
      headers: { 'X-CSRFToken': csrf },
    },
  );
  expect(denied.status()).toBe(403);
  await page.route('**/api/projects/', (route) =>
    route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }),
  );
  await page.getByRole('button', { name: 'Refresh access', exact: true }).click();
  await expect(page.locator('app-training-launch')).toHaveCount(0);
  await expect(page.getByLabel('Project datasets')).toHaveCount(0);
});
