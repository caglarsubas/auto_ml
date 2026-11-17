import { test, expect, Page } from '@playwright/test';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

function sha256(value: Buffer) {
  return createHash('sha256').update(value).digest('hex');
}

function seededDevelopmentCsv(task: string) {
  // Match seed_native_assessment_e2e.py, including Python's representation of 0.0.
  const rows = Array.from(
    { length: 80 },
    (_, i) =>
      `${i === 0 ? '0.0' : i / 80},${i % 7},${task === 'regression' ? i % 4 : i % 2 ? 'bad' : 'good'}`,
  );
  return Buffer.from(['x,z,outcome', ...rows, ''].join('\n'));
}

async function exerciseNativeReview(
  page: Page,
  datasetName: string,
  fileId: number,
  manifest: Buffer,
  manifestSha: string,
) {
  const recorded = JSON.parse(manifest.toString('utf8'));
  const { training, assessment, protected_input } = recorded;
  const result = assessment.result;
  const identity = {
    assessment_job_id: assessment.job_id,
    assessment_result_sha256: assessment.result_sha256,
    manifest_sha256: manifestSha,
  };
  // This exercises the reviewer action contract. CI runs the independent
  // calculation separately and joins its report digest to the approval event.
  const report = {
    schema_version: 1,
    scope: 'native_refit_assessment_reproduction_v1',
    status: 'passed',
    task: 'classification',
    manifest_sha256: manifestSha,
    training_result_sha256: training.result_sha256,
    assessment_result_sha256: assessment.result_sha256,
    development_sha256: training.specification.training.source.sha256,
    outcomes_sha256: protected_input.specification.input_sha256,
    candidate_export_sha256: result.candidate_export_sha256,
    model_sha256: training.fit.model_sha256,
    scores_sha256: result.scores_sha256,
    outcome_access_id: result.outcome_access_id,
    n_assessed: result.n_assessed,
    model_refit_reproduced: true,
    assessment_reproduced: true,
    comparison: 'exact_canonical_result_and_scores_sha256',
    confirmation_granted: false,
    review_approved: false,
    production_use_approved: false,
  };
  await page
    .getByRole('button', { name: 'Review package for ' + datasetName, exact: true })
    .click();
  const panel = page.locator('app-package-review');
  const reviewButton = panel.getByRole('button', {
    name: 'Open native assessment review',
    exact: true,
  });
  await panel.getByRole('button', { name: 'Open job ' + assessment.job_id, exact: true }).click();
  await expect(reviewButton).toHaveCount(0);
  const downloaded = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Download reproduction manifest', exact: true }).focus();
  await page.keyboard.press('Enter');
  expect(sha256(await readFile((await (await downloaded).path())!))).toBe(manifestSha);

  const pendingOpen = page.waitForResponse((response) => {
    return (
      new URL(response.url()).pathname === `/api/reviews/datasets/${fileId}/` &&
      response.request().method() === 'POST'
    );
  });
  await reviewButton.focus();
  await page.keyboard.press('Enter');
  const opened = await pendingOpen;
  expect(opened.status()).toBe(200);
  expect(opened.request().postDataJSON()).toMatchObject(identity);
  const review = await opened.json();
  expect(review).toMatchObject({ ...identity, bundle_id: null, production_use_approved: false });
  await expect(panel.getByLabel('Technical review decision')).toContainText(
    'Technical review: pending',
  );

  async function record(
    action: string,
    text: string,
    findingId?: string,
    details?: { expiry?: string; report?: typeof report },
  ) {
    await panel.getByLabel('Review action', { exact: true }).selectOption(action);
    if (findingId) await panel.getByLabel('Finding', { exact: true }).selectOption(findingId);
    if (details?.expiry) {
      await panel.getByLabel('Exception expiry (include timezone)').fill(details.expiry);
    }
    if (details?.report) {
      await panel.getByLabel('Reproduction report JSON').fill(JSON.stringify(details.report));
    }
    await panel.getByLabel('Finding, response or disposition').fill(text);
    const posted = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/reviews/${review.id}/` &&
        response.request().method() === 'POST',
    );
    await panel.getByRole('button', { name: 'Record review action', exact: true }).focus();
    await page.keyboard.press('Enter');
    const response = await posted;
    expect(response.status()).toBe(200);
    const latest = await response.json();
    expect(latest.production_use_approved).toBe(false);
    return latest;
  }

  const finding = await record('finding', 'Synthetic finding requires a documented disposition.');
  const findingId = finding.findings[0].id;
  const exception = await record(
    'exception',
    'A bounded exception defers this synthetic finding.',
    findingId,
    {
      expiry: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    },
  );
  expect(exception.findings[0].state).toBe('excepted');
  expect(exception.findings[0].exception.status).toBe('active');
  await expect(panel.getByLabel('Review findings')).toContainText('Exception active');

  const approval = await record('approve', 'Review the exact reproduced assessment.', undefined, {
    report,
  });
  expect(approval.review_approved).toBe(true);
  expect(approval.decision.status).toBe('approved');
  const approvalEvent = approval.events.find(
    (event: any) => event.id === approval.decision.event_id,
  );
  expect(approvalEvent.details.report_sha256).toMatch(/^[a-f0-9]{64}$/);
  await expect(panel.getByLabel('Technical review decision')).toContainText(
    'Technical review: approved',
  );

  const invalidated = await record('reopen', 'A new observation reopens the finding.', findingId);
  expect(invalidated.review_approved).toBe(false);
  expect(invalidated.decision).toMatchObject({
    status: 'invalidated',
    reason_code: 'review_discussion_changed',
    event_id: approval.decision.event_id,
  });
  await expect(panel.getByLabel('Technical review decision')).toContainText(
    'Technical review: invalidated',
  );
  const resolved = await record('resolve', 'The new observation is addressed.', findingId);
  expect(resolved.review_approved).toBe(false);
  await record('approve', 'Record a new independent decision after resolution.', undefined, {
    report,
  });
  const revoked = await record('revoke', 'Revoke the renewed technical decision.');
  expect(revoked.review_approved).toBe(false);
  expect(revoked.decision.status).toBe('revoked');
  expect(revoked.events.map((event: any) => event.event_type)).toEqual([
    'opened',
    'finding',
    'exception',
    'approve',
    'reopen',
    'resolve',
    'approve',
    'revoke',
  ]);
  await expect(panel.getByLabel('Technical review decision')).toContainText(
    'Technical review: revoked',
  );
  await expect(panel.getByLabel('Technical review decision')).toContainText(
    'Production-use approval: false',
  );
  return {
    schema_version: 1,
    scope: 'synthetic_native_assessment_review',
    ...identity,
    review_id: review.id,
    exception_event_id: exception.findings[0].exception.event_id,
    approval_event_id: approval.decision.event_id,
    reproduction_report_sha256: approvalEvent.details.report_sha256,
    invalidation_reason_code: invalidated.decision.reason_code,
    revocation_event_id: revoked.decision.event_id,
    production_use_approved: false,
  };
}

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
    await panel.getByLabel('Protected assessment CSV', { exact: true }).setInputFiles({
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

    const manifestResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        url.pathname === `/api/jobs/${job.id}/reproduction/` &&
        url.searchParams.get('sha256') === receipt.result_sha256 &&
        url.searchParams.get('project_id') === project &&
        response.request().method() === 'GET'
      );
    });
    const manifestDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download reproduction manifest', exact: true }).focus();
    await page.keyboard.press('Enter');
    const [reproduction, savedManifest] = await Promise.all([manifestResponse, manifestDownload]);
    expect(reproduction.status()).toBe(200);
    expect(reproduction.headers()['content-type']).toContain('application/json');
    expect(reproduction.headers()['content-disposition']).toContain('attachment');
    expect(reproduction.headers()['cache-control']).toBe('no-store');
    expect(savedManifest.suggestedFilename()).toBe(`reproduction-${job.id}.json`);
    const manifest = await readFile((await savedManifest.path())!);
    const manifestSha = sha256(manifest);
    expect(reproduction.headers()['x-declarai-export-sha256']).toBe(manifestSha);
    await expect(
      page.getByRole('status').filter({ hasText: 'Retain this reproduction manifest SHA-256' }),
    ).toContainText(manifestSha);

    const development = seededDevelopmentCsv(task);
    const outcomes = Buffer.from(rows);
    expect(sha256(development)).toBe(preview.input_sha256);
    expect(sha256(outcomes)).toBe(receipt.result.input_sha256);
    await mkdir(testInfo.outputDir, { recursive: true });
    // These exact synthetic inputs are consumed locally by the clean-run check.
    // Only its metadata report is uploaded.
    await Promise.all([
      writeFile(testInfo.outputPath('reproduction-manifest.json'), manifest),
      writeFile(testInfo.outputPath('reproduction-development.csv'), development),
      writeFile(testInfo.outputPath('reproduction-outcomes.csv'), outcomes),
    ]);
    if (task === 'classification') {
      const qualification = await exerciseNativeReview(
        page,
        name,
        dataset.id,
        manifest,
        manifestSha,
      );
      const body = Buffer.from(JSON.stringify(qualification));
      await writeFile(testInfo.outputPath('native-review-qualification.json'), body);
      await testInfo.attach('native-review-qualification.json', {
        body,
        contentType: 'application/json',
      });
    }
    await writeFile(
      testInfo.outputPath('native-reproduction-context.json'),
      JSON.stringify({
        task,
        synthetic_fixture: true,
        manifest_sha256: manifestSha,
        development_sha256: sha256(development),
        outcomes_sha256: sha256(outcomes),
        assessment_result_sha256: receipt.result_sha256,
        scores_sha256: receipt.result.scores_sha256,
        n_assessed: receipt.result.n_assessed,
      }),
    );
  });
}
