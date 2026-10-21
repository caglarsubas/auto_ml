import { test, expect } from '@playwright/test';
import { requireTestCredentials } from './fixtures/credentials';

test('developer navigates bounded queue history and filters by keyboard without executing work', async ({
  page,
}, testInfo) => {
  const credentials = requireTestCredentials();
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username + '-training');
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  await page
    .getByRole('button', { name: 'Training jobs for Queue history.csv', exact: true })
    .focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Browse queue and history', exact: true }),
  ).toBeEnabled();
  const mutations: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/jobs/') && r.method() !== 'GET')
      mutations.push(r.method() + ' ' + r.url());
  });
  const observed = page.waitForResponse((r) => r.url().includes('/history/'));
  await page.getByRole('button', { name: 'Browse queue and history', exact: true }).focus();
  await page.keyboard.press('Enter');
  const first = await (await observed).json();
  expect(first.jobs).toHaveLength(50);
  expect(first.queue.states).toMatchObject({ failed: 41, cancelled: 41, blocked: 41, running: 0 });
  expect(first.queue.live_service_health).toBe('not_observed');
  expect(first.queue.recovery_authorized).toBe(false);
  const panel = page.locator('app-native-job-history');
  await expect(page.getByRole('list', { name: 'Dataset jobs', exact: true })).toHaveCount(0);
  await expect(
    panel.getByText('Live worker and broker health: not observed.', { exact: false }),
  ).toBeVisible();
  await expect(
    panel.getByRole('list', { name: 'Bounded job history' }).getByRole('listitem'),
  ).toHaveCount(50);
  await expect(panel.getByRole('button', { name: 'Newer history', exact: true })).toBeDisabled();
  async function navigate(label: string) {
    const response = page.waitForResponse((r) => r.url().includes('/history/'));
    await panel.getByRole('button', { name: label, exact: true }).focus();
    await page.keyboard.press('Enter');
    const result = await response;
    expect(result.status()).toBe(200);
    const value = await result.json();
    await expect(
      panel.getByRole('button', { name: 'Inspect history job ' + value.jobs[0].id, exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole('list', { name: 'Bounded job history' }).getByRole('listitem'),
    ).toHaveCount(value.jobs.length);
    return value;
  }
  const second = await navigate('Older history');
  expect(second.jobs).toHaveLength(50);
  expect(second.history_cutoff).toBe(first.history_cutoff);
  expect(second.jobs.every((j: any) => !first.jobs.some((p: any) => p.id === j.id))).toBe(true);
  const third = await navigate('Older history');
  expect(third.jobs).toHaveLength(23);
  await expect(panel.getByRole('button', { name: 'Older history', exact: true })).toBeDisabled();
  const back = await navigate('Newer history');
  expect(back.jobs).toEqual(second.jobs);
  let response = page.waitForResponse((r) => r.url().includes('/history/'));
  await panel.getByLabel('Job state', { exact: true }).selectOption('failed');
  const filtered = await (await response).json();
  expect(filtered.jobs).toHaveLength(41);
  expect(filtered.jobs.every((j: any) => j.state === 'failed')).toBe(true);
  await expect(panel.getByRole('button', { name: 'Older history', exact: true })).toBeDisabled();
  response = page.waitForResponse((r) => r.url().includes('/history/'));
  await panel.getByLabel('Job type', { exact: true }).selectOption('native_csv_scoring_v1');
  expect((await (await response).json()).jobs).toHaveLength(0);
  await expect(panel.getByText('No jobs match this history view.', { exact: true })).toBeVisible();
  response = page.waitForResponse((r) => r.url().includes('/history/'));
  await panel.getByLabel('Job type', { exact: true }).selectOption('');
  await response;
  const refreshed = await navigate('Refresh queue and history');
  expect(refreshed.jobs).toHaveLength(41);
  await panel
    .getByRole('button', { name: 'Inspect history job ' + refreshed.jobs[0].id, exact: true })
    .focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('app-package-jobs')).toContainText('Job state: failed');
  expect(mutations).toEqual([]);
  await testInfo.attach('read-only-history-observation', {
    body: JSON.stringify({
      pages: [50, 50, 23],
      states: first.queue.states,
      snapshot: first.queue.live_service_health,
      job_mutations: mutations,
    }),
    contentType: 'application/json',
  });
  await testInfo.attach('bounded-queue-history', {
    body: await panel.screenshot(),
    contentType: 'image/png',
  });
  await page.getByRole('button', { name: 'Close queue and history', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(panel).toHaveCount(0);
  await expect(
    page.getByRole('list', { name: 'Dataset jobs', exact: true }).getByRole('listitem'),
  ).toHaveCount(50);
});
