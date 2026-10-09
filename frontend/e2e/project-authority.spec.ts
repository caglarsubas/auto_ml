import { randomUUID } from 'node:crypto';
import { test, expect } from './fixtures/session';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';
import { uploadUntrainedDataset } from './fixtures/dataset';

test('project-bound API denials preserve a real browser session', async ({ page, context, authenticatedApi: api }) => {
  const credentials = requireTestCredentials();
  const directory = await (await api.get('projects/')).json();
  expect(directory.governed).toBe(true);
  expect(directory.projects).toHaveLength(1);
  expect(directory.projects[0].role).toBe('developer');
  const dataset = await uploadUntrainedDataset(api);
  try {
    const denied = await api.post(`projects/${directory.projects[0].id}/members/`, {
      data: { username: credentials.username, role: 'admin', request_id: randomUUID() },
    });
    expect(denied.status()).toBe(403);
    expect((await denied.json()).error_code).toBe('project_access_denied');
    const unassigned = await api.get('modeling/status/9223372036854775807/');
    expect(unassigned.status()).toBe(403);
    expect((await unassigned.json()).error_code).toBe('dataset_project_assignment_required');
    expect((await api.get(`declaration/${dataset.id}/`)).status()).toBe(200);
    await page.goto('/login');
    await page.getByLabel('Username', { exact: true }).fill(credentials.username);
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(page).toHaveURL(/\/home$/);
    expect((await context.request.get(`${API_BASE_URL}modeling/status/9223372036854775807/`)).status()).toBe(403);
    await page.reload();
    await expect(page).toHaveURL(/\/home$/);
    await expect(page.getByRole('button', { name: /sign out/i })).toBeVisible();
  } finally {
    await api.delete(`declaration/${dataset.id}/`);
  }
});
