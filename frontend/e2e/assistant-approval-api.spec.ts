import { randomUUID } from 'node:crypto';
import { APIRequestContext } from '@playwright/test';
import { test, expect } from './fixtures/session';

async function upload(api: APIRequestContext): Promise<number> {
  const response = await api.post('declaration/', {
    multipart: {
      file: {
        name: 'approval.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(
          `x,target,fixture\n1,0,${randomUUID()}\n2,1,${randomUUID()}\n3,0,${randomUUID()}\n`,
        ),
      },
      column_separator: 'comma',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).id;
}

function action(file_id: number) {
  return {
    file_id,
    action_type: 'update_metadata',
    source: 'panel',
    payload: {
      updates: [
        { column: 'x', field: 'Feature_Description', value: 'Approved browser description' },
      ],
    },
  };
}

function selector(record: { approval_id: string; proposal_sha256: string }) {
  return { approval_id: record.approval_id, proposal_sha256: record.proposal_sha256 };
}

async function description(api: APIRequestContext, fileId: number): Promise<string> {
  const response = await api.get(`declaration/${fileId}/data_dictionary/`);
  expect(response.status()).toBe(200);
  return (await response.json()).find((item: any) => item.Feature_Name === 'x').Feature_Description;
}

test('real session requires exact approval and returns retained replay receipts', async ({
  authenticatedApi: api,
}) => {
  const fileId = await upload(api);
  try {
    const request = action(fileId);
    const before = await description(api, fileId);
    expect((await api.post('ai-assistant/execute-action/', { data: request })).status()).toBe(403);
    const prepared = await api.post('ai-assistant/prepare-action/', { data: request });
    expect(prepared.status()).toBe(200);
    const record = await prepared.json();
    expect(record.budget.downstream_job_authority).toBe(false);
    expect(await description(api, fileId)).toBe(before);
    expect(
      (
        await api.post('ai-assistant/execute-action/', {
          data: { ...request, ...selector(record) },
        })
      ).status(),
    ).toBe(409);
    expect(
      (await api.post('ai-assistant/approve-action/', { data: selector(record) })).status(),
    ).toBe(200);
    const result = await api.post('ai-assistant/execute-action/', {
      data: { ...request, ...selector(record) },
    });
    expect(result.status()).toBe(200);
    expect((await result.json()).approval_receipt.state).toBe('completed');
    expect(await description(api, fileId)).toBe('Approved browser description');
    const repeated = await api.post('ai-assistant/execute-action/', {
      data: { ...request, ...selector(record) },
    });
    expect(repeated.status()).toBe(200);
    expect((await repeated.json()).approval_receipt.replayed_receipt).toBe(true);
    const receipt = await api.get(`ai-assistant/action-approval/${record.approval_id}/`, {
      params: { proposal_sha256: record.proposal_sha256 },
    });
    expect(receipt.status()).toBe(200);
    expect((await receipt.json()).downstream_job_authority).toBe(false);
  } finally {
    expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
  }
});

test('real session rejects altered and cancelled proposals and expert Python', async ({
  authenticatedApi: api,
}) => {
  const fileId = await upload(api);
  try {
    const request = action(fileId);
    const prepared = await api.post('ai-assistant/prepare-action/', { data: request });
    expect(prepared.status()).toBe(200);
    const record = await prepared.json();
    expect(
      (await api.post('ai-assistant/approve-action/', { data: selector(record) })).status(),
    ).toBe(200);
    const altered = await api.post('ai-assistant/execute-action/', {
      data: { ...request, payload: { updates: [] }, ...selector(record) },
    });
    expect(altered.status()).toBe(409);
    expect((await altered.json()).error_code).toBe('action_approval_mismatch');
    expect(
      (await api.post('ai-assistant/cancel-action/', { data: selector(record) })).status(),
    ).toBe(200);
    expect(
      (
        await api.post('ai-assistant/execute-action/', {
          data: { ...request, ...selector(record) },
        })
      ).status(),
    ).toBe(409);
    for (const endpoint of ['prepare-action', 'execute-action']) {
      const code = await api.post(`ai-assistant/${endpoint}/`, {
        data: {
          file_id: fileId,
          action_type: 'execute_code',
          payload: { code: "df['x'] = 1" },
          ...selector(record),
        },
      });
      expect(code.status()).toBe(400);
      expect((await code.json()).error_code).toBe('expert_isolation_unavailable');
    }
    expect(await description(api, fileId)).not.toBe('Approved browser description');
  } finally {
    expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
  }
});

test('real session makes a changed recorded pipeline stale before dispatch', async ({
  authenticatedApi: api,
}) => {
  const fileId = await upload(api);
  let pipelineId: number | undefined;
  try {
    const request = action(fileId);
    const prepared = await api.post('ai-assistant/prepare-action/', { data: request });
    expect(prepared.status()).toBe(200);
    const record = await prepared.json();
    expect(
      (await api.post('ai-assistant/approve-action/', { data: selector(record) })).status(),
    ).toBe(200);
    const pipeline = await api.post('pipeline/create/', {
      data: { name: `changed-${fileId}`, file_id: fileId },
    });
    expect(pipeline.status()).toBe(201);
    pipelineId = (await pipeline.json()).id;
    const stale = await api.post('ai-assistant/execute-action/', {
      data: { ...request, ...selector(record) },
    });
    expect(stale.status()).toBe(409);
    expect((await stale.json()).error_code).toBe('action_approval_stale');
    expect(await description(api, fileId)).not.toBe('Approved browser description');
  } finally {
    if (pipelineId) expect((await api.delete(`pipeline/${pipelineId}/`)).status()).toBe(200);
    expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
  }
});

test('keyboard review confirms a synthetic proposal through real authority endpoints', async ({
  authenticatedApi: api,
  page,
}, testInfo) => {
  const fileId = await upload(api);
  const runName = `assistant-review-${fileId}`;
  let pipelineId: number | undefined;
  try {
    const pipeline = await api.post('pipeline/create/', {
      data: {
        name: runName,
        file_id: fileId,
        current_step: 'declaration',
        state: { file_id: fileId, pipeline_type: 'boosting', flags: { is_started: true } },
      },
    });
    expect(pipeline.status()).toBe(201);
    pipelineId = (await pipeline.json()).id;
    // Proposal generation is synthetic; every authority and mutation endpoint is real.
    await page.route('**/api/ai-assistant/chat/', async (route) => {
      await route.fulfill({
        contentType: 'application/x-ndjson',
        body:
          JSON.stringify({
            type: 'result',
            data: {
              message: 'Please review this description update.',
              actions: [{ type: 'update_metadata', payload: action(fileId).payload }],
            },
          }) + '\n',
      });
    });
    await page.context().addCookies((await api.storageState()).cookies);
    await page.goto('/model-development');
    await page.getByRole('button', { name: /Saved Pipelines/ }).click();
    await page
      .getByTitle(runName, { exact: true })
      .locator('..')
      .locator('..')
      .getByRole('button', { name: 'Load', exact: true })
      .click();
    const panel = page.locator('app-ai-chat-panel');
    if (!(await panel.locator('.chat-input').isVisible()))
      await page.getByTitle('Toggle AI Assistant', { exact: true }).click();
    await panel.locator('.chat-input').fill('Suggest a description update');
    await panel.locator('.chat-input').press('Enter');
    const review = panel.getByRole('button', { name: 'Review action', exact: true });
    await review.focus();
    await review.press('Enter');
    const proposal = panel.getByRole('region', { name: 'Prepared assistant action' });
    await expect(proposal).toContainText('Approved browser description');
    await expect(proposal).toContainText('One typed dispatch');
    expect(await description(api, fileId)).not.toBe('Approved browser description');
    await proposal.screenshot({ path: testInfo.outputPath('assistant-action-review.png') });
    const confirm = proposal.getByRole('button', { name: 'Approve this action', exact: true });
    await confirm.focus();
    await confirm.press('Enter');
    await expect(
      panel.locator('.action-applied-badge').filter({ hasText: 'Dispatched' }),
    ).toBeVisible();
    const receipt = panel.getByText('Action dispatch receipt', { exact: true });
    await receipt.focus();
    await receipt.press('Space');
    await expect(receipt.locator('..')).toHaveAttribute('open', '');
    await expect(receipt.locator('..')).toContainText('completed');
    expect(await description(api, fileId)).toBe('Approved browser description');
    await panel.screenshot({ path: testInfo.outputPath('assistant-action-receipt.png') });
  } finally {
    if (pipelineId) expect((await api.delete(`pipeline/${pipelineId}/`)).status()).toBe(200);
    expect((await api.delete(`declaration/${fileId}/`)).status()).toBe(204);
  }
});
