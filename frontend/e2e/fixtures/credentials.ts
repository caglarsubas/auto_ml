/** Disposable test account supplied by the caller; no account is shipped. */
export const TEST_CREDENTIALS = {
  username: process.env['E2E_USER'] ?? '',
  password: process.env['E2E_PASSWORD'] ?? '',
};
export const BASE_URL = process.env['E2E_BASE_URL'] ?? 'http://localhost:4300';
export const API_BASE_URL = (process.env['E2E_API_BASE_URL'] ?? 'http://localhost:8001/api/').replace(/\/?$/, '/');

export function requireTestCredentials(): typeof TEST_CREDENTIALS {
  if (!TEST_CREDENTIALS.username || !TEST_CREDENTIALS.password) {
    throw new Error('Supply E2E_USER and E2E_PASSWORD for a disposable Django account.');
  }
  return TEST_CREDENTIALS;
}
