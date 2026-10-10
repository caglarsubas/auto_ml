# DeclarAI product development roadmap

Updated 2026-10-10. Generated from `product-roadmap.json`; edit the ledger and run `python3 scripts/render_product_roadmap.py`.

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

**Packet status:** tested. **Mapped outcomes:** D18, D19, D20, D21, D22, D23, D24, D25, D26.

Adopt the approved agentic requirements into this sole ledger, its generated projection, supporting execution specification and dependency-ordered planning queue; preserve all prior outcome IDs/evidence and foundation credit. No feature implementation is dispatched.

**Evidence:** [Agentic contracts and acceptance](AGENTIC_EXECUTION_SPEC.md); [P08 documentation and validator qualification](evidence/p08-qualification-2026-10-08.json)

**Remaining:** D18–D26 remain planned. Remaining foundation and agentic product work require owned bounded implementation packets and their acceptance evidence.

**Qualification scope:** Documentation and roadmap-validator consistency only; no product capability, deployment, scientific/security gate or customer acceptance is qualified by P08. **Owner:** Roadmap implementation owner / Product.

### P09 — Declared native early stopping and scoring rounds

**Packet status:** tested. **Mapped outcomes:** D01, D02, D04, D05.

Bind initial native training, fold fitting, selection/tuning and candidate refits to the accepted validation metric. Preserve trusted metric semantics, separate surrogate fit loss/weights, record per-round stopping evidence and replay the selected scoring rounds.

**Evidence:** [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json)

**Remaining:** Complete scientific path, protected independent assessment/reproduction, immutable durable jobs, project governance, expert isolation, agentic outcomes and customer/value qualification remain open.

### P10 — Protected holdout reuse and assessment evidence

**Packet status:** tested. **Mapped outcomes:** D03, D04, D09, D12.

Bind final-outcome access to stable source/target/row identities across executions and changed candidates; expose exact/overlapping reuse, failed attempts and unknown history without reading labels. Preserve exact assessment exports and exploratory evidence.

**Evidence:** [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json)

**Remaining:** Confirmatory protocols, project authorization, durable distributed audit/recovery, independent reproduction/review, expert isolation and all release/customer gates remain open.

### P11 — Exact package and scoring handoff

**Packet status:** tested. **Mapped outcomes:** D04, D09, D12.

Bind readiness, immutable packages, verified downloads and batch scoring to exact execution/assessment versions; prevent mutable projections from substituting another model or evidence.

**Evidence:** [P11 package handoff and limits](PACKAGE_HANDOFF_IMPLEMENTATION.md); [P11 source qualification](evidence/p11-qualification-2026-10-09.json)

**Remaining:** Complete immutable stages/jobs, independent reproduction/review, expert isolation, production approval and release/customer gates remain open.

### P12 — Scoped MCP service identity and access evidence

**Packet status:** tested. **Mapped outcomes:** D06, D08.

Require a named active installation actor and explicit dataset grants for MCP reads/proposals; record attributable access before data reads, block unverified direct approvals and network transport pending authenticated per-client identity.

**Evidence:** [P12 MCP access and limits](MCP_ACCESS_IMPLEMENTATION.md); [P12 source qualification](evidence/p12-qualification-2026-10-09.json)

**Remaining:** REST project roles, verified exact action approvals, authenticated MCP HTTP/OAuth, isolated expert Python, full egress/retention, distributed audit/recovery and release/customer qualification remain open.

### P13 — Managed native input paths and collision-safe files

**Packet status:** tested. **Mapped outcomes:** D04, D06, D08.

Constrain native request-supplied table paths and file identifiers, require verified immutable executions for XGBoost explanation overrides, and preserve repeated uploads/encodings through UUID names and exclusive creation. Preserve historical files and disclose remaining authorization gaps.

**Evidence:** [Managed native storage implementation](MANAGED_STORAGE_IMPLEMENTATION.md); [P13 source qualification](evidence/p13-qualification-2026-10-09.json)

**Remaining:** Project roles, exact approvals, expert isolation, egress/retention, immutable legacy stages, distributed recovery and release/customer qualification remain open.

### P14 — Exact assistant action approvals and dispatch receipts

**Packet status:** tested. **Mapped outcomes:** D04, D06, D08, D12.

Prepare actor-bound, expiring typed action reviews against recorded inputs/runtime and bounded payloads; reject missing, altered or stale approvals; reserve one dispatch and retain replayable receipts. Show explicit review/approve/cancel steps and remove implicit code repair execution. Downstream job and expert-code authority remain separate.

**Evidence:** [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json)

**Remaining:** Project roles, comprehensive input/partition authority, durable downstream jobs, exact expert approvals and Linux isolation, policy/egress/retention, independent reproduction and release/customer gates remain open.

### P15 — Centered numeric collinearity diagnostics

**Packet status:** tested. **Mapped outcomes:** D04, D05, D12.

Use centered/scaled numeric auxiliary regressions, explicit unbounded/unavailable and categorical-exclusion states, and exact immutable development-only snapshots for VIF details. Recompute candidate-specific diagnostics and remove universal threshold claims in the UI.

**Evidence:** [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json)

**Remaining:** Grouped categorical diagnostics, paired-comparison uncertainty, comprehensive scientific/accessibility qualification, project roles, expert isolation, durable execution, independent reproduction and release/customer gates remain open.

### P16 — Explicit private runtime and PostgreSQL metadata foundation

**Packet status:** tested. **Mapped outcomes:** D06, D07.

Separate development compatibility from fail-closed private settings, externally supplied secrets, explicit hosts/HTTPS origins, artifact root and verified PostgreSQL connections. Qualify native metadata/session compatibility and bounded migration/restore without claiming durable jobs or release readiness.

**Evidence:** [Explicit runtime configuration and limits](private-runtime-configuration.md); [P16 source qualification](evidence/p16-qualification-2026-10-09.json)

**Remaining:** Project roles, egress/retention, encrypted/offline production packaging, queued workers, cancellation/recovery, coordinated production restoration, expert isolation, independent reproduction and release/customer gates remain open.

### P17 — Durable authentication audit and browser-session revocation

**Packet status:** tested. **Mapped outcomes:** D06.

Reserve login limits in shared metadata, record privacy-conscious authentication evidence, bind browser sessions to current authority and provide retry-safe operator revocation/cancellation of unused typed approvals. Qualify real private middleware and concurrent PostgreSQL admission.

**Evidence:** [Authentication audit and revocation](AUTHENTICATION_GOVERNANCE.md); [P17 source qualification](evidence/p17-qualification-2026-10-09.json)

**Remaining:** Project roles, egress/retention, identity-provider/MFA enrollment, complete security/deployment/recovery qualification, expert isolation, independent reproduction and all release/customer gates remain open.

### P18 — Recorded project authority across native APIs and MCP

**Packet status:** tested. **Mapped outcomes:** D06.

Bind datasets, pre-upload pipelines and registered artifacts to explicit projects; enforce developer/reviewer/admin authority across native API, media, MCP and typed approvals. Preserve legacy assertions, exact retries and revocation evidence. This is partial D06.

**Evidence:** [Project authorization foundation](PROJECT_AUTHORIZATION_IMPLEMENTATION.md); [P18 source qualification](evidence/p18-qualification-2026-10-10.json)

**Remaining:** Project/reviewer UI, identity-provider/MFA enrollment, egress/retention, tamper-proof audit, durable jobs, qualified expert isolation, independent reproduction, production recovery and all release/customer gates remain open.

### P19 — Role-aware project workspace and explicit development context

**Packet status:** tested. **Mapped outcomes:** D06, D12.

Expose current projects and roles, filter native records, bind browser development/upload/checkpoints to an explicit project and provide read-only report access. Retain server authority checks and legacy compatibility; do not relabel or reassign existing resources.

**Evidence:** [Project workspace implementation](PROJECT_WORKSPACE_IMPLEMENTATION.md); [P19 source qualification](evidence/p19-qualification-2026-10-10.json)

**Remaining:** Full independent review/findings/approvals/reproduction, member/enrollment UI, SSO/MFA, egress/retention, tamper-proof audit, durable job authority, expert isolation, comprehensive accessibility, production recovery and all release/customer gates remain open.

### P20 — Attributable exact-package findings and developer responses

**Packet status:** tested. **Mapped outcomes:** D09, D12.

Extend the project workspace with reviewer findings/dispositions, developer responses and retained exact-package discussion receipts. Reject unauthorized, conflicting or stale mutations; preserve historical evidence and download original package plus fresh discussion snapshots.

**Evidence:** [Exact-package review implementation](PACKAGE_REVIEW_IMPLEMENTATION.md); [P20 source qualification](evidence/p20-qualification-2026-10-10.json)

**Remaining:** Complete independent reviewer/author separation, clean-environment reproduction, organizational exceptions/approval and downstream invalidation, retention/deletion procedures, comprehensive accessibility, durable jobs/recovery, Linux expert isolation and release/value/customer gates remain open.

### P21 — Offline native CSV scoring verification and full receipts

**Packet status:** tested. **Mapped outcomes:** D09, D12.

Bind full batch receipts to exact CSV bytes and scoring runtime; authorize digest-pinned downloads and independently verify exported native scores in a clean fixed runtime across batch sizes. Expose evidence anchors and keyboard downloads.

**Evidence:** [Offline native score verification](OFFLINE_SCORING_IMPLEMENTATION.md); [P21 source qualification](evidence/p21-qualification-2026-10-10.json)

**Remaining:** Full refit/assessment reproduction, artifact authenticity, expert isolation, organizational independence/exceptions/approval, full accessibility, data egress/retention, durable jobs/offline installation/recovery and all release/value/customer gates remain open.

### P22 — Durable exact-package integrity jobs and fenced receipts

**Packet status:** tested. **Mapped outcomes:** D07, D12.

Record bounded read-only native package checks before broker dispatch; recheck project authority/runtime, fence duplicate/expired workers and retain cancellation/result history. Expose explicit keyboard queue, status, cancellation and freshly authorized receipts. No native model state is loaded.

**Evidence:** [Durable native job foundation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md); [P22 source qualification](evidence/p22-qualification-2026-10-10.json)

**Remaining:** Training/search/scoring migration, durable assistant/mission grants, private Redis TLS and installation packaging, coordinated job backup/restore and production recovery, expert isolation, full accessibility and all release/value/customer gates remain open.

### P23 — Private native job preflight and TLS/quiescent recovery qualification

**Packet status:** tested. **Mapped outcomes:** D07.

Fail closed before private worker/dispatcher startup unless PostgreSQL TLS, migrations and the real broker connection pass. Qualify authenticated Redis TLS, real broker removal, exact quiescent job database/artifact restore and empty-broker recovery under unchanged leases and attempt budgets.

**Evidence:** [Private native job startup and recovery](PRIVATE_JOB_RUNTIME_IMPLEMENTATION.md); [P23 source qualification](evidence/p23-qualification-2026-10-10.json)

**Remaining:** Complete private installation/offline packaging, production supervisor/resource/clock/machine-loss and live-backup qualification, migration of training/search/scoring, expert isolation and every release/value/customer gate remain open.

### P24 — Durable exact-package native CSV scoring and full receipts

**Packet status:** tested. **Mapped outcomes:** D04, D07, D09, D12.

Queue bounded registered CSV scoring against exact frozen native packages; pin input bytes/parser and both dataset authorities, fence atomic full-result publication, authorize digest-pinned downloads and reuse isolated offline parity verification. Provide explicit developer preparation/submission and reviewer receipt inspection.

**Evidence:** [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json)

**Remaining:** Training/search and other scoring-profile migration, durable assistant/mission grants, complete private/offline packaging, production resource/clock/hard-timeout/live-backup/machine-loss recovery, artifact authenticity/full reproduction, expert isolation, full accessibility and every release/value/customer gate remain open.

### P25 — Private native scoring restore and empty-broker recovery qualification

**Packet status:** tested. **Mapped outcomes:** D04, D07, D09.

Extend the disposable private TLS recovery fixture with calibrated native classification and regression scoring, exact full-result/input/authority restore, natural orphan leases, observed Celery duplicate completions and fail-closed changed/missing-input/current-authority checks. Retain synthetic recovered packages for independent score replay.

**Evidence:** [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json)

**Remaining:** Production interrupted-scoring/supervisor/clock/hard-timeout/live-backup/machine-loss recovery, complete private/offline installation, training/search migration, authenticity/retention/egress, full refit/assessment reproduction, expert isolation, accessibility and all release/value/customer gates remain open.

### P26 — Exact native execution receipts in package review

**Packet status:** tested. **Mapped outcomes:** D04, D06, D09, D12.

Let review findings, responses and dispositions cite a successful native integrity or CSV scoring receipt from the exact package. Retain attributable, digest-bound references, recheck model and input authority, and expose keyboard attachment and freshly authorized receipt download.

**Evidence:** [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json)

**Remaining:** Full refit/assessment reproduction, organizational independence/exceptions/approval, expert isolation, comprehensive accessibility, training/search migration, private/offline installation, authenticity/retention/egress, production recovery and all release/value/customer gates remain open.

### P27 — Reference-checked multiclass objective execution

**Packet status:** tested. **Mapped outcomes:** D01, D04, D07.

Use support-weighted average ranks for requested multiclass ROC-AUC, retaining independent scikit-learn full assessment and exact declared-method/source receipts. Reject malformed encoded labels before conversion; compare native stopping histories, selected models and replay against reference callbacks under unchanged scientific and runtime budgets.

**Evidence:** [Multiclass objective execution](MULTICLASS_METRIC_RUNTIME_IMPLEMENTATION.md); [P27 source qualification](evidence/p27-qualification-2026-10-10.json)

**Remaining:** Full independent refit/assessment reproduction, production capacity/recovery, private offline installation, training/search job migration, expert isolation, egress/retention, accessibility and every release/value/customer gate remain open.

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

**Progress:** Explicit task/target/positive-label/objective contract is frozen with native runs and carried through assessment/scoring. UI and assistant preserve accepted task; binary, 65-class and low-cardinality regression behavior has local regression coverage. Full contract/channel validation remains open. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; historical paths remain unverified. P07 aligns native tuning selection with accepted metric/direction/cost semantics, rejects contradictions and records exact winner/refit evidence; fitter criteria were outside P07 scope. P09 binds current native early stopping to the accepted metric across initial training, fold fitting, selection/tuning and candidate refits. Per-round values, selected scoring rounds and separate surrogate loss/weights are retained; undefined criteria block without fallback. Disabled stopping excludes validation data from fitting. Historical paths, protected confirmatory protocols and full milestone qualification remain open. P27 adds method-named support-weighted rank AUC for requested multiclass stopping, retaining independent sklearn full assessment, input validation and unavailable-objective blocking. Reference callback histories, selected models and replay match across all three native boosters; private/full workflow qualification passes with unchanged budgets. No full reproduction, capacity or release claim.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json); [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json); [P27 source qualification](evidence/p27-qualification-2026-10-10.json)

### D02 Shared validation and fold-local preprocessing

Preserve time, entity, and outcome-window constraints through early stopping, encoding, selection, tuning, and calibration. Fit learned operations within their training partitions.

**Acceptance:** Export fold membership and fit provenance; no prohibited overlap or silent shuffled fallback.

**Source mapping:** Claude CC-1/CC-5; GPT P02/P03; Gemini C2/C3.

**Progress:** Strict time/entity/outcome-window partitions and shared current booster CV/SFS/HPO folds record memberships. New raw-input recipes bind the split/version; purifier, encoding and imputation fit within model/fold partitions. Focused temporal/group and XGBoost classification/regression replay coverage is recorded in P03. Full alternate/search/supervised-encoding and legacy-path qualification remain open; constrained target encoding stays blocked. P04 adds shared classification/regression development assessment, complete fold-metric coverage, frozen target/task checks and fold-local automatic binary weights. Numeric temporal/grouped CV spans three boosters plus binary alternate CV; full search/encoding and objective consistency remain open. P05 adds input/configuration-bound native fit receipts and candidate-specific selected-feature CV with explicit post-selection limitations; exact-version acceptance preserves prior model evidence. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; historical paths remain unverified. P07 records tuning trial/curve fold-local transformations and native fit receipts, complete objective availability and fold-training class-weight policy. Separate candidate assessment remains exploratory. P09 binds current native early stopping to the accepted metric across initial training, fold fitting, selection/tuning and candidate refits. Per-round values, selected scoring rounds and separate surrogate loss/weights are retained; undefined criteria block without fallback. Disabled stopping excludes validation data from fitting. Historical paths, protected confirmatory protocols and full milestone qualification remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P03 implementation and limits](PURIFIER_REPLAY_IMPLEMENTATION.md); [P03 qualification](evidence/p03-qualification-2026-10-08.json); [P04 development validation and limits](DEVELOPMENT_VALIDATION_IMPLEMENTATION.md); [P04 source qualification](evidence/p04-qualification-2026-10-08.json); [P05 candidate evidence and limits](CANDIDATE_EVIDENCE_IMPLEMENTATION.md); [P05 source qualification](evidence/p05-qualification-2026-10-08.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json); [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json)

### D03 Protected final assessment

Separate development, calibration, and threshold choice from final holdout assessment. Record access and distinguish exploratory and confirmatory evidence.

**Acceptance:** Development cannot inspect final outcomes; changed candidates cannot inherit confirmatory status after holdout inspection.

**Source mapping:** Claude CC-6; GPT P03; Gemini C3.

**Progress:** Development artifacts exclude final outcomes; explicit assessment records attributable holdout access. Binary thresholds use development labels, and anomaly assessment has no holdout threshold search. Evidence is always exploratory; confirmatory/reuse protocols remain open. P10 adds source/target/final-row identity, receipt-before-read accounting and exact/overlapping/unknown reuse across executions. Failed/interrupted attempts and actor snapshots remain attributable; history reads do not deserialize outcomes. Exact assessment exports and a resumed, keyboard-operated history panel are qualified locally. All evidence remains exploratory; confirmatory protocols and complete milestone qualification remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json)

### D04 Immutable runs and reliable scoring

Version dataset, contract, transforms, models, evaluations and bundles by run. Preserve older iterations; fail explicitly on required-calibration failure and make anomaly scores batch invariant.

**Acceptance:** Iteration N+1 cannot overwrite N; evaluated and bundled scores match across row ordering and batch sizes within declared tolerances.

**Source mapping:** Claude CC-7/RM-7; GPT P06; Repository artifact and scoring inspection.

**Progress:** Immutable native executions, assessment receipts, candidate refits, unique bundles/batch outputs and hash verification are implemented. P03 adds UUID preprocessing versions, raw/recipe snapshots, fitted purifier replay and feature-subset raw dependencies. Focused XGBoost raw scoring/calibration, category, alignment and chunk parity are tested. Complete immutable stages/jobs, independent reproduction and concurrency/recovery qualification remain open. P05 adds input/configuration-bound native fit receipts and candidate-specific selected-feature CV with explicit post-selection limitations; exact-version acceptance preserves prior model evidence. P07 preserves tuning selection inside immutable candidate manifests and uses unique legacy refit paths; failed/stopped tuning cannot publish completion. Per-file search/job projections remain mutable. P09 binds current native early stopping to the accepted metric across initial training, fold fitting, selection/tuning and candidate refits. Per-round values, selected scoring rounds and separate surrogate loss/weights are retained; undefined criteria block without fallback. Disabled stopping excludes validation data from fitting. Historical paths, protected confirmatory protocols and full milestone qualification remain open. P10 adds source/target/final-row identity, receipt-before-read accounting and exact/overlapping/unknown reuse across executions. Failed/interrupted attempts and actor snapshots remain attributable; history reads do not deserialize outcomes. Exact assessment exports and a resumed, keyboard-operated history panel are qualified locally. All evidence remains exploratory; confirmatory protocols and complete milestone qualification remain open. P11 pins package readiness/builds to verified execution/assessment evidence and scoring/export to immutable bundle IDs. Publication is staged and current-version checked; receipts bind manifest metadata, required native artifacts and original review evidence. Historical versions remain usable; UI exposes blocked states and keyboard-accessible package/score receipts. Full distributed durability, independent reproduction and release qualification remain open. P13 prevents upload and encoded CSV collisions with UUID names/exclusive creation, blocks success when required encoding metadata fails, and removes arbitrary legacy fallback selection. Full immutable legacy stages and distributed publication/recovery remain open. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open. P15 archives native training-only numeric diagnostic matrices and method/state metadata for each execution and selected candidate subset. Detail inspection and saved-run refresh use exact execution identity with integrity checks; latest projections cannot silently replace saved evidence. Historical inputs remain unverified. P25 adds synthetic private TLS scoring recovery qualification: exact quiescent metadata/input/package/full-result restore, natural orphan leases, actual duplicate completions, changed/missing-input and current-authority blocking, plus recovered-score exports. Native application behavior and budgets are unchanged; production interrupted-scoring/live-backup/machine-loss recovery and full reproduction/release gates remain open. P26 pins optional review references to exact successful native job results and specifications. Job retention, complete scoring receipts, digest/snapshot validation and exact request replay are tested; references do not certify independent reproduction or authenticity. P27 adds method-named support-weighted rank AUC for requested multiclass stopping, retaining independent sklearn full assessment, input validation and unavailable-objective blocking. Reference callback histories, selected models and replay match across all three native boosters; private/full workflow qualification passes with unchanged budgets. No full reproduction, capacity or release claim.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P03 implementation and limits](PURIFIER_REPLAY_IMPLEMENTATION.md); [P03 qualification](evidence/p03-qualification-2026-10-08.json); [P05 candidate evidence and limits](CANDIDATE_EVIDENCE_IMPLEMENTATION.md); [P05 source qualification](evidence/p05-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json); [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json); [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json); [P11 package handoff and limits](PACKAGE_HANDOFF_IMPLEMENTATION.md); [P11 source qualification](evidence/p11-qualification-2026-10-09.json); [Managed native storage implementation](MANAGED_STORAGE_IMPLEMENTATION.md); [P13 source qualification](evidence/p13-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json); [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json); [P27 source qualification](evidence/p27-qualification-2026-10-10.json)

### D05 Trustworthy diagnostics

Correct categorical collinearity treatment, describe combined importance as a heuristic, and use associational terminology for sequential pattern detection.

**Acceptance:** Diagnostics are invariant to arbitrary category-code permutations; uncertainty and limitations accompany comparisons.

**Source mapping:** Claude CC-9; GPT FIX-04; Gemini C4.

**Progress:** Categorical codes no longer enter numeric VIF; combined importance is a ranking heuristic, sequential patterns are associational, and anomaly metrics are ranking-only. Unsupported multiclass SHAP/PDP is disclosed/blocked. Grouped diagnostics and paired-comparison uncertainty remain open. P04 reports undefined constant-target R² and incomplete metric aggregates explicitly, labels fold spread as descriptive, records actual adapter training metrics and exposes task-specific validation limitations. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; historical paths remain unverified. P07 exposes failed/unusable attempts and curve gaps without invented spread; surrogate importance/range guidance is explicitly descriptive rather than causal. P09 binds current native early stopping to the accepted metric across initial training, fold fitting, selection/tuning and candidate refits. Per-round values, selected scoring rounds and separate surrogate loss/weights are retained; undefined criteria block without fallback. Disabled stopping excludes validation data from fitting. Historical paths, protected confirmatory protocols and full milestone qualification remain open. P15 centers/scales native numeric auxiliary regressions explicitly and distinguishes finite, unbounded/precision-indistinguishable, constant, excluded, solver and compute-budget states. Exact category-derived output groups are excluded; fixed VIF severity/removal thresholds are removed. Grouped categorical methods and paired uncertainty remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P04 development validation and limits](DEVELOPMENT_VALIDATION_IMPLEMENTATION.md); [P04 source qualification](evidence/p04-qualification-2026-10-08.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json); [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json); [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json)

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

**Progress:** Real server sessions/CSRF, route guards, protected REST/media and streaming credentials replace browser-local sign-in. Production HTTP boundary tests and browser login/reload/logout were exercised. Project roles, MCP identity, audit/retention and egress policy remain open. P02 adds disposable non-admin session/CSRF CI on every PR and repairs HPO/SFS/pipeline payload parsing under real sessions. P12 binds local MCP reads/proposals to active installation actors and explicit dataset grants, with access reservations and authority rechecks before output. Live stdio grant changes/revocation and retained audit snapshots are qualified; HTTP/SSE and unverified direct execution are blocked. REST project roles, exact approvals, expert isolation, egress/retention and deployment/security qualification remain open. P13 validates native REST file identifiers and confines table selectors/generated files to managed storage before reads, including traversal, hidden, symlink and nonregular-file rejection. This is a root boundary, not REST project/dataset authorization; roles, egress/retention and release threat-model qualification remain open. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open. P16 adds an explicit fail-closed private runtime with external secret/value-file sources, explicit hosts/HTTPS origins, secure cookies/redirects, an existing artifact root and PostgreSQL verify-full TLS. Both SQLite and PostgreSQL full marked suites pass unchanged assertions, skip and coverage budgets. Real private middleware/session/CSRF, non-superuser migrations, certificate/hostname rejection, restart persistence and a quiescent synthetic database/artifact restore are qualified; the live-reload stack rejects private mode. This is metadata/configuration support, not PostgreSQL dataset intake or qualified production deployment. Project roles, egress/retention, durable workers, expert isolation, independent reproduction and production recovery remain open. P17 shares bounded password-login admission across API/admin processes, records authentication facts without raw credentials, requires current browser-session revisions and adds retry-safe installation-operator revocation with unused typed-approval cancellation. Private TLS PostgreSQL five-process budget/revocation checks, session/audit restart/restore and marked suites on both databases pass. Development browser denial, unaffected-user access and fresh-session retry are independently checked. Historical unbound sessions require reauthentication. Operator labels are assertions, not authenticated human identity; project roles, tamper-proof audit/retention, egress and full private release qualification remain open. P18 adds explicit project membership and developer/reviewer/admin roles, durable activation, scoped native API/pipeline/table/artifact access, project-aware MCP and revision-bound typed approvals. Legacy adoption records current assertions; cross-project holdout reuse counts remain while unrelated details are withheld. Full legacy/scientific matrices, project regressions, governed browser/stdio workflows and private PostgreSQL role/retry/restart/restore fixtures are qualified with separately pinned sources. This is partial D06; unactivated development remains unqualified. Project/reviewer UI, SSO/MFA/enrollment, egress/retention, tamper-proof audit, durable job authority, expert isolation and full private release qualification remain open. P19 adds a server-backed project picker, role explanations and project-filtered dataset/pipeline records. Developer workspaces pin upload/checkpoint ownership and saved-pipeline operations to the selected project; reviewers/admins browse records and download existing reports. Fresh membership checks, canceled/stale response handling, explicit blocked states, visible selection after redirects and keyboard/browser workflows are qualified. This is partial D06/D12; full reviewer findings/approvals/reproduction, member/enrollment UI, SSO/MFA, egress/retention, durable jobs, expert isolation, comprehensive accessibility and release/customer gates remain open. P26 rechecks cited scoring-input access on discussion adoption, reads and downloads, including final HTTP response checks. A cross-project input reassignment withholds linked evidence even for an actor with both memberships; retained events remain unchanged.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [P12 MCP access and limits](MCP_ACCESS_IMPLEMENTATION.md); [P12 source qualification](evidence/p12-qualification-2026-10-09.json); [Managed native storage implementation](MANAGED_STORAGE_IMPLEMENTATION.md); [P13 source qualification](evidence/p13-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json); [Explicit runtime configuration and limits](private-runtime-configuration.md); [P16 source qualification](evidence/p16-qualification-2026-10-09.json); [Authentication audit and revocation](AUTHENTICATION_GOVERNANCE.md); [P17 source qualification](evidence/p17-qualification-2026-10-09.json); [Project authorization foundation](PROJECT_AUTHORIZATION_IMPLEMENTATION.md); [P18 source qualification](evidence/p18-qualification-2026-10-10.json); [Project workspace implementation](PROJECT_WORKSPACE_IMPLEMENTATION.md); [P19 source qualification](evidence/p19-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json)

### D07 Durable execution and production packaging

PostgreSQL, dedicated Celery/Redis jobs, bounded concurrency, cancellation, recovery, monitoring and backups. Production TLS/static assets and reproducible private deployment; Django 5.2 LTS and Angular 22.

**Acceptance:** Clean install, upgrade/rollback, worker/broker recovery and coordinated data/artifact restore pass on the supported Linux profile.

**Source mapping:** Claude RM-2; GPT P04 and operations gaps; Repository development topology.

**Progress:** Django 5.2 LTS/DRF 3.16 and Angular/Material 22 with Node 24/TypeScript 6 are adopted; local framework tests/builds pass. Database/jobs remain SQLite/synchronous/local threads; production installation, PostgreSQL/Celery, offline packaging and recovery are not qualified. P02 qualifies a public-dependency core build without the optional SDK and a full marked Linux/ARM64 backend run; production deployment and locked offline supply remain open. P16 adds an explicit fail-closed private runtime with external secret/value-file sources, explicit hosts/HTTPS origins, secure cookies/redirects, an existing artifact root and PostgreSQL verify-full TLS. Both SQLite and PostgreSQL full marked suites pass unchanged assertions, skip and coverage budgets. Real private middleware/session/CSRF, non-superuser migrations, certificate/hostname rejection, restart persistence and a quiescent synthetic database/artifact restore are qualified; the live-reload stack rejects private mode. This is metadata/configuration support, not PostgreSQL dataset intake or qualified production deployment. Project roles, egress/retention, durable workers, expert isolation, independent reproduction and production recovery remain open. P22 adds one exact-package integrity job with durable request/event/result receipts, explicit dedicated Celery/Redis dispatch, database admission/lease bounds, cooperative cancellation, authority/runtime rechecks and fenced terminal publication. Actual prefork delivery, killed-worker recovery after injected lease expiry, duplicate/stale publication, active cancellation and failed broker connection recovery pass against TLS PostgreSQL metadata. Real native package keyboard queue/status/receipt handoff passes in the review workspace. This is partial D07/D12: training/search/scoring migration, private Redis TLS, complete private worker packaging, job backup/restore and production recovery, expert isolation, complete accessibility and release/customer gates remain open. P23 adds a fail-closed private launcher and actual metadata TLS/migration/broker preflight. Authenticated Redis TLS and wrong CA/hostname/credential rejection pass. Actual broker removal retains requests; a quiescent four-state native-job PostgreSQL/artifact snapshot restores exactly into a separate database with an empty broker. The actual dispatcher naturally expires the original 180-second controlled abandoned lease, fences its old token and a fresh prefork worker publishes pending results once; terminal history and original event prefixes remain intact. Both full metadata matrices pass 2032 tests and six skips with unchanged gates. This is bounded synthetic Linux qualification, not complete private packaging, live/machine-loss disaster recovery, expert isolation or D07/release/customer completion. P25 adds synthetic private TLS scoring recovery qualification: exact quiescent metadata/input/package/full-result restore, natural orphan leases, actual duplicate completions, changed/missing-input and current-authority blocking, plus recovered-score exports. Native application behavior and budgets are unchanged; production interrupted-scoring/live-backup/machine-loss recovery and full reproduction/release gates remain open. P27 adds method-named support-weighted rank AUC for requested multiclass stopping, retaining independent sklearn full assessment, input validation and unavailable-objective blocking. Reference callback histories, selected models and replay match across all three native boosters; private/full workflow qualification passes with unchanged budgets. No full reproduction, capacity or release claim.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [Explicit runtime configuration and limits](private-runtime-configuration.md); [P16 source qualification](evidence/p16-qualification-2026-10-09.json); [Durable native job foundation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md); [P22 source qualification](evidence/p22-qualification-2026-10-10.json); [Private native job startup and recovery](PRIVATE_JOB_RUNTIME_IMPLEMENTATION.md); [P23 source qualification](evidence/p23-qualification-2026-10-10.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json); [P27 source qualification](evidence/p27-qualification-2026-10-10.json)

### D08 Governed assistant and sandboxed expert Python

Typed actions plus generated/user-authored Python in separate Linux gVisor/runsc jobs. Bind approval to code/input/environment/partition/resource policy; keep fitted expert state sandbox-only through replay and scoring.

**Acceptance:** Supported expert transformations/scorers succeed; unauthorized data/host/network access and resource exhaustion fail safely; no fallback into host execution.

**Source mapping:** Claude CC-3/CC-7/RM-3; GPT FIX-07/P04; Gemini C5; User first-release expert-code requirement.

**Progress:** Unsafe in-process expert Python was removed; execute_code fails closed before customer data loads. Dedicated Linux gVisor isolation, exact approvals, valid expert operations and replay/scoring remain unimplemented and mandatory for first release. P12 binds local MCP reads/proposals to active installation actors and explicit dataset grants, with access reservations and authority rechecks before output. Live stdio grant changes/revocation and retained audit snapshots are qualified; HTTP/SSE and unverified direct execution are blocked. REST project roles, exact approvals, expert isolation, egress/retention and deployment/security qualification remain open. P13 requires client-selected XGBoost explanation models to belong to a hash-verified immutable execution and matching dataset; development-only diagnostics support legitimate native overrides. Exact action approvals and isolated expert execution/replay/scoring remain unimplemented and mandatory. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P12 MCP access and limits](MCP_ACCESS_IMPLEMENTATION.md); [P12 source qualification](evidence/p12-qualification-2026-10-09.json); [Managed native storage implementation](MANAGED_STORAGE_IMPLEMENTATION.md); [P13 source qualification](evidence/p13-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json)

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

**Progress:** Environment manifests and independently hashed assessment/model-card artifacts provide evidence foundations. P01-P11 left reviewer findings/responses/approvals and clean-environment reproduction open. P10 adds source/target/final-row identity, receipt-before-read accounting and exact/overlapping/unknown reuse across executions. Failed/interrupted attempts and actor snapshots remain attributable; history reads do not deserialize outcomes. Exact assessment exports and a resumed, keyboard-operated history panel are qualified locally. All evidence remains exploratory; confirmatory protocols and complete milestone qualification remain open. P11 pins package readiness/builds to verified execution/assessment evidence and scoring/export to immutable bundle IDs. Publication is staged and current-version checked; receipts bind manifest metadata, required native artifacts and original review evidence. Historical versions remain usable; UI exposes blocked states and keyboard-accessible package/score receipts. Full distributed durability, independent reproduction and release qualification remain open. P20 adds exact-package review discussion with attributable reviewer findings/dispositions and developer responses. Active project roles, exact retry receipts, optimistic revisions, concurrent publication, context/integrity freshness and retained historical events are qualified on both metadata engines. Browser keyboard handoff and exact package/discussion downloads pass. Finding closure never confers model or production approval; full independence rules, exceptions/approvals, clean-environment reproduction, full retention and comprehensive accessibility remain open. P21 adds input/runtime-bound full CSV scoring receipts, current-role exact downloads and installed offline native score-parity verification. Clean fixed runtimes without network or installation data reproduce 300-row XGBoost classification/regression exports across whole batches and chunk sizes 1/17/64; calibrated logistic replay and tamper/runtime/authority boundaries pass. Core modules and declared tolerances are recorded. Native serialized state requires explicit trust; full refit/assessment reproduction, independent approval and release qualification remain open. P25 adds synthetic private TLS scoring recovery qualification: exact quiescent metadata/input/package/full-result restore, natural orphan leases, actual duplicate completions, changed/missing-input and current-authority blocking, plus recovered-score exports. Native application behavior and budgets are unchanged; production interrupted-scoring/live-backup/machine-loss recovery and full reproduction/release gates remain open. P26 connects findings, responses and dispositions to successful native integrity/scoring receipts from the exact package, with separate review and execution actors and full result downloads. Independent refit/assessment reproduction and organizational approval remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json); [P11 package handoff and limits](PACKAGE_HANDOFF_IMPLEMENTATION.md); [P11 source qualification](evidence/p11-qualification-2026-10-09.json); [Exact-package review implementation](PACKAGE_REVIEW_IMPLEMENTATION.md); [P20 source qualification](evidence/p20-qualification-2026-10-10.json); [Offline native score verification](OFFLINE_SCORING_IMPLEMENTATION.md); [P21 source qualification](evidence/p21-qualification-2026-10-10.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json)

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

**Progress:** Explicit declaration fields, session-aware navigation, clearer package-versus-production state and bounded keyboard/browser smoke checks are implemented. Full screen-reader and independent-review workflow qualification remains open. P02 makes the bounded keyboard/session/reload and authenticated API checks mandatory in CI; all legacy journeys and screen-reader review remain unqualified. P10 adds source/target/final-row identity, receipt-before-read accounting and exact/overlapping/unknown reuse across executions. Failed/interrupted attempts and actor snapshots remain attributable; history reads do not deserialize outcomes. Exact assessment exports and a resumed, keyboard-operated history panel are qualified locally. All evidence remains exploratory; confirmatory protocols and complete milestone qualification remain open. P11 pins package readiness/builds to verified execution/assessment evidence and scoring/export to immutable bundle IDs. Publication is staged and current-version checked; receipts bind manifest metadata, required native artifacts and original review evidence. Historical versions remain usable; UI exposes blocked states and keyboard-accessible package/score receipts. Full distributed durability, independent reproduction and release qualification remain open. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open. P15 adds expandable numeric diagnostic tables and keyboard/focus-managed dialogs with states, provenance and limitations, independent of SHAP availability. Late diagnostic/restore responses are rejected, and assistant cache forwarding retains current execution identity. Comprehensive accessibility remains open. P19 adds a server-backed project picker, role explanations and project-filtered dataset/pipeline records. Developer workspaces pin upload/checkpoint ownership and saved-pipeline operations to the selected project; reviewers/admins browse records and download existing reports. Fresh membership checks, canceled/stale response handling, explicit blocked states, visible selection after redirects and keyboard/browser workflows are qualified. This is partial D06/D12; full reviewer findings/approvals/reproduction, member/enrollment UI, SSO/MFA, egress/retention, durable jobs, expert isolation, comprehensive accessibility and release/customer gates remain open. P20 adds exact-package review discussion with attributable reviewer findings/dispositions and developer responses. Active project roles, exact retry receipts, optimistic revisions, concurrent publication, context/integrity freshness and retained historical events are qualified on both metadata engines. Browser keyboard handoff and exact package/discussion downloads pass. Finding closure never confers model or production approval; full independence rules, exceptions/approvals, clean-environment reproduction, full retention and comprehensive accessibility remain open. P21 adds input/runtime-bound full CSV scoring receipts, current-role exact downloads and installed offline native score-parity verification. Clean fixed runtimes without network or installation data reproduce 300-row XGBoost classification/regression exports across whole batches and chunk sizes 1/17/64; calibrated logistic replay and tamper/runtime/authority boundaries pass. Core modules and declared tolerances are recorded. Native serialized state requires explicit trust; full refit/assessment reproduction, independent approval and release qualification remain open. P22 adds one exact-package integrity job with durable request/event/result receipts, explicit dedicated Celery/Redis dispatch, database admission/lease bounds, cooperative cancellation, authority/runtime rechecks and fenced terminal publication. Actual prefork delivery, killed-worker recovery after injected lease expiry, duplicate/stale publication, active cancellation and failed broker connection recovery pass against TLS PostgreSQL metadata. Real native package keyboard queue/status/receipt handoff passes in the review workspace. This is partial D07/D12: training/search/scoring migration, private Redis TLS, complete private worker packaging, job backup/restore and production recovery, expert isolation, complete accessibility and release/customer gates remain open. P26 adds explicit keyboard receipt selection, removal and downloading in package review, preserves job context during writes, and retains exact references across ambiguous retries. Real browser workflows pass; comprehensive accessibility remains open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json); [P11 package handoff and limits](PACKAGE_HANDOFF_IMPLEMENTATION.md); [P11 source qualification](evidence/p11-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json); [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json); [Project workspace implementation](PROJECT_WORKSPACE_IMPLEMENTATION.md); [P19 source qualification](evidence/p19-qualification-2026-10-10.json); [Exact-package review implementation](PACKAGE_REVIEW_IMPLEMENTATION.md); [P20 source qualification](evidence/p20-qualification-2026-10-10.json); [Offline native score verification](OFFLINE_SCORING_IMPLEMENTATION.md); [P21 source qualification](evidence/p21-qualification-2026-10-10.json); [Durable native job foundation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md); [P22 source qualification](evidence/p22-qualification-2026-10-10.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json)

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
