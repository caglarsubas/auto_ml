import { test, expect } from '@playwright/test';
import { login } from './pages/login.page';

test.describe('Pipeline Setup Journey', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);
  });

  test('should display Model Development heading', async ({ page }) => {
    await expect(page.locator('h1', { hasText: 'Model Development' })).toBeVisible();
  });

  test('should display pipeline type dropdown', async ({ page }) => {
    await expect(page.locator('text=Pipeline Declarations')).toBeVisible();
    await expect(page.locator('select')).toBeVisible();
  });

  test('should display pipeline options in dropdown', async ({ page }) => {
    const select = page.locator('.pipeline-type-dropdown select');
    // Verify expected pipeline types are available
    await expect(select.locator('option', { hasText: 'Boosting' })).toHaveCount(1);
    await expect(select.locator('option', { hasText: 'Logit' })).toHaveCount(1);
    await expect(select.locator('option', { hasText: 'Credit Scoring' })).toHaveCount(1);
    await expect(select.locator('option', { hasText: 'Anomaly Detection' })).toHaveCount(1);
  });

  test('Start button should be disabled without pipeline selection', async ({ page }) => {
    const startBtn = page.locator('button.start-button');
    await expect(startBtn).toBeVisible();
    await expect(startBtn).toBeDisabled();
  });

  test('should enable Start button after selecting a pipeline', async ({ page }) => {
    await page.selectOption('.pipeline-type-dropdown select', 'boosting');
    const startBtn = page.locator('button.start-button');
    await expect(startBtn).toBeEnabled();
  });

  test('should show the Event/Target Definition field in Business Understanding', async ({ page }) => {
    await expect(page.locator('.bu-section')).toBeVisible();
    await expect(page.locator('#targetDefinition')).toBeVisible();
  });

  test('should reveal optional fields behind the Details toggle', async ({ page }) => {
    await expect(page.locator('#bu-details-panel')).toHaveCount(0);
    await page.click('.bu-details-toggle');
    await expect(page.locator('#bu-details-panel')).toBeVisible();
  });

  test('should restrict Pipeline Declarations to regression pipelines when RMSE is chosen', async ({ page }) => {
    await page.selectOption('.bu-criteria select', 'rmse');
    const options = page.locator('.pipeline-type-dropdown select option:not([disabled])');
    await expect(options).toHaveCount(1);
    await expect(options.first()).toHaveText('1- Boosting Pipeline');
  });

  test('should start pipeline and show declaration section', async ({ page }) => {
    await page.selectOption('.pipeline-type-dropdown select', 'boosting');

    // Optionally fill target definition
    await page.fill('#targetDefinition', 'Predict loan default within 12 months');

    await page.click('button.start-button');

    // After starting, declaration component should show content
    await expect(page.locator('text=Data Declaration')).toBeVisible({ timeout: 10_000 });
  });


  test('Saved Pipelines button should be visible', async ({ page }) => {
    await expect(page.locator('button', { hasText: 'Saved Pipelines' })).toBeVisible();
  });

  test('clicking Saved Pipelines should open panel', async ({ page }) => {
    await page.click('button:has-text("Saved Pipelines")');
    await expect(page.locator('h3', { hasText: 'Saved Pipeline Runs' })).toBeVisible();
  });

  test('panel toggle buttons should be visible', async ({ page }) => {
    await expect(page.locator('.toggle-label', { hasText: 'Navigation' })).toBeVisible();
    await expect(page.locator('.toggle-label', { hasText: 'Pipeline' })).toBeVisible();
    await expect(page.locator('.toggle-label', { hasText: 'AI Assistant' })).toBeVisible();
  });
});
