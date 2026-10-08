import { test, expect } from '@playwright/test';

test('server session, declared task and local fonts survive a browser reload', async ({ page, baseURL }, testInfo) => {
  const username = process.env['E2E_USER'];
  const password = process.env['E2E_PASSWORD'];
  test.skip(!username || !password, 'Requires an existing Django test account in the chosen installation.');
  const apiURL = process.env['E2E_API_BASE_URL'] || 'http://localhost:8002/api/';
  const allowed = new Set([new URL(baseURL!).origin, new URL(apiURL).origin]);
  const external: string[] = [];
  const runtimeErrors: string[] = [];
  page.on('pageerror', error => runtimeErrors.push(error.message));
  await page.route('**/*', route => {
    const url = route.request().url();
    if (!url.startsWith('http') || allowed.has(new URL(url).origin)) return route.continue();
    external.push(new URL(url).origin);
    return route.abort();
  });
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(username!);
  await page.getByLabel('Password', { exact: true }).fill(password!);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  await page.reload();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('button', { name: /sign out/i })).toBeVisible();
  await page.goto('/model-development');
  await expect(page.getByRole('heading', { name: 'Model Development', exact: true })).toBeVisible();
  const field = (label: string) => page.locator('label.bu-field').filter({ hasText: label });
  const task = field('Declared task').locator('select');
  await task.focus();
  await task.press('c');
  await task.press('Tab');
  await expect(task).toHaveValue('classification');
  await field('Positive class for binary outcomes').locator('input').fill('bad');
  await field('Label maturity rule').locator('input').fill('Observed after 12 months');
  await field('Feature availability at prediction time').locator('select').selectOption('available_at_prediction');
  const fontsLoaded = await page.evaluate(async () => {
    const checks = ['400 16px "Instrument Sans"', '400 16px "Instrument Serif"',
      '400 16px "IBM Plex Mono"', '400 24px "Material Icons"'];
    await Promise.all(checks.map(font => document.fonts.load(font)));
    return checks.every(font => document.fonts.check(font));
  });
  expect(fontsLoaded).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('business-declaration.png') });
  await page.getByRole('button', { name: /sign out/i }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/home');
  await expect(page).toHaveURL(/\/login$/);
  expect(runtimeErrors).toEqual([]);
  expect(external).toEqual([]);
});
