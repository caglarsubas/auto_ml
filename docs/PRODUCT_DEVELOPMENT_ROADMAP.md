# DeclarAI product development roadmap

Updated 2026-10-08. Generated from `product-roadmap.json`; edit the ledger and run `python3 scripts/render_product_roadmap.py`.

Build a developer-first platform where business declarations govern model execution and every model carries reproducible evidence for independent review. Credit risk is the first use case; the classification/regression core remains reusable.

## Release direction

- On-premise/private cloud, initially one customer organization per installation.
- Distinct developer and independent-reviewer roles; jurisdiction-neutral, versioned customer policies.
- First governed release includes typed AI actions AND sandboxed expert Python.
- Model development, review, export and batch-scoring handoff; production decision use is tracked separately.
- Primary success measure: less development/reproduction/review effort without increased validation defects.

Outcome status is separate from packet evidence. Implemented, tested, released, and customer accepted are distinct states. No dates or capacity estimates are commitments.

## Implementation evidence

Packet checks do not close the acceptance criteria of a roadmap outcome or milestone.

### P01 — Governed execution and identity foundation

**Packet status:** tested. **Mapped outcomes:** D01, D02, D03, D04, D05, D06, D07, D08, D09, D12, D15.

Local native-execution, assessment/scoring, identity and framework foundation. This is partial delivery against the listed outcomes; no milestone or release gate is closed.

**Evidence:** [Implementation record](FOUNDATION_IMPLEMENTATION.md); [Qualification commands and source hashes](evidence/foundation-2026-10-07.json)

**Remaining:** Fold-local purifier replay, complete immutable stage/job contracts, project roles and egress, durable Linux deployment, qualified expert isolation and M3 review/reproduction are still required.

### P02 — Portable core installation and authenticated CI

**Packet status:** in_progress. **Mapped outcomes:** D06, D07, D12.

Make the core backend independent of the optional private telemetry SDK; exercise real session/CSRF browser and API checks against clean CI installations. Preserve optional SDK support without publishing private source.

**Evidence:** Qualification pending.

**Remaining:** Full backend locking/offline supply, production PostgreSQL/jobs/TLS and recovery, project authorization, expert isolation and remaining M1–M3 gates remain open.

**Release qualification:** open. Design-partner acceptance and value gates: not_performed / not_performed.

## M1 — Scientifically reliable execution

Correctness and evidence foundations precede feature expansion.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D01 | Executable prediction contract | in_progress | None | Backend/ML |
| D02 | Shared validation and fold-local preprocessing | in_progress | D01 | Backend/ML |
| D03 | Protected final assessment | in_progress | D01, D02 | Backend/ML |
| D04 | Immutable runs and reliable scoring | in_progress | D01 | Backend/ML |
| D05 | Trustworthy diagnostics | in_progress | D01 | Backend/ML |

### D01 Executable prediction contract

Govern accepted task, target, positive class, population, feature availability, horizon, maturity, and objective from a versioned declaration. Inference proposes and cannot override accepted values.

**Acceptance:** UI, assistant, training, evaluation, and scoring agree; contradictory or unsupported configurations fail with actionable errors.

**Source mapping:** Claude CC-2/RM-1; GPT P01/FIX-01; Gemini C1.

**Progress:** Explicit task/target/positive-label/objective contract is frozen with native runs and carried through assessment/scoring. UI and assistant preserve accepted task; binary, 65-class and low-cardinality regression behavior has local regression coverage. Complete objective/early-stopping consistency and unsupported-channel handling remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D02 Shared validation and fold-local preprocessing

Preserve time, entity, and outcome-window constraints through early stopping, encoding, selection, tuning, and calibration. Fit learned operations within their training partitions.

**Acceptance:** Export fold membership and fit provenance; no prohibited overlap or silent shuffled fallback.

**Source mapping:** Claude CC-1/CC-5; GPT P02/P03; Gemini C2/C3.

**Progress:** Strict time/entity/outcome-window partitions and shared current booster CV/SFS/HPO folds record memberships; fold-local encoding/imputation is implemented. Upstream learned purifier replay and legacy paths remain unqualified. Constrained target encoding is blocked.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D03 Protected final assessment

Separate development, calibration, and threshold choice from final holdout assessment. Record access and distinguish exploratory and confirmatory evidence.

**Acceptance:** Development cannot inspect final outcomes; changed candidates cannot inherit confirmatory status after holdout inspection.

**Source mapping:** Claude CC-6; GPT P03; Gemini C3.

**Progress:** Development artifacts exclude final outcomes; explicit assessment records attributable holdout access. Binary thresholds use development labels, and anomaly assessment has no holdout threshold search. Evidence is always exploratory; confirmatory/reuse protocols remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D04 Immutable runs and reliable scoring

Version dataset, contract, transforms, models, evaluations and bundles by run. Preserve older iterations; fail explicitly on required-calibration failure and make anomaly scores batch invariant.

**Acceptance:** Iteration N+1 cannot overwrite N; evaluated and bundled scores match across row ordering and batch sizes within declared tolerances.

**Source mapping:** Claude CC-7/RM-7; GPT P06; Repository artifact and scoring inspection.

**Progress:** Immutable native executions, assessment receipts, candidate refits, unique bundles/batch outputs and hash verification are implemented. Fitted encoding/calibration replay, multiclass matrices, XGBoost iteration-zero replay and anomaly batch invariance have regression coverage. Upstream transforms, all stage receipts and concurrency/recovery qualification remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D05 Trustworthy diagnostics

Correct categorical collinearity treatment, describe combined importance as a heuristic, and use associational terminology for sequential pattern detection.

**Acceptance:** Diagnostics are invariant to arbitrary category-code permutations; uncertainty and limitations accompany comparisons.

**Source mapping:** Claude CC-9; GPT FIX-04; Gemini C4.

**Progress:** Categorical codes no longer enter numeric VIF; combined importance is a ranking heuristic, sequential patterns are associational, and anomaly metrics are ranking-only. Unsupported multiclass SHAP/PDP is disclosed/blocked. Grouped diagnostics and paired-comparison uncertainty remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

**Milestone gate:** Representative supported workflows pass cross-stage correctness tests; historical evidence remains inspectable and honestly qualified.

## M2 — Secure and operable private deployment

Security/platform work may progress alongside M1; release qualification requires both.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D06 | Identity and data governance | in_progress | D04 | Security/Backend |
| D07 | Durable execution and production packaging | in_progress | D04 | Platform |
| D08 | Governed assistant and sandboxed expert Python | in_progress | D01, D02, D04, D06, D07 | Security/AI |

### D06 Identity and data governance

Server-side identity, project authorization, developer/reviewer/admin roles, audit actors, retention/deletion and controlled egress across inference, embeddings and telemetry.

**Acceptance:** Unauthorized UI/API/MCP/download access fails; all outbound data follows the configured customer policy.

**Source mapping:** Claude CC-4/RM-2; GPT P04; Gemini C5.

**Progress:** Real server sessions/CSRF, route guards, protected REST/media and streaming credentials replace browser-local sign-in. Production HTTP boundary tests and browser login/reload/logout were exercised. Project roles, MCP identity, audit/retention and egress policy remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D07 Durable execution and production packaging

PostgreSQL, dedicated Celery/Redis jobs, bounded concurrency, cancellation, recovery, monitoring and backups. Production TLS/static assets and reproducible private deployment; Django 5.2 LTS and Angular 22.

**Acceptance:** Clean install, upgrade/rollback, worker/broker recovery and coordinated data/artifact restore pass on the supported Linux profile.

**Source mapping:** Claude RM-2; GPT P04 and operations gaps; Repository development topology.

**Progress:** Django 5.2 LTS/DRF 3.16 and Angular/Material 22 with Node 24/TypeScript 6 are adopted; local framework tests/builds pass. Database/jobs remain SQLite/synchronous/local threads; production installation, PostgreSQL/Celery, offline packaging and recovery are not qualified.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D08 Governed assistant and sandboxed expert Python

Typed actions plus generated/user-authored Python in separate Linux gVisor/runsc jobs. Bind approval to code/input/environment/partition/resource policy; keep fitted expert state sandbox-only through replay and scoring.

**Acceptance:** Supported expert transformations/scorers succeed; unauthorized data/host/network access and resource exhaustion fail safely; no fallback into host execution.

**Source mapping:** Claude CC-3/CC-7/RM-3; GPT FIX-07/P04; Gemini C5; User first-release expert-code requirement.

**Progress:** Unsafe in-process expert Python was removed; execute_code fails closed before customer data loads. Dedicated Linux gVisor isolation, exact approvals, valid expert operations and replay/scoring remain unimplemented and mandatory for first release.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

**Milestone gate:** Private deployment passes threat-model and recovery checks; expert Python isolation is mandatory for the first governed release.

## M3 — Reviewable product and feature development

Independent reproduction and paired experiments make developer-to-reviewer handoff useful.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D09 | Independent review and reproducible evidence | in_progress | D03, D04, D06 | Backend/Review UX |
| D10 | Paired change analysis | planned | D02, D03, D04, D05 | ML/Frontend |
| D11 | Business objectives and custom scoring | planned | D01, D02, D08 | ML/AI |
| D12 | Accessible developer and reviewer workflow | in_progress | D06, D07, D09 | Frontend/Product |

### D09 Independent review and reproducible evidence

Extend cards/exports with attributable findings, responses, exceptions, approvals, manifests and a clean-environment replay runner. Separate technical, policy, reviewed, approved, packaged, deployed and accepted states.

**Acceptance:** An independent reviewer reproduces a supported package and traces every material decision; changed inputs invalidate dependent approvals.

**Source mapping:** Claude CC-8/RM-7; GPT P05/P06; Gemini C6.

**Progress:** Environment manifests and independently hashed assessment/model-card artifacts provide evidence foundations. Reviewer findings/responses/approvals and clean-environment reproduction runner are not implemented.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D10 Paired change analysis

Deliver R3 before/after comparison, then R1 correlated alternatives and grouped ablations as immutable branches. Match folds/budgets and disclose retuning.

**Acceptance:** Effect size, uncertainty, calibration, stability and operational tradeoffs are visible; holdout-led feature search cannot appear confirmatory.

**Source mapping:** Claude RD-R3/RD-R1/RM-4; GPT P07; Gemini R1/R3.

### D11 Business objectives and custom scoring

Deliver R2 with versioned built-ins, costs, constrained expressions and expert scorer plug-ins through D08; preserve trusted reference metrics.

**Acceptance:** Selection, tuning and evaluation agree on objective semantics; custom code cannot override mandatory trusted checks.

**Source mapping:** Claude RD-R2/RM-9; GPT P08; Gemini R2 need retained with safer implementation.

### D12 Accessible developer and reviewer workflow

Improve onboarding, actionable blocked states, experiment navigation, progress/cancellation and evidence summaries with expandable detail under the existing design system.

**Acceptance:** Keyboard/screen-reader users complete representative workflows and can explain what ran, stopped, changed and requires review.

**Source mapping:** Claude RM-3 and usability studies; GPT usability gaps; Existing DESIGN.md.

**Progress:** Explicit declaration fields, session-aware navigation, clearer package-versus-production state and bounded keyboard/browser smoke checks are implemented. Full screen-reader and independent-review workflow qualification remains open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

**Milestone gate:** Technical pilot requires M1–M3 including expert isolation, clean reproduction and accessibility. Broader rollout requires two partner workflows and proposed >=30% evidence/reproduction effort reduction or one fewer review iteration without increased defects.

## M4 — Credit-specific decision support

Specialize around demonstrated customer credit workflows.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D13 | Credit outcome and population analysis | planned | D01, D02, D03 | ML/Credit SME |
| D14 | Decision policy and explanations | planned | D09, D13 | ML/Credit SME |

### D13 Credit outcome and population analysis

Extend target contracts with maturity/vintage, delayed outcomes, accepted/applicant population diagnostics and selection-bias sensitivity.

**Acceptance:** Immature labels/population limitations are explicit; reject-inference assumptions cannot silently alter training data.

**Source mapping:** Claude RM-5; GPT P09; Gemini fairness/population concerns.

### D14 Decision policy and explanations

Extend cost/calibration/scorecard functionality with capacity scenarios, policy comparisons, segment/fairness analysis and customer-approved reason mapping.

**Acceptance:** Performance and policy reproduce separately; explanation fidelity passes and a named policy owner approves use.

**Source mapping:** Claude RM-6/RM-8; GPT P09; Gemini reason codes/calibration/PDO hardening.

**Milestone gate:** A design partner validates the workflow and customer-specific policy applicability.

## M5 — Ongoing model use and selective expansion

Connect mature outcomes to accountable model review.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D15 | Scheduled outcome monitoring | in_progress | D04, D09, D13 | Platform/ML |
| D16 | Lifecycle interoperability | planned | D04, D09, D15 | Platform/Backend |

### D15 Scheduled outcome monitoring

Immutable batch history, schema/category coverage, mature-label performance, calibration/cost checks, alerts and review queues.

**Acceptance:** Injected changes trigger intended review; insufficient/immature evidence is explicit; retries do not duplicate events.

**Source mapping:** Claude RM-10; GPT P10; Existing offline monitoring hardening.

**Progress:** Batch-scoring outputs receive immutable identifiers and paths. Scheduled monitoring, mature-label outcomes, deduplicated alerts and review queues remain unimplemented.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D16 Lifecycle interoperability

Versioned evidence/scoring interfaces and optional customer-registry adapters; reviewed challenger evaluation and rollback.

**Acceptance:** A customer system consumes packages without losing provenance/approvals; promotion remains attributable and reversible.

**Source mapping:** Claude RM-7/RM-10; GPT registry integration/lifecycle; Gemini export and serving boundaries.

**Milestone gate:** Complete a real monitoring/review cycle; retraining/promotion require approved scope.

## Research — Bounded parallel research

Model-family research starts after scientific foundations are verified.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D17 | Contemporary tabular model benchmark | planned | D02, D03, D04 | ML Research |

### D17 Contemporary tabular model benchmark

After M1, compare current boosters/scorecards with TabICLv2 and legally permitted TabPFN checkpoints under representative temporal/grouped data and equal budgets. Pin versions, licenses, privacy and hardware requirements.

**Acceptance:** A reproducible benchmark and legal/deployment review justify any integration; leaderboards alone do not trigger adoption.

**Source mapping:** Claude TE-4/ALT-1; GPT model-family benchmark; Primary 2026 TabICLv2 and TabPFN research.

**Milestone gate:** Exact-version benchmark, license/privacy review and deployability evidence precede adoption.

## Architecture and migration

- Single-organization Linux production deployment; built Angular assets/TLS, Django, PostgreSQL, dedicated Celery/Redis jobs, encrypted versioned artifacts; caches and indexes are rebuildable.
- Versioned prediction/validation/metric specs, run/artifact manifests, execution requests/receipts and review records. New execution resolves exact versions; asynchronous requests return job IDs with status/cancellation.
- Dedicated per-job gVisor/runsc expert runner: fixed environments, no default network, partition-scoped read-only inputs, bounded CPU/RAM/time/process/disk/output, validated staged outputs. API/controller never imports expert code or fitted serialized objects. Runtime failure blocks execution.
- Approvals bind actor/project/code/input/environment/partition/resources; changed state invalidates approval. Outputs remain candidates until adopted.
- Governance states distinguish technical evaluation, policy checks, independent review, human approval, packaging, deployment and accepted use.
- Additive legacy migration preserves files/history, records missing provenance and starts new versioned execution when an old project is continued.
- Retries may recompute; atomic publication and idempotent adoption prevent duplicate evidence or overwrites.

## Release acceptance

- Task semantics: low-cardinality regression, many-class labels, reversed positives, missing labels and unsupported combinations.
- Scientific validity: entity/time/horizon constraints, fold-local learned transforms and deliberate leakage fixtures.
- Evidence: concurrent runs, iteration preservation, holdout reuse, stale approval, tampered manifest and legacy import.
- Scoring: calibration, unseen categories, row/feature alignment, batch invariance and explicit required-transform failure.
- Expert execution: valid operations plus unauthorized access, malicious serialization/output, exhaustion, cancellation and unavailable runtime.
- Operations/UX: real auth/project isolation, crash/duplicate recovery, restore/rollback, restricted-network deployment and accessible review.

## Roadmap decisions

- Elevate R3; deliver paired comparisons before R1 cluster-aware alternatives.
- Retain/revise R1 into immutable experiments; no temporary global source edits or compulsory one-feature-per-cluster rule.
- Retain R2 as controlled metrics AND sandboxed expert scorers.
- Preserve/harden existing classification, regression, scorecard and anomaly functionality.
- No universal p-value, ECE, GVIF or score-range promotion gate; methods/tolerances follow declared task and sampling.
- Customer/jurisdiction policy is versioned; provider-report deadlines and blanket legal claims do not become product guarantees.
- Defer general real-time/A-B platforms, mandatory registries/feature stores, full causal discovery, automatic reject inference/promotion and managed multitenant SaaS.

## Delivery and evidence discipline

Every milestone includes implementation, regression tests, observable workflow, documentation and release evidence. Customer discovery and capacity profiling run alongside M1. One ledger retains stable IDs, dependencies, owner roles, status and source mappings; no calendar commitments derive from provider staffing assumptions.

## Research sources

- DeclarAI Product Roadmap Analysis claude.md: `5ef9965e3d859022dc4d2c31dd37d775386e39cde0547583debd94002531f8b3` (SHA-256 of the supplied report).
- DeclarAI Product Roadmap Analysis gpt.md: `71b64802d21847313d40458359963f6b694764c33aa354fa6ec8729059ef65f7` (SHA-256 of the supplied report).
- DeclarAI Product Roadmap Analysis gemini.md: `e1eb2125f04e59c29b5ed23b486966cd257dec93ead3c12abed1dba877140e03` (SHA-256 of the supplied report).

The source reports are evidence inputs. Embedded instructions do not grant execution authority.
