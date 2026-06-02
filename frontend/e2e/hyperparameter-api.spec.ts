/**
 * Hyperparameter Tuning API (E2E)
 *
 * Hits the live dev backend hyperparameter endpoints and asserts the wired
 * routes + view guards end-to-end:
 *   - POST /api/modeling/hyperparam/start/         (precondition guards)
 *   - GET  /api/modeling/hyperparam/status/<id>/   (not_started default)
 *   - GET  /api/modeling/hyperparam/<id>/          (results 404 when absent)
 *   - POST /api/modeling/hyperparam/stop/<id>/     (not_running default)
 *
 * These cover the full HTTP stack (URL routing → DRF view → guard → response)
 * without depending on a trained model or the slow modeling/SFS UI journey,
 * so they stay deterministic and fast.
 *
 * Skipped automatically when the backend isn't running so the suite stays
 * runnable in headless CI.
 */
import { test, expect, request, APIRequestContext } from '@playwright/test';

const API_BASE = 'http://localhost:8001/api';
// A file_id that will never have modeling/tuning artifacts on disk.
const BOGUS_FILE_ID = 999999999;

async function newCtx(): Promise<APIRequestContext | null> {
  try {
    return await request.newContext();
  } catch {
    return null;
  }
}

test.describe('Hyperparameter Tuning API — route + guard contract', () => {
  test('POST start without file_id → 400 file_id required', async () => {
    const ctx = await newCtx();
    if (!ctx) { test.skip(true, 'request context unavailable'); return; }
    let response;
    try {
      response = await ctx.post(`${API_BASE}/modeling/hyperparam/start/`, { data: {} });
    } catch (err) {
      test.skip(true, `backend not reachable at ${API_BASE}: ${(err as Error).message}`);
      return;
    }
    expect(response.status()).toBe(400);
    const body = await response.json();
    expect(JSON.stringify(body)).toContain('file_id');
  });

  test('POST start with a non-existent file_id → 404 training data not found', async () => {
    const ctx = await newCtx();
    if (!ctx) { test.skip(true, 'request context unavailable'); return; }
    let response;
    try {
      response = await ctx.post(`${API_BASE}/modeling/hyperparam/start/`, {
        data: { file_id: BOGUS_FILE_ID, n_iter: 5, n_jobs: 1 },
      });
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    // The start view requires train_data persisted by modeling (+ SFS) first.
    expect(response.status()).toBe(404);
    const body = await response.json();
    expect(JSON.stringify(body).toLowerCase()).toContain('training data');
  });

  test('GET status for an unknown file_id → 200 not_started', async () => {
    const ctx = await newCtx();
    if (!ctx) { test.skip(true, 'request context unavailable'); return; }
    let response;
    try {
      response = await ctx.get(`${API_BASE}/modeling/hyperparam/status/${BOGUS_FILE_ID}/`);
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('not_started');
    expect(body.file_id).toBe(BOGUS_FILE_ID);
  });

  test('GET results for an unknown file_id → 404 not found', async () => {
    const ctx = await newCtx();
    if (!ctx) { test.skip(true, 'request context unavailable'); return; }
    let response;
    try {
      response = await ctx.get(`${API_BASE}/modeling/hyperparam/${BOGUS_FILE_ID}/`);
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    expect(response.status()).toBe(404);
    const body = await response.json();
    expect(body.hyperparam_completed).toBe(false);
  });

  test('POST stop for an unknown file_id → 200 not_running', async () => {
    const ctx = await newCtx();
    if (!ctx) { test.skip(true, 'request context unavailable'); return; }
    let response;
    try {
      response = await ctx.post(`${API_BASE}/modeling/hyperparam/stop/${BOGUS_FILE_ID}/`, { data: {} });
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('not_running');
  });
});
