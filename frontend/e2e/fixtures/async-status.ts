import { expect, APIRequestContext, TestInfo } from '@playwright/test';

/** Retain the actual async failure before fixture cleanup or a test retry. */
export async function expectAsyncStatus(
  api: APIRequestContext,
  testInfo: TestInfo,
  endpoint: string,
  expected: string,
  context: { operation: string; file_id: number; execution_id?: string; job_id?: string },
  field: 'status' | 'state' = 'status',
) {
  let latest: Record<string, unknown> = {};
  let responseStatus: number | undefined;
  try {
    await expect
      .poll(
        async () => {
          const response = await api.get(endpoint);
          responseStatus = response.status();
          const body = await response.json();
          latest = Object.fromEntries(
            ['status', 'state', 'error', 'message', 'failure', 'duration_seconds'].map((key) => [
              key,
              body[key],
            ]),
          );
          return body[field];
        },
        { timeout: 30_000 },
      )
      .toBe(expected);
  } catch (error) {
    const diagnostic = JSON.stringify(
      { ...context, expected, response_status: responseStatus, observed: latest },
      null,
      2,
    );
    try {
      await testInfo.attach('async-operation-failure', {
        body: Buffer.from(diagnostic),
        contentType: 'application/json',
      });
    } catch {
      // A reporter/storage fault must not replace the operation's assertion.
    }
    if (error instanceof Error) error.message += `\nAsync failure diagnostic:\n${diagnostic}`;
    throw error;
  }
}
