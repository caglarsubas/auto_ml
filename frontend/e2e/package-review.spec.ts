import { test, expect } from '@playwright/test';
import { API_BASE_URL, BASE_URL, requireTestCredentials } from './fixtures/credentials';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

async function developerApi(playwright: any) {
  const credentials = requireTestCredentials();
  const bootstrap = await playwright.request.newContext({ baseURL: API_BASE_URL });
  const csrf = (await (await bootstrap.get('auth/session/')).json()).csrf_token;
  const login = await bootstrap.post('auth/login/', {
    data: { username: credentials.username + '-review-developer', password: credentials.password },
    headers: { 'X-CSRFToken': csrf, Origin: new URL(BASE_URL).origin },
  });
  expect(login.status()).toBe(200);
  const session = await login.json();
  const api = await playwright.request.newContext({
    baseURL: API_BASE_URL,
    storageState: await bootstrap.storageState(),
    extraHTTPHeaders: { 'X-CSRFToken': session.csrf_token, Origin: new URL(BASE_URL).origin },
  });
  await bootstrap.dispose();
  return api;
}
async function signIn(page: any, suffix: string) {
  const credentials = requireTestCredentials();
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username + suffix);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  if (suffix === '-workspace')
    await page.getByLabel('Current project').selectOption({ label: 'Workspace Review — reviewer' });
  await page
    .getByRole('button', { name: 'Review package for Workspace Review.csv', exact: true })
    .click();
  await expect(page.getByRole('heading', { name: /Package review · Dataset/ })).toBeVisible();
  await expect(page.getByText('Current frozen package:')).toBeVisible();
}

let api: any;
let fileId: number;
test.beforeEach(async ({ playwright }) => {
  api = await developerApi(playwright);
  const datasets = await (await api.get('declaration/')).json();
  fileId = datasets.find((d: any) => d.original_name === 'Workspace Review.csv').id;
  const packageResult = await api.post('deployment/bundle/', { data: { file_id: fileId } });
  expect(packageResult.status()).toBe(200);
});
test.afterEach(async () => {
  await api.post('auth/logout/');
  await api.dispose();
});

async function openNewReview(page: any) {
  await signIn(page, '-workspace');
  const created = page.waitForResponse(
    (r: any) => r.url().includes('/reviews/datasets/') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Start package review', exact: true }).focus();
  await page.keyboard.press('Enter');
  const result = await created;
  expect(result.status()).toBe(200);
  return await result.json();
}

test('reviewer and developer complete an attributable keyboard workflow and export exact evidence', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const created = await openNewReview(page);
  await page.getByRole('button', { name: 'Queue integrity check', exact: true }).focus();
  const submitted = page.waitForResponse(
    (r: any) => r.url().includes('/jobs/datasets/') && r.request().method() === 'POST',
  );
  await page.keyboard.press('Enter');
  const jobResponse = await submitted;
  expect(jobResponse.status()).toBe(202);
  const job = await jobResponse.json();
  expect(job.specification.bundle_id).toBe(created.bundle_id);
  expect(job.specification.manifest_sha256).toBe(created.manifest_sha256);
  await expect
    .poll(async () => (await (await api.get(`jobs/${job.id}/`)).json()).state, { timeout: 30000 })
    .toBe('succeeded');
  await page.getByRole('button', { name: 'Refresh jobs', exact: true }).click();
  await expect(page.locator('app-package-jobs')).toContainText('Job state: succeeded');
  const downloadButton = page.getByRole('button', { name: 'Download job receipt', exact: true });
  await expect(downloadButton).toBeEnabled();
  const jobDownload = page.waitForEvent('download');
  await downloadButton.focus();
  await page.keyboard.press('Enter');
  const receiptDownload = await jobDownload;
  expect(receiptDownload.suggestedFilename()).toBe(`job-${job.id}.json`);
  const jobReceipt = JSON.parse(await readFile((await receiptDownload.path())!, 'utf8'));
  expect(jobReceipt.events.map((e: any) => e.event_type)).toEqual([
    'submitted',
    'started',
    'succeeded',
  ]);
  expect(jobReceipt.result.model_state_loaded).toBe(false);
  expect(jobReceipt.production_use_approved).toBe(false);
  await page.getByLabel('Finding severity').selectOption('major');
  await page
    .getByLabel('Finding, response or disposition')
    .fill('<script>synthetic finding requiring evidence</script>');
  await page.getByRole('button', { name: 'Record review action', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Review findings')).toContainText('major · open');
  await expect(page.locator('app-package-review script')).toHaveCount(0);
  await page.getByRole('button', { name: /sign out/i }).click();
  await signIn(page, '-review-developer');
  await page.getByRole('button', { name: 'Open review ' + created.id, exact: true }).click();
  await expect(page.getByLabel('Review action')).toHaveValue('response');
  await expect(page.getByRole('button', { name: 'Start package review', exact: true })).toHaveCount(
    0,
  );
  const finding = page.getByLabel('Finding', { exact: true });
  await finding.selectOption({ index: 1 });
  await page
    .getByLabel('Finding, response or disposition')
    .fill('Developer supplies reproducible supporting evidence.');
  await page.getByRole('button', { name: 'Record review action', exact: true }).click();
  await expect(page.getByLabel('Review findings')).toContainText('1 developer responses');
  await page.screenshot({
    path: testInfo.outputPath('review-developer.png'),
    animations: 'disabled',
  });
  await page.getByRole('button', { name: /sign out/i }).click();
  await signIn(page, '-workspace');
  await page.getByRole('button', { name: 'Open review ' + created.id, exact: true }).click();
  await page.getByLabel('Review action').selectOption('resolve');
  await page.getByLabel('Finding', { exact: true }).selectOption({ index: 1 });
  await page
    .getByLabel('Finding, response or disposition')
    .fill('Reviewer checked the supplied evidence; finding resolved.');
  await page.getByRole('button', { name: 'Record review action', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Review findings')).toContainText('major · resolved');
  const discussionDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download discussion evidence', exact: true }).focus();
  await page.keyboard.press('Enter');
  const discussion = await discussionDownload;
  expect(discussion.suggestedFilename()).toBe(`review-${created.id}.json`);
  const exported = JSON.parse(await readFile((await discussion.path())!, 'utf8'));
  expect(exported.events.map((e: any) => e.event_type)).toEqual([
    'opened',
    'finding',
    'response',
    'resolve',
  ]);
  expect(exported.events[2].authority.role).toBe('developer');
  expect(exported.events[3].authority.role).toBe('reviewer');
  expect(exported.manifest_sha256).toBe(created.manifest_sha256);
  expect(exported.review_approved).toBe(false);
  expect(exported.production_use_approved).toBe(false);
  const packageDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download exact package', exact: true }).click();
  expect((await packageDownload).suggestedFilename()).toBe(`package-${created.bundle_id}.zip`);
  await page.screenshot({
    path: testInfo.outputPath('review-reviewer.png'),
    animations: 'disabled',
  });
  expect(errors).toEqual([]);
});

test('changed development context preserves historical discussion and blocks edits', async ({
  page,
}) => {
  const created = await openNewReview(page);
  const pipelines = await (await api.get('pipeline/')).json();
  const run = pipelines.find((p: any) => p.file_id === fileId);
  const changed = await api.put(`pipeline/${run.id}/`, {
    data: {
      state: { file_id: fileId, business_understanding: { objective: 'Changed after review' } },
    },
  });
  expect(changed.status()).toBe(200);
  await page.getByRole('button', { name: 'Refresh review', exact: true }).click();
  await expect(page.getByText('This review is historical', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Record review action', exact: true })).toHaveCount(
    0,
  );
  const denied = await api.post(`reviews/${created.id}/`, {
    data: {
      request_id: crypto.randomUUID(),
      expected_revision: created.revision,
      event_type: 'response',
      finding_id: crypto.randomUUID(),
      text: 'Stale response',
    },
  });
  expect(denied.status()).toBe(409);
  expect((await denied.json()).error_code).toBe('package_review_stale');
});

test('developer queues exact CSV scoring by keyboard and downloads a full worker receipt', async ({
  page,
}, testInfo) => {
  await signIn(page, '-review-developer');
  await expect(page.getByLabel('Scoring input dataset ID')).toHaveValue(String(fileId));
  await page.getByRole('button', { name: 'Prepare scoring input', exact: true }).focus();
  await page.keyboard.press('Enter');
  const queue = page.getByRole('button', { name: 'Queue CSV scoring', exact: true });
  await expect(queue).toBeEnabled();
  const submitted = page.waitForResponse(
    (r: any) => r.url().includes('/jobs/datasets/') && r.request().method() === 'POST',
  );
  await queue.focus();
  await page.keyboard.press('Enter');
  const response = await submitted;
  expect(response.status()).toBe(202);
  const job = await response.json();
  expect(job.specification.source.file_id).toBe(fileId);
  await expect
    .poll(async () => (await (await api.get(`jobs/${job.id}/`)).json()).state, { timeout: 30_000 })
    .toBe('succeeded');
  await page.getByRole('button', { name: 'Refresh jobs', exact: true }).click();
  await expect(page.locator('app-package-jobs')).toContainText('Job state: succeeded');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download full scoring receipt', exact: true }).focus();
  await page.keyboard.press('Enter');
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe(`scoring-${job.id}.json`);
  const raw = await readFile((await download.path())!);
  const receipt = JSON.parse(raw.toString());
  const current = await (await api.get(`jobs/${job.id}/`)).json();
  expect(createHash('sha256').update(raw).digest('hex')).toBe(current.result_sha256);
  expect(receipt.n_scored).toBeGreaterThan(0);
  expect(receipt.scores.length).toBe(receipt.n_scored);
  expect(receipt.input.sha256).toBe(job.specification.source.sha256);
  expect(receipt.review_approved).toBe(false);
  expect(receipt.production_use_approved).toBe(false);
  await page.screenshot({
    path: testInfo.outputPath('durable-csv-scoring.png'),
    animations: 'disabled',
  });
});

test('review panel and authority disappear on project switch or access refresh failure', async ({
  page,
}) => {
  await openNewReview(page);
  await page.getByLabel('Current project').selectOption({ label: 'Workspace A — developer' });
  await expect(page.locator('app-package-review')).toHaveCount(0);
  await page.getByLabel('Current project').selectOption({ label: 'Workspace Review — reviewer' });
  await page
    .getByRole('button', { name: 'Review package for Workspace Review.csv', exact: true })
    .click();
  await page.route('**/api/projects/', (route) =>
    route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }),
  );
  await page.getByRole('button', { name: 'Refresh access', exact: true }).click();
  await expect(page.locator('app-package-review')).toHaveCount(0);
});
