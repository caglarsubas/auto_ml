import { test, expect } from './fixtures/session';

test.describe('Authenticated purifier options catalog', () => {
  test('returns the catalog and selected IDs', async ({ authenticatedApi: api }) => {
    const response = await api.get('preprocessing/options/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body.options)).toBe(true);
    expect(Array.isArray(body.default_selected_ids)).toBe(true);
  });
  test('retains all 34 option identifiers', async ({ authenticatedApi: api }) => {
    const response = await api.get('preprocessing/options/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.options.map((o: { id: number }) => o.id).sort((a: number, b: number) => a - b))
      .toEqual(Array.from({ length: 34 }, (_, i) => i + 1));
  });
  test('option labels and quantiles retain their declared meaning', async ({ authenticatedApi: api }) => {
    const response = await api.get('preprocessing/options/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    const byId = new Map<number, { name: string; quantile_range: number[] | null }>(
      body.options.map((o: { id: number }) => [o.id, o]));
    for (const [id, name] of [
      [9, 'Corr-drop threshold = 0.75'], [11, 'Sparsity-drop threshold = 0.95'],
      [17, 'Missing-drop threshold = 0.95'], [23, '[Sparsity+Missing]-drop threshold = 0.95'],
      [24, '[Sparsity+Missing]-drop threshold = 0.90'], [27, '[Sparsity+Missing]-drop threshold = 0.75'],
      [29, 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]'],
    ] as const) expect(byId.get(id)?.name).toBe(name);
    expect(byId.get(29)?.quantile_range).toEqual([0.05, 0.95]);
  });
  test('default selection only references valid options', async ({ authenticatedApi: api }) => {
    const response = await api.get('preprocessing/options/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    const ids = new Set(body.options.map((o: { id: number }) => o.id));
    expect(body.default_selected_ids.every((id: number) => ids.has(id))).toBe(true);
  });
});
