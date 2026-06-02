/**
 * Hyperparameter Tuning UI (E2E)
 *
 * Drives the Hyperparameter Tuning panel that appears in the Modeling step
 * after SFS.  Because `currentFileId` and the modeling checkpoint are held
 * in-memory (not persisted), the panel can only be reached by loading a saved
 * pipeline that already advanced through SFS.  This spec therefore:
 *
 *   1. logs in and opens Saved Pipelines,
 *   2. loads the first saved pipeline (if any) and looks for the tuning panel,
 *   3. when the panel is present, asserts its config controls and exercises a
 *      Start → progress → results cycle with the backend endpoints MOCKED so
 *      the assertion is deterministic and fast,
 *   4. skips cleanly when no suitable pipeline exists — matching the
 *      conditional pattern used by full-pipeline / pipeline-management specs,
 *      so the suite never false-fails in a fresh environment.
 */
import { test, expect, Page } from '@playwright/test';

const PANEL = 'Hyperparameter Tuning';

/** Canned tuning results used by the mocked results endpoint. */
const MOCK_RESULTS = {
  status: 'completed',
  hyperparam_completed: true,
  feature_count: 12,
  duration_seconds: 7.4,
  primary_metric: 'roc_auc',
  best_points: {
    roc_auc: { params: { max_depth: 4, learning_rate: 0.08 }, cv_mean: 0.91, cv_std: 0.012, test: 0.89, train: 0.97 },
    pr_auc: { params: { max_depth: 5 }, cv_mean: 0.74, cv_std: 0.03, test: 0.71, train: 0.85 },
  },
  validation_curves: [
    { param: 'max_depth', metric: 'roc_auc', values: [2, 4, 6, 8],
      cv_mean: [0.85, 0.91, 0.90, 0.88], cv_std: [0.01, 0.01, 0.02, 0.02],
      train_mean: [0.88, 0.95, 0.98, 0.99], train_std: [0.01, 0.01, 0.01, 0.01] },
    { param: 'learning_rate', metric: 'roc_auc', values: [0.01, 0.05, 0.1, 0.2],
      cv_mean: [0.86, 0.90, 0.91, 0.89], cv_std: [0.02, 0.01, 0.01, 0.02],
      train_mean: [0.89, 0.94, 0.97, 0.99], train_std: [0.01, 0.01, 0.01, 0.01] },
  ],
  emphasized: { most_cv_gain: 'max_depth', most_overfitting: 'learning_rate', most_shrinkage: 'max_depth' },
  param_importance: { cv_gain: { max_depth: 0.7, learning_rate: 0.3 } },
  guidance: [
    { param: 'max_depth', type: 'zoom_in', suggested_range: [3, 6], rationale: 'CV roc_auc peaks at depth 4 (interior).' },
  ],
};

async function mockHyperparamEndpoints(page: Page): Promise<void> {
  await page.route('**/api/modeling/hyperparam/start/', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'started', message: 'started', space_warnings: [] }) });
  });
  await page.route('**/api/modeling/hyperparam/status/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'completed', progress: 1.0, completed_trials: 40, duration_seconds: 7.4 }) });
  });
  // Results endpoint: GET /api/modeling/hyperparam/<id>/  (no trailing keyword)
  await page.route('**/api/modeling/hyperparam/*', async (route) => {
    const url = route.request().url();
    // Only the results GET matches the bare /<id>/ shape; let start/status/stop
    // fall through to their dedicated handlers above.
    if (/\/hyperparam\/(start|status|stop)\b/.test(url)) {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_RESULTS) });
  });
}

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.fill('#username', 'caglarsubas@gmail.com');
  await page.fill('#password', 'con3e7ne');
  await page.click('button.login-button');
  await expect(page).toHaveURL(/\/home/, { timeout: 15_000 });
}

test.describe('Hyperparameter Tuning panel (post-SFS)', () => {
  test('config controls render and a Start→results cycle works (mocked)', async ({ page }) => {
    await mockHyperparamEndpoints(page);

    try {
      await login(page);
    } catch (err) {
      test.skip(true, `login/backend unavailable: ${(err as Error).message}`);
      return;
    }

    // Go to Model Development and open Saved Pipelines.
    await page.click('a[routerLink="/model-development"]');
    await expect(page).toHaveURL(/\/model-development/);

    const savedBtn = page.locator('button:has-text("Saved Pipelines")');
    if (await savedBtn.count() === 0) {
      test.skip(true, 'No Saved Pipelines control — cannot reach the tuning panel deterministically');
      return;
    }
    await savedBtn.click();

    const loadButtons = page.locator('button:has-text("Load")');
    if (await loadButtons.count() === 0) {
      test.skip(true, 'No saved pipeline available to load — skipping UI tuning journey');
      return;
    }
    await loadButtons.first().click();
    await page.waitForTimeout(2_000);

    // The tuning panel only appears for pipelines that advanced through SFS.
    const panelHeading = page.getByRole('heading', { name: PANEL }).first();
    let panelVisible = false;
    try {
      await panelHeading.scrollIntoViewIfNeeded({ timeout: 8_000 });
      panelVisible = await panelHeading.isVisible();
    } catch {
      panelVisible = false;
    }
    if (!panelVisible) {
      test.skip(true, 'Loaded pipeline has not reached SFS — tuning panel not present');
      return;
    }

    // ── Config controls present ──
    const startBtn = page.locator('button', { hasText: /Start Hyperparameter Tuning|Run Next Search/i }).first();
    await expect(startBtn).toBeVisible();
    // Param-space rows + the compute-power (n_jobs) and curve-metric controls.
    await expect(page.locator('text=Compute power (n_jobs)')).toBeVisible();
    await expect(page.locator('text=n_estimators')).toBeVisible();

    // ── Start → mocked completion → results render ──
    await startBtn.click();
    // Best-metric-points table + CV curve headings appear once results load.
    await expect(page.getByRole('heading', { name: 'Best Metric Space Points' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('heading', { name: /Cross-Validation Curves/i })).toBeVisible();
    // Emphasis cards reflect the mocked attribution.
    await expect(page.locator('text=Most Impactful Hyperparameters')).toBeVisible();
  });
});
