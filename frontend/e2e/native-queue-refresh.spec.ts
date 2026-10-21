import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { requireTestCredentials } from './fixtures/credentials';

test('refresh withdraws stale job evidence before delayed responses and restores keyboard export', async ({
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
    .click();
  const panel = page.locator('app-package-jobs');
  const first = panel.getByRole('button', { name: /^Open job / }).first();
  const label = await first.innerText();
  const identifier = label.replace('Open job ', '');
  await first.click();
  const download = panel.getByRole('button', { name: 'Download job receipt', exact: true });
  await expect(download).toBeEnabled();
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  let hold = true;
  await page.route('**/api/jobs/datasets/*/?*', async (route) => {
    if (hold && route.request().method() === 'GET') {
      hold = false;
      await gate;
    }
    await route.continue();
  });
  const mutations: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/jobs/') && request.method() !== 'GET')
      mutations.push(request.method());
  });
  const pending = page.waitForRequest(
    (request) => request.url().includes('/jobs/datasets/') && request.method() === 'GET',
  );
  try {
    await panel.getByRole('button', { name: 'Refresh jobs', exact: true }).click();
    await pending;
    await expect(download).toHaveCount(0);
    await expect(panel.getByRole('status')).toContainText('Checking job receipt');
  } finally {
    release();
  }
  await expect(download).toBeEnabled();
  const exported = page.waitForEvent('download');
  await download.focus();
  await page.keyboard.press('Enter');
  const file = await exported;
  expect(file.suggestedFilename()).toBe(`job-${identifier}.json`);
  const receipt = JSON.parse(await readFile((await file.path())!, 'utf8'));
  expect(receipt.id).toBe(identifier);
  expect(receipt.result).toBeNull();
  expect(mutations).toEqual([]);
  await testInfo.attach('delayed-refresh-evidence', {
    body: JSON.stringify({
      stale_receipt_withdrawn: true,
      refreshed_export_id: receipt.id,
      mutations,
    }),
    contentType: 'application/json',
  });
});
