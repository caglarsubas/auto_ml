import { test as base, expect, APIRequestContext } from '@playwright/test';
import { API_BASE_URL, BASE_URL, requireTestCredentials } from './credentials';

export const test = base.extend<{ authenticatedApi: APIRequestContext }>({
  authenticatedApi: async ({ playwright }, use) => {
    const credentials = requireTestCredentials();
    const origin = new URL(BASE_URL).origin;
    const bootstrap = await playwright.request.newContext({ baseURL: API_BASE_URL });
    let authenticated: APIRequestContext | undefined;
    try {
      const session = await bootstrap.get('auth/session/');
      expect(session.status(), 'Session endpoint must be reachable').toBe(200);
      const csrf = (await session.json()).csrf_token;
      const login = await bootstrap.post('auth/login/', {
        data: credentials, headers: { 'X-CSRFToken': csrf, Origin: origin },
      });
      expect(login.status(), 'Disposable test account must authenticate').toBe(200);
      const current = await login.json();
      expect(current.authenticated).toBe(true);
      authenticated = await playwright.request.newContext({
        baseURL: API_BASE_URL, storageState: await bootstrap.storageState(),
        extraHTTPHeaders: { 'X-CSRFToken': current.csrf_token, Origin: origin },
      });
      await use(authenticated);
    } finally {
      if (authenticated) {
        try { await authenticated.post('auth/logout/'); }
        finally { await authenticated.dispose(); }
      }
      await bootstrap.dispose();
    }
  },
});
export { expect };
