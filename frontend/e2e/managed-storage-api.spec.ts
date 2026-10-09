import { randomUUID } from 'node:crypto';
import { test, expect } from './fixtures/session';
import { API_BASE_URL } from './fixtures/credentials';

test('real-session native table selectors reject external and traversing references', async ({
  authenticatedApi: api,
}) => {
  for (const endpoint of [
    'encoding/analyze/',
    'encoding/apply/',
    'preprocessing/datq_detail/',
    'preprocessing/datq_timeseries/',
    'modeling/start/',
    'modeling/feature-explainability/',
  ]) {
    for (const processed_file of ['/etc/passwd', '../outside.csv', '.private/secret.csv']) {
      const response = await api.post(endpoint, {
        data: { file_id: 1, processed_file, feature_name: 'x' },
      });
      expect(response.status()).toBe(400);
      expect((await response.json()).error_code).toBe('managed_storage_reference_invalid');
      expect(await response.text()).not.toContain('/etc/passwd');
    }
  }
  const card = await api.get('feature-card/1/get_feature_info/', {
    params: { column: 'x', file_override: '/etc/passwd' },
  });
  expect(card.status()).toBe(400);
  expect((await card.json()).error_code).toBe('managed_storage_reference_invalid');
});

test('real-session invalid and conflicting dataset IDs fail before execution', async ({
  authenticatedApi: api,
}) => {
  for (const file_id of [true, '01', '../escape', '9'.repeat(5000)]) {
    const response = await api.post('encoding/apply/', {
      data: { file_id, processed_file: 'data_files/missing.csv' },
    });
    expect(response.status()).toBe(400);
    expect((await response.json()).error_code).toBe('managed_storage_reference_invalid');
  }
  for (const query of ['file_id=2', 'file_id=1&file_id=1']) {
    expect((await api.get(`modeling/status/1/?${query}`)).status()).toBe(400);
  }
  expect(
    (
      await api.post('encoding/analyze/?file_id=2', {
        data: { file_id: 1, processed_file: 'data_files/missing.csv' },
      })
    ).status(),
  ).toBe(400);
});

test('real-session model overrides require a verified matching execution', async ({
  authenticatedApi: api,
}) => {
  const unverified = await api.post('modeling/feature-explainability/', {
    data: {
      file_id: 1,
      feature_name: 'x',
      model_path: 'models/unverified.json',
    },
  });
  expect(unverified.status()).toBe(409);
  expect((await unverified.json()).error_code).toBe('unverified_model_override');
  const mismatched = await api.post('modeling/feature-explainability/', {
    data: {
      file_id: 1,
      feature_name: 'x',
      execution_id: '00000000-0000-0000-0000-000000000001',
      model_path: 'execution_runs/00000000-0000-0000-0000-000000000002/models/model.json',
    },
  });
  expect(mismatched.status()).toBe(409);
  expect((await mismatched.json()).error_code).toBe('unverified_model_override');
});

test('real-session repeated uploads and encodings preserve earlier managed files', async ({
  authenticatedApi: api,
}) => {
  const identifiers: number[] = [];
  const versions: { id: number; file: string }[] = [];
  try {
    for (const value of [10, 100]) {
      const csv = `Value,Target,fixture_id\n${value},0,${randomUUID()}\n${value + 1},1,${randomUUID()}\n${value + 2},0,${randomUUID()}\n`;
      const response = await api.post('declaration/', {
        multipart: {
          file: { name: 'input.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) },
          column_separator: 'comma',
        },
      });
      expect(response.status()).toBe(201);
      const declaration = await response.json();
      identifiers.push(declaration.id);
      versions.push(declaration);
    }
    expect(versions[0].file).not.toBe(versions[1].file);
    const firstUrl = new URL(versions[0].file, API_BASE_URL).href;
    const original = await api.get(firstUrl);
    expect(original.status()).toBe(200);
    const originalBytes = await original.body();
    expect(originalBytes.toString()).toContain('10,0');
    const second = await api.get(new URL(versions[1].file, API_BASE_URL).href);
    expect(second.status()).toBe(200);
    expect((await second.body()).equals(originalBytes)).toBe(false);
    const processed_file = new URL(firstUrl).pathname.replace(/^\/media\//, '');
    const encoded: string[] = [];
    for (let index = 0; index < 2; index++) {
      const response = await api.post('encoding/apply/', {
        data: { file_id: identifiers[0], processed_file, plan: [] },
      });
      expect(response.status()).toBe(200);
      encoded.push((await response.json()).encoded_file as string);
    }
    expect(encoded[0]).not.toBe(encoded[1]);
    for (const path of encoded) {
      const table = await api.get(new URL(`/media/${path}`, API_BASE_URL).href);
      expect(table.status()).toBe(200);
      expect((await table.body()).equals(originalBytes)).toBe(true);
      const metadata = await api.get(
        new URL(`/media/${path.replace(/\.csv$/, '.meta.json')}`, API_BASE_URL).href,
      );
      expect(metadata.status()).toBe(200);
      expect(await metadata.json()).toEqual({ categorical_columns: [] });
    }
    expect((await (await api.get(firstUrl)).body()).equals(originalBytes)).toBe(true);
  } finally {
    for (const id of identifiers) await api.delete(`declaration/${id}/`);
  }
});
