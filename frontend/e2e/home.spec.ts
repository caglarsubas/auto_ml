import { test, expect } from '@playwright/test';
import { login } from './pages/login.page';

test.describe('Home Page Journey', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('should display welcome heading and tagline', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('declar.ai');
    await expect(page.locator('.tagline')).toContainText('Democratizing the power of ML');
  });

  test('should display 5 menu items', async ({ page }) => {
    const menuItems = page.locator('.menu-item');
    await expect(menuItems).toHaveCount(5);
  });

  test('should display correct menu item names', async ({ page }) => {
    const menuNames = ['Feature Store', 'Model Store', 'Deployments', 'Reporting', 'About'];
    for (const name of menuNames) {
      await expect(page.locator('.menu-item h4', { hasText: name })).toBeVisible();
    }
  });

  test('should have Model Development as a clickable link', async ({ page }) => {
    const link = page.locator('a[routerLink="/model-development"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText('Model Development');
  });

  test('should navigate to model-development when clicking Model Development', async ({ page }) => {
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);
  });

  test('should show Sign Out button on home page', async ({ page }) => {
    // Material buttons render text uppercase; match case-insensitively
    await expect(page.locator('button').filter({ hasText: /sign out/i }).first()).toBeVisible();
  });

  test('Sign Out should redirect to login', async ({ page }) => {
    await page.locator('button').filter({ hasText: /sign out/i }).first().click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('should display menu icons', async ({ page }) => {
    const icons = page.locator('.menu-icon');
    await expect(icons.first()).toBeVisible();
  });

  test('should show sub-items under each menu category', async ({ page }) => {
    // Model Store should list Model Development, Model Re-Fitting, Model Monitoring
    const modelStore = page.locator('.menu-item', { hasText: 'Model Store' });
    await expect(modelStore.locator('li')).toHaveCount(3);
  });
});
