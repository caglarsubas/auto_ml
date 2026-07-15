# DeclarAI Frontend

Angular 18 single-page application for the DeclarAI AutoML platform. Generated
with the [Angular CLI](https://github.com/angular/angular-cli) and served on
port `4300` in the docker-compose stack.

## Development server

```bash
npm start        # ng serve (http://localhost:4200 locally, 4300 in Docker)
```

The app reloads automatically on source changes.

## Build

```bash
npm run build    # artifacts in dist/frontend
```

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
