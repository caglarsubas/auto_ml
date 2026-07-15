/**
 * Test credentials for E2E journeys.
 *
 * Never hard-code real credentials in specs. Values come from the environment
 * (set E2E_USER / E2E_PASSWORD, e.g. via CI secrets or a local .env) and fall
 * back to a conventional local dev account for convenience.
 */
export const TEST_CREDENTIALS = {
  username: process.env['E2E_USER'] ?? 'test@example.com',
  password: process.env['E2E_PASSWORD'] ?? 'changeme',
};

/** Base URL of the running frontend under test. */
export const BASE_URL = process.env['E2E_BASE_URL'] ?? 'http://localhost:4300';
