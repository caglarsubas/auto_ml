import { test, expect } from './fixtures/session';
import { API_BASE_URL } from './fixtures/credentials';

test('real-session raw input survives preprocessing versions and batch scoring', async ({
  authenticatedApi: api,
}) => {
  const rows = Array.from({ length: 300 }, (_, index) => ({
    x: index < 200 ? (index % 37) - 18 : 1e9,
    category: index < 200 ? (index % 3 ? 'common' : 'other') : 'unseen',
    outcome: index % 2 ? 'bad' : 'good',
    date: new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10),
  }));
  const csv = ['x,category,outcome,date', ...rows.map((row) => Object.values(row).join(','))].join(
    '\n',
  );
  const uploaded = await api.post('declaration/', {
    multipart: {
      file: { name: 'raw-replay.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
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
          problem_type: 'classification',
          objective: 'Predict the declared outcome',
          population: 'Synthetic applicants',
          prediction_horizon: '12 months',
          feature_availability: { default: 'available_at_prediction' },
          target_contract: {
            target_column: 'outcome',
            positive_class: 'bad',
            event_definition: 'Observed bad outcome',
            label_maturity: 'Complete follow-up',
          },
          success_criteria: { primary_metric: 'roc_auc', cost_matrix: { fn_cost: 4, fp_cost: 1 } },
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
    expect(run.model.input_stage).toBe('raw_unencoded');
    const assessed = await api.post('evaluation/run/', {
      data: { file_id: fileId, execution_id: run.execution_id },
    });
    expect(assessed.status()).toBe(200);
    const evidence = (await assessed.json()).evaluation;
    expect(evidence.evidence_status).toBe('exploratory');
    expect(evidence.purifier_provenance.recipe_id).toBe(first.purifier_recipe_id);
    expect(evidence.purifier_provenance.fit_rows.length).toBeLessThan(200);
    expect(evidence.purifier_provenance.clip_bounds.x.hi).toBeLessThan(100);
    const bundleResponse = await api.post('deployment/bundle/', { data: { file_id: fileId } });
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
    const fullScores = (await full.json()).scores;
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
  } finally {
    expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
  }
});
