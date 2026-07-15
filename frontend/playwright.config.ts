import { defineConfig, devices } from '@playwright/test';
import { BASE_URL } from './e2e/fixtures/credentials';

// Optionally let Playwright start the app itself so E2E is a single command.
// Set E2E_WEB_SERVER_CMD (e.g. "npm run start" or a docker compose up wrapper)
// to enable; otherwise Playwright assumes the stack is already running at
// BASE_URL (the default when a docker-compose stack is up).
const webServerCommand = process.env['E2E_WEB_SERVER_CMD'];

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env['CI'],
  retries: process.env['CI'] ? 2 : 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  ...(webServerCommand
    ? {
        webServer: {
          command: webServerCommand,
          url: BASE_URL,
          reuseExistingServer: !process.env['CI'],
          timeout: 120_000,
        },
      }
    : {}),
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
