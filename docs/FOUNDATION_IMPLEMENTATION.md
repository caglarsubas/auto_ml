# Governed foundation implementation

Updated 7 October 2026. Branch: `codex/governed-foundation`; baseline: `dac05741`.

The approved D01–D17 roadmap is adopted in [the ledger](product-roadmap.json)
and [its generated projection](PRODUCT_DEVELOPMENT_ROADMAP.md). This packet
implements and verifies a substantial execution, scoring, identity and
framework foundation. **It does not complete M1–M3 or qualify a governed
release.** Existing local changes were preserved; no production deployment,
merge, customer acceptance or design-partner result is claimed.

## Implemented behavior

| Area | Current behavior | Qualification boundary |
| --- | --- | --- |
| D01 prediction contract | Training requires explicit classification/regression/anomaly, target, positive label for binary outcomes, population, horizon, maturity, feature availability and compatible objective. The contract and its hash travel with the model. UI/assistant suggestions preserve accepted task semantics. | Business facts remain declarations requiring review. Unsupported task/model/encoding/objective combinations fail explicitly. Custom objectives remain D11 work. |
| D02 validation | Shared folds preserve chronology, entity disjointness and outcome-window purging. Initial booster CV, current booster SFS and HPO fit encoders and numeric imputation on their fold's training rows. Membership and fit provenance are recorded. Invalid stored splits fail without shuffled fallback. | Inputs are still processed datasets. Learned upstream purifier decisions need fold-local replay. Legacy helper paths remain explicitly unqualified. Temporal/grouped target encoding and multiclass target encoding are blocked. |
| D03 final assessment | Development training data excludes final holdout inputs/outcomes. Assessment records an attributable access receipt before opening final outcomes. Binary operating-point selection uses development validation; final binary assessment reports a single operating point. New diagnostics use verified development rows. | All current assessments are exploratory. Confirmatory protocols, complete holdout-reuse lineage and independent review remain open. |
| D04 evidence and scoring | UUID execution snapshots, separate assessment receipts and unique bundles preserve prior versions. Integrity is verified before trusted native loading. Candidate adoption refits a model, preserves its parent and rejects stale parents. Fitted encoding/imputation replay, calibration failure blocking and fixed anomaly score normalization improve scoring parity. | Hashes detect alteration relative to a manifest; they are not signatures or authorization. Scoring accepts the declared **processed, unencoded** schema. Upstream purifier replay is not included. Some file-ID compatibility projections and stage results remain mutable. |
| D05 diagnostics | Numeric VIF excludes categorical types and recorded arbitrary category codes. Combined importance is labelled a ranking heuristic. Sequential patterns use associational terminology. Anomaly assessment reports ranking metrics without probability/calibration claims or holdout threshold sweeps. | Grouped categorical diagnostics, comparison uncertainty and class-specific multiclass SHAP remain open. Unsupported interactive PDP paths return a blocked-state explanation. |
| D06 identity | Django server sessions replace hard-coded browser credentials. REST endpoints and artifact downloads require authentication; unsafe requests require CSRF. Browser route guards recheck sessions, including reload; assistant streaming sends session/CSRF credentials. Native pickle/code downloads are blocked. | Project authorization, developer/reviewer/admin separation, MCP service identity, complete audit/retention and controlled egress remain open. Current authenticated users share the installation's datasets. Login throttling uses the configured cache and is not qualified for distributed workers. |
| D07 framework baseline | Django 5.2 LTS / DRF 3.16; Angular/Material 22, TypeScript 6 and Node 24. Official Angular migrations preserve existing components, update control flow and use client rendering for protected browser sessions. Dependency locking, vendored SheetJS and bundled typography/icons support repeatable frontend builds without a font CDN. | SQLite, synchronous training, local thread state and development servers remain. PostgreSQL, durable Celery/Redis jobs, production serving/TLS, complete offline packaging and recovery drills are not delivered. |
| D08 expert-code boundary | In-process generated/user Python execution was removed. Browser/MCP `execute_code` requests fail with `expert_isolation_unavailable` before loading data. | **Expert Python is unavailable.** A qualified dedicated Linux gVisor service, exact approvals, transform/scorer replay and hostile-code tests are still mandatory for the first governed release. The current gate is not a substitute for that service. |
| D09/D12/D15 foundations | Environment manifests and independent assessment artifacts; clearer declaration and package states; immutable batch-scoring output IDs. Packaging distinguishes review/scoring handoff from production-use approval. | No independent-review records/reproduction runner, complete accessible reviewer workflow, scheduled outcome monitoring or alert lifecycle is claimed. |

The booster adapters preserve `rows × classes` probabilities for multiclass
classification. Binary/regression outputs remain one score per row. XGBoost
retains zero-based best iteration, including iteration zero, across replay and
does not silently switch to all trees when a requested iteration fails.
CatBoost multiclass uses Bernoulli sampling for the shared subsample parameter,
consistent with its [bootstrap configuration](https://catboost.ai/docs/en/concepts/algorithm-main-stages_bootstrap-options).
Multiclass assessment defines weighted one-vs-rest ROC-AUC and weighted F1;
unsupported objectives, calibration, selection/tuning and class-specific
explanations are disclosed or blocked.

## Migration and use

1. Back up the database and the complete artifact tree together before upgrading.
2. Install backend requirements and apply `python backend/manage.py migrate`
   from the repository root. Compose's existing entrypoint performs migration.
   Migration `modeling/0002_holdoutaccess.py` adds receipts; it does not rewrite
   historical models, datasets or pipeline state.
3. Create a Django administrator interactively with
   `docker compose exec backend python backend/manage.py createsuperuser`.
   Existing users can sign in with their Django credentials. Old browser-local
   credentials no longer authenticate. No initial password is shipped.
4. Use Node 24 and `cd frontend && npm ci`. The official SheetJS archive is
   committed under `frontend/vendor/` with source, hash and license notes.
   The container stages it before dependency installation.
5. For another frontend origin, set `DECLARAI_ALLOWED_ORIGINS` to the exact
   comma-separated browser origins. Session and CSRF origins must agree.
   Current defaults cover local development endpoints. Production requires
   TLS and secure-cookie qualification.
6. Existing artifacts remain inspectable under legacy paths. Continuing a
   project trains a new immutable execution with an accepted declaration.
   Missing historical provenance remains unknown. A legacy metadata-only
   champion cannot become a new governed package without new execution evidence.
7. Supply processed, unencoded feature inputs to new scoring bundles. Frozen
   encoders and imputation replay inside the bundle; missing required inputs or
   required calibration fail. Select exact `execution_id`/`bundle_id` where
   supported to reproduce a historical version.

New requests must provide the accepted `business_understanding` declaration.
Classification no longer becomes regression because a target has many values;
regression no longer becomes classification because it has few values. Anomaly
ranking is a separate declared task. Label maturity is required and missing
outcomes are rejected rather than converted to negative labels.

## Verification

The [qualification evidence](evidence/foundation-2026-10-07.json) records local
commands, environments, test results and source hashes. It is local execution
evidence, not CI, release, penetration-test or customer-acceptance evidence.

Latest results: **1,033 backend tests; 517 Angular tests; one persisted browser
workflow**, all passed. Production frontend compilation passed on the host and
in a clean Linux container with networking disabled; migration drift and ledger
projection checks passed. The [declaration screenshot](evidence/foundation-business-declaration.png)
captures the bounded browser check, not a complete model-review acceptance run.

- Backend behavioral tests include real logit/XGBoost training, 65-class
  classification and two-value regression through assessment and scoring,
  unseen/missing categories, reversed labels, group/time/window constraints,
  fold-local imputation, candidate refitting, version preservation, assessment
  tampering, calibration failure and batch/order parity.
- Real HTTP boundary tests use production session permissions and CSRF
  middleware. Isolated scientific-handler unit tests use a **test-only**
  permission fixture; they do not prove access control. No runtime bypass exists.
- Angular tests exercise accepted declarations, server authentication and
  credential boundaries. A browser smoke check exercised actual Django login,
  reload/session restoration, keyboard task selection, positive label,
  maturity/availability controls, logout and access revocation without runtime
  errors. It did not qualify screen-reader use or the entire reviewer workflow.
  The persisted `frontend/e2e/governed-session.spec.ts` also blocks external
  browser requests while checking all four bundled font/icon families. Run it
  against a disposable account with `E2E_USER` / `E2E_PASSWORD`; no account
  credential is embedded in the test.
- Production frontend builds retain the existing size budgets. Initial assets
  exceed the 6 MB warning budget while remaining below the 8 MB error budget;
  component styles and CommonJS dependencies also produce warnings.
- The clean frontend image installs the locked dependencies, and production
  builds are checked with container networking disabled. This proves frontend
  asset compilation without public-network access after dependency staging;
  it does not qualify a complete offline installation or backend deployment.
- `npm audit --omit=dev` reported zero known runtime advisories. The complete
  audit reported 11 high advisories in development tooling, including the
  deprecated Webpack/Karma chain. No forced framework downgrade was applied.
  Backend dependency security and deployment threat-model qualification remain
  separate open checks.

## Required next implementation

Complete M1 with raw/versioned preprocessing specifications and fold-local
purifier replay, consistent objective semantics in every early-stopping and
selection path, immutable stage receipts and broader concurrency/legacy tests.
Then close M2 with project roles/audit/egress, PostgreSQL and durable jobs,
Linux isolation and reproducible private installation/restore. These
prerequisites precede M3 independent reproduction, R3 paired comparisons, R1
grouped alternatives and expert scorers. Credit policy, mature-outcome
monitoring, interoperability and bounded model-family research remain in the
adopted dependency sequence.

No milestone gate or broader rollout/value gate is closed. Two real partner
workflows and the proposed effort/defect acceptance target still require
customer evidence.
