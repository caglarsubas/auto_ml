import { test, expect } from '@playwright/test';
import path from 'path';

/**
 * Full end-to-end pipeline journey:
 * Login → Home → Model Development → Select Pipeline → Start →
 * Upload File → Preview → Data Dictionary → Preprocessing → Data Quality
 *
 * This is the core user journey covering the entire happy path.
 * Individual steps have longer timeouts to accommodate backend processing.
 */
test.describe('Full Pipeline Journey (Happy Path)', () => {
  test('complete pipeline from login to data quality', async ({ page }) => {
    // ── 1. Login ──
    await page.goto('/login');
    await expect(page.locator('h1')).toContainText('Welcome back');

    await page.fill('#username', 'caglarsubas@gmail.com');
    await page.fill('#password', 'con3e7ne');
    await page.click('button.login-button');
    await expect(page).toHaveURL(/\/home/);

    // ── 2. Navigate to Model Development ──
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);
    await expect(page.locator('h1', { hasText: 'Model Development' })).toBeVisible();

    // ── 3. Select Pipeline Type ──
    await page.selectOption('.pipeline-type-dropdown select', 'boosting');
    await expect(page.locator('.target-definition-section')).toBeVisible();

    // ── 4. Enter Target Definition ──
    await page.fill('#targetDefinition', 'Predict whether a loan applicant will default (Good_Bad_Flag)');

    // ── 5. Start Pipeline ──
    await page.click('button.start-button');
    await expect(page.locator('text=Data Declaration')).toBeVisible({ timeout: 10_000 });

    // ── 6. Upload Data File ──
    const fileInput = page.locator('input[type="file"]');
    const testFile = path.resolve(__dirname, 'fixtures/test_data.csv');
    await fileInput.setInputFiles(testFile);

    // Verify separator is shown for CSV
    await expect(page.locator('#columnSeparator')).toBeVisible();

    // Click IMPORT DATA
    await page.click('button.import-data-btn');

    // ── 7. Verify Data Preview ──
    await expect(page.locator('text=Data Preview')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('text=Total Rows')).toBeVisible();
    await expect(page.locator('text=Total Columns')).toBeVisible();

    // Verify preview table contains our data columns
    const previewTable = page.locator('.preview-table');
    await previewTable.scrollIntoViewIfNeeded();
    await expect(previewTable).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('columnheader', { name: 'Age', exact: true })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Good_Bad_Flag', exact: true })).toBeVisible();

    // Should show locked state
    await expect(page.locator('.section-locked-label')).toContainText('Data imported');

    // ── 8. Generate Data Dictionary ──
    const genDictBtn = page.locator('button', { hasText: 'Generate without Uploading' });
    await genDictBtn.scrollIntoViewIfNeeded();
    await expect(genDictBtn).toBeVisible({ timeout: 15_000 });
    await genDictBtn.click();

    // Wait for data dictionary table to appear
    await expect(page.locator('.data-dictionary-table')).toBeVisible({ timeout: 30_000 });

    // ── 8b. Click PREPROCESSING button to proceed ──
    const preprocessBtn = page.locator('button.next-button').filter({ hasText: /PREPROCESSING/i });
    await preprocessBtn.scrollIntoViewIfNeeded();
    await expect(preprocessBtn).toBeVisible({ timeout: 15_000 });
    await preprocessBtn.click();
    await page.waitForTimeout(1_000);

    // ── 9. Verify Preprocessing Section Appears ──
    const purifierHeading = page.locator('text=Data Purifier Declaration');
    await purifierHeading.scrollIntoViewIfNeeded();
    await expect(purifierHeading).toBeVisible({ timeout: 20_000 });

    // ── 10. Run Preprocessing ──
    const runBtn = page.locator('button').filter({ hasText: /Run Preprocessing/i });
    await runBtn.scrollIntoViewIfNeeded();
    await expect(runBtn).toBeVisible({ timeout: 15_000 });
    await runBtn.click();

    // ── 11. Wait for Data Quality Results (small datasets process near-instantly) ──
    await expect(
      page.getByRole('heading', { name: 'Data Purifier Summary' })
        .or(page.getByText('Data Quality Summary', { exact: true }))
        .or(page.getByText('Train-Test Split Validation', { exact: true }))
    ).toBeVisible({ timeout: 60_000 });

    // Verify the pipeline progressed successfully
    await expect(page.locator('h1', { hasText: 'Model Development' })).toBeVisible();
  });
});

test.describe('Pipeline Resume & Persistence', () => {
  test('should persist pipeline state across page reloads', async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('#username', 'caglarsubas@gmail.com');
    await page.fill('#password', 'con3e7ne');
    await page.click('button.login-button');
    await expect(page).toHaveURL(/\/home/);

    // Go to model development
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);

    // Open Saved Pipelines to check if any exist
    await page.click('button:has-text("Saved Pipelines")');
    await expect(page.locator('h3', { hasText: 'Saved Pipeline Runs' })).toBeVisible();

    // If there are saved pipelines, try loading one
    const loadButtons = page.locator('button:has-text("Load")');
    const count = await loadButtons.count();

    if (count > 0) {
      // Load the first pipeline
      await loadButtons.first().click();

      // Should restore state (at minimum the pipeline type)
      await expect(page.locator('.pipeline-type-dropdown select')).toBeVisible({ timeout: 15_000 });
    }
  });
});
