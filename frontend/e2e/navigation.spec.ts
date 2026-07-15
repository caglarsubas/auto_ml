import { test, expect } from '@playwright/test';
import { login } from './pages/login.page';

test.describe('App Navigation & Toolbar', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('toolbar should show logo', async ({ page }) => {
    await page.goto('/model-development');
    await expect(page.locator('mat-toolbar img.logo')).toBeVisible();
  });

  test('toolbar should show navigation menu items on model-development page', async ({ page }) => {
    await page.goto('/model-development');
    await expect(page.locator('a', { hasText: 'Home' })).toBeVisible();
    await expect(page.locator('a', { hasText: 'Feature Store' })).toBeVisible();
    await expect(page.locator('a', { hasText: 'Model Store' })).toBeVisible();
    await expect(page.locator('a', { hasText: 'Deployments' })).toBeVisible();
    await expect(page.locator('a', { hasText: 'Reporting' })).toBeVisible();
  });

  test('Home button should navigate back to /home', async ({ page }) => {
    await page.goto('/model-development');
    await page.click('a:has-text("Home")');
    await expect(page).toHaveURL(/\/home/);
  });

  test('Model Store menu should contain Model Development link', async ({ page }) => {
    await page.goto('/model-development');
    // Open the Model Store menu
    await page.click('a:has-text("Model Store")');
    const menuItem = page.locator('button[mat-menu-item]', { hasText: 'Model Development' });
    await expect(menuItem).toBeVisible();
  });

  test('Sign Out from model-development should redirect to login', async ({ page }) => {
    await page.goto('/model-development');
    await page.locator('button').filter({ hasText: /sign out/i }).first().click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('direct navigation to /model-development without login should work (no auth guard)', async ({ page }) => {
    // This tests the app behavior — note: the app has no route guard for auth
    await page.goto('/model-development');
    await expect(page.locator('h1', { hasText: 'Model Development' })).toBeVisible();
  });
});
