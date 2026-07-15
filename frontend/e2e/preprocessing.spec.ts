import { test, expect } from '@playwright/test';
import path from 'path';
import { login } from './pages/login.page';

test.describe('Preprocessing & Data Quality Journey', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);

    // Start pipeline
    await page.selectOption('.pipeline-type-dropdown select', 'boosting');
    await page.click('button.start-button');
    await expect(page.locator('text=Data Declaration')).toBeVisible({ timeout: 10_000 });

    // Upload file
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);
    await page.click('button.import-data-btn');
    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });

    // Scroll to and click "Generate without Uploading" to generate dictionary
    const genDictBtn = page.locator('button', { hasText: 'Generate without Uploading' });
    await genDictBtn.scrollIntoViewIfNeeded();
    await expect(genDictBtn).toBeVisible({ timeout: 15_000 });
    await genDictBtn.click();

    // Wait for data dictionary table to appear
    await expect(page.locator('.data-dictionary-table')).toBeVisible({ timeout: 30_000 });

    // Click the PREPROCESSING button to proceed to the preprocessing step
    const preprocessBtn = page.locator('button.next-button').filter({ hasText: /PREPROCESSING/i });
    await preprocessBtn.scrollIntoViewIfNeeded();
    await expect(preprocessBtn).toBeVisible({ timeout: 15_000 });
    await preprocessBtn.click();

    // Wait for the Data Purifier section to render (condition, not a fixed sleep)
    await expect(page.locator('text=Data Purifier Declaration')).toBeVisible({ timeout: 20_000 });
  });

  test('should show Data Purifier Declaration after file upload', async ({ page }) => {
    const purifier = page.locator('text=Data Purifier Declaration');
    await purifier.scrollIntoViewIfNeeded();
    await expect(purifier).toBeVisible({ timeout: 20_000 });
  });

  test('should show purifier options dropdown', async ({ page }) => {
    const purifier = page.locator('text=Data Purifier Declaration');
    await purifier.scrollIntoViewIfNeeded();
    await expect(page.locator('mat-select').first()).toBeVisible({ timeout: 20_000 });
  });

  test('should show split strategy selector', async ({ page }) => {
    const purifier = page.locator('text=Data Purifier Declaration');
    await purifier.scrollIntoViewIfNeeded();
    await expect(page.locator('text=Split Strategy')).toBeVisible({ timeout: 20_000 });
  });

  test('Run Preprocessing button should be visible', async ({ page }) => {
    const runBtn = page.locator('button').filter({ hasText: /Run Preprocessing/i });
    await runBtn.scrollIntoViewIfNeeded();
    await expect(runBtn).toBeVisible({ timeout: 20_000 });
  });

  test('should run preprocessing and show results', async ({ page }) => {
    const runBtn = page.locator('button').filter({ hasText: /Run Preprocessing/i });
    await runBtn.scrollIntoViewIfNeeded();
    await expect(runBtn).toBeVisible({ timeout: 20_000 });
    await runBtn.click();

    // Wait for data quality results (small datasets process near-instantly)
    await expect(
      page.getByRole('heading', { name: 'Data Purifier Summary' })
        .or(page.getByText('Data Quality Summary', { exact: true }))
        .or(page.getByText('Train-Test Split Validation', { exact: true }))
    ).toBeVisible({ timeout: 60_000 });
  });

  test('should be able to add a pipeline note', async ({ page }) => {
    const addNoteBtn = page.locator('.pipeline-note-add').first();
    await addNoteBtn.scrollIntoViewIfNeeded();
    await expect(addNoteBtn).toBeVisible({ timeout: 20_000 });
    await addNoteBtn.click();

    await expect(page.locator('.pipeline-note-textarea').first()).toBeVisible();
  });
});
