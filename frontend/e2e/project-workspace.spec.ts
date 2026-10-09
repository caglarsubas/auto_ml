import { test, expect } from '@playwright/test';
import { API_BASE_URL, requireTestCredentials } from './fixtures/credentials';

async function signIn(page: any) {
  const credentials = requireTestCredentials();
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username + '-workspace');
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByLabel('Current project')).toBeVisible();
}

test('multiple projects require choice; keyboard selection pins pipeline creation and upload', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await signIn(page);
  await expect(page.getByLabel('Current project')).toHaveValue('');
  await page.goto('/model-development');
  await expect(page).toHaveURL(/\/home$/);
  const picker = page.getByLabel('Current project');
  const labels = await picker.locator('option').allTextContents();
  const index = labels.findIndex((label) => label.trim() === 'Workspace A — developer');
  expect(index).toBeGreaterThan(0);
  const projectId = await picker.locator('option').nth(index).getAttribute('value');
  await picker.focus();
  await page.keyboard.type('Workspace A ');
  await picker.press('Tab');
  await expect(picker).toHaveValue(projectId!);
  await expect(page.getByLabel('Project datasets')).toContainText('Workspace A.csv');
  await expect(page.getByLabel('Project datasets')).not.toContainText('Workspace B.csv');
  await expect(page.getByLabel('Project pipelines')).toContainText('Workspace A pipeline');
  await page.getByRole('link', { name: 'Open development workspace', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp('project_id=' + projectId));
  await expect(page.locator('.workspace-context')).toContainText('Workspace A');
  await page.locator('.pipeline-type-dropdown select').selectOption('boosting');
  const create = page.waitForResponse(
    (response) =>
      response.url().includes('/pipeline/create/') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  const created = await create;
  expect(created.status()).toBe(201);
  expect(created.request().postDataJSON().project_id).toBe(projectId);
  await page
    .locator('app-declaration input[type="file"]')
    .first()
    .setInputFiles({
      name: 'workspace-upload-' + Date.now() + '.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('x,target\n1,0\n2,1\n3,0\n4,1\n'),
    });
  await page.getByLabel('COLUMN SEPARATOR').selectOption('comma');
  const upload = page.waitForResponse(
    (response) =>
      response.url().endsWith('/declaration/') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'IMPORT DATA', exact: true }).click();
  const uploaded = await upload;
  expect(uploaded.status()).toBe(201);
  expect((await uploaded.json()).project_id).toBe(projectId);
  const directory = await (await page.request.get(API_BASE_URL + 'projects/')).json();
  const other = directory.projects.find((p: any) => p.name === 'Workspace B');
  const mismatch = await page.request.get(
    `${API_BASE_URL}pipeline/${(await created.json()).id}/?project_id=${other.id}`,
  );
  expect(mismatch.status()).toBe(403);
  await page.screenshot({
    path: testInfo.outputPath('workspace-developer.png'),
    animations: 'disabled',
  });
  expect(errors).toEqual([]);
});

for (const [name, role] of [
  ['Workspace Review', 'reviewer'],
  ['Workspace Admin', 'admin'],
]) {
  test(`${role} browses only selected records and downloads evidence; development remains blocked`, async ({
    page,
  }, testInfo) => {
    await signIn(page);
    const picker = page.getByLabel('Current project');
    await picker.selectOption({ label: `${name} — ${role}` });
    const id = await picker.inputValue();
    await expect(page.locator('#workspace-role')).toContainText(`Your role: ${role}`);
    await page.getByRole('button', { name: 'Refresh access', exact: true }).click();
    await expect(picker).toHaveValue(id);
    await expect(page.getByLabel('Project datasets')).toContainText(`${name}.csv`);
    await expect(page.getByLabel('Project pipelines')).not.toContainText('Workspace A pipeline');
    await expect(
      page.getByRole('link', { name: 'Open development workspace', exact: true }),
    ).toHaveCount(0);
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: `Download report for ${name} pipeline` }).focus();
    await page.keyboard.press('Enter');
    expect((await download).suggestedFilename()).toMatch(/^pipeline-\d+-report.html$/);
    await page.goto('/model-development?project_id=' + id);
    await expect(page).toHaveURL(/\/home\?project_id=/);
    await expect(picker).toHaveValue(id);
    await expect(page.locator('#workspace-role')).toContainText(`Your role: ${role}`);
    const denied = await page.request.post(API_BASE_URL + 'pipeline/create/', {
      data: { name: 'forbidden', project_id: id },
      headers: {
        'X-CSRFToken': (await (await page.request.get(API_BASE_URL + 'auth/session/')).json())
          .csrf_token,
      },
    });
    expect(denied.status()).toBe(403);
    await page.screenshot({
      path: testInfo.outputPath(`workspace-${role}.png`),
      animations: 'disabled',
    });
    // The redirected home URL still names the read-only project. A manual
    // selection must remain the refresh preference instead of resetting to it.
    await picker.selectOption({ label: 'Workspace B — developer' });
    const changedId = await picker.inputValue();
    await page.getByRole('button', { name: 'Refresh access', exact: true }).click();
    await expect(picker).toHaveValue(changedId);
    await expect(page.getByLabel('Project datasets')).toContainText('Workspace B.csv');

    await page.getByRole('button', { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator('app-project-workspace')).toHaveCount(0);
  });
}

test('directory failure leaves no stale project records or development authority', async ({
  page,
}) => {
  await signIn(page);
  await page.getByLabel('Current project').selectOption({ label: 'Workspace A — developer' });
  await expect(page.getByLabel('Project datasets')).toContainText('Workspace A.csv');
  await page.route('**/api/projects/', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Fixture authority outage' }),
    }),
  );
  await page.getByRole('button', { name: 'Refresh access', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Retry to load');
  await expect(page.getByLabel('Project datasets')).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'Open development workspace', exact: true }),
  ).toHaveCount(0);
  await page.goto('/model-development');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('alert')).toContainText('Retry to load');
});
