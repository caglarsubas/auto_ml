/**
 * v2.27.0 — Preprocessing Options Catalog API (E2E)
 *
 * Hits GET /api/preprocessing/options/ on the live dev backend and
 * asserts the canonical 34-option catalog is reachable end-to-end
 * with the post-realignment IDs.  Pre-v2.27.0 the endpoint did not
 * exist; pre-v2.27.0 the labels for IDs 9-27 disagreed with what the
 * UI showed.
 *
 * Skipped automatically when the backend isn't running so the suite
 * stays runnable in headless CI.
 */
import { test, expect, request } from '@playwright/test';

const API_BASE = 'http://localhost:8001/api';

test.describe('GET /api/preprocessing/options/ — canonical purifier catalog', () => {
  test('returns 200 with options array and default_selected_ids', async () => {
    const ctx = await request.newContext();
    let response;
    try {
      response = await ctx.get(`${API_BASE}/preprocessing/options/`);
    } catch (err) {
      test.skip(true, `backend not reachable at ${API_BASE}: ${(err as Error).message}`);
      return;
    }
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty('options');
    expect(body).toHaveProperty('default_selected_ids');
    expect(Array.isArray(body.options)).toBe(true);
    expect(Array.isArray(body.default_selected_ids)).toBe(true);
  });

  test('catalog contains exactly 34 entries with IDs 1..34', async () => {
    const ctx = await request.newContext();
    let response;
    try {
      response = await ctx.get(`${API_BASE}/preprocessing/options/`);
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.options.length).toBe(34);
    const ids = body.options.map((o: { id: number }) => o.id).sort((a: number, b: number) => a - b);
    expect(ids).toEqual(Array.from({ length: 34 }, (_, i) => i + 1));
  });

  test('IDs that were misaligned pre-v2.27.0 now match their UI labels', async () => {
    // These are the smoking-gun IDs from the v2.27.0 audit.  Each was
    // routing to a different transform in the backend than its UI
    // label promised.  Pinning them here means any regression on
    // either side trips this end-to-end test instead of silently
    // dropping the wrong features.
    const ctx = await request.newContext();
    let response;
    try {
      response = await ctx.get(`${API_BASE}/preprocessing/options/`);
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    expect(response.status()).toBe(200);
    const body = await response.json();
    const byId = new Map<number, { id: number; name: string; kind: string; threshold: number | null; quantile_range: number[] | null }>(
      body.options.map((o: { id: number }) => [o.id, o])
    );

    const expectations: Array<[number, string]> = [
      [9,  'Corr-drop threshold = 0.75'],
      [11, 'Sparsity-drop threshold = 0.95'],
      [17, 'Missing-drop threshold = 0.95'],
      [23, '[Sparsity+Missing]-drop threshold = 0.95'],
      [24, '[Sparsity+Missing]-drop threshold = 0.90'],
      [27, '[Sparsity+Missing]-drop threshold = 0.75'],
      [29, 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]'],
    ];
    for (const [optId, label] of expectations) {
      expect(byId.get(optId)?.name, `id=${optId} label drifted`).toBe(label);
    }
    // ID 29 — the user request that triggered v2.27.0 — must carry
    // [0.05, 0.95] quantile range.
    expect(byId.get(29)?.quantile_range).toEqual([0.05, 0.95]);
  });

  test('default_selected_ids only contains valid catalog IDs', async () => {
    const ctx = await request.newContext();
    let response;
    try {
      response = await ctx.get(`${API_BASE}/preprocessing/options/`);
    } catch {
      test.skip(true, 'backend not reachable');
      return;
    }
    expect(response.status()).toBe(200);
    const body = await response.json();
    const catalogIds = new Set<number>(body.options.map((o: { id: number }) => o.id));
    for (const optId of body.default_selected_ids) {
      expect(catalogIds.has(optId), `default id ${optId} not in catalog`).toBe(true);
    }
  });
});
