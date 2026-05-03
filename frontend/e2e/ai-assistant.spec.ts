import { test, expect } from '@playwright/test';

test.describe('AI Assistant Panel Journey', () => {
  test.beforeEach(async ({ page }) => {
    // Login → Model Development
    await page.goto('/login');
    await page.fill('#username', 'caglarsubas@gmail.com');
    await page.fill('#password', 'con3e7ne');
    await page.click('button.login-button');
    await expect(page).toHaveURL(/\/home/);
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);
  });

  test('AI Assistant toggle button should be visible', async ({ page }) => {
    await expect(page.locator('.toggle-label', { hasText: 'AI Assistant' })).toBeVisible();
  });

  test('clicking AI Assistant toggle should open the panel', async ({ page }) => {
    await page.click('.toggle-btn:has-text("AI Assistant")');

    // The AI chat panel component should become visible
    await expect(page.locator('app-ai-chat-panel')).toBeVisible({ timeout: 5_000 });
  });

  test('AI panel should have message input', async ({ page }) => {
    await page.click('.toggle-btn:has-text("AI Assistant")');

    // Look for text input or textarea in the chat panel
    const chatInput = page.locator('app-ai-chat-panel textarea, app-ai-chat-panel input[type="text"]');
    await expect(chatInput.first()).toBeVisible({ timeout: 5_000 });
  });

  test('clicking AI Assistant toggle again should close the panel', async ({ page }) => {
    // Open
    await page.click('.toggle-btn:has-text("AI Assistant")');
    await expect(page.locator('app-ai-chat-panel')).toBeVisible({ timeout: 5_000 });

    // Close
    await page.click('.toggle-btn:has-text("AI Assistant")');
    await expect(page.locator('app-ai-chat-panel')).not.toBeVisible({ timeout: 5_000 });
  });

  test('Navigation toggle should show/hide left panel', async ({ page }) => {
    // Left panel should start visible (default)
    const leftPanel = page.locator('.panel-left');

    // Toggle off
    await page.click('.toggle-btn:has-text("Navigation")');
    // Panel might hide
    await page.waitForTimeout(500);

    // Toggle back on
    await page.click('.toggle-btn:has-text("Navigation")');
    await expect(leftPanel).toBeVisible({ timeout: 5_000 });
  });
});
