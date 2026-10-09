import { randomUUID } from 'node:crypto';
import { APIRequestContext, expect } from '@playwright/test';

/** A project-owned dataset without training artifacts; removed by the caller. */
export async function uploadUntrainedDataset(api: APIRequestContext): Promise<{ id: number; file: string }> {
  const response = await api.post('declaration/', {
    multipart: {
      file: {
        name: 'untrained.csv', mimeType: 'text/csv',
        buffer: Buffer.from(`x,target,fixture\n1,0,${randomUUID()}\n2,1,${randomUUID()}\n3,0,${randomUUID()}\n`),
      },
      column_separator: 'comma',
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}
