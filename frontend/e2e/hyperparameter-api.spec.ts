import { test, expect } from './fixtures/session';
import { uploadUntrainedDataset } from './fixtures/dataset';
let fileId: number;
test.beforeEach(async ({ authenticatedApi: api }) => { fileId = (await uploadUntrainedDataset(api)).id; });
test.afterEach(async ({ authenticatedApi: api }) => { if (fileId) await api.delete(`declaration/${fileId}/`); });

test.describe('Authenticated hyperparameter API contract', () => {
  test('start requires file_id', async ({ authenticatedApi: api }) => {
    const response = await api.post('modeling/hyperparam/start/', { data: {} });
    expect(response.status()).toBe(400);
    expect(JSON.stringify(await response.json())).toContain('file_id');
  });
  test('start requires persisted development training data', async ({ authenticatedApi: api }) => {
    const response = await api.post('modeling/hyperparam/start/', {
      data: { file_id: fileId, n_iter: 5, n_jobs: 1 },
    });
    expect(response.status()).toBe(404);
    expect(JSON.stringify(await response.json()).toLowerCase()).toContain('training data');
  });
  test('untrained run status is not_started', async ({ authenticatedApi: api }) => {
    const response = await api.get(`modeling/hyperparam/status/${fileId}/`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('not_started');
    expect(body.file_id).toBe(fileId);
  });
  test('untrained results are absent', async ({ authenticatedApi: api }) => {
    const response = await api.get(`modeling/hyperparam/${fileId}/`);
    expect(response.status()).toBe(404);
    expect((await response.json()).hyperparam_completed).toBe(false);
  });
  test('untrained run cannot be stopped', async ({ authenticatedApi: api }) => {
    const response = await api.post(`modeling/hyperparam/stop/${fileId}/`, { data: {} });
    expect(response.status()).toBe(200);
    expect((await response.json()).status).toBe('not_running');
  });
});
