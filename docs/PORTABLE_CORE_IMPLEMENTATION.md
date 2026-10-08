# P02 — Portable core installation and authenticated CI

Updated 8 October 2026. This packet follows [PR #91](https://github.com/caglarsubas/auto_ml/pull/91),
merged as `d91b453c`, and partially advances D06, D07 and D12. Milestone and
release acceptance remain open in the [roadmap ledger](product-roadmap.json).

The merged foundation could not pass backend CI because its mandatory
`prometa-sdk>=0.20.2` dependency was unavailable from the configured index.
The core now installs without that optional telemetry integration. The SDK
compatibility floor lives in `backend/requirements-observability.txt`; operators
supply an approved package separately. No private SDK source or credentials
are included. Wrapper unit tests explicitly mock their import/call boundary;
four checks of installed SDK behavior remain separate and skip in the core profile.
Invalid cache/retrieval metadata still fails when the SDK is absent.

CI now runs a bounded governed browser suite on every PR, main push, nightly
and manual run. Each job creates a non-admin account with a masked random
password in its disposable database. There is no shipped account or default
password. The seed helper requires an explicit disposable-installation flag
and refuses to modify existing users. Authentication failures, missing
credentials and unreachable endpoints fail the suite.

The checks exercise actual login, rotated CSRF tokens, session persistence,
logout revocation, blocked anonymous data/artifact access, blocked expert code,
purifier options, SFS/HPO request guards and pipeline creation/update/deletion.
The browser scenario also exercises keyboard login, an explicit regression
declaration, reload and local font loading. Built assets use a small loopback
preview server with deep-link fallback; it is a test helper.

Real session qualification exposed four handlers that read `request.body`
after CSRF processing had consumed its stream. HPO/SFS starts and pipeline
creation/update now use DRF's parsed `request.data`. Thirteen new backend cases
cover real session/CSRF JSON and multipart requests, malformed/non-object JSON
and pipeline persistence. The existing 44 foundation/session cases were also
missing from CI's marker selection; they now run in its unit scope.

The [qualification record](evidence/p02-qualification-2026-10-08.json) identifies
the exact executable source commit, resolved packages, commands, retained logs
and hashes. Local results:

| Check | Result |
| --- | --- |
| Stock Python 3.12 core Docker build, public requirements | Passed; optional SDK absent; `pip check` passed |
| Full CI-marked backend suite with Redis | 1,216 passed, 6 skipped; 60.03% coverage against the unchanged 50% gate |
| Governed Chromium and authenticated API suite | 17 passed, no skips |
| Cached optional installed-SDK compatibility profile | 166 passed, 1 local-environment skip |
| Backend lint, migration drift, browser TypeScript, workflow YAML, roadmap projection | Passed |
| Frontend production build and lint | Passed; existing size/style/CommonJS and 155 lint warnings remain |

Four backend skips require the optional installed SDK; the other two require
a live model engine and a local `.env`. The six skips pass the existing maximum
of 15. The broader legacy Playwright suite remains available for separate
qualification. P02 does not claim its journeys passed. Frontend unit source is
unchanged from P01; CI independently runs the complete unit suite.

Local backend execution used Linux/ARM64. The browser used built assets and a
disposable API/Redis installation with telemetry disabled, provider keys blank
and no live model calls. Optional SDK checks used an existing SDK-installed
image, rather than a fresh installation of the optional profile. Original
checkout modifications were preserved in a separate managed worktree.

GitHub CI is a separate observation from these local results. This packet does
not qualify a production web server, TLS, PostgreSQL, durable workers, locked
offline dependencies, upgrades or restore. Project-level developer/reviewer
permissions, MCP identity, retention/egress controls and full accessibility
remain open. Expert Python still fails with `expert_isolation_unavailable`
until D08's Linux isolation is implemented and qualified. Independent model
review/reproduction and design-partner acceptance also remain required.
