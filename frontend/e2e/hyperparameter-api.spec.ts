import { test, expect } from './fixtures/session';
const BOGUS_FILE_ID = 999999999;

test.describe('Authenticated hyperparameter API contract', () => {
  test('start requires file_id', async ({ authenticatedApi: api }) => {
    const response = await api.post('modeling/hyperparam/start/', { data: {} });
    expect(response.status()).toBe(400);
    expect(JSON.stringify(await response.json())).toContain('file_id');
  });
  test('start requires persisted development training data', async ({ authenticatedApi: api }) => {
    const response = await api.post('modeling/hyperparam/start/', {
      data: { file_id: BOGUS_FILE_ID, n_iter: 5, n_jobs: 1 },
    });
    expect(response.status()).toBe(404);
    expect(JSON.stringify(await response.json()).toLowerCase()).toContain('training data');
  });
  test('unknown run status is not_started', async ({ authenticatedApi: api }) => {
    const response = await api.get(`modeling/hyperparam/status/${BOGUS_FILE_ID}/`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('not_started');
    expect(body.file_id).toBe(BOGUS_FILE_ID);
  });
  test('unknown results are absent', async ({ authenticatedApi: api }) => {
    const response = await api.get(`modeling/hyperparam/${BOGUS_FILE_ID}/`);
    expect(response.status()).toBe(404);
    expect((await response.json()).hyperparam_completed).toBe(false);
  });
  test('unknown run cannot be stopped', async ({ authenticatedApi: api }) => {
    const response = await api.post(`modeling/hyperparam/stop/${BOGUS_FILE_ID}/`, { data: {} });
    expect(response.status()).toBe(200);
    expect((await response.json()).status).toBe('not_running');
  });
});
