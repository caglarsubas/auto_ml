import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Declaration (Data Upload) Journey', () => {
  test.beforeEach(async ({ page }) => {
    // Login → Home → Model Development → Start pipeline
    await page.goto('/login');
    await page.fill('#username', 'caglarsubas@gmail.com');
    await page.fill('#password', 'con3e7ne');
    await page.click('button.login-button');
    await expect(page).toHaveURL(/\/home/);
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);

    // Select pipeline and start
    await page.selectOption('.pipeline-type-dropdown select', 'boosting');
    await page.click('button.start-button');
    await expect(page.locator('text=Data Declaration')).toBeVisible({ timeout: 10_000 });
  });

  test('should show file input and import button', async ({ page }) => {
    await expect(page.locator('input[type="file"]')).toBeVisible();
    await expect(page.locator('button.import-data-btn')).toBeVisible();
  });

  test('should show column separator dropdown when CSV is selected', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);

    await expect(page.locator('#columnSeparator')).toBeVisible();
    // Default should be semicolon
    await expect(page.locator('#columnSeparator')).toHaveValue('semicolon');
  });

  test('should show "First line is not header" checkbox', async ({ page }) => {
    await expect(page.locator('#firstLineHeader')).toBeVisible();
    await expect(page.locator('label[for="firstLineHeader"]')).toContainText('First line is not header');
  });

  test('should upload CSV and show data preview', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);

    // Click IMPORT DATA
    await page.click('button.import-data-btn');

    // Wait for preview to appear
    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('text=Total Rows')).toBeVisible();
    await expect(page.locator('text=Total Columns')).toBeVisible();
  });

  test('should show preview table with correct columns', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);
    await page.click('button.import-data-btn');

    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });

    // Scroll the table into view and check column headers
    const table = page.locator('.preview-table');
    await table.scrollIntoViewIfNeeded();
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('columnheader', { name: 'Age', exact: true })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Income', exact: true })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Good_Bad_Flag', exact: true })).toBeVisible();
  });

  test('should show locked state and Edit button after upload', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);
    await page.click('button.import-data-btn');

    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });

    // Should show "Data imported" locked bar
    await expect(page.locator('.section-locked-label')).toContainText('Data imported');
    await expect(page.locator('.section-edit-btn')).toBeVisible();
  });

  test('should show data dictionary after generation', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);
    await page.click('button.import-data-btn');
    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });

    // Click "Generate without Uploading" to generate dictionary
    const genDictBtn = page.locator('button', { hasText: 'Generate without Uploading' });
    await genDictBtn.scrollIntoViewIfNeeded();
    await expect(genDictBtn).toBeVisible({ timeout: 15_000 });
    await genDictBtn.click();

    // Wait for data dictionary table to appear
    await expect(page.locator('.data-dictionary-table')).toBeVisible({ timeout: 30_000 });
  });

  test('Edit button should re-enable import controls', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);
    await page.click('button.import-data-btn');

    await expect(page.locator('.section-edit-btn')).toBeVisible({ timeout: 30_000 });

    // Click Edit
    await page.click('.section-edit-btn');

    // Import controls should reappear (file input may be CSS-hidden behind styled button)
    await expect(page.locator('.data-import-controls')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('button.import-data-btn')).toBeVisible();
  });

  test('should show "Add note" button after data preview', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);
    await page.click('button.import-data-btn');

    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });

    // "Add note" buttons should appear
    await expect(page.locator('.pipeline-note-add').first()).toBeVisible();
  });
});
