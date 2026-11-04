import { test, expect, Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';

test('reviewed legacy training survives browser navigation and requires development selection', async ({
  page,
  context,
}) => {
  const credentials = requireTestCredentials();
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username + '-training');
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  const project = await page.getByLabel('Current project').inputValue();
  const csrf = (await (await page.request.get(API_BASE_URL + 'auth/session/')).json()).csrf_token;
  const headers = { 'X-CSRFToken': csrf };
  const raw =
    'x,z,outcome\n' +
    Array.from({ length: 120 }, (_, i) => `${i / 120},${i % 7},${i % 2 ? 'bad' : 'good'}`).join(
      '\n',
    ) +
    '\n';
  const uploaded = await page.request.post(API_BASE_URL + `declaration/?project_id=${project}`, {
    headers,
    multipart: {
      file: { name: 'Durable browser.csv', mimeType: 'text/csv', buffer: Buffer.from(raw) },
      column_separator: 'comma',
    },
  });
  expect(uploaded.status()).toBe(201);
  const dataset = await uploaded.json();
  const processed = new URL(dataset.file).pathname.split('/media/')[1];
  const name = 'Durable browser ' + randomUUID();
  const business = {
    problem_type: 'classification',
    objective: 'Synthetic durable browser fixture',
    population: 'Synthetic rows',
    prediction_horizon: '12 months',
    feature_availability: { default: 'available_at_prediction' },
    target_contract: {
      target_column: 'outcome',
      positive_class: 'bad',
      event_definition: 'Synthetic recorded outcome',
      label_maturity: 'Complete follow-up',
    },
    success_criteria: { primary_metric: 'roc_auc' },
  };
  const saved = await page.request.post(API_BASE_URL + 'pipeline/create/', {
    headers,
    data: {
      name,
      project_id: project,
      file_id: dataset.id,
      pipeline_type: 'boosting',
      current_step: 'modeling',
      state: {
        file_id: dataset.id,
        pipeline_type: 'boosting',
        business_understanding: business,
        flags: { is_started: true, preprocessing_available: true, modeling_available: true },
        preprocessing: { processed_file_path: processed },
        modeling: { substep: 'algorithm_selected', selectedAlgorithm: 'xgboost' },
      },
    },
  });
  expect(saved.status()).toBe(201);
  async function load(browserPage: Page) {
    await browserPage.goto('/model-development');
    await browserPage.getByRole('button', { name: 'Saved Pipelines', exact: true }).click();
    const row = browserPage.getByTitle(name, { exact: true }).locator('..').locator('..');
    await row.getByRole('button', { name: 'Load', exact: true }).click();
    await expect(
      browserPage.getByRole('button', { name: 'Start Modeling', exact: true }),
    ).toBeEnabled();
  }
  await load(page);
  await page.getByRole('button', { name: 'Start Modeling', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Review model development execution' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('120 seconds');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  expect(
    (await (await page.request.get(API_BASE_URL + `jobs/datasets/${dataset.id}/`)).json()).total,
  ).toBe(0);
  await page.getByRole('button', { name: 'Start Modeling', exact: true }).click();
  await expect(dialog).toBeVisible();
  const launched = page.waitForResponse(
    (response) => response.url().endsWith('/modeling/start/') && response.status() === 202,
  );
  await dialog.getByRole('button', { name: 'Submit reviewed execution', exact: true }).click();
  const receipt = await (await launched).json();
  expect(receipt.native_job_id).toBeTruthy();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(API_BASE_URL + `jobs/${receipt.native_job_id}/`)).json())
          .state,
      { timeout: 30000 },
    )
    .toBe('succeeded');
  const snapshot = await (
    await page.request.get(API_BASE_URL + `jobs/${receipt.native_job_id}/`)
  ).json();
  expect(snapshot.result.model_adopted).toBe(false);
  // A fresh page must recover the receipt independently of the old component.
  await page.close();
  const reopened = await context.newPage();
  await load(reopened);
  await expect(
    reopened.getByRole('button', { name: 'Review development selection', exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await reopened.getByRole('button', { name: 'Review development selection', exact: true }).click();
  await expect(reopened.getByLabel('Candidate version', { exact: true })).toBeVisible();
  await reopened
    .getByRole('button', { name: 'Confirm development selection', exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await reopened.request.get(
              API_BASE_URL + `modeling/status/${dataset.id}/?selected=true`,
            )
          ).json()
        ).selected_for_development,
    )
    .toBe(true);
  const unchanged = await (
    await reopened.request.get(API_BASE_URL + `jobs/${receipt.native_job_id}/`)
  ).json();
  expect(unchanged.result_sha256).toBe(snapshot.result_sha256);
  expect(unchanged.result.review_approved).toBe(false);
});
