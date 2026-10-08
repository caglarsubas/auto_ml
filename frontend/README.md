# DeclarAI Frontend

Angular 22 single-page application for the DeclarAI AutoML platform. Use Node 24
and `npm ci` to install the locked dependencies. Generated
with the [Angular CLI](https://github.com/angular/angular-cli) and served on
port `4300` in the docker-compose stack.

## Development server

```bash
npm start        # ng serve (http://localhost:4200 locally, 4300 in Docker)
```

The app reloads automatically on source changes.

Sign-in uses Django sessions and CSRF protection. Create an account through the
backend administration command; browser-local credentials no longer grant
access. Configure the API's `DECLARAI_ALLOWED_ORIGINS` for the frontend origin.
The default frontend build uses client rendering so protected routes recheck
the browser session. Retained SSR sources are not part of the supported build.

## Build

```bash
npm run build    # artifacts in dist/frontend
npm run serve:preview # local preview of the production configuration
```

The Compose frontend remains a development server. Built assets, TLS and an
offline installation/recovery profile are still required by D07 before private
release. See [foundation implementation](../docs/FOUNDATION_IMPLEMENTATION.md)
for the current qualification boundary.

Typography and Material Icons are bundled under `src/assets/fonts/` with their
licenses and source hashes. Frontend production builds require no font CDN.

## Testing

See the repository [testing guide](../docs/testing.md) for the full strategy.

### Unit tests (Karma + Jasmine)

```bash
npm test         # interactive (watch mode)
npm run test:ci  # headless Chrome + coverage (used by CI)
```

Karma is configured in `karma.conf.js` with a `ChromeHeadlessCI` launcher and
coverage thresholds. Coverage reports land in `coverage/`.

### End-to-end tests (Playwright)

```bash
npm run test:e2e         # headless
npm run test:e2e:headed  # headed
```

- Config: `playwright.config.ts` (`baseURL` from `E2E_BASE_URL`, default
  `http://localhost:4300`). The stack must be running, or set
  `E2E_WEB_SERVER_CMD` to let Playwright start it.
- Credentials come from `E2E_USER` / `E2E_PASSWORD` — never hard-code them
  (see `e2e/fixtures/credentials.ts`).
- Shared login lives in `e2e/pages/login.page.ts`.

## Linting & formatting

```bash
npm run lint          # ESLint (angular-eslint)
npm run format        # Prettier write
npm run format:check  # Prettier check
```

## Further help

Run `ng help` or see the
[Angular CLI reference](https://angular.dev/tools/cli).
