import { test, expect } from './fixtures/session';
import { API_BASE_URL, BASE_URL, requireTestCredentials } from './fixtures/credentials';

test('anonymous requests cannot read installation data or artifacts', async ({ request }) => {
  expect((await request.get(`${API_BASE_URL}preprocessing/options/`)).status()).toBe(403);
  const artifact = new URL('/media/not-present.json', API_BASE_URL);
  expect((await request.get(artifact.href)).status()).toBe(403);
  expect((await request.post(`${API_BASE_URL}modeling/start/`, { data: {} })).status()).toBe(403);
  const history = `${API_BASE_URL}evaluation/holdout-history/00000000-0000-0000-0000-000000000000/?file_id=1`;
  expect((await request.get(history)).status()).toBe(403);
});

test('an authenticated mutation still requires CSRF', async ({ authenticatedApi: api, playwright }) => {
  const unprotected = await playwright.request.newContext({
    baseURL: API_BASE_URL, storageState: await api.storageState(),
  });
  try {
    expect((await unprotected.post('modeling/hyperparam/start/', { data: {} })).status()).toBe(403);
    expect((await api.post('modeling/hyperparam/start/', { data: {} })).status()).toBe(400);
  } finally { await unprotected.dispose(); }
});

test('logout revokes access using the previous session cookie', async ({ authenticatedApi: api, playwright }) => {
  const previous = await playwright.request.newContext({
    baseURL: API_BASE_URL, storageState: await api.storageState(),
  });
  try {
    expect((await api.post('auth/logout/')).status()).toBe(200);
    expect((await previous.get('preprocessing/options/')).status()).toBe(403);
  } finally { await previous.dispose(); }
});

test('a wrong password does not establish a server session', async ({ request }) => {
  const session = await request.get(`${API_BASE_URL}auth/session/`);
  expect(session.status()).toBe(200);
  const response = await request.post(`${API_BASE_URL}auth/login/`, {
    data: { username: requireTestCredentials().username, password: 'deliberately-invalid' },
    headers: { 'X-CSRFToken': (await session.json()).csrf_token, Origin: new URL(BASE_URL).origin },
  });
  expect(response.status()).toBe(401);
  expect((await (await request.get(`${API_BASE_URL}auth/session/`)).json()).authenticated).toBe(false);
});

test('expert code stays blocked until isolation is available', async ({ authenticatedApi: api }) => {
  const result = await api.post('ai-assistant/execute-action/', {
    data: { file_id: 999999999, action_type: 'execute_code', payload: { code: 'df["x"] = 1' } },
  });
  expect(result.status()).toBe(400);
  expect((await result.json()).error_code).toBe('expert_isolation_unavailable');
});

test('session and CSRF parsing preserves feature-selection requests', async ({ authenticatedApi: api }) => {
  expect((await api.post('modeling/sfs/start/', { data: {} })).status()).toBe(400);
  const missing = await api.post('modeling/sfs/start/', { data: { file_id: 999999999 } });
  expect(missing.status()).toBe(404);
  expect((await missing.json()).error).toContain('Training data not found');
});

test('a signed-in user can create, update and delete a pipeline', async ({ authenticatedApi: api }) => {
  const created = await api.post('pipeline/create/', { data: { name: 'disposable-session-check' } });
  expect(created.status()).toBe(201);
  const path = `pipeline/${(await created.json()).id}/`;
  try {
    const changed = await api.put(path, {
      data: { current_step: 'modeling', state: { modeling: { substep: 'encoding_completed' } } },
    });
    expect(changed.status()).toBe(200);
    expect((await changed.json()).current_step).toBe('modeling');
    expect((await (await api.get(path)).json()).state.modeling.substep).toBe('encoding_completed');
  } finally {
    expect((await api.delete(path)).status()).toBe(200);
  }
  expect((await api.get(path)).status()).toBe(404);
});
