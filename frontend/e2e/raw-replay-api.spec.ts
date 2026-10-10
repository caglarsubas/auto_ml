import { test, expect } from './fixtures/session';
import { API_BASE_URL } from './fixtures/credentials';
import { randomUUID, createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

for (const task of ['classification', 'regression'] as const) {
  test(`real-session ${task} raw input survives preprocessing versions and batch scoring`, async ({
    authenticatedApi: api,
    page,
  }, testInfo) => {
    const primary = task === 'regression' ? 'mse' : 'pr_auc';
    const fixtureId = randomUUID();
    const rows = Array.from({ length: 300 }, (_, index) => ({
      x: index < 200 ? (index % 37) - 18 : 1e9,
      category: index < 200 ? (index % 3 ? 'common' : 'other') : 'unseen',
      outcome: task === 'regression' ? ((index % 37) - 18) * 2 : index % 2 ? 'bad' : 'good',
      date: new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10),
      fixture_id: fixtureId,
    }));
    const csv = [
      'x,category,outcome,date,fixture_id',
      ...rows.map((row) => Object.values(row).join(',')),
    ].join('\n');
    const uploaded = await api.post('declaration/', {
      multipart: {
        file: { name: `raw-replay-${task}.csv`, mimeType: 'text/csv', buffer: Buffer.from(csv) },
        column_separator: 'comma',
      },
    });
    expect(uploaded.status()).toBe(201);
    const fileId = (await uploaded.json()).id;
    try {
      const preprocessed = await api.post('preprocessing/run/', {
        data: {
          file_id: fileId,
          options: [29],
          target_column: 'outcome',
          split: { strategy: 'oot', date_column: 'date', cutoff: '2025-07-19' },
        },
      });
      expect(preprocessed.status()).toBe(200);
      const first = await preprocessed.json();
      expect(first.purifier_recipe_id).toBeTruthy();
      const trained = await api.post('modeling/start/', {
        data: {
          file_id: fileId,
          processed_file: first.processed_file,
          algorithm: 'xgboost',
          business_understanding: {
            problem_type: task,
            objective: 'Predict the declared outcome',
            population: 'Synthetic applicants',
            prediction_horizon: '12 months',
            feature_availability: { default: 'available_at_prediction' },
            forbidden_features: ['fixture_id'],
            target_contract: {
              target_column: 'outcome',
              positive_class: 'bad',
              event_definition: 'Observed bad outcome',
              label_maturity: 'Complete follow-up',
            },
            success_criteria: {
              primary_metric: primary,
              cost_matrix: { fn_cost: 4, fp_cost: 1 },
            },
          },
          encoding_plan: [
            {
              feature: 'category',
              user_lom: 'nominal',
              nunique: 3,
              encoding_method: 'one_hot_encoding',
            },
          ],
          encoding_use_native: false,
        },
      });
      expect(trained.status()).toBe(200);
      const run = await trained.json();
      expect(run.model.collinearity.method).toBe('centered_scaled_auxiliary_ols_v1');
      expect(run.model.collinearity.execution_id).toBe(run.execution_id);
      expect(run.model.collinearity.columns).toEqual(['x']);
      expect(run.model.collinearity.features.x.vif).toBeCloseTo(1, 9);
      for (const [name, diagnostic] of Object.entries(run.model.collinearity.features)) {
        if (name !== 'x')
          expect((diagnostic as { vif_status: string }).vif_status).toBe('excluded_categorical');
      }
      const numericDetail = await api.post('modeling/vif-detail/', {
        data: { file_id: fileId, execution_id: run.execution_id, feature: 'x' },
      });
      expect(numericDetail.status()).toBe(200);
      expect((await numericDetail.json()).row_count).toBe(run.model.collinearity.row_count);
      expect(run.model.input_stage).toBe('raw_unencoded');
      expect(run.model.cv.task).toBe(task);
      expect(run.model.cv.status).toBe('completed');
      expect(run.model.cv.cv_strategy).toBe('time_series');
      expect(run.model.fit_receipt.training_eval_metric).toBe(primary);
      expect(run.model.fit_receipt.stopping_evidence).toMatchObject({
        mode: 'declared_metric',
        metric_spec: { primary_metric: primary, cost_matrix: { fn_cost: 4, fp_cost: 1 } },
      });
      expect(run.model.fit_receipt.stopping_evidence.prediction_rounds).toBeGreaterThan(0);
      expect(run.model.cv.metric_coverage[primary]).toMatchObject({
        n_valid: 5,
        n_total: 5,
        status: 'complete',
      });
      expect(run.model.cv.fold_provenance.length).toBe(5);
      for (const fold of run.model.cv.fold_provenance) {
        expect(fold.purifier.fit_rows).toEqual(fold.train_rows);
        expect(Math.max(...fold.train_rows)).toBeLessThan(Math.min(...fold.valid_rows));
        expect(Math.max(...fold.valid_rows)).toBeLessThan(200);
        expect(fold.native_fit.training_eval_metric).toBe(primary);
      }
      if (task === 'regression') {
        expect(run.model.cv.rmse_mean).toBeGreaterThanOrEqual(0);
        expect(run.model.cv.roc_curve).toBeNull();
        expect(run.model.cv.pr_curve).toBeNull();
      }
      const assessed = await api.post('evaluation/run/', {
        data: { file_id: fileId, execution_id: run.execution_id },
      });
      expect(assessed.status()).toBe(200);
      const evidence = (await assessed.json()).evaluation;
      expect(evidence.evidence_status).toBe('exploratory');
      expect(evidence.holdout_history).toMatchObject({
        identity_status: 'verified_snapshot',
        same_final_rows_accesses: 0,
        overlapping_final_rows_accesses: 0,
      });
      const historyPath = `evaluation/holdout-history/${run.execution_id}/?file_id=${fileId}`;
      for (let check = 0; check < 2; check++) {
        const historyResponse = await api.get(historyPath);
        expect(historyResponse.status()).toBe(200);
        const history = await historyResponse.json();
        expect(history.same_final_rows_accesses).toBe(1);
        expect(history.records[0].actor.username).toBeTruthy();
        expect(history.records[0].attempt_state).toBe('completed');
      }
      expect(evidence.purifier_provenance.recipe_id).toBe(first.purifier_recipe_id);
      expect(evidence.purifier_provenance.fit_rows.length).toBeLessThan(200);
      expect(evidence.purifier_provenance.clip_bounds.x.hi).toBeLessThan(100);
      const bundleResponse = await api.post('deployment/bundle/', {
        data: {
          file_id: fileId,
          execution_id: run.execution_id,
          assessment_id: evidence.holdout_access_id,
        },
      });
      expect(bundleResponse.status()).toBe(200);
      const bundle = await bundleResponse.json();
      expect(bundle.manifest.input_stage).toBe('raw_unencoded');
      expect(bundle.manifest.input_features.sort()).toEqual(['category', 'x']);
      const scoreRows = [rows[299], rows[0], rows[0], rows[160], rows[199]].map(
        ({ x, category }) => ({ category, x }),
      );
      const full = await api.post('deployment/score/', {
        data: { file_id: fileId, rows: scoreRows },
      });
      expect(full.status()).toBe(200);
      const scoringReceipt = await full.json();
      expect(scoringReceipt.execution_id).toBe(run.execution_id);
      expect(scoringReceipt.assessment_id).toBe(evidence.holdout_access_id);
      expect(scoringReceipt.manifest_sha256).toBe(bundle.manifest_sha256);
      const fullScores = scoringReceipt.scores;
      expect(fullScores.length).toBe(scoreRows.length);
      for (let index = 0; index < scoreRows.length; index++) {
        const part = await api.post('deployment/score/', {
          data: { file_id: fileId, rows: [scoreRows[index]] },
        });
        expect(part.status()).toBe(200);
        expect((await part.json()).scores[0]).toBeCloseTo(fullScores[index], 9);
      }
      const missing = await api.post('deployment/score/', {
        data: { file_id: fileId, rows: [{ x: 1 }] },
      });
      expect(missing.status()).toBe(400);
      expect((await missing.json()).error).toContain('Missing required raw features');
      const media = new URL(`/media/${first.processed_file}`, API_BASE_URL);
      const original = await api.get(media.href);
      expect(original.status()).toBe(200);
      const originalBytes = await original.body();
      const next = await api.post('preprocessing/run/', {
        data: {
          file_id: fileId,
          options: [],
          target_column: 'outcome',
          split: { strategy: 'random' },
        },
      });
      expect(next.status()).toBe(200);
      expect((await next.json()).processed_file).not.toBe(first.processed_file);
      expect(await (await api.get(media.href)).body()).toEqual(originalBytes);
      const replay = await api.post('deployment/score/', {
        data: { file_id: fileId, bundle_id: bundle.manifest.bundle_id, rows: scoreRows },
      });
      expect(replay.status()).toBe(200);
      expect((await replay.json()).scores).toEqual(fullScores);
      const selected = await api.post('modeling/sfs/start/', {
        data: {
          file_id: fileId,
          execution_id: run.execution_id,
          initial_features: ['x'],
          methods: ['forward'],
          cv_folds: 2,
          stopping_criteria: {
            metrics: [{ metric: primary, pct_change: 0 }],
            min_features: 1,
            max_features: 1,
          },
        },
      });
      expect(selected.status()).toBe(200);
      await expect
        .poll(async () => (await (await api.get(`modeling/sfs/status/${fileId}/`)).json()).status, {
          timeout: 30_000,
        })
        .toBe('completed');
      const selectionResponse = await api.get(`modeling/sfs/${fileId}/`);
      expect(selectionResponse.status()).toBe(200);
      const selection = await selectionResponse.json();
      expect(selection.selection_objective).toMatchObject({
        primary_metric: primary,
        direction: task === 'regression' ? 'minimize' : 'maximize',
      });
      expect(selection.resume_basis).toMatchObject({ execution_id: run.execution_id, cv_folds: 2 });
      expect(selection.resume_basis.train.features).toEqual(['x']);
      expect(selection.search_bases[selection.resume_basis.sha256]).toEqual(selection.resume_basis);
      const step = selection.forward[0];
      expect(step.selected_features).toEqual(['x']);
      expect(step.cv_evidence.metric_coverage[primary]).toMatchObject({
        status: 'complete',
        n_total: 2,
        n_valid: 2,
      });
      expect(step.test_partition).toBe('development_validation');
      expect(step.selection_objective.qualification).toContain('Not independent assessment');
      for (const fold of step.validation_provenance) {
        expect(fold.purifier.fit_rows).toEqual(fold.train_rows);
        expect(Math.max(...fold.train_rows)).toBeLessThan(Math.min(...fold.valid_rows));
        expect(Math.max(...fold.valid_rows)).toBeLessThan(200);
        expect(fold.native_fit.train.features).toEqual(['x']);
      }
      if (task === 'regression') {
        expect(step.cv_rmse).toBeGreaterThanOrEqual(0);
        expect(step.cv_roc_auc).toBeUndefined();
      }
      const changedResume = await api.post('modeling/sfs/start/', {
        data: {
          file_id: fileId,
          execution_id: run.execution_id,
          resume: true,
          methods: ['forward'],
          cv_folds: 3,
        },
      });
      expect(changedResume.status()).toBe(409);
      expect((await changedResume.json()).error).toContain('Start a fresh search');
      for (const incomplete of [{ features: ['x'] }, { execution_id: run.execution_id }]) {
        const blocked = await api.post('modeling/champion/', {
          data: { file_id: fileId, ...incomplete },
        });
        expect(blocked.status()).toBe(409);
      }
      const parentStatus = new URL(
        `/media/execution_runs/${run.execution_id}/modeling_status.json`,
        API_BASE_URL,
      );
      const parentResponse = await api.get(parentStatus.href);
      expect(parentResponse.status()).toBe(200);
      const parentBytes = await parentResponse.body();
      const accepted = await api.post('modeling/champion/', {
        data: {
          file_id: fileId,
          execution_id: run.execution_id,
          features: ['x'],
          hyperparam: { n_estimators: 10, max_depth: 2 },
        },
      });
      expect(accepted.status()).toBe(200);
      const child = await accepted.json();
      expect(child.execution_id).not.toBe(run.execution_id);
      expect(child.model.holdout_spec).toEqual(run.model.holdout_spec);
      const childHistory = await api.get(
        `evaluation/holdout-history/${child.execution_id}/?file_id=${fileId}`,
      );
      expect(childHistory.status()).toBe(200);
      expect((await childHistory.json()).same_final_rows_accesses).toBe(1);
      const childAssessment = await api.post('evaluation/run/', {
        data: { file_id: fileId, execution_id: child.execution_id },
      });
      expect(childAssessment.status()).toBe(200);
      expect(
        (await childAssessment.json()).evaluation.holdout_history.same_final_rows_accesses,
      ).toBe(1);
      const exactPack = await api.post('evaluation/pack/', {
        data: {
          file_id: fileId,
          execution_id: run.execution_id,
          assessment_id: evidence.holdout_access_id,
        },
      });
      expect(exactPack.status()).toBe(200);
      expect(exactPack.headers()['content-type']).toContain('application/zip');
      expect(child.model.collinearity.columns).toEqual(['x']);
      expect(child.model.collinearity.execution_id).toBe(child.execution_id);
      const oldDiagnostic = await api.post('modeling/vif-detail/', {
        data: { file_id: fileId, execution_id: run.execution_id, feature: 'x' },
      });
      expect(oldDiagnostic.status()).toBe(200);
      expect((await oldDiagnostic.json()).execution_id).toBe(run.execution_id);
      const ambiguous = await api.post('modeling/vif-detail/', {
        data: { file_id: fileId, feature: 'x' },
      });
      expect(ambiguous.status()).toBe(400);
      expect(child.model.fit_receipt.train.features).toEqual(['x']);
      expect(child.model.fit_receipt.num_boost_round).toBe(10);
      expect(child.model.fit_receipt.training_eval_metric).toBe(primary);
      expect(child.model.cv.configuration).toMatchObject({
        feature_scope: 'selected',
        features: ['x'],
        num_boost_round: 10,
      });
      expect(child.model.cv.evidence_scope).toContain('Post-selection');
      expect(child.model.test_auc).toBeNull();
      expect(child.champion.production_use_approved).toBe(false);
      expect(await (await api.get(parentStatus.href)).body()).toEqual(parentBytes);
      const stale = await api.post('modeling/champion/', {
        data: { file_id: fileId, execution_id: run.execution_id, features: ['x'] },
      });
      expect(stale.status()).toBe(409);
      const tuned = await api.post('modeling/hyperparam/start/', {
        data: {
          file_id: fileId,
          execution_id: child.execution_id,
          features: ['x'],
          primary_metric: primary,
          search_method: 'grid',
          cv_folds: 2,
          n_jobs: 1,
          grid_points_per_param: 2,
          validation_curve_points: 2,
          fixed_params: { n_estimators: 5 },
          param_space: Object.fromEntries(
            [
              'n_estimators',
              'max_depth',
              'learning_rate',
              'min_child_weight',
              'subsample',
              'colsample_bytree',
              'gamma',
              'reg_alpha',
              'reg_lambda',
            ].map((name) => [
              name,
              name === 'max_depth' ? { enabled: true, min: 1, max: 2 } : { enabled: false },
            ]),
          ),
        },
      });
      expect(tuned.status()).toBe(200);
      expect((await tuned.json()).parent_execution_id).toBe(child.execution_id);
      await expect
        .poll(
          async () =>
            (await (await api.get(`modeling/hyperparam/status/${fileId}/`)).json()).status,
          { timeout: 30_000 },
        )
        .toBe('completed');
      const tuning = await (await api.get(`modeling/hyperparam/${fileId}/`)).json();
      expect(tuning.hyperparam_completed).toBe(true);
      expect(tuning.search_basis.execution_id).toBe(child.execution_id);
      expect(tuning.selection_objective.primary_metric).toBe(primary);
      expect(tuning.n_attempted).toBe(2);
      expect(tuning.n_failed).toBe(0);
      expect(tuning.refit_params).toEqual(tuning.selected_params);
      expect(tuning.refit_receipt.num_boost_round).toBe(5);
      expect(tuning.refit_receipt.training_eval_metric).toBe(primary);
      expect(tuning.execution_id).not.toBe(child.execution_id);
      for (const trial of tuning.trials) {
        expect(trial.fit_receipt.training_eval_metric).toBe(primary);
        expect(trial.cv[primary]).toMatchObject({ status: 'complete', n_valid: 2, n_total: 2 });
        for (const fold of trial.validation_provenance) {
          expect(Math.max(...fold.train_rows)).toBeLessThan(Math.min(...fold.valid_rows));
          expect(Math.max(...fold.valid_rows)).toBeLessThan(200);
          expect(fold.purifier.fit_rows).toEqual(fold.train_rows);
          expect(fold.fit_receipt.train.features).toEqual(['x']);
          expect(fold.fit_receipt.num_boost_round).toBe(5);
        }
      }
      const evidenceUrl = new URL(
        `/media/execution_runs/${tuning.execution_id}/tuning_selection.json`,
        API_BASE_URL,
      );
      const evidenceResponse = await api.get(evidenceUrl.href);
      expect(evidenceResponse.status()).toBe(200);
      expect((await evidenceResponse.json()).search_basis.sha256).toBe(tuning.search_basis.sha256);
      expect(await (await api.get(parentStatus.href)).body()).toEqual(parentBytes);
      const oldReplay = await api.post('deployment/score/', {
        data: { file_id: fileId, bundle_id: bundle.manifest.bundle_id, rows: scoreRows },
      });
      expect(oldReplay.status()).toBe(200);
      expect((await oldReplay.json()).scores).toEqual(fullScores);
      const blockedPackage = await api.get(`deployment/bundle/?file_id=${fileId}`);
      expect(blockedPackage.status()).toBe(409);
      const historical = await api.post('deployment/bundle/', {
        data: {
          file_id: fileId,
          execution_id: run.execution_id,
          assessment_id: evidence.holdout_access_id,
        },
      });
      expect(historical.status()).toBe(200);
      expect((await historical.json()).adoption_status).toBe('version_only_current_changed');
      expect((await (await api.get(`deployment/status/${fileId}/`)).json()).bundle_id).toBe(
        bundle.bundle_id,
      );
      const exactScoringPack = await api.post('deployment/pack/', {
        data: { file_id: fileId, bundle_id: bundle.bundle_id },
      });
      expect(exactScoringPack.status()).toBe(200);
      expect(exactScoringPack.headers()['x-declarai-bundle-id']).toBe(bundle.bundle_id);
      expect(exactScoringPack.headers()['x-declarai-manifest-sha256']).toBe(bundle.manifest_sha256);
      const verificationScore = await api.post('deployment/score/', {
        multipart: {
          file_id: String(fileId),
          bundle_id: bundle.bundle_id,
          file: { name: 'offline-input.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
        },
      });
      expect(verificationScore.status()).toBe(200);
      const verificationReceipt = await verificationScore.json();
      const preparedInput = await api.get(`jobs/datasets/${fileId}/input/`);
      expect(preparedInput.status()).toBe(200);
      expect((await preparedInput.json()).sha256).toBe(
        createHash('sha256').update(csv).digest('hex'),
      );
      const queuedScore = await api.post(`jobs/datasets/${fileId}/`, {
        data: {
          request_id: randomUUID(),
          kind: 'native_csv_scoring_v1',
          bundle_id: bundle.bundle_id,
          manifest_sha256: bundle.manifest_sha256,
          input_file_id: fileId,
          input_sha256: (await preparedInput.json()).sha256,
        },
      });
      expect(queuedScore.status()).toBe(202);
      const jobId = (await queuedScore.json()).id;
      await expect
        .poll(async () => (await (await api.get(`jobs/${jobId}/`)).json()).state, {
          timeout: 30_000,
        })
        .toBe('succeeded');
      const jobReceipt = await (await api.get(`jobs/${jobId}/`)).json();
      expect(jobReceipt.attempts).toBe(1);
      expect(jobReceipt.result.scores).toEqual(verificationReceipt.scores);
      expect(jobReceipt.events.map((event: any) => event.event_type)).toEqual([
        'submitted',
        'started',
        'succeeded',
      ]);
      const exactReceipt = await api.get(
        `jobs/${jobId}/scores/?sha256=${jobReceipt.result_sha256}`,
      );
      expect(exactReceipt.status()).toBe(200);
      const packBytes = await exactScoringPack.body();
      const receiptBytes = await exactReceipt.body();
      expect(createHash('sha256').update(receiptBytes).digest('hex')).toBe(
        jobReceipt.result_sha256,
      );
      await writeFile(testInfo.outputPath('offline-package.zip'), packBytes);
      await writeFile(testInfo.outputPath('offline-input.csv'), csv);
      await writeFile(testInfo.outputPath('offline-receipt.json'), receiptBytes);
      await writeFile(
        testInfo.outputPath('offline-context.json'),
        JSON.stringify({
          task,
          synthetic_fixture: true,
          package_sha256: createHash('sha256').update(packBytes).digest('hex'),
          receipt_sha256: jobReceipt.result_sha256,
          manifest_sha256: bundle.manifest_sha256,
        }),
      );
      if (task === 'classification') {
        const runName = `holdout-review-${fileId}`;
        const pipeline = await api.post('pipeline/create/', {
          data: {
            name: runName,
            file_id: fileId,
            current_step: 'evaluation',
            state: {
              file_id: fileId,
              pipeline_type: 'boosting',
              flags: { is_started: true, preprocessing_available: true, modeling_available: true },
              modeling: {
                substep: 'hyperparam_completed',
                modelingStatus: child,
                hpResults: tuning,
              },
            },
          },
        });
        expect(pipeline.status()).toBe(201);
        const pipelineId = (await pipeline.json()).id;
        try {
          await page.context().addCookies((await api.storageState()).cookies);
          await page.goto('/model-development');
          await page.getByRole('button', { name: /Saved Pipelines/ }).click();
          await page
            .getByTitle(runName, { exact: true })
            .locator('..')
            .locator('..')
            .getByRole('button', { name: 'Load', exact: true })
            .click();
          const numeric = page.getByTestId('numeric-diagnostics');
          await expect(numeric).toBeVisible();
          await numeric.locator('summary').focus();
          await numeric.locator('summary').press('Space');
          await expect(numeric).toContainText(child.execution_id);
          const inspect = numeric.getByRole('button', {
            name: 'Inspect collinearity for x',
            exact: true,
          });
          await inspect.focus();
          await inspect.press('Enter');
          const dialog = page.getByRole('dialog', { name: 'VIF Decomposition: x' });
          await expect(dialog).toBeVisible();
          await expect(dialog).toContainText('Overall VIF: 1.00');
          await expect(dialog).toContainText(child.execution_id);
          await expect(dialog).toContainText('not model importance');
          await expect(
            dialog.getByRole('button', { name: 'Close collinearity details' }),
          ).toBeFocused();
          await dialog.screenshot({ path: testInfo.outputPath('numeric-collinearity.png') });
          await dialog.press('Escape');
          await expect(dialog).not.toBeVisible();
          await expect(inspect).toBeFocused();
          const history = page.getByRole('region', { name: 'Final-outcome access history' });
          await expect(history).toBeVisible();
          await expect(history).toContainText('2 accesses to the same final rows');
          const details = history.locator('summary');
          await details.focus();
          await details.press('Space');
          await expect(history.locator('details')).toHaveAttribute('open', '');
          await expect(history).toContainText('completed');
          await history.screenshot({ path: testInfo.outputPath('holdout-review.png') });
          const deployment = page.locator('app-deployment');
          await expect(deployment).toContainText('Review package and batch scoring');
          await expect(deployment).toContainText('different execution');
          await expect(
            deployment.getByRole('button', { name: 'Create score bundle', exact: true }),
          ).toBeDisabled();
          const version = deployment.getByText('Package version and evidence', { exact: true });
          await version.focus();
          await version.press('Space');
          await expect(deployment).toContainText(bundle.bundle_id);
          const downloadEvent = page.waitForEvent('download');
          await deployment
            .getByRole('button', { name: 'Download selected bundle', exact: true })
            .click();
          const download = await downloadEvent;
          expect(download.suggestedFilename()).toBe(`declarai-bundle-${bundle.bundle_id}.zip`);
          const scoreResponse = page.waitForResponse(
            (response) =>
              response.url().includes('/deployment/score/') &&
              response.request().method() === 'POST',
          );
          await deployment.locator('input[type="file"]').setInputFiles({
            name: 'approved-verification.csv',
            mimeType: 'text/csv',
            buffer: Buffer.from(csv),
          });
          const scoredResponse = await scoreResponse;
          expect(scoredResponse.status()).toBe(200);
          const scored = await scoredResponse.json();
          expect(scored.input.sha256).toBe(createHash('sha256').update(csv).digest('hex'));
          const scoreDetails = deployment.getByText('Scoring version receipt', { exact: true });
          await scoreDetails.focus();
          await scoreDetails.press('Space');
          await expect(deployment).toContainText('Verification checks score parity');
          const receiptDownload = page.waitForEvent('download');
          await deployment
            .getByRole('button', { name: 'Download full scoring receipt', exact: true })
            .focus();
          await page.keyboard.press('Enter');
          const receiptFile = await receiptDownload;
          const receiptBytes = await readFile((await receiptFile.path())!);
          expect(createHash('sha256').update(receiptBytes).digest('hex')).toBe(
            scored.receipt_sha256,
          );
          const receipt = JSON.parse(receiptBytes.toString('utf8'));
          expect(receipt.bundle_id).toBe(bundle.bundle_id);
          expect(receipt.scores).toHaveLength(rows.length);
          expect(receipt.production_use_approved).toBe(false);
          await deployment.screenshot({ path: testInfo.outputPath('package-handoff.png') });
        } finally {
          expect((await api.delete(`pipeline/${pipelineId}/`)).status()).toBe(200);
        }
      }
    } finally {
      expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
    }
  });
}

test('real-session numeric diagnostics retain singular and excluded states through keyboard review', async ({
  authenticatedApi: api,
  page,
}, testInfo) => {
  const csv = [
    'x,duplicate,category,outcome',
    ...Array.from(
      { length: 200 },
      (_, i) => `${i % 23},${2 * (i % 23) + 100},${i % 3 ? 'a' : 'b'},${i % 2}`,
    ),
  ].join('\n');
  const uploaded = await api.post('declaration/', {
    multipart: {
      file: { name: 'numeric-states.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
      column_separator: 'comma',
    },
  });
  expect(uploaded.status()).toBe(201);
  const fileId = (await uploaded.json()).id;
  let pipelineId: number | undefined;
  try {
    const prepared = await api.post('preprocessing/run/', {
      data: { file_id: fileId, options: [], target_column: 'outcome' },
    });
    expect(prepared.status()).toBe(200);
    const trained = await api.post('modeling/start/', {
      data: {
        file_id: fileId,
        processed_file: (await prepared.json()).processed_file,
        algorithm: 'xgboost',
        business_understanding: {
          problem_type: 'classification',
          objective: 'Synthetic numeric dependence',
          population: 'Synthetic applicants',
          prediction_horizon: '12 months',
          feature_availability: { default: 'available_at_prediction' },
          target_contract: {
            target_column: 'outcome',
            positive_class: 1,
            event_definition: 'Synthetic event',
            label_maturity: 'Complete',
          },
          success_criteria: { primary_metric: 'roc_auc' },
        },
        encoding_plan: [
          {
            feature: 'category',
            user_lom: 'nominal',
            nunique: 2,
            encoding_method: 'one_hot_encoding',
          },
        ],
        encoding_use_native: false,
      },
    });
    expect(trained.status()).toBe(200);
    const run = await trained.json();
    expect(run.model.collinearity.features.x).toMatchObject({ vif: null, vif_status: 'unbounded' });
    const excluded = Object.entries(run.model.collinearity.features).find(
      ([, record]) => (record as { vif_status: string }).vif_status === 'excluded_categorical',
    )?.[0];
    expect(excluded).toBeTruthy();
    const exclusion = await api.post('modeling/vif-detail/', {
      data: { file_id: fileId, execution_id: run.execution_id, feature: excluded },
    });
    expect(exclusion.status()).toBe(200);
    expect((await exclusion.json()).vif_status).toBe('excluded_categorical');
    const name = `numeric-review-${fileId}`;
    const pipeline = await api.post('pipeline/create/', {
      data: {
        name,
        file_id: fileId,
        current_step: 'modeling',
        state: {
          file_id: fileId,
          pipeline_type: 'boosting',
          flags: { is_started: true, preprocessing_available: true, modeling_available: true },
          modeling: { substep: 'modeling_completed', modelingStatus: run },
        },
      },
    });
    expect(pipeline.status()).toBe(201);
    pipelineId = (await pipeline.json()).id;
    await page.context().addCookies((await api.storageState()).cookies);
    await page.goto('/model-development');
    await page.getByRole('button', { name: /Saved Pipelines/ }).click();
    await page
      .getByTitle(name, { exact: true })
      .locator('..')
      .locator('..')
      .getByRole('button', { name: 'Load', exact: true })
      .click();
    const numeric = page.getByTestId('numeric-diagnostics');
    await numeric.locator('summary').focus();
    await numeric.locator('summary').press('Space');
    await expect(numeric).toContainText('Unbounded');
    await expect(numeric).toContainText('Category excluded');
    await numeric.getByRole('button', { name: 'Inspect collinearity for x', exact: true }).focus();
    await numeric
      .getByRole('button', { name: 'Inspect collinearity for x', exact: true })
      .press('Enter');
    const dialog = page.getByRole('dialog', { name: 'VIF Decomposition: x' });
    await expect(dialog).toContainText('Overall VIF: Unbounded');
    await expect(dialog).toContainText(run.execution_id);
    await expect(dialog).toContainText('indistinguishable');
    await dialog.screenshot({ path: testInfo.outputPath('unbounded-collinearity.png') });
    await dialog.press('Escape');
    await expect(dialog).not.toBeVisible();
    const inspect = numeric.getByRole('button', {
      name: `Inspect collinearity for ${excluded}`,
      exact: true,
    });
    await inspect.focus();
    await inspect.press('Enter');
    const categoryDialog = page.getByRole('dialog', { name: `VIF Decomposition: ${excluded}` });
    await expect(categoryDialog).toContainText('Overall VIF: Category excluded');
    await categoryDialog.press('Escape');
    await expect(inspect).toBeFocused();
  } finally {
    if (pipelineId) expect((await api.delete(`pipeline/${pipelineId}/`)).status()).toBe(200);
    expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
  }
});
