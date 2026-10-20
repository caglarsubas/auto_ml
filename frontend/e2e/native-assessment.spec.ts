import { test, expect, Page } from '@playwright/test';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';
import { readFile } from 'node:fs/promises';

async function signIn(page: Page, role: string) {
  const credentials = requireTestCredentials();
  await page.goto('/login');
  await page
    .getByLabel('Username', { exact: true })
    .fill(credentials.username + '-adoption-' + role);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
}
for (const task of ['classification', 'regression']) {
  test(`independent ${task} adoption seals outcomes and runs a protected assessment`, async ({
    page,
  }, testInfo) => {
    await signIn(page, 'dev');
    const project = await page.getByLabel('Current project').inputValue();
    const datasets = await (await page.request.get(API_BASE_URL + 'declaration/')).json();
    const name = 'Adoption ' + (task === 'regression' ? 'regression' : 'binary') + '.csv';
    const dataset = datasets.find((d: any) => d.original_name === name);
    const csrf = (await (await page.request.get(API_BASE_URL + 'auth/session/')).json()).csrf_token;
    const headers = { 'X-CSRFToken': csrf };
    const options = {
      data_role: 'development_only',
      business_understanding: {
        problem_type: task,
        objective: 'Synthetic protected assessment',
        population: 'Development applicants',
        prediction_horizon: '12 months',
        feature_availability: { default: 'available_at_prediction' },
        target_contract: {
          target_column: 'outcome',
          positive_class: task === 'classification' ? 'bad' : null,
          event_definition: 'Synthetic outcome',
          label_maturity: 'Complete follow-up',
        },
        success_criteria: { primary_metric: task === 'classification' ? 'roc_auc' : 'rmse' },
      },
      features: ['x', 'z'],
      validation: { strategy: 'random', n_splits: 2 },
    };
    const base = API_BASE_URL + `jobs/datasets/${dataset.id}/`;
    const prepared = await page.request.post(base + `training-input/?project_id=${project}`, {
      data: options,
      headers,
    });
    expect(prepared.status()).toBe(200);
    const preview = await prepared.json();
    const response = await page.request.post(base + `?project_id=${project}`, {
      headers,
      data: {
        ...options,
        kind: preview.kind,
        input_sha256: preview.input_sha256,
        training_sha256: preview.training_sha256,
        request_id: crypto.randomUUID(),
      },
    });
    expect(response.status()).toBe(202);
    const training = await response.json();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(API_BASE_URL + `jobs/${training.id}/`)).json()).state,
        { timeout: 30000 },
      )
      .toBe('succeeded');
    await page.getByRole('button', { name: 'Training jobs for ' + name, exact: true }).click();
    await page.getByRole('button', { name: 'Open job ' + training.id, exact: true }).click();
    const panel = page.locator('app-native-adoption');
    await panel
      .getByLabel('Candidate adoption rationale', { exact: true })
      .fill('Freeze the exact candidate before independent protected evaluation.');
    await panel.getByLabel('I propose this exact frozen candidate', { exact: false }).check();
    const proposed = page.waitForResponse(
      (r) => r.url().includes('/adoptions/?') && r.request().method() === 'POST',
    );
    await panel
      .getByRole('button', { name: 'Propose native candidate adoption', exact: true })
      .click();
    const proposal = await (await proposed).json();
    expect(proposal.state).toBe('proposed');
    expect(
      await page
        .getByRole('button', { name: 'Accept candidate for protected assessment', exact: true })
        .count(),
    ).toBe(0);
    await page.request.post(API_BASE_URL + 'auth/logout/', { headers });
    await signIn(page, 'reviewer');
    await page.getByRole('button', { name: 'Training jobs for ' + name, exact: true }).click();
    await page.getByRole('button', { name: 'Open job ' + training.id, exact: true }).click();
    await expect(panel).toContainText(proposal.id);
    await panel
      .getByLabel('Independent review rationale', { exact: true })
      .fill(
        'Independent model review accepts this frozen candidate for protected assessment only.',
      );
    await panel
      .getByLabel('I independently reviewed this exact candidate', { exact: false })
      .check();
    await expect(
      panel.getByRole('button', { name: 'Accept candidate for protected assessment', exact: true }),
    ).toBeEnabled();
    await panel
      .getByRole('button', { name: 'Accept candidate for protected assessment', exact: true })
      .focus();
    await page.keyboard.press('Enter');
    await expect(panel).toContainText('Current scope usable: true');
    const rows =
      [
        'z,x,outcome',
        ...Array.from(
          { length: 60 },
          (_, i) =>
            `${i % 3 === 0 ? '' : i % 7},${10 + i / 60},${task === 'regression' ? i % 4 : i % 2 ? 'bad' : 'good'}`,
        ),
      ].join('\n') + '\n';
    await panel
      .getByLabel('Protected assessment CSV', { exact: true })
      .setInputFiles({
        name: 'private-outcomes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(rows),
      });
    await panel
      .getByLabel('Assessment as-of with timezone', { exact: true })
      .fill('2026-10-21T00:00:00Z');
    await panel
      .getByLabel('Protected population and maturity rationale', { exact: true })
      .fill(
        'Synthetic independent, disjoint population with complete follow-up; no prior analysis.',
      );
    await panel.getByLabel('I attest this frozen assessment population', { exact: false }).check();
    if (task === 'classification') {
      await page.route(
        '**/api/native-adoptions/*/protected-inputs/?*',
        async (route) => {
          const actual = await route.fetch();
          expect(actual.status()).toBe(200);
          await route.abort('failed');
        },
        { times: 1 },
      );
      await panel
        .getByRole('button', { name: 'Seal protected assessment input', exact: true })
        .click();
      await expect(panel.getByRole('alert')).toContainText('unconfirmed');
      await expect(panel.getByLabel('Protected assessment CSV', { exact: true })).toBeDisabled();
      await panel
        .getByRole('button', {
          name: 'Retry identical adoption or assessment request',
          exact: true,
        })
        .click();
    } else
      await panel
        .getByRole('button', { name: 'Seal protected assessment input', exact: true })
        .click();
    await expect(
      panel.getByRole('button', { name: 'Prepare protected assessment', exact: true }),
    ).toBeEnabled();
    const adoption = await (
      await page.request.get(API_BASE_URL + `native-adoptions/${proposal.id}/`)
    ).json();
    expect(adoption.protected_inputs).toHaveLength(1);
    expect(adoption.production_use_approved).toBe(false);
    expect(JSON.stringify(adoption)).not.toContain(rows);
    await panel.getByRole('button', { name: 'Prepare protected assessment', exact: true }).click();
    await expect(
      panel.getByRole('button', { name: 'Queue reviewed protected assessment', exact: true }),
    ).toBeDisabled();
    await panel.getByLabel('I authorize this exact frozen assessment', { exact: false }).check();
    await expect(
      panel.getByRole('button', { name: 'Queue reviewed protected assessment', exact: true }),
    ).toBeEnabled();
    const queued = page.waitForResponse(
      (r) => r.url().includes(`/jobs/datasets/${dataset.id}/?`) && r.request().method() === 'POST',
    );
    await panel
      .getByRole('button', { name: 'Queue reviewed protected assessment', exact: true })
      .click();
    const job = await (await queued).json();
    await expect
      .poll(
        async () => (await (await page.request.get(API_BASE_URL + `jobs/${job.id}/`)).json()).state,
        { timeout: 30000 },
      )
      .toBe('succeeded');
    await page.getByRole('button', { name: 'Refresh jobs', exact: true }).click();
    await expect(page.locator('app-package-jobs')).toContainText('Protected assessment: 60 rows');
    await expect(page.locator('app-package-jobs')).toContainText('exploratory');
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download job receipt', exact: true }).click();
    const download = await downloaded;
    const receipt = JSON.parse(await readFile((await download.path())!, 'utf8'));
    expect(receipt.result.final_holdout_accessed).toBe(true);
    expect(receipt.result.confirmatory).toBe(false);
    expect(receipt.result.production_use_approved).toBe(false);
    expect(receipt.result.review_approved).toBe(false);
    expect(receipt.result.metrics).toBeDefined();
    expect(receipt.result.scores).toBeUndefined();
    expect(receipt.result.labels).toBeUndefined();
    const original = await (await page.request.get(API_BASE_URL + `jobs/${training.id}/`)).json();
    expect(original.result.final_holdout_accessed).toBe(false);
    expect(original.result.model_adopted).toBe(false);
    await testInfo.attach('protected-native-assessment-evidence', {
      body: JSON.stringify({ adoption, assessment: receipt }),
      contentType: 'application/json',
    });
    await page.screenshot({
      path: testInfo.outputPath('protected-assessment-result.png'),
      animations: 'disabled',
    });
  });
}
