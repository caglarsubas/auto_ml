import { Page, expect } from '@playwright/test';
import { TEST_CREDENTIALS } from '../fixtures/credentials';

/**
 * Page object for the login screen and the shared "sign in" journey.
 *
 * Centralises the selectors and the success/failure assertions that were
 * previously duplicated in a `beforeEach` across ~10 spec files.
 */
export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('/login');
  }

  async fill(username: string, password: string): Promise<void> {
    await this.page.fill('#username', username);
    await this.page.fill('#password', password);
  }

  async submit(): Promise<void> {
    await this.page.click('button.login-button');
  }

  /** Log in with the configured test credentials and wait for /home. */
  async login(
    username: string = TEST_CREDENTIALS.username,
    password: string = TEST_CREDENTIALS.password,
  ): Promise<void> {
    await this.goto();
    await this.fill(username, password);
    await this.submit();
    await expect(this.page).toHaveURL(/\/home/, { timeout: 15_000 });
  }
}

/**
 * Convenience helper for specs that just need to be authenticated before the
 * real assertions. Mirrors the old inline `beforeEach` behaviour.
 */
export async function login(page: Page): Promise<void> {
  await new LoginPage(page).login();
}
