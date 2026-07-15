import { test, expect } from '@playwright/test';
import { TEST_CREDENTIALS } from './fixtures/credentials';

test.describe('Authentication Journey', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should redirect to login page by default', async ({ page }) => {
    await expect(page).toHaveURL(/\/login/);
  });

  test('should display login form elements', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Welcome back');
    await expect(page.locator('p.subtitle')).toContainText('declar.ai');
    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('button.login-button')).toBeVisible();
  });

  test('should show error on invalid credentials', async ({ page }) => {
    await page.fill('#username', 'wrong@email.com');
    await page.fill('#password', 'wrongpass');
    await page.click('button.login-button');

    await expect(page.locator('.error-message')).toBeVisible();
    await expect(page.locator('.error-message')).toContainText('Invalid username or password');
    await expect(page).toHaveURL(/\/login/);
  });

  test('should login successfully and navigate to home', async ({ page }) => {
    await page.fill('#username', TEST_CREDENTIALS.username);
    await page.fill('#password', TEST_CREDENTIALS.password);
    await page.click('button.login-button');

    await expect(page).toHaveURL(/\/home/);
    await expect(page.locator('h1')).toContainText('declar.ai');
  });

  test('should display "Remember me" checkbox and "Forgot password" link', async ({ page }) => {
    await expect(page.locator('.remember-me')).toBeVisible();
    await expect(page.locator('.forgot-link')).toBeVisible();
  });

  test('should show footer text on login page', async ({ page }) => {
    await expect(page.locator('.login-footer')).toContainText('Democratizing the power of ML');
  });
});
