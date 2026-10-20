import { test, expect } from '@playwright/test';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';
import { readFile } from 'node:fs/promises';

for (const task of ['classification', 'regression']) {
  test(`native ${task} candidate export and queued feature-only scoring preserve evidence`, async ({
    page,
  }, testInfo) => {
    const credentials = requireTestCredentials();
    await page.goto('/login');
    await page.getByLabel('Username', { exact: true }).fill(credentials.username + '-training');
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(page).toHaveURL(/\/home$/);
    const project = await page.getByLabel('Current project').inputValue();
    const datasets = await (await page.request.get(API_BASE_URL + 'declaration/')).json();
    const name = task === 'regression' ? 'Training regression.csv' : 'Training binary.csv';
    const dataset = datasets.find((d: any) => d.original_name === name);
    const input = datasets.find((d: any) => d.original_name === 'Candidate features.csv');
    const csrf = (await (await page.request.get(API_BASE_URL + 'auth/session/')).json()).csrf_token;
    const headers = { 'X-CSRFToken': csrf };
    const base = API_BASE_URL + `jobs/datasets/${dataset.id}/`;
    const options = {
      data_role: 'development_only',
      business_understanding: {
        problem_type: task,
        objective: 'Synthetic native candidate workflow',
        population: 'Synthetic development inputs',
        prediction_horizon: '12 months',
        feature_availability: { default: 'available_at_prediction' },
        target_contract: {
          target_column: 'outcome',
          positive_class: task === 'classification' ? 'bad' : null,
          event_definition: 'Synthetic recorded outcome',
          label_maturity: 'Complete follow-up',
        },
        success_criteria: { primary_metric: task === 'classification' ? 'roc_auc' : 'rmse' },
      },
      features: ['x', 'z'],
      validation: { strategy: 'random', n_splits: 2 },
    };
    const preview = await page.request.post(base + `training-input/?project_id=${project}`, {
      data: options,
      headers,
    });
    expect(preview.status()).toBe(200);
    const p = await preview.json();
    const submitted = await page.request.post(base + `?project_id=${project}`, {
      headers,
      data: {
        ...options,
        kind: p.kind,
        input_sha256: p.input_sha256,
        training_sha256: p.training_sha256,
        request_id: crypto.randomUUID(),
      },
    });
    expect(submitted.status()).toBe(202);
    const trained = await submitted.json();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(API_BASE_URL + `jobs/${trained.id}/`)).json()).state,
        { timeout: 30000 },
      )
      .toBe('succeeded');
    await page.getByRole('button', { name: 'Training jobs for ' + name, exact: true }).click();
    await page.getByRole('button', { name: 'Open job ' + trained.id, exact: true }).click();
    const candidate = page.locator('app-native-candidate');
    const downloaded = page.waitForEvent('download');
    await candidate.getByRole('button', { name: 'Download native candidate', exact: true }).click();
    const download = await downloaded;
    const exported = JSON.parse(await readFile((await download.path())!, 'utf8'));
    expect(exported.result.prediction_contract.task).toBe(task);
    expect(exported.result.model_adopted).toBe(false);
    expect(exported.result.review_approved).toBe(false);
    expect(exported.result.production_use_approved).toBe(false);
    await expect(candidate).toContainText('Retain this export SHA-256 separately');
    await candidate
      .getByLabel('Candidate scoring dataset ID', { exact: true })
      .fill(String(input.id));
    await candidate.getByRole('button', { name: 'Prepare candidate scoring', exact: true }).click();
    await expect(
      candidate.getByRole('button', { name: 'Queue reviewed candidate scoring', exact: true }),
    ).toBeDisabled();
    await candidate.getByLabel('I approve this exact candidate', { exact: false }).check();
    // Editing invalidates review and requires another server preview.
    await candidate
      .getByLabel('Candidate scoring dataset ID', { exact: true })
      .fill(String(dataset.id));
    await expect(
      candidate.getByRole('button', { name: 'Queue reviewed candidate scoring', exact: true }),
    ).toHaveCount(0);
    await candidate
      .getByLabel('Candidate scoring dataset ID', { exact: true })
      .fill(String(input.id));
    await candidate.getByRole('button', { name: 'Prepare candidate scoring', exact: true }).click();
    await candidate.getByLabel('I approve this exact candidate', { exact: false }).check();
    const queued = page.waitForResponse(
      (r) => r.url().includes(`/jobs/datasets/${dataset.id}/?`) && r.request().method() === 'POST',
    );
    await expect(
      candidate.getByRole('button', { name: 'Queue reviewed candidate scoring', exact: true }),
    ).toBeEnabled();
    await candidate
      .getByRole('button', { name: 'Queue reviewed candidate scoring', exact: true })
      .focus();
    await expect(
      candidate.getByRole('button', { name: 'Queue reviewed candidate scoring', exact: true }),
    ).toBeFocused();
    await page.keyboard.press('Enter');
    const response = await queued;
    expect(response.status()).toBe(202);
    const job = await response.json();
    await expect
      .poll(
        async () => (await (await page.request.get(API_BASE_URL + `jobs/${job.id}/`)).json()).state,
        { timeout: 30000 },
      )
      .toBe('succeeded');
    await page.getByRole('button', { name: 'Refresh jobs', exact: true }).click();
    await expect(page.locator('app-package-jobs')).toContainText('Scored 3 rows');
    await expect(
      page.getByRole('button', { name: 'Use receipt for review action', exact: true }),
    ).toHaveCount(0);
    const scoresDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download full scoring receipt', exact: true }).click();
    const scores = JSON.parse(await readFile((await (await scoresDownload).path())!, 'utf8'));
    expect(scores.scores).toHaveLength(3);
    expect(scores.training_result_sha256).toBe(exported.result_sha256);
    expect(scores.features).toEqual(['x', 'z']);
    expect(scores.final_holdout_accessed).toBe(false);
    expect(scores.review_approved).toBe(false);
    await testInfo.attach('native-candidate-scoring-evidence', {
      body: JSON.stringify({ export: exported, scoring: scores }),
      contentType: 'application/json',
    });
    await page.screenshot({
      path: testInfo.outputPath('native-candidate-scored.png'),
      animations: 'disabled',
    });
  });
}
