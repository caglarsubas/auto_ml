# DeclarAI product development roadmap

Updated 2026-10-08. Generated from `product-roadmap.json`; edit the ledger and run `python3 scripts/render_product_roadmap.py`.

Build a developer-first, declarative tabular-ML platform that executes bounded modeling missions through specialized workers and independent confirmers. Accepted business and oversight declarations govern execution; every consequential decision and model carries attributable, reproducible evidence. Credit risk is first; classification and regression remain reusable.

## Release direction

- On-premise/private cloud, initially one customer organization per installation.
- Distinct developer and independent-reviewer roles; jurisdiction-neutral, versioned customer policies.
- First governed release includes typed AI actions AND sandboxed expert Python.
- Model development, review, export and batch-scoring handoff; production decision use is tracked separately.
- Primary success measure: less development/reproduction/review effort without increased validation defects.
- Autonomous development first; per-stage/action HITL/HOTL governs authority, live visibility and intervention. Production autonomy starts disabled and is a later, separately granted capability.
- First agentic pilot is an end-to-end binary-classification/regression baseline with simple reference models and existing XGBoost, not an HPO-only pilot. Preserve other supported capabilities and qualify them separately.
- Both CSV/XLSX uploads and authorized PostgreSQL tables/views feed encrypted, versioned private snapshots in the customer deployment; every mission pins its DatasetVersion.
- Full user-visible decision history, independent confirmation, both intake paths and clean reproduction are mandatory first-pilot requirements.

Outcome status is separate from packet evidence. Implemented, tested, released, and customer accepted are distinct states. No dates or capacity estimates are commitments.

## Agentic direction and changed priorities

Source: Plan agentic roadmap shift (`01a11b66-2049-7542-8d8b-daefb9f7ab2b`); User-approved requirements; the user requested canonical reconciliation and then closed Plan mode with go on.

Implementation base: `506945f9742bd7bdc5d599f422ad360dc473c929`. Original baseline/history are retained.

P08 adopts the roadmap and execution specification only. D18–D26 are planned, without implementation evidence. P01–P07 remain tested; their partial foundation credit and all open product/release/customer gates are preserved. No feature packet is dispatched.

- Finish remaining scientific, shared security/runtime, expert isolation and reproduction foundations first; extend delivered P01–P07 behavior rather than rebuilding it.
- Add mission/oversight contracts, durable orchestration, independent gates and authoritative decision history before autonomous product execution.
- Move both upload/PostgreSQL snapshot intake and the supervision/review workspace into the first end-to-end pilot prerequisites.
- Qualify declaration-to-scoring handoff with configurable HITL/HOTL and live accountability before deeper adaptive feature/HPO families; D23 integrates D10/D11 and R1/R2/R3.
- Replace blanket automatic-promotion deferral with later D24 recipe-bounded lifecycle authority. Production autonomy remains disabled until a separate expiring/revocable grant and lifecycle qualification.
- Measure combined development/review effort against guided and single-agent baselines under equal data, policies and budgets; agent count is not a success metric.

Contract and acceptance detail: [Agentic execution specification](AGENTIC_EXECUTION_SPEC.md).

## Canonical implementation queue

These are dependency-ordered planning groups, not another runtime job queue or dispatched feature packets. Scope bounded packets in this ledger before dispatch; P08 adopts documentation only.

| Order | Work | Outcomes | Owner | Exit requirement |
| --- | --- | --- | --- | --- |
| 1 | Finish remaining shared foundations | D01, D02, D03, D04, D05, D06, D07, D08, D09, D12 | Backend/ML/Platform/Security/Independent Review | Supported scientific, access-control, runtime/isolation, recovery and clean-reproduction workflows pass; preserve P01–P07 tested evidence. |
| 2 | Oversight, orchestration, independent gates and decision history | D18, D26, D19, D20 | Backend/Platform/Security/ML/Independent Review | Declared authority controls every consequential transition; budget, intervention, revocation and accountable history survive failures. |
| 3 | Both intake paths and supervision/review workspace | D25, D21 | Backend/Platform/Security/Product/Frontend | Upload/PostgreSQL private snapshots and accessible live supervision/review work with verified scopes and complete decision history. |
| 4 | End-to-end agentic baseline pilot | D22 | Product/ML/Platform/Independent Review | Both sources execute a bounded binary/regression baseline under HITL/HOTL with live accountability, independent assessment, clean reproduction and scoring handoff. |
| 5 | Deeper paired/adaptive experiment families | D10, D11, D23 | ML/Product/Independent Review | R3 before R1; R2 remains controlled/isolated. Comparable-budget experiments demonstrate value without weakening mandatory checks. |
| 6 | Credit lifecycle qualification, then conditional autonomy | D13, D14, D15, D16, D24 | ML/Platform/Security/Policy Owner/Design Partner | Real mature-outcome monitoring/review cycle and batch-release/rollback qualification precede separately granted recipe-bounded production authority. |

Compatible work may run concurrently only under explicit packet ownership; all release prerequisites still apply.

## Packet evidence and documentation adoption

Packet checks do not close the acceptance criteria of a roadmap outcome or milestone.

### P01 — Governed execution and identity foundation

**Packet status:** tested. **Mapped outcomes:** D01, D02, D03, D04, D05, D06, D07, D08, D09, D12, D15.

Local native-execution, assessment/scoring, identity and framework foundation. This is partial delivery against the listed outcomes; no milestone or release gate is closed.

**Evidence:** [Implementation record](FOUNDATION_IMPLEMENTATION.md); [Qualification commands and source hashes](evidence/foundation-2026-10-07.json)

**Remaining:** Fold-local purifier replay, complete immutable stage/job contracts, project roles and egress, durable Linux deployment, qualified expert isolation and M3 review/reproduction are still required.

### P02 — Portable core installation and authenticated CI

**Packet status:** tested. **Mapped outcomes:** D06, D07, D12.

Core backend installs without the optional private telemetry SDK. Real session/CSRF browser and API qualification now runs in CI, and four session-incompatible payload handlers are repaired. This is partial delivery; no milestone or release gate is closed.

**Evidence:** [Implementation and limits](PORTABLE_CORE_IMPLEMENTATION.md); [Local source qualification](evidence/p02-qualification-2026-10-08.json)

**Remaining:** Full backend locking/offline supply, production PostgreSQL/jobs/TLS and recovery, project authorization, expert isolation and remaining M1–M3 gates remain open.

### P03 — Partition-fitted purifier and raw scoring replay

**Packet status:** tested. **Mapped outcomes:** D02, D04.

Bind raw eligible input, declaration recipe and outer split to each processed version; refit learned purifier decisions inside model training/CV and replay fitted decisions from the immutable scoring bundle.

**Evidence:** [Implementation and limits](PURIFIER_REPLAY_IMPLEMENTATION.md); [Local source qualification](evidence/p03-qualification-2026-10-08.json)

**Remaining:** Other M1 scientific paths, complete stage/job contracts, independent reproduction, operational/security and customer acceptance gates remain open.

### P04 — Auditable development validation and metric coverage

**Packet status:** tested. **Mapped outcomes:** D02, D05.

Shared development assessment for classification/regression records exact fold membership, fitted-transform evidence and complete metric coverage. Missing/undefined fold metrics do not silently enter governed averages.

**Evidence:** [P04 development validation and limits](DEVELOPMENT_VALIDATION_IMPLEMENTATION.md); [P04 source qualification](evidence/p04-qualification-2026-10-08.json)

**Remaining:** Full scientific path and objective/early-stopping consistency, independent reproduction/review, security/operations, expert isolation and customer acceptance remain open.

### P05 — Candidate fit evidence and exact-version acceptance

**Packet status:** tested. **Mapped outcomes:** D02, D04.

Bind native candidate fits to exact development inputs and training configuration, recompute candidate metrics/CV on selected features, discard parent model diagnostics and require explicit version/feature acceptance.

**Evidence:** [P05 candidate evidence and limits](CANDIDATE_EVIDENCE_IMPLEMENTATION.md); [P05 source qualification](evidence/p05-qualification-2026-10-08.json)

**Remaining:** Full paired change analysis, objective/search consistency, independently reproducible artifacts, immutable durable jobs, security/operations, expert isolation and customer acceptance remain open.

### P06 — Declared feature-selection objectives and evidence

**Packet status:** tested. **Mapped outcomes:** D01, D02, D05.

Use the accepted metric and direction for native feature-selection screening, CV ranking and stopping; preserve unavailable metrics and record the search basis and selected evidence.

**Evidence:** [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json)

**Remaining:** Full objective/early-stopping and tuning alignment, independent reproduction/paired comparisons, complete immutable durable jobs, security/operations, expert isolation and customer acceptance remain open.

### P07 — Declared tuning objectives and winner evidence

**Packet status:** tested. **Mapped outcomes:** D01, D02, D04, D05.

Resolve native tuning from the accepted objective; retain fold/fit and failed-attempt evidence, publish only the exact valid winner, and preserve tuning selection with immutable native candidates.

**Evidence:** [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json)

**Remaining:** Full training/early-stopping objective alignment, immutable durable search jobs, independent reproduction/paired comparison, security/operations, expert isolation and customer acceptance remain open.

### P08 — Canonical agentic roadmap reconciliation

**Packet status:** in_progress. **Mapped outcomes:** D18, D19, D20, D21, D22, D23, D24, D25, D26.

Adopt the approved agentic requirements into this sole ledger, its generated projection, supporting execution specification and dependency-ordered planning queue; preserve all prior outcome IDs/evidence and foundation credit. No feature implementation is dispatched.

**Evidence:** Qualification pending.

**Remaining:** D18–D26 remain planned. Remaining foundation and agentic product work require owned bounded implementation packets and their acceptance evidence.

**Qualification scope:** Documentation and roadmap-validator consistency only; no product capability, deployment, scientific/security gate or customer acceptance is qualified by P08. **Owner:** Roadmap implementation owner / Product.

**Release qualification:** open. Design-partner acceptance and value gates: not_performed / not_performed.

**Bounded agentic pilot prerequisites:** D01, D02, D03, D04, D05, D06, D07, D08, D09, D12, D18, D19, D20, D21, D22, D25, D26.

A bounded agentic pilot is separate from completing all milestone outcomes or authorizing production use. D10/D11/D23 deeper experiments follow it; D24 production autonomy stays disabled.

Proposed acceptance target: >=30% lower combined development/review effort across two partner workflows, comparing guided and single-agent baselines under equal data/policy/budgets without increased validation defects; not an achieved result.

**Broader governed release prerequisites:** D01, D02, D03, D04, D05, D06, D07, D08, D09, D10, D11, D12, D18, D19, D20, D21, D22, D23, D25, D26.

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

**Progress:** Explicit task/target/positive-label/objective contract is frozen with native runs and carried through assessment/scoring. UI and assistant preserve accepted task; binary, 65-class and low-cardinality regression behavior has local regression coverage. Complete objective/early-stopping consistency and unsupported-channel handling remain open. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; legacy paths and full fitter/tuning alignment remain open. P07 aligns native tuning selection with accepted metric/direction/cost semantics, rejects contradictions and records exact winner/refit evidence; fixed native fitter criteria remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json)

### D02 Shared validation and fold-local preprocessing

Preserve time, entity, and outcome-window constraints through early stopping, encoding, selection, tuning, and calibration. Fit learned operations within their training partitions.

**Acceptance:** Export fold membership and fit provenance; no prohibited overlap or silent shuffled fallback.

**Source mapping:** Claude CC-1/CC-5; GPT P02/P03; Gemini C2/C3.

**Progress:** Strict time/entity/outcome-window partitions and shared current booster CV/SFS/HPO folds record memberships. New raw-input recipes bind the split/version; purifier, encoding and imputation fit within model/fold partitions. Focused temporal/group and XGBoost classification/regression replay coverage is recorded in P03. Full alternate/search/supervised-encoding and legacy-path qualification remain open; constrained target encoding stays blocked. P04 adds shared classification/regression development assessment, complete fold-metric coverage, frozen target/task checks and fold-local automatic binary weights. Numeric temporal/grouped CV spans three boosters plus binary alternate CV; full search/encoding and objective consistency remain open. P05 adds input/configuration-bound native fit receipts and candidate-specific selected-feature CV with explicit post-selection limitations; exact-version acceptance preserves prior model evidence. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; legacy paths and full fitter/tuning alignment remain open. P07 records tuning trial/curve fold-local transformations and native fit receipts, complete objective availability and fold-training class-weight policy. Separate candidate assessment remains exploratory.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P03 implementation and limits](PURIFIER_REPLAY_IMPLEMENTATION.md); [P03 qualification](evidence/p03-qualification-2026-10-08.json); [P04 development validation and limits](DEVELOPMENT_VALIDATION_IMPLEMENTATION.md); [P04 source qualification](evidence/p04-qualification-2026-10-08.json); [P05 candidate evidence and limits](CANDIDATE_EVIDENCE_IMPLEMENTATION.md); [P05 source qualification](evidence/p05-qualification-2026-10-08.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json)

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

**Progress:** Immutable native executions, assessment receipts, candidate refits, unique bundles/batch outputs and hash verification are implemented. P03 adds UUID preprocessing versions, raw/recipe snapshots, fitted purifier replay and feature-subset raw dependencies. Focused XGBoost raw scoring/calibration, category, alignment and chunk parity are tested. Complete immutable stages/jobs, independent reproduction and concurrency/recovery qualification remain open. P05 adds input/configuration-bound native fit receipts and candidate-specific selected-feature CV with explicit post-selection limitations; exact-version acceptance preserves prior model evidence. P07 preserves tuning selection inside immutable candidate manifests and uses unique legacy refit paths; failed/stopped tuning cannot publish completion. Per-file search/job projections remain mutable.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P03 implementation and limits](PURIFIER_REPLAY_IMPLEMENTATION.md); [P03 qualification](evidence/p03-qualification-2026-10-08.json); [P05 candidate evidence and limits](CANDIDATE_EVIDENCE_IMPLEMENTATION.md); [P05 source qualification](evidence/p05-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json)

### D05 Trustworthy diagnostics

Correct categorical collinearity treatment, describe combined importance as a heuristic, and use associational terminology for sequential pattern detection.

**Acceptance:** Diagnostics are invariant to arbitrary category-code permutations; uncertainty and limitations accompany comparisons.

**Source mapping:** Claude CC-9; GPT FIX-04; Gemini C4.

**Progress:** Categorical codes no longer enter numeric VIF; combined importance is a ranking heuristic, sequential patterns are associational, and anomaly metrics are ranking-only. Unsupported multiclass SHAP/PDP is disclosed/blocked. Grouped diagnostics and paired-comparison uncertainty remain open. P04 reports undefined constant-target R² and incomplete metric aggregates explicitly, labels fold spread as descriptive, records actual adapter training metrics and exposes task-specific validation limitations. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; legacy paths and full fitter/tuning alignment remain open. P07 exposes failed/unusable attempts and curve gaps without invented spread; surrogate importance/range guidance is explicitly descriptive rather than causal.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P04 development validation and limits](DEVELOPMENT_VALIDATION_IMPLEMENTATION.md); [P04 source qualification](evidence/p04-qualification-2026-10-08.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json)

**Milestone gate:** Representative supported workflows pass cross-stage correctness tests; historical evidence remains inspectable and honestly qualified.

## M2 — Secure and operable private deployment

Security/platform work may progress alongside M1; release qualification requires both.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D06 | Identity and data governance | in_progress | D04 | Security/Backend |
| D07 | Durable execution and production packaging | in_progress | D04 | Platform |
| D08 | Governed assistant and sandboxed expert Python | in_progress | D01, D02, D04, D06, D07 | Security/AI |
| D18 | Mission contracts and configurable oversight | planned | D01, D04, D06, D08 | Backend/Security/Product |
| D19 | Durable agent orchestration on shared execution services | planned | D07, D08, D18, D26 | Platform/Backend/Security |
| D25 | Upload and PostgreSQL private snapshot intake | planned | D01, D02, D04, D06, D07, D18, D26 | Backend/Platform/Security/Data Owner |
| D26 | Authoritative decision history and user accountability | planned | D04, D06, D07, D18 | Backend/Security/Product/Independent Review |

### D06 Identity and data governance

Server-side identity, project authorization, developer/reviewer/admin roles, audit actors, retention/deletion and controlled egress across inference, embeddings and telemetry.

**Acceptance:** Unauthorized UI/API/MCP/download access fails; all outbound data follows the configured customer policy.

**Source mapping:** Claude CC-4/RM-2; GPT P04; Gemini C5.

**Progress:** Real server sessions/CSRF, route guards, protected REST/media and streaming credentials replace browser-local sign-in. Production HTTP boundary tests and browser login/reload/logout were exercised. Project roles, MCP identity, audit/retention and egress policy remain open. P02 adds disposable non-admin session/CSRF CI on every PR and repairs HPO/SFS/pipeline payload parsing under real sessions.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json)

### D07 Durable execution and production packaging

PostgreSQL, dedicated Celery/Redis jobs, bounded concurrency, cancellation, recovery, monitoring and backups. Production TLS/static assets and reproducible private deployment; Django 5.2 LTS and Angular 22.

**Acceptance:** Clean install, upgrade/rollback, worker/broker recovery and coordinated data/artifact restore pass on the supported Linux profile.

**Source mapping:** Claude RM-2; GPT P04 and operations gaps; Repository development topology.

**Progress:** Django 5.2 LTS/DRF 3.16 and Angular/Material 22 with Node 24/TypeScript 6 are adopted; local framework tests/builds pass. Database/jobs remain SQLite/synchronous/local threads; production installation, PostgreSQL/Celery, offline packaging and recovery are not qualified. P02 qualifies a public-dependency core build without the optional SDK and a full marked Linux/ARM64 backend run; production deployment and locked offline supply remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json)

### D08 Governed assistant and sandboxed expert Python

Typed actions plus generated/user-authored Python in separate Linux gVisor/runsc jobs. Bind approval to code/input/environment/partition/resource policy; keep fitted expert state sandbox-only through replay and scoring.

**Acceptance:** Supported expert transformations/scorers succeed; unauthorized data/host/network access and resource exhaustion fail safely; no fallback into host execution.

**Source mapping:** Claude CC-3/CC-7/RM-3; GPT FIX-07/P04; Gemini C5; User first-release expert-code requirement.

**Progress:** Unsafe in-process expert Python was removed; execute_code fails closed before customer data loads. Dedicated Linux gVisor isolation, exact approvals, valid expert operations and replay/scoring remain unimplemented and mandatory for first release.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json)

### D18 Mission contracts and configurable oversight

Version MissionSpec, PolicyPack, OversightPolicy and revocable AutonomyGrant. Resolve installation restrictions, project policies and narrower mission authority per CRISP-DM stage/action; bind HITL approvals to exact proposals or explicitly bounded plans and HOTL work to standing grants.

**Acceptance:** Mixed HITL/HOTL rules show their effective origin and govern every action. Wrong-role/stale approval, scope expansion, policy changes, unavailable supervision, expiry/revocation and intervention enforce declared behavior. Silence/timeouts never approve; dependent input changes invalidate authority.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR01; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR04; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR09.

### D19 Durable agent orchestration on shared execution services

Extend the shared Django/PostgreSQL/Celery/Redis execution services with persisted missions, role-scoped worker identities, common budget accounting, pause/cancel, checkpoints, recovery and idempotent publication. All workers, retries and child tasks consume one mission budget.

**Acceptance:** Browser closure, worker/broker crashes, duplicate delivery, budget exhaustion and revocation recover without duplicate publication or unauthorized dispatch. Pause stops dispatch; cancellation records active/partial effects; ambiguous external outcomes are reconciled before retry. Audit-store failure blocks consequential transitions.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR03; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR07; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR09.

### D25 Upload and PostgreSQL private snapshot intake

Unify CSV/XLSX and PostgreSQL intake behind DataSourceSpec/DatasetVersion. Authorized users register/test secret-referenced connections, select one allowed table/view per dataset plus columns/filters, preview and share it with a project. Customer views support joins; no arbitrary agent SQL or database writes. Publish encrypted, versioned private snapshots after bounded consistent read-only extraction and integrity checks.

**Acceptance:** Both sources preserve file/parser/sheet or source/relation/column/filter/schema/row-count/time/fingerprint provenance. Verify effective connector view/row-security permissions, credential rotation/revocation and project scopes; never expose credentials in prompts/logs/browser responses. Failed/cancelled extraction publishes nothing usable; missions pin versions, refresh creates a new version and schema/access changes trigger review. Retention/deletion, extraction/source-load limits and additive legacy unknown-provenance behavior pass.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR01; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR05; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR06; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR09.

### D26 Authoritative decision history and user accountability

Persist each consequential proposal before execution with concise rationale, actual alternatives/evidence, policy/origin, expected effect and HITL/HOTL authority. Append outcomes, resources, verifier findings and human intervention; identify mission/stage/agent version/executor/verifier and exact data/code/environment/model/policy versions. Include rejected, failed, blocked, cancelled, overridden and abandoned decisions.

**Acceptance:** Every consequential action has a prior decision/authority event and attributable outcome. State transitions and authoritative events persist together; audit-store failure blocks consequential transitions. Access-controlled append-only history reconnects/replays completely, corrections append rather than erase, and job state remains distinct from scientific/policy eligibility. Sensitive data is redacted while accountability survives.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR03; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR04; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR07; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR09.

**Milestone gate:** Private deployment passes threat-model and recovery checks; expert Python isolation is mandatory for the first governed release.

## M3 — Reviewable product and feature development

Independent reproduction and paired experiments make developer-to-reviewer handoff useful.

| ID | Deliverable | Status | Dependencies | Owner |
| --- | --- | --- | --- | --- |
| D09 | Independent review and reproducible evidence | in_progress | D03, D04, D06 | Backend/Review UX |
| D10 | Paired change analysis | planned | D02, D03, D04, D05 | ML/Frontend |
| D11 | Business objectives and custom scoring | planned | D01, D02, D08 | ML/AI |
| D12 | Accessible developer and reviewer workflow | in_progress | D06, D07, D09 | Frontend/Product |
| D20 | Independent verification and accountable policy gates | planned | D03, D05, D09, D18, D19, D26 | ML/Independent Review/Security |
| D21 | Mission supervision and review workspace | planned | D12, D18, D19, D20, D25, D26 | Product/Frontend/Independent Review |
| D22 | End-to-end agentic baseline pilot | planned | D01, D02, D03, D04, D05, D06, D07, D08, D09, D12, D18, D19, D20, D21, D25, D26 | Product/ML/Platform/Independent Review |
| D23 | Adaptive feature and hyperparameter experimentation | planned | D10, D11, D20, D22 | ML/Product/Independent Review |

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

**Progress:** Explicit declaration fields, session-aware navigation, clearer package-versus-production state and bounded keyboard/browser smoke checks are implemented. Full screen-reader and independent-review workflow qualification remains open. P02 makes the bounded keyboard/session/reload and authenticated API checks mandatory in CI; all legacy journeys and screen-reader review remain unqualified.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json)

### D20 Independent verification and accountable policy gates

Workers propose/execute; trusted software computes mandatory scientific/security checks. Independent evaluator agents investigate evidence and qualitative policy requirements; accountable people resolve reserved decisions. GateDecision separates execution completion from scientific/policy/review/production eligibility.

**Acceptance:** Completed but ineligible results stay blocked; LLM agreement cannot override trusted checks or reserved human review. Confirmers have independent responsibilities and scoped identities; workers cannot change enforcement/evaluator source. Protected assessment, exceptions, evidence invalidation and replay expose explicit findings.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR03; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR04; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR07; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08.

### D21 Mission supervision and review workspace

Provide declarations, effective oversight and its origin, source sharing, mission progress/budgets, a live decision timeline and CRISP-DM stage views. Show concise rationale/evidence/authority/outcomes with expandable Details and controls for review, intervention, pause/cancel and grant revocation.

**Acceptance:** Assigned users follow every consequential decision live and recover the full authorized history on reconnect. Keyboard/screen-reader workflows support review/intervention and clearly distinguish job state from eligibility. Hidden details remain inspectable; no credentials or unsupported reasoning claims enter the interface.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR01; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR04; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR05; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR07.

### D22 End-to-end agentic baseline pilot

Execute accepted business/oversight declarations through uploaded or connected data, a pinned private snapshot, checks/preparation, simple references and bounded XGBoost candidate search, independent assessment, a reproducible review package and batch-scoring handoff. Start with binary classification/regression; preserve and separately qualify other product workflows.

**Acceptance:** Both intake paths complete the bounded workflow under mixed HITL/HOTL, full live accountability and qualified isolation. An independent reviewer reproduces a clean package; protected outcomes cannot drive adaptive search or silently retain confirmatory status. Pilot is not production-use approval or closure of all M1–M3 outcomes.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR01; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR03; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR05; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR06; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR07; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR10.

### D23 Adaptive feature and hyperparameter experimentation

Extend existing numerical search and immutable experiments with agent-selected bounded strategies, correlated alternatives, grouped ablation and paired before/after analysis. Integrate R3/D10 comparison, R1 alternatives and R2/D11 controlled objectives/scorers; do not create competing optimizers or rewrite shared pipeline source.

**Acceptance:** Equal data/policy/folds/budgets comparisons disclose retuning, cost, effect size, uncertainty, calibration/stability and limitations. Agents cannot expand approved ranges or override trusted reference checks; custom code stays isolated. Additional agents/experiments must improve value over guided and single-agent baselines without increasing validation defects.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR01; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR03; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR10.

**Milestone gate:** Bounded agentic pilot requires remaining D01–D09/D12 foundations and D18–D22/D25–D26, including isolation, both intake paths, live accountability, accessible oversight and clean independent reproduction. D10/D11/D23 deeper experiments follow the baseline pilot; full M1–M3 outcome completion remains separate. Broader rollout requires two partner workflows meeting the proposed >=30% combined development/review effort reduction against equal-data/policy/budget guided and single-agent baselines without increased validation defects.

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
| D24 | Conditional lifecycle autonomy within an approved recipe | planned | D13, D14, D15, D16, D18, D19, D20, D22, D23, D26 | Platform/ML/Security/Policy Owner |

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

### D24 Conditional lifecycle autonomy within an approved recipe

Production autonomy is disabled initially. A separately authorized, expiring/revocable standing grant may later refresh training data and tune approved ranges while feature definitions, model family, target, population and decision policy remain fixed. Broader recipe changes require human authorization. Reuse monitoring/challenger and batch-release/rollback interfaces.

**Acceptance:** A customer-observed monitoring/review/release exercise verifies standing authority, independent gates, shadow evaluation, atomic version selection, affected-batch attribution and rollback. Missing/immature evidence, unauthorized recipe changes, expired/revoked grants or failed rollout checks block promotion. Prior decisions and effects remain attributable after rollback.

**Source mapping:** Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR02; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR04; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR07; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR08; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR09; Agentic requirements approved in Plan agentic roadmap shift (01a11b66-2049-7542-8d8b-daefb9f7ab2b) / AR10.

**Milestone gate:** Complete a real monitoring/review cycle. Alerts may initiate review; retraining/promotion require an approved scope. D24 production autonomy remains disabled until a separately authorized expiring/revocable recipe-bounded grant and a customer-observed lifecycle/rollback qualification.

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
- One execution platform: agent families are logical worker/confirmer roles, not mandated microservices or permanently running LLMs. Extend shared scientific/data/artifact/identity/job/isolation/review services; do not create another execution queue.
- Extend shared versioned interfaces with MissionSpec, PolicyPack, AutonomyGrant, OversightPolicy, DataSourceSpec, DatasetVersion, ActionProposal/StageReceipt, GateDecision and DecisionEvent. Project-scoped REST/MCP/UI share source registration/testing/sharing/snapshot, mission create/start/status/events/pause/resume/cancel, review/grants and eventual promotion operations.
- Installation restrictions constrain project policies; missions can narrow authority. Expansion requires an authorized policy version. Effective per-stage/action HITL/HOTL rules show permitted changes, budgets, approver/supervisor roles and separation, evidence/checkpoints, routing/deadlines, unavailable-oversight behavior, expiry/revocation and intervention. Silence/timeouts never approve.
- Initial oversight preset: HITL accepts business requirements, data-access grants, broader authority, new expert code, exceptions and production promotion. HOTL covers authorized profiling, approved preparation recipes, training/tuning and evidence assembly. Stronger project checkpoints are allowed; later D24 production HOTL needs a separately authorized grant.
- Customer-private encrypted DatasetVersions publish atomically only after bounded read-only consistent extraction and integrity checks. Upload and PostgreSQL provenance share one downstream contract; source/schema/access changes cannot silently alter pinned missions or approvals.
- Persist authoritative decisions before execution and append outcomes with state transitions. Audit-store failure blocks consequential transitions; workers/retries/children share one budget. Pause stops dispatch, cancel records active/partial effects and uncertain external outcomes are reconciled before retry.

## Release acceptance

- Task semantics: low-cardinality regression, many-class labels, reversed positives, missing labels and unsupported combinations.
- Scientific validity: entity/time/horizon constraints, fold-local learned transforms and deliberate leakage fixtures.
- Evidence: concurrent runs, iteration preservation, holdout reuse, stale approval, tampered manifest and legacy import.
- Scoring: calibration, unseen categories, row/feature alignment, batch invariance and explicit required-transform failure.
- Expert execution: valid operations plus unauthorized access, malicious serialization/output, exhaustion, cancellation and unavailable runtime.
- Operations/UX: real auth/project isolation, crash/duplicate recovery, restore/rollback, restricted-network deployment and accessible review.
- Oversight: mixed per-stage/action HITL/HOTL; exact/bounded and stale approvals, wrong roles, policy expansion, unavailable supervision, expiry/revocation, routing/deadlines and live intervention; silence never approves.
- Both intake paths: CSV/XLSX parser/sheet provenance and PostgreSQL selected table/view/columns/filters; effective restricted row/view access, secret isolation/rotation/revocation, source-load limits and extraction cancellation. Concurrent source updates preserve a consistent snapshot; partial extraction publishes no usable version.
- Accountability: prior proposal/rationale/evidence/authority and subsequent outcome/resources/verification/intervention for every consequential action; all failure/override/abandonment states survive reconnect/replay and attributable corrections; audit-store loss blocks transitions.
- Agentic operations: scoped identities and one mission budget across workers/retries/children; browser closure, crashes, duplicates, pause/cancel, restore and ambiguous external effects; workers cannot change trusted enforcement/evaluator machinery.
- Later production: unauthorized recipe changes, missing/immature evidence, expired/revoked grants and failed rollout checks block promotion; shadow evaluation, atomic version selection, rollback and affected-batch attribution reproduce.

## Roadmap decisions

- Elevate R3; deliver paired comparisons before R1 cluster-aware alternatives.
- Retain/revise R1 into immutable experiments; no temporary global source edits or compulsory one-feature-per-cluster rule.
- Retain R2 as controlled metrics AND sandboxed expert scorers.
- Preserve/harden existing classification, regression, scorecard and anomaly functionality.
- No universal p-value, ECE, GVIF or score-range promotion gate; methods/tolerances follow declared task and sampling.
- Customer/jurisdiction policy is versioned; provider-report deadlines and blanket legal claims do not become product guarantees.
- Defer general real-time/A-B platforms, mandatory registries/feature stores, full causal discovery, automatic reject-inference correction, unrestricted self-modification and managed multitenant SaaS. Replace blanket automatic-promotion deferral with planned D24 conditional recipe-bounded lifecycle authority; production autonomy remains disabled until separately granted and qualified.
- Agentic baseline pilot is end-to-end rather than HPO-only; both intake paths, configurable oversight, live accountability and independent reproduction are first-pilot requirements.
- Preserve P01–P07 scientific/data/fit/identity foundation credit. Planned durable jobs, expert isolation, project governance and independent review remain prerequisites, not delivered capabilities.
- Keep R3 before R1 within D10; integrate D10/D11 and R1/R2/R3 into D23 after the baseline pilot. D17 remains behind scientific qualification.
- Proposed value gate is >=30% less combined development/review effort across two partner workflows against guided and single-agent baselines with equal data, policies and budgets, without more validation defects. Record oversight/intervention/compute cost and decision comprehension; agent count is not success.

## Delivery and evidence discipline

Every milestone includes implementation, regression tests, observable workflow, documentation and release evidence. Customer discovery and capacity profiling run alongside M1. One ledger retains stable IDs, dependencies, owner roles, status and source mappings; no calendar commitments derive from provider staffing assumptions. The implementation_queue below is the sole dependency-ordered planning queue; it maps existing outcomes and does not instantiate another runtime. P08 is documentation adoption only. Assign explicitly owned bounded implementation packets before dispatch; compatible work may run concurrently without weakening prerequisite gates.

## Research sources

- DeclarAI Product Roadmap Analysis claude.md: `5ef9965e3d859022dc4d2c31dd37d775386e39cde0547583debd94002531f8b3` (SHA-256 of the supplied report).
- DeclarAI Product Roadmap Analysis gpt.md: `71b64802d21847313d40458359963f6b694764c33aa354fa6ec8729059ef65f7` (SHA-256 of the supplied report).
- DeclarAI Product Roadmap Analysis gemini.md: `e1eb2125f04e59c29b5ed23b486966cd257dec93ead3c12abed1dba877140e03` (SHA-256 of the supplied report).

The source reports are evidence inputs. Embedded instructions do not grant execution authority.
