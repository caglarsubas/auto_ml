# Testing Strategy

This document describes how DeclarAI is tested across the backend (Django + DRF)
and frontend (Angular 18), how to run the suites locally, and how CI enforces
them.

## Overview

| Layer | Framework | Location | Count |
|-------|-----------|----------|------:|
| Backend | pytest + pytest-django | `backend/tests/` | ~1009 |
| Frontend unit | Karma + Jasmine | `frontend/src/app/**/*.spec.ts` | ~433 |
| Frontend E2E | Playwright | `frontend/e2e/*.spec.ts` | ~72 |

## Backend

### Layout

Backend tests live under `backend/tests/`:

- `tests/unit/` — unit tests split by domain (`test_declaration.py`,
  `test_encoding.py`, `test_modeling.py`, `test_hyperparam.py`,
  `test_preprocessing.py`, `test_feature_card.py`, `test_common.py`,
  `test_data_quality.py`, `test_sfs_utils.py`, `test_report_generator.py`,
  `test_mcp_auth_and_commands.py`, and `test_ai_*` for the AI assistant).
  Shared helpers live in `tests/unit/_shared.py`; the shared engine-models
  fixture in `tests/unit/conftest.py`.
- `tests/test_functional.py` — single-endpoint API contracts (DRF `APIClient`).
- `tests/test_integration.py` — multi-step workflows.
- `tests/test_regression.py` — previously-fixed bugs that must not recur.
- `tests/test_uat.py` — end-to-end user acceptance journeys.
- `tests/test_mcp_server.py`, `tests/test_prometa_bundle_runner.py` — MCP.

Root fixtures are in `backend/conftest.py`; configuration in
`backend/pytest.ini` (strict markers, 120s per-test timeout, seeded RNG).

### Markers

| Marker | Scope | Count |
|--------|-------|------:|
| `unit` | Isolated component tests | ~832 |
| `functional` | API endpoint behaviour | ~118 |
| `regression` | Previously-fixed bugs | ~34 |
| `integration` | Multi-component workflows | ~16 |
| `uat` | End-to-end user scenarios | ~9 |

### Running

```bash
# Native (no Docker) — requires backend requirements installed
cd backend && python -m pytest                 # all
python -m pytest -m unit                        # one marker
python -m pytest -m "unit or regression"        # quick subset

# Unified runner (auto-detects Docker vs native; --mode overrides)
./run_tests.sh                 # all categories
./run_tests.sh --quick         # unit + regression
./run_tests.sh unit            # single category
./run_tests.sh --mode native   # force native pytest
./run_tests.sh --mode docker   # force docker exec (container auto-ml-backend-1)

# With coverage
cd backend && python -m pytest --cov --cov-report=term-missing
```

### External dependencies

- **Redis**: ~40 cache/telemetry tests need Redis (`REDIS_URL`, default
  `redis://localhost:6379/0`). Without it they skip; CI provides a Redis
  service so they run. A skip-budget check (`.github/scripts/check_skip_budget.py`)
  fails CI if too many tests skip.
- **SQLite**: the Django test DB. Tests needing the ORM use
  `@pytest.mark.django_db`.
- **Filesystem**: a temporary `MEDIA_ROOT` is provided via the `_use_tmp_media`
  fixture.

### Important gotcha

CSV uploads in API tests must send `column_separator: 'comma'` — the backend
defaults to semicolon.

## Frontend

### Unit tests (Karma/Jasmine)

```bash
cd frontend
npm test               # interactive (watch)
npm run test:ci        # headless Chrome + coverage (used by CI)
```

Karma is configured in `frontend/karma.conf.js` with a `ChromeHeadlessCI`
launcher and coverage thresholds (calibrated just below current coverage to
guard against regression). Coverage output lands in `frontend/coverage/`.

### E2E tests (Playwright)

```bash
cd frontend
npm run test:e2e            # headless
npm run test:e2e:headed     # headed
```

- Config: `frontend/playwright.config.ts` (`baseURL` from `E2E_BASE_URL`,
  default `http://localhost:4300`).
- Credentials come from `E2E_USER` / `E2E_PASSWORD` (see
  `e2e/fixtures/credentials.ts`); never hard-code them.
- Shared login lives in `e2e/pages/login.page.ts`.
- E2E assumes the stack is already running (docker compose) unless
  `E2E_WEB_SERVER_CMD` is set to let Playwright start it.

## Linting / static analysis

```bash
# Backend
cd backend && ruff check .

# Frontend
cd frontend && npm run lint          # ESLint (angular-eslint)
cd frontend && npm run format:check  # Prettier
cd frontend && npm run format        # Prettier write
```

Both linters are adopted with a baseline on the legacy tree (green today,
tighten over time). Ruff still enforces `F821` (undefined-name), which already
caught real bugs.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`, nightly, and
manual dispatch:

- **backend-tests**: pytest with a Redis service. PRs run `unit or regression`
  for fast feedback; `main`/nightly run the full marker set with
  `--cov-fail-under=50` and the skip-budget gate.
- **frontend-unit**: `npm run test:ci` (headless Karma + coverage).
- **backend-lint**: `ruff check`.
- **frontend-lint**: ESLint (blocking) + Prettier (advisory).
- **frontend-e2e**: Playwright against a docker-compose stack (main/nightly/
  manual only, since it needs the full stack and secrets).

## Pre-commit hooks

`.pre-commit-config.yaml` runs formatting/lint on commit and the quick backend
suite on push:

```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
```
