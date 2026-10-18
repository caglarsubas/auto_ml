# DeclarAI product development roadmap

Updated 2026-10-18. Generated from `product-roadmap.json`; edit the ledger and run `python3 scripts/render_product_roadmap.py`.

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

### P28 — Immutable grouped categorical and numeric dependence

**Packet status:** tested. **Mapped outcomes:** D04, D05, D06, D12.

Retain centered training-input group bases and descriptive GVIF with explicit representation, rank, precision and compute states. Replay exact native evidence without fitted state/outcomes; allow current reviewers to inspect numeric/grouped diagnostics and expose accessible summaries without universal cutoffs.

**Evidence:** [Grouped input diagnostics](GROUPED_COLLINEARITY_IMPLEMENTATION.md); [P28 source qualification](evidence/p28-qualification-2026-10-11.json)

**Remaining:** Paired uncertainty, lossy-source categorical reconstruction, full scientific/accessibility qualification, expert isolation, independent refit/assessment reproduction, private/offline packaging, production recovery and all release/value/customer gates remain open.

### P29 — Fixed private native API and offline image handoff

**Packet status:** tested. **Mapped outcomes:** D06, D07.

Build an explicit application source allowlist into a fresh system-dependency image snapshot, retain runtime/package inventories, launch fixed unprivileged native services only after verification/TLS/migration preflight, and import one exact tag-free image through a trusted-digest handoff.

**Evidence:** [Private native API packaging](PRIVATE_API_PACKAGING_IMPLEMENTATION.md); [P29 source qualification](evidence/p29-qualification-2026-10-11.json)

**Remaining:** Complete frontend/TLS ingress and offline installation, supply-chain authentication, upgrade/rollback and production recovery, comprehensive egress/retention, training/search migration, expert isolation, independent reproduction and all release/value/customer gates remain open.

### P30 — Fixed buffering private TLS ingress

**Packet status:** tested. **Mapped outcomes:** D06, D07.

Build one canonical-authority NGINX image from exact trusted dependencies, separate the edge network and read-only socket/certificate mounts, and qualify real HTTPS identity, CSRF, buffered uploads and current media authorization without application changes.

**Evidence:** [Fixed private TLS ingress](PRIVATE_TLS_INGRESS_IMPLEMENTATION.md); [P30 source qualification](evidence/p30-qualification-2026-10-11.json)

**Remaining:** Complete frontend/static assets and multi-image offline installation, supply-chain authentication, upgrades/rollback and production recovery, comprehensive egress/retention, training/search migration, expert isolation, independent refit reproduction and all release/value/customer gates remain open.

### P31 — Compiled same-origin private frontend

**Packet status:** tested. **Mapped outcomes:** D06, D07, D12.

Compile an allowlisted source snapshot with recorded locked compiler inputs, seal static assets into the fixed TLS ingress, preserve API/media authority and qualify a real same-origin private browser workflow.

**Evidence:** [Compiled private frontend](PRIVATE_FRONTEND_IMPLEMENTATION.md); [P31 source qualification](evidence/p31-qualification-2026-10-11.json)

**Remaining:** Complete restricted-network multi-image installation, authenticated software supply, upgrades/rollback and production recovery, client-source attribution, egress/retention, durable training/search, expert isolation, independent refit reproduction, complete private UI/accessibility and all release/value/customer gates remain open.

### P32 — Verified offline native image set

**Packet status:** tested. **Mapped outcomes:** D07.

Prepare pinned native dependencies and hand off four exact API/compiled-ingress/database/broker images through an externally trusted outer digest; verify all staged components before import and check identities/runtime inventories without service adoption.

**Evidence:** [Verified offline native image set](PRIVATE_IMAGE_SET_IMPLEMENTATION.md); [P32 source qualification](evidence/p32-qualification-2026-10-11.json)

**Remaining:** Complete restricted-network installation, operator profile/secrets/storage initialization, authenticated supply, fixed-image worker completion, upgrades/rollback and production recovery, egress/retention, training/search migration, expert isolation, independent reproduction, accessibility and every release/value/customer gate remain open.

### P33 — Packaged private native job execution

**Packet status:** tested. **Mapped outcomes:** D07.

Qualify actual separate fixed-image native worker/dispatcher execution under private TLS and daemon-verified isolation; correct PID-1 dispatcher shutdown and prove duplicate acknowledgement after warm worker exit.

**Evidence:** [Packaged private native jobs](PRIVATE_PACKAGED_JOBS_IMPLEMENTATION.md); [P33 source qualification](evidence/p33-qualification-2026-10-11.json)

**Remaining:** Complete restricted-network installation, operator profile/secrets/storage initialization, authenticated supply, upgrade/rollback and production recovery, training/search migration, comprehensive egress/retention, expert isolation, independent refit reproduction, accessibility and every release/value/customer gate remain open.

### P34 — Offline private application installation plans

**Packet status:** tested. **Mapped outcomes:** D07.

Render a reviewable, digest-bound native application-layer Compose plan and explicit operator prerequisites after verifying all four offline images and the sealed ingress configuration. No Docker operations or secret reads enter rendering.

**Evidence:** [Offline private application installation plan](PRIVATE_INSTALLATION_PLAN_IMPLEMENTATION.md); [P34 source qualification](evidence/p34-qualification-2026-10-11.json)

**Remaining:** Host prerequisite verification, dependency/secrets/storage initialization and service adoption remain open, along with authenticated supply, upgrade/rollback, production recovery, expert isolation and every release/value/customer gate.

### P35 — Private plan verification and filesystem prerequisites

**Packet status:** tested. **Mapped outcomes:** D07.

Verify digest-bound saved application plans and their supported profile, and inspect Linux filesystem metadata through pinned descriptors before installation. Qualify actual UID 10001 and fail-closed path/link/mode behavior with owned synthetic volumes.

**Evidence:** [Private plan verification and filesystem prerequisites](PRIVATE_INSTALLATION_CHECK_IMPLEMENTATION.md); [P35 source qualification](evidence/p35-qualification-2026-10-11.json)

**Remaining:** Secret contents/certificate trust, encryption/capacity/retention, network/socket setup, database and broker initialization, actual installation/adoption, authenticated supply, upgrade/rollback, production recovery, expert isolation and all release/value/customer gates remain open.

### P36 — Fresh private filesystem initialization

**Packet status:** tested. **Mapped outcomes:** D07.

Initialize a fresh Linux filesystem from a verified plan and bounded operator-delivered secrets, using pinned descriptors, exact identities and atomic no-replace publication. Preserve existing destinations and qualify interruption/race/retry behavior on owned volumes.

**Evidence:** [Fresh private filesystem initialization](PRIVATE_INSTALLATION_INIT_IMPLEMENTATION.md); [P36 source qualification](evidence/p36-qualification-2026-10-11.json)

**Remaining:** Certificate trust, encrypted storage/capacity/retention, network/socket and dependency provisioning, actual service adoption, authenticated supply, upgrades/rollback, production recovery, expert isolation and all release/value/customer gates remain open.

### P37 — Dedicated private networks and socket

**Packet status:** tested. **Mapped outcomes:** D07.

Bind dedicated local internal networks and an empty native socket volume to the verified plan and fresh initialization. Recheck local native Docker, exact resource ownership, mounts and safe socket identity; reject foreign/occupied resources without repair.

**Evidence:** [Dedicated private networks and socket](PRIVATE_INSTALLATION_RESOURCES_IMPLEMENTATION.md); [P37 source qualification](evidence/p37-qualification-2026-10-11.json)

**Remaining:** Dependency initialization and controlled application adoption remain open, with complete storage/security qualification, authenticated supply, upgrades/rollback, production recovery, expert isolation and all release/value/customer gates.

### P38 — Controlled private application adoption

**Packet status:** tested. **Mapped outcomes:** D07.

Adopt exact pinned application services after saved-plan, initialization, bound-resource, complete service-profile, sealed TLS/migration/application-role and client HTTPS checks. Preserve existing services and reject incompatible profiles; add complete owned Linux-root acceptance to the existing native CI fixture. Uses v2 ingress publication prerequisites while preserving v1 inspection and blocking legacy adoption before host access.

**Evidence:** [Controlled private application adoption](PRIVATE_INSTALLATION_ADOPT_IMPLEMENTATION.md); [P38 source qualification](evidence/p38-qualification-2026-10-11.json)

**Remaining:** Operator dependency provisioning/hardening, encrypted storage/capacity, authenticated supply, upgrades/rollback, production recovery, expert isolation, reproduction, accessibility and all release/value/customer gates remain open. Local profile checks do not qualify the complete Linux controller; hosted acceptance is required before merge.

### P39 — Final adoption receipt readiness

**Packet status:** tested. **Mapped outcomes:** D07.

Require the same complete active exact service profiles after HTTPS, and recheck bound dependency/socket membership before successful adoption receipt publication. Preserve all services on mismatch; qualify a real owned worker pause after valid HTTPS.

**Evidence:** [Adoption receipt readiness](PRIVATE_ADOPTION_READINESS_IMPLEMENTATION.md); [P39 source qualification](evidence/p39-qualification-2026-10-12.json)

**Remaining:** Dependency provisioning/hardening, complete storage/security qualification, authenticated supply, upgrades/rollback, production recovery, expert isolation and all release/value/customer gates remain open. Final source Linux acceptance remains required before merge.

### P40 — Fresh dependency preparation

**Packet status:** tested. **Mapped outcomes:** D07.

Prepare a new bound dependency root with captured approved credentials, selected-CA server validation, exact non-root/private resource profiles, root-owned configuration and empty PostgreSQL/broker storage. Publish with native no-replace semantics; preserve existing paths and source files.

**Evidence:** [Fresh dependency preparation](PRIVATE_DEPENDENCY_INIT_IMPLEMENTATION.md); [P40 source qualification](evidence/p40-qualification-2026-10-12.json)

**Remaining:** Actual dependency startup/database initialization, full hardening, migrations, encrypted storage/capacity/retention, supply authenticity, upgrades/rollback, production recovery and release/value/customer gates remain open.

### P41 — Controlled dependency startup and app database

**Packet status:** tested. **Mapped outcomes:** D07.

Start exact prepared non-root private dependency profiles, initialize the declared app database/role without elevation or credential repair, verify actual TLS/authentication, preserve same-identity startup history and apply the checks through managed application adoption.

**Evidence:** [Private dependency startup](PRIVATE_DEPENDENCY_START_IMPLEMENTATION.md); [P41 source qualification](evidence/p41-qualification-2026-10-12.json)

**Remaining:** Approved schema migration/account enrollment, complete storage/policy qualification, authenticated supply, upgrades/rollback, production recovery, expert isolation and release/value/customer gates remain open.

### P42 — Pinned fresh private schema initialization

**Packet status:** tested. **Mapped outcomes:** D07.

Describe the sealed migration graph without execution; initialize only a fresh schema from its explicitly approved digest with ordinary application TLS authority, atomic PostgreSQL DDL and immutable bound intent/results. Preserve history through repeat/recovery and block stale, foreign or partial state.

**Evidence:** [Fresh schema initialization](PRIVATE_SCHEMA_INIT_IMPLEMENTATION.md); [P42 source qualification](evidence/p42-qualification-2026-10-12.json)

**Remaining:** Account enrollment, full installation/storage/policy/cache/supply/upgrade/recovery/expert qualification and all release/value/customer gates remain open. Exact-head native Linux acceptance is required before merge.

### P43 — Ordinary account enrollment and fresh adoption

**Packet status:** tested. **Mapped outcomes:** D06, D07.

Enroll ordinary accounts into an explicit project scope with actual private preflight, private credential-file delivery, atomic attributable records and exact-current-state retry checks. Isolate adoption preflight media so empty customer artifacts remain unchanged until application startup. Qualify fresh schema/accounts/services and actual HTTPS roles.

**Evidence:** [Private account enrollment and fresh adoption](PRIVATE_ACCOUNT_ENROLLMENT_IMPLEMENTATION.md); [P43 source qualification](evidence/p43-qualification-2026-10-12.json)

**Remaining:** Final exact-head Linux acceptance is required before merge. Complete account lifecycle, cache/storage/policy/supply/upgrade/recovery/expert qualification and release/value/customer gates remain open.

### P44 — Private cache authentication and TLS

**Packet status:** tested. **Mapped outcomes:** D07.

Bind fresh v3 installation/dependency profiles to separately delivered cache credentials and selected trust. Require hostname-verified TLS with plaintext disabled, actual sealed API/worker cache parity and startup preflight, and credential-safe logs/traces. Preserve historical plans and existing roots without implicit migration.

**Evidence:** [Private cache authentication and TLS](PRIVATE_CACHE_TLS_IMPLEMENTATION.md); [P44 source qualification](evidence/p44-qualification-2026-10-12.json)

**Remaining:** Final exact-head Linux acceptance is required before merge. Cache recovery, account/storage/egress/supply/upgrade/recovery/expert and release/value/customer gates remain open.

### P45 — Bounded cache reconnection and owned-pool cleanup

**Packet status:** tested. **Mapped outcomes:** D07.

Recover from a failed initial cache connection through a fixed monotonic cooldown and serialized initialization; close owned pools deterministically. Qualify cold and warm authenticated exclusive-CA TLS recovery, same dependency identities/receipts, cache-loss misses and refusal of nonfixture interruption.

**Evidence:** [Bounded private cache recovery](PRIVATE_CACHE_RECOVERY_IMPLEMENTATION.md); [P45 source qualification](evidence/p45-qualification-2026-10-13.json)

**Remaining:** Final exact-head Linux acceptance is required before merge. Complete policy/account/storage/supply/upgrade/production-recovery/expert and release/value/customer gates remain open.

### P46 — Private broker CA-only TLS trust

**Packet status:** tested. **Mapped outcomes:** D07.

Capture bounded declared broker CA bytes and select a private Celery/Kombu transport with exclusive roots, hostname verification and TLS minimum. Use the same TLS class for dependency readiness; qualify actual producer/consumer/application roles and ambient-root bypass refusal without altering development transports or saved roots.

**Evidence:** [Private broker CA-only trust](PRIVATE_BROKER_TLS_IMPLEMENTATION.md); [P46 source qualification](evidence/p46-qualification-2026-10-13.json)

**Remaining:** Final exact-head Linux/private-role/queue/recovery acceptance is required before merge. Complete policy/account/storage/supply/upgrade/production-recovery/expert and release/value/customer gates remain open.

### P47 — Managed broker trust and replay through restart

**Packet status:** tested. **Mapped outcomes:** D07.

Extend the exclusively owned Linux fixture with validated broker interruption, same-process/pool CA-only reconnection, unavailable-state refusal and single AOF payload replay. Require unchanged dependency IDs/startup receipt and current API/worker/dispatcher ordinary preflight plus same-ID repeat application admission.

**Evidence:** [Managed broker restart qualification](PRIVATE_BROKER_RECOVERY_QUALIFICATION.md); [P47 source qualification](evidence/p47-qualification-2026-10-13.json)

**Remaining:** Exact-head hosted Linux controller and current main receipts required before merge. Full production recovery, upgrade/rollback, expert isolation and all release/value/customer gates remain open.

### P48 — Stable protected private secret capture

**Packet status:** tested. **Mapped outcomes:** D07.

Require absolute, regular, single-link mode-0400/0600 private credential files. Compare bounded repeated bytes and descriptor metadata before accepting Django, PostgreSQL or broker configuration; suppress underlying credential/path diagnostics. Qualify protected deliveries and unsafe copies in the actual sealed API without modifying installed files.

**Evidence:** [Protected private secret capture](PRIVATE_SECRET_CAPTURE_IMPLEMENTATION.md); [P48 source qualification](evidence/p48-qualification-2026-10-13.json)

**Remaining:** Exact-head full/native/Linux acceptance is required before merge. Complete secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/value/customer gates remain open.

### P49 — Stable selected TLS input capture

**Packet status:** tested. **Mapped outcomes:** D07.

Compare repeated bounded bytes and complete descriptor metadata for protected cache URL/CA and selected public broker CA capture. Reject inter-read byte/mode/link changes even with coarse timestamps while preserving owner/mode policy, CA-only trust and transport interfaces. Qualify actual sealed configuration using only owned temporary copies.

**Evidence:** [Stable TLS input capture](PRIVATE_TLS_INPUT_CAPTURE_IMPLEMENTATION.md); [P49 source qualification](evidence/p49-qualification-2026-10-13.json)

**Remaining:** Exact-head full/native/Linux and separate base-main receipts are required before merge. Complete rotation/secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/value/customer gates remain open.

### P50 — Explicit private PostgreSQL TLS transport

**Packet status:** tested. **Mapped outcomes:** D07.

Share explicit verify-full/declared CA/GSS-disabled/TLSv1.2 options between Django and prepared dependency readiness. Qualify effective options under conflicting ambient libpq defaults and wrong-CA/hostname refusals in the actual sealed runtime and fresh adopted roles.

**Evidence:** [Explicit private PostgreSQL TLS](PRIVATE_POSTGRES_TLS_IMPLEMENTATION.md); [P50 source qualification](evidence/p50-qualification-2026-10-13.json)

**Remaining:** Exact-head all-six CI and fresh Linux adopted-role receipts required before merge; selected CA-file preflight follows. Full secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/customer gates remain open.

### P51 — Bounded selected PostgreSQL CA preflight

**Packet status:** tested. **Mapped outcomes:** D07.

Validate absolute regular single-link non-group/other-writable bounded PEM CA inputs through consistent repeated bytes/full descriptor metadata before private Django or readiness options. Preserve public modes and libpq path semantics; qualify safe delivery and seven unsafe/changing copies in the actual sealed API.

**Evidence:** [Selected PostgreSQL CA preflight](PRIVATE_POSTGRES_CA_IMPLEMENTATION.md); [P51 source qualification](evidence/p51-qualification-2026-10-13.json)

**Remaining:** Exact-head all-six checks, complete fresh Linux receipts and separate base-main qualification are required before merge. CA remains a protected libpq path. Full rotation/secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/customer gates remain open.

### P52 — Consistent stored controller capture

**Packet status:** tested. **Mapped outcomes:** D07.

Compare repeated bounded bytes/full descriptor identity, permissions, ownership, links and timestamps for stored controller configuration/evidence, and recheck ACL refusal. Preserve caller policy and immutable publication; qualify six real inter-read faults on owned copies under coarse timestamps.

**Evidence:** [Stored controller capture](PRIVATE_CONTROLLER_CAPTURE_IMPLEMENTATION.md); [P52 source qualification](evidence/p52-qualification-2026-10-13.json)

**Remaining:** Exact-head all-six checks and complete fresh Linux receipts required before merge; delivery capture follows. Full secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/customer gates remain open.

### P53 — Consistent installation delivery capture

**Packet status:** tested. **Mapped outcomes:** D07.

Compare repeated bounded bytes/full descriptor metadata and initial/post-read ACL custody for application and dependency delivery, including prepared app secrets. Preserve pinned paths, exact members/ownership/modes, value validation and immutable publication; qualify three real Linux copy routes with six inter-read faults and initial ACL refusal.

**Evidence:** [Installation delivery capture](PRIVATE_DELIVERY_CAPTURE_IMPLEMENTATION.md); [P53 source qualification](evidence/p53-qualification-2026-10-13.json)

**Remaining:** Exact-head all-six checks, full fresh Linux receipts and independent main qualification required before adoption claims. Full secret lifecycle, upgrade/rollback, production recovery, expert isolation and release/customer gates remain open.

### P54 — SFS publication race and async failure diagnostics

**Packet status:** tested. **Mapped outcomes:** D07.

Reserve development SQLite atomic writes before reads; retain correlated search/refit/publication/final-write failure stages without logging exception values or data; attach underlying async status errors before browser cleanup/retry. Preserve scientific and operational budgets and private PostgreSQL policy.

**Evidence:** [SFS async failure diagnostics](SFS_ASYNC_FAILURE_IMPLEMENTATION.md); [P54 source qualification](evidence/p54-qualification-2026-10-14.json)

**Remaining:** Exact-head all-six checks, complete fresh Linux/private PostgreSQL receipts and independent main required before adoption claims. Disk-only status honesty follows; distributed SFS, full lifecycle/recovery, expert isolation and release/customer gates remain open.

### P55 — Honest saved SFS state and failure recovery

**Packet status:** tested. **Mapped outcomes:** D07.

Share strict recorded-state parsing across UI/results/assistant; preserve operation/failure diagnostics after process state is lost, and refuse false completion or absence for invalid evidence without rewriting history or authorizing resume.

**Evidence:** [Honest saved SFS state](SFS_PERSISTED_STATUS_IMPLEMENTATION.md); [P55 source qualification](evidence/p55-qualification-2026-10-14.json)

**Remaining:** Exact-head all-six checks, complete fresh Linux/private PostgreSQL receipts and independent main required. Distributed SFS, full lifecycle/recovery, expert isolation and release/customer gates remain open.

### P56 — Atomic SFS checkpoint publication

**Packet status:** tested. **Mapped outcomes:** D07.

Publish strict current SFS JSON through private same-directory staging, synchronized bytes, atomic replacement and directory synchronization. Preserve checkpoints through pre-replacement failures; report post-replacement durability uncertainty and retain operation correlation without weakening scientific or operational gates.

**Evidence:** [Atomic SFS checkpoints](SFS_ATOMIC_EVIDENCE_IMPLEMENTATION.md); [P56 source qualification](evidence/p56-qualification-2026-10-14.json)

**Remaining:** Exact-head all-six checks, complete fresh Linux/private PostgreSQL receipts and independent main required. Immutable archive completion follows. Distributed SFS, lifecycle/upgrade/restore, expert isolation and release/customer gates remain open.

### P57 — Operation-bound immutable SFS history

**Packet status:** tested. **Mapped outcomes:** D07.

Atomically publish synchronized no-overwrite search archives by canonical operation ID; reuse identical retries, reject changed/corrupt evidence, reconcile concurrent publication and directory-sync uncertainty. Require archive retention before current-result/live completion and preserve legacy history without numeric-count identity.

**Evidence:** [Operation-bound SFS history](SFS_IMMUTABLE_HISTORY_IMPLEMENTATION.md); [P57 source qualification](evidence/p57-qualification-2026-10-14.json)

**Remaining:** Exact-head all-six checks, complete fresh Linux/private PostgreSQL receipts and independent main required. Distributed SFS, lifecycle/upgrade/restore, expert isolation and release/customer gates remain open.

### P58 — Honest tuning failures and atomic result recovery

**Packet status:** tested. **Mapped outcomes:** D07.

Share strict recorded-state validation across tuning status/results, retain exact operation and failure metadata, reject false completion, and publish tuning/error results through synchronized atomic replacement. Retain original and secondary storage failures and attach async browser evidence with unchanged budgets and accepted-operation matching.

**Evidence:** [Honest tuning failures and atomic results](HYPERPARAM_FAILURE_RECOVERY_IMPLEMENTATION.md); [P58 source qualification](evidence/p58-qualification-2026-10-14.json)

**Remaining:** Exact-head and separate parent main qualified with retained initial timeout. Distributed search, operation journaling/history, lifecycle/upgrade/restore, expert isolation and release/customer gates remain open.

### P59 — Explicit SFS resume and process-local search admission

**Packet status:** tested. **Mapped outcomes:** D07.

Reject malformed, terminal, foreign or contradictory SFS resume evidence before work; preserve byte history and reconstruct only validated directional feature state. Record active merged-direction keys, fingerprint recovery/admission code, normalize accepted file IDs and serialize process-local owner registration without holding a lock during fitting. Derive tuning completion after copying saved fields so imported flags cannot contradict status.

**Evidence:** [Explicit SFS resume and search admission](SFS_RESUME_ADMISSION_IMPLEMENTATION.md); [P59 source qualification](evidence/p59-qualification-2026-10-14.json)

**Remaining:** Exact final-head all-six and private receipts qualified after one unchanged-head retry. Independent main run38546092115 failed the900-second PostgreSQL suite limit; P60 performance correction and fresh exact-head/main qualification required. Distributed ownership/journaling/history, lifecycle and release/customer gates remain open.

### P60 — Binary threshold evaluation performance with reference parity

**Packet status:** tested. **Mapped outcomes:** D07.

Remove repeated sklearn validation from supported binary threshold tables using exact confusion counts and reference-equivalent metrics. Preserve threshold ordering/ties/defaults, zero-denominator conventions and legacy validation for other shapes/types. Address a measured qualification bottleneck without changing scientific assertions/data, durability or acceptance budgets.

**Evidence:** [Binary threshold evaluation performance](BINARY_THRESHOLD_PERFORMANCE_IMPLEMENTATION.md); [P60 source qualification](evidence/p60-qualification-2026-10-14.json)

**Remaining:** All-six exact-head and independent current main passed first attempt with complete private/Linux receipts. Host-level timing variation, distributed search/journaling, full lifecycle/upgrade/restore, expert isolation and release/customer gates remain open.

### P61 — Operation-bound immutable tuning history

**Packet status:** tested. **Mapped outcomes:** D07.

Retain strict terminal tuning evidence once per operation before current/live publication. Reuse identical archives without rewriting bytes, reject conflicting evidence, preserve legacy history and expose exact archive references. Require project artifact registration and preserve original plus secondary failure stages.

**Evidence:** [Operation-bound tuning history](TUNING_IMMUTABLE_HISTORY_IMPLEMENTATION.md); [P61 source qualification](evidence/p61-qualification-2026-10-14.json)

**Remaining:** All-six exact-head and independent main passed first attempt with complete private/Linux receipts. Candidate adoption/registry/history/pointer are not one transaction; full journals/distributed search, lifecycle/upgrade/restore, expert isolation and release/customer gates remain open.

### P62 — Search worker-launch failure and owner safety

**Packet status:** tested. **Mapped outcomes:** D07.

Share an attributable launch boundary for SFS/tuning. Known startup failures return503 and fail only the matching owner under the admission lock; stale, possibly started or already terminal owners are preserved with explicit uncertainty. Redact exception values and retain accepted-operation correlation, prior files and normal successful launches.

**Evidence:** [Search worker launch failures](SEARCH_WORKER_LAUNCH_IMPLEMENTATION.md); [P62 source qualification](evidence/p62-qualification-2026-10-14.json)

**Remaining:** PR #152 merged after all-six exact-head checks and complete private receipts; independent main run38579094834 also passed all six with full SQLite/PostgreSQL3371/six existing skips/zero failures and37 first-attempt browser cases. Durable/distributed ownership, lifecycle/expert/release/customer gates remain open.

### P63 — Search progress and cancellation ownership

**Packet status:** tested. **Mapped outcomes:** D07.

Bind SFS/tuning callbacks, stop flags and final/error progress to the accepted object and operation UUID. Ignore stale/terminal callbacks, pin callback identity, and publish terminal diagnostic fields together under the admission lock. Preserve evidence and scientific execution.

**Evidence:** [Search progress ownership](SEARCH_PROGRESS_OWNERSHIP_IMPLEMENTATION.md); [P63 source qualification](evidence/p63-qualification-2026-10-14.json)

**Remaining:** PR #153 merged after all-six exact-head checks and complete private receipts; independent main run38592635221 passed all six first attempt with full SQLite/PostgreSQL3399/six existing skips/zero failures each and37 first-attempt browser cases. Process-local progress is not complete artifact/adoption fencing or distributed recovery; lifecycle/expert/release/customer gates remain open.

### P64 — Search worker database lifetime and cleanup diagnostics

**Packet status:** tested. **Mapped outcomes:** D07.

Wrap SFS/tuning targets with explicit thread-owned Django connection setup and finally cleanup. Preserve caller transactions and operation ownership; distinguish redacted setup/execution failures from secondary cleanup uncertainty without overwriting completed evidence.

**Evidence:** [Search worker database lifetime](SEARCH_WORKER_CONNECTIONS_IMPLEMENTATION.md); [P64 source qualification](evidence/p64-qualification-2026-10-15.json)

**Remaining:** PR #154 merged after all-six exact-head CI38599331702 and complete native receipts. Independent main CI38603527434 passed all six first attempt; full SQLite/PostgreSQL3416/six existing skips/zero failures each,17 lifecycle cases under PostgreSQL,37 first-attempt browser cases. Latest same-head scheduled CI38675147079 and full native receipts also verified. Durable recovery/lifecycle/expert/release/customer gates remain open.

### P65 — Atomic operation-aware search cancellation

**Packet status:** tested. **Mapped outcomes:** D07.

Serialize cancellation with admission and terminal publication for SFS/tuning. Optional canonical operation UUIDs reject stale or invalid requests without mutation; matching and legacy stops remain idempotent, correlated and cooperative. Preserve terminal evidence and existing missing-run behavior.

**Evidence:** [Atomic search cancellation](SEARCH_STOP_OWNERSHIP_IMPLEMENTATION.md); [P65 source qualification](evidence/p65-qualification-2026-10-15.json)

**Remaining:** PR #155 merged after all-six exact-head CI38680392962 and complete native receipts. Independent main CI38682651478 passed all six first attempt with full SQLite/PostgreSQL3466/six existing skips/zero failures each,all50 stop cases under PostgreSQL and37 first-attempt browser cases. Legacy unbound callers retain current-run semantics; browser binding follows in P66. Durable/lifecycle/expert/release/customer gates remain open.

### P66 — Browser operation-bound cancellation and stale response handling

**Packet status:** tested. **Mapped outcomes:** D07.

Send the displayed operation UUID with SFS/tuning stops. Runtime validation prevents undefined arguments becoming unbound requests. Bind fresh start/resume/status metadata, clear authority across lifecycle/dataset changes and ignore stale stop responses. Explain conflicts/unverified acknowledgements without automatic retry or fallback.

**Evidence:** [Browser operation-bound cancellation](BROWSER_SEARCH_STOP_IMPLEMENTATION.md); [P66 source qualification](evidence/p66-qualification-2026-10-15.json)

**Remaining:** PR #156 merged after all-six exact-head CI38686071261 and complete native receipts. Independent main CI38688607967 passed all six first attempt: full SQLite/PostgreSQL3466 passed/six existing skips/zero failures each,651 frontend cases and37 first-attempt browser cases. Durable/lifecycle/expert/release/customer gates remain open.

### P67 — Bounded active search admission

**Packet status:** tested. **Mapped outcomes:** D07.

Bound combined SFS/tuning active owners to two per API process with atomic admission. Return explicit capacity refusal without launching workers, changing prior evidence or disclosing other projects. Cooperative stops and uncertain launches keep capacity; terminal evidence does not consume slots.

**Evidence:** [Bounded search admission](SEARCH_CAPACITY_IMPLEMENTATION.md); [P67 source qualification](evidence/p67-qualification-2026-10-15.json)

**Remaining:** PR #157 merged as2e064351142a755448525a66c543719e4ddb28f3 after all-six exact-head CI38694009405 and complete native receipts. Independent main CI38697357961 passed all six first attempt: full SQLite/PostgreSQL3483 passed/six existing skips/zero failures each,651 frontend cases and37 first-attempt browser cases. Logical capacity excludes preparation and physical cleanup; durable/lifecycle/expert/release/customer gates remain open.

### P68 — Operation-bound search storage setup

**Packet status:** tested. **Mapped outcomes:** D07.

Move SFS/tuning directory preparation into the worker connection/failure boundary before scientific work. Redacted setup failures terminate only their matching running owner, retain prior result bytes and allow explicit fresh retries without changing capacity.

**Evidence:** [Search storage setup](SEARCH_STORAGE_SETUP_IMPLEMENTATION.md); [P68 source qualification](evidence/p68-qualification-2026-10-15.json)

**Remaining:** PR #158 merged as 7b6681b0c28f8e5c61f90dcde7aa54af3f815552 after all-six exact-head CI 38701709280 and complete native receipts. Independent main CI 38705531780 passed all six first attempt: full SQLite/PostgreSQL each 3500 passed/six existing skips/zero failures,651 frontend cases and37 first-attempt browser cases. Durable/process-loss recovery,lifecycle/expert/release/customer gates remain open.

### P69 — Bounded native metadata lock waits

**Packet status:** tested. **Mapped outcomes:** D07.

Cap PostgreSQL lock waits at five seconds per acquisition inside durable job serialization, preserving stricter caller settings. Apply before queue bootstrap and restore caller settings across success,errors,nesting and rollback. Preserve all existing execution budgets and SQLite behavior.

**Evidence:** [Native metadata lock waits](NATIVE_JOB_LOCK_WAITS_IMPLEMENTATION.md); [P69 source qualification](evidence/p69-qualification-2026-10-15.json)

**Remaining:** PR #159 merged as d6242f464489390630f17fd788cae4f24f07168d after all-six exact-head CI 38712257192 and complete native receipts. Independent main CI 38715077943 passed all six first attempt: full SQLite/PostgreSQL each3517 passed/six existing skips/zero failures,all17 new lock-wait cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P70 — Refreshed native job expiry checks

**Packet status:** tested. **Mapped outcomes:** D07.

Recheck request expiry after claim validation and lease/request expiry after publication authority checks and result preparation. Preserve expired-lease metadata for reconciliation,prevent late terminal receipts,and sample reconciliation time after queue-lock acquisition.

**Evidence:** [Refreshed native expiry checks](NATIVE_JOB_EXPIRY_IMPLEMENTATION.md); [P70 source qualification](evidence/p70-qualification-2026-10-15.json)

**Remaining:** PR #160 merged as 99a36557c01775466ba1675aa9314952d079c23c after all-six exact-head CI 38719749204 and complete native receipts. Independent main CI 38723167994 passed all six first attempt: full SQLite/PostgreSQL each3542 passed/six existing skips/zero failures,all25 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P71 — Dispatcher database connection recovery

**Packet status:** tested. **Mapped outcomes:** D07.

Retire obsolete/unusable database connections around standalone dispatcher cycles and handle driver InterfaceError through the existing redacted storage retry path. Preserve retry cadence,once-mode rejection,signal restoration and durable execution budgets.

**Evidence:** [Dispatcher database recovery](DISPATCHER_DATABASE_RECOVERY_IMPLEMENTATION.md); [P71 source qualification](evidence/p71-qualification-2026-10-15.json)

**Remaining:** PR #161 merged as e46016e860abd245366a5fe59c3bfb899d86a1b5 after all-six exact-head CI38730607737 and complete native receipts. Independent main CI38734225902 passed all six first attempt: full SQLite/PostgreSQL each3553 passed/six existing skips/zero failures,all11 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Full server/lifecycle/expert/release/customer gates remain open.

### P72 — Dispatcher queued-batch shutdown

**Packet status:** tested. **Mapped outcomes:** D07.

Propagate continuous dispatcher stop requests into outbox pumping. Complete the current publish and metadata unit,then stop before further queued publishes; preserve pending requests,evidence,redaction and default/once full-batch behavior.

**Evidence:** [Dispatcher queued-batch shutdown](DISPATCHER_BATCH_SHUTDOWN_IMPLEMENTATION.md); [P72 source qualification](evidence/p72-qualification-2026-10-15.json)

**Remaining:** PR #162 merged as25ade9e71972ae5ddf5f80fa148d112b107fe5ae after all-six exact-head CI38738923493 and complete native receipts. Independent main CI38742095226 passed all six first attempt: full SQLite/PostgreSQL each3562 passed/six existing skips/zero failures,all9 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P73 — Database authority on every private service launch

**Packet status:** tested. **Mapped outcomes:** D07.

Require the existing non-elevated application database role preflight for every fixed API,worker,dispatcher and adoption action,and the direct private native entrypoint. Reject elevated/unavailable authority before service execution without changing execution budgets.

**Evidence:** [Private service startup authority](PRIVATE_SERVICE_ROLE_PREFLIGHT_IMPLEMENTATION.md); [P73 source qualification](evidence/p73-qualification-2026-10-15.json)

**Remaining:** PR #163 merged as7ac4f9802da8bc2755981aecf6fb0c494ed0f760 after all-six exact-head CI38748692807 and complete native receipts. Independent main CI38752994785 passed all six first attempt: full SQLite/PostgreSQL each3578 passed/six existing skips/zero failures,all16 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P74 — Session and active database authority

**Packet status:** tested. **Mapped outcomes:** D07.

Check both active and session principal membership in the existing privileged-role policy,so SET ROLE cannot hide elevated session authority. Preserve current direct flags,strict result validation,static failures and execution budgets.

**Evidence:** [Session and active database authority](PRIVATE_SESSION_ROLE_AUTHORITY_IMPLEMENTATION.md); [P74 source qualification](evidence/p74-qualification-2026-10-15.json)

**Remaining:** PR #164 merged as979507b7209706e9a27c7e31356a6e7889a119aa after all-six exact-head CI38758489033 and complete native receipts. Independent main CI38763022828 passed all six first attempt: full SQLite/PostgreSQL each3589 passed/six existing skips/zero failures,all11 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P75 — Require private broker authentication

**Packet status:** tested. **Mapped outcomes:** D07.

Reject missing or malformed private broker credentials before trust capture and network construction. Preserve valid default-user/ACL authentication,credential decoding parity,development behavior and existing execution budgets.

**Evidence:** [Private broker authentication](PRIVATE_BROKER_AUTHENTICATION_IMPLEMENTATION.md); [P75 source qualification](evidence/p75-qualification-2026-10-16.json)

**Remaining:** PR #165 merged asbedb230534308f2fbdd9614a2140dd9ce37b1106 after all-six exact-head CI38836817671 and complete native receipts. Independent main CI38839362896 passed all six first attempt: full SQLite/PostgreSQL each3621 passed/six existing skips/zero failures,all32 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P76 — Preserve decoded dependency credential bytes

**Packet status:** tested. **Mapped outcomes:** D07.

Separate delivered-file newline handling from decoded Redis credential validation. Reject encoded trailing CR/LF before dependency staging while preserving valid credential bytes,configuration generation and existing budgets.

**Evidence:** [Dependency credential byte preservation](DEPENDENCY_CREDENTIAL_BYTES_IMPLEMENTATION.md); [P76 source qualification](evidence/p76-qualification-2026-10-16.json)

**Remaining:** PR #166 merged as8f5cf78fc1f9cec606db13acb5342e130cbed1a3 after all-six exact-head CI38842566792 and complete native receipts. Independent main CI38845104390 passed all six first attempt: full SQLite/PostgreSQL each3653 passed/six existing skips/zero failures,all32 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Durable search,lifecycle/expert/release/customer gates remain open.

### P77 — Native CSV regular-file capture

**Packet status:** tested. **Mapped outcomes:** D07.

Reject special CSV inputs and late final-component symlinks through an owned nonblocking regular-file descriptor. Close descriptors on failure/cancellation and preserve byte,authority and scoring contracts.

**Evidence:** [Native CSV regular-file capture](NATIVE_CSV_INPUT_FILES_IMPLEMENTATION.md); [P77 source qualification](evidence/p77-qualification-2026-10-16.json)

**Remaining:** PR #167 merged as1158b69b7832c4beba0bcc9fb71fde4bd061abeb after all-six exact-head CI38850952606 and complete native receipts. Independent main CI38853476180 passed all six first attempt: full SQLite/PostgreSQL each3676 passed/six existing skips/zero failures,all23 new cases under PostgreSQL,651 frontend and37 first-attempt browser cases. Initial failure and corrected missing-input compatibility evidence retained. Durable search,lifecycle/expert/release/customer gates remain open.

### P78 — Bounded native package reads

**Packet status:** tested. **Mapped outcomes:** D07.

Reject late special files during native package admission,evidence reads and worker hashing using owned regular-file descriptors. Bound metadata reads before parsing while preserving missing-file diagnostics and existing execution limits.

**Evidence:** [Bounded native package reads](NATIVE_PACKAGE_FILES_IMPLEMENTATION.md); [P78 source qualification](evidence/p78-qualification-2026-10-16.json)

**Remaining:** PR #168 merged as619f9efa72e16712bd5fe6ecc510d96352287b46 after all-six exact-head CI38858095079 and complete native receipts. Independent main CI38860913876 passed all six first attempt: full SQLite/PostgreSQL each3710 passed/six existing skips/zero failures,all34 new cases under both full profiles,651 frontend and37 first-attempt browser cases. Native TLS,recovery,image identity,fresh Linux schema/accounts/adoption/HTTPS and cleanup receipts verified. Durable search,lifecycle/expert/release/customer gates remain open.

### P79 — Reliable native metadata validation

**Packet status:** tested. **Mapped outcomes:** D07.

Keep JSON decoder nesting failures inside the native invalid-input boundary and inspect decoder-supported deep evidence iteratively without weakening project authorization or unexpected-error recovery.

**Evidence:** [Reliable native metadata validation](NATIVE_METADATA_VALIDATION_IMPLEMENTATION.md); [P79 source qualification](evidence/p79-qualification-2026-10-16.json)

**Remaining:** PR #169 merged as b06c35e66b0e7f7bbd2a8f72daa77b00834609d7 after all-six exact-head CI 38867755334 and complete native receipts. Independent main CI 38870945602 passed all six first attempt: full SQLite/PostgreSQL each 3,747 passed with six existing skips and zero failures; all 37 new cases passed in both full profiles. Frontend: 651. Browser: 37 first-attempt passes. Native TLS, recovery, image identity, fresh Linux schema/accounts/adoption/HTTPS and cleanup receipts verified. Durable search, lifecycle/expert/release/customer gates remain open.

### P80 — Native job pagination input bounds

**Packet status:** tested. **Mapped outcomes:** D07.

Reject job-list offsets outside the supported database range before native job queries. Preserve authorization precedence, valid integer syntax, response shape, ordering and 50-row pagination.

**Evidence:** [Native job pagination input bounds](NATIVE_JOB_PAGINATION_IMPLEMENTATION.md); [P80 source qualification](evidence/p80-qualification-2026-10-16.json)

**Remaining:** PR #170 merged as 25d375eee0ef09f32011c4758d64b95cfd238c26 after all-six exact-head CI 38875874574 and complete native receipts. Independent main CI 38879118203 passed all six first attempt: full SQLite/PostgreSQL each 3,772 passed with six existing skips and zero failures; all 25 new cases passed in both. Frontend: 651. Browser: 37 first-attempt passes. Native controls, image identities, fresh Linux schema/accounts/adoption/HTTPS and cleanup receipts verified. Durable search, lifecycle/expert/release/customer gates remain open.

### P81 — Native publication work deadline

**Packet status:** tested. **Mapped outcomes:** D07.

Carry the original monotonic execution deadline into native integrity and CSV-scoring publication. Refuse late success after metadata/authority waits or result preparation while preserving cancellation, lease, request-expiry and unexpected-failure recovery.

**Evidence:** [Native publication work deadline](NATIVE_PUBLICATION_DEADLINE_IMPLEMENTATION.md); [P81 source qualification](evidence/p81-qualification-2026-10-16.json)

**Remaining:** PR #171 merged as 072e467ba2035c26b163f062f2f0241f169b92ef after all-six exact-head CI 38885288545 and complete native reports. Independent main CI 38888687099 passed all six first attempt: full SQLite/PostgreSQL each 3,813 passed with six existing skips and zero failures; all 41 new deadline cases passed in both. Frontend: 651. Browser: 37 first-attempt passes. Native controls, image identities, fresh Linux schema/accounts/adoption/HTTPS and cleanup verified. PostgreSQL completed in 781.397 seconds under the unchanged 900-second budget. Durable search, lifecycle/expert/release/customer gates remain open.

### P82 — Canonical frontend dependency installation

**Packet status:** tested. **Mapped outcomes:** D07.

Remove the unused Angular 18 root npm manifests and make the supported frontend installation path explicit. Preserve the qualified Angular 22 manifest, lockfile and vendored archive; retain supported dependency findings as open work.

**Evidence:** [Canonical frontend dependency installation](CANONICAL_FRONTEND_DEPENDENCIES_IMPLEMENTATION.md); [P82 source qualification](evidence/p82-qualification-2026-10-16.json)

**Remaining:** PR #172 merged as d19ded130336747bdffc572ff6eec9f3318536c8 after all-six exact-head CI 38892591077 and complete native receipts. Independent main CI 38895881460 passed all six first attempt: full SQLite/PostgreSQL each 3,813 passed with six existing skips and zero failures; frontend 651 and browser 37 first-attempt passes. Native controls, image identities, fresh Linux schema/accounts/adoption/HTTPS and cleanup verified. Supported build/test dependency findings, durable search, lifecycle/expert/release/customer gates remain open.

### P83 — Private migration history startup guard

**Packet status:** tested. **Mapped outcomes:** D07.

Block private service startup against migration history unknown to the selected sealed image or inconsistent with its dependency graph; preserve pending-migration diagnostics and never repair schema automatically.

**Evidence:** [Private migration history guard](PRIVATE_MIGRATION_HISTORY_IMPLEMENTATION.md); [P83 source qualification](evidence/p83-qualification-2026-10-16.json)

**Remaining:** PR #173 merged as 07b4c73c3b60e28f12c4b15c09a56c3647f8d140 after all-six exact-head CI 38904498886 and complete native receipts. Independent main CI 38907856333 passed all six first attempt: full SQLite/PostgreSQL each 3,825 passed with six existing skips and zero failures/errors; all 12 new cases pass in both profiles, frontend 651 and browser 37 first-attempt passes. Native controls, exact image identities, fresh Linux schema/accounts/adoption/HTTPS and cleanup verified. Main PostgreSQL 796.880 seconds under unchanged 900-second budget. Browser artifact listing required a read retry; CI was not rerun. Physical schema, migration squash/removal, full lifecycle/upgrade/restore, durable search, expert and release/customer gates remain open.

### P84 — Reserved private service DNS identities

**Packet status:** tested. **Mapped outcomes:** D07.

Reject another service role’s reserved DNS identity during dependency reuse, application adoption and temporary helper validation. Preserve valid own/generated names and existing TLS, authorization, network and resource contracts.

**Evidence:** [Private service DNS identities](PRIVATE_SERVICE_DNS_IMPLEMENTATION.md); [P84 source qualification](evidence/p84-qualification-2026-10-16.json)

**Remaining:** PR #174 merged as eae04d97c27106d9ed50da73af4abe4716091f5a after all-six exact-commit CI 38913460901 and complete native receipts. Independent main CI 38918645504 passed all six first attempt: full SQLite/PostgreSQL each 3,872 passed with six existing skips and zero failures/errors; all 47 new DNS and 12 retained migration-history cases pass in both profiles; frontend 651 and browser 37 first-attempt passes. Native controls, exact image identities, fresh Linux schema/accounts/adoption/HTTPS and cleanup verified. PostgreSQL 598.796 seconds under unchanged 900-second budget. Original checkout preserved; later Docker administration, supported dependency findings, durable search, complete lifecycle/expert/release/customer gates remain open.

### P85 — Private managed-schema presence guard

**Packet status:** tested. **Mapped outcomes:** D07.

Block private startup when migration history is current but required managed tables/columns are missing, replaced by views or shadowed. Inspect PostgreSQL catalogs without model-row reads or automatic repair.

**Evidence:** [Private schema presence guard](PRIVATE_SCHEMA_PRESENCE_IMPLEMENTATION.md); [P85 source qualification](evidence/p85-qualification-2026-10-16.json)

**Remaining:** PR #175 merged as 73a73781 after exact-commit run 38927952528 and independent main 38932353971 passed all six checks on attempt one with complete private/native reports; full PostgreSQL 3,900 passed/six existing skips in each. Presence remains bounded, not full type/constraint/index/privilege/data or lifecycle equivalence. Supported dependency findings, durable search, expert/release/customer gates remain open.

### P86 — Private effective metadata permission guard

**Packet status:** tested. **Mapped outcomes:** D07.

Require every effective table-level CRUD right on the current private managed schema before broker/cache contact. Reuse required-schema discovery and fail with a static diagnostic without changing grants or ownership.

**Evidence:** [Private schema privilege guard](PRIVATE_SCHEMA_PRIVILEGES_IMPLEMENTATION.md); [P86 source qualification](evidence/p86-qualification-2026-10-17.json)

**Remaining:** PR #176 merged as e6519609 after exact-commit run 38937979273 and independent main run 38942306229 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 3,930 passed, six existing skips; main completed in 837.136s within the unchanged 900s budget. Current table-level owner profile only; sequence, RLS/data, full-schema, lifecycle and release/customer gates remain open.

### P87 — Private metadata row-security guard

**Packet status:** tested. **Mapped outcomes:** D07.

Reject unsupported enabled or forced RLS on required managed metadata tables before broker/cache contact. Read catalogs without changing policies or reading model rows.

**Evidence:** [Private metadata row security](PRIVATE_METADATA_ROW_SECURITY_IMPLEMENTATION.md); [P87 source qualification](evidence/p87-qualification-2026-10-17.json)

**Remaining:** PR #177 merged as 3a2381d4 after exact-commit run 38991817353 and independent main run 38993892949 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 3,960 passed, six existing skips; main completed in 451.019s within the unchanged 900s budget. Fixed unfiltered metadata profile only; later-state fencing and broader lifecycle/release/customer gates remain open.

### P88 — Private metadata write-mode guard

**Packet status:** tested. **Mapped outcomes:** D07.

Require current and default metadata transaction modes to be writable after TLS and before history/schema/broker/cache work. Read settings without changing modes or probing writes.

**Evidence:** [Private metadata write mode](PRIVATE_METADATA_WRITE_MODE_IMPLEMENTATION.md); [P88 source qualification](evidence/p88-qualification-2026-10-17.json)

**Remaining:** PR #178 merged as bb12b100 after exact-commit run 38996441100 and independent main run 38998047158 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 3,972 passed, six existing skips; main completed in 811.807s within the unchanged 900s budget. Later-state fencing, general write/availability and full lifecycle/release/customer gates remain open.

### P89 — Private role catalog trust

**Packet status:** tested. **Mapped outcomes:** D07.

Pin startup active/session authority catalogs, membership functions and role-name equality to pg_catalog so caller-controlled namespaces cannot conceal elevated authority. Preserve existing role policy, order, receipts and redacted diagnostics.

**Evidence:** [Private role catalog trust](PRIVATE_ROLE_CATALOG_IMPLEMENTATION.md); [P89 source qualification](evidence/p89-qualification-2026-10-17.json)

**Remaining:** PR #179 merged as 419deb63 after exact-commit run 39004701966 and independent main run 39010850791 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 3,996 passed, six existing skips; main completed in 790.324s within the unchanged 900s budget. Startup authority observation only; continuous monitoring and full lifecycle/release/customer gates remain open.

### P90 — Private PostgreSQL TLS evidence trust

**Packet status:** tested. **Mapped outcomes:** D07.

Bind startup metadata TLS evidence to the built-in statistics view, actual backend PID and built-in PID comparison. Reject namespace substitutions without changing TLS requirements, diagnostics or connection configuration.

**Evidence:** [Private TLS catalog trust](PRIVATE_TLS_CATALOG_IMPLEMENTATION.md); [P90 source qualification](evidence/p90-qualification-2026-10-17.json)

**Remaining:** PR #180 merged as 67f81410 after exact-commit run 39013110227 and independent main run 39014604290 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,004 passed, six existing skips; main completed in 799.822s within the unchanged 900s budget. Current-connection startup evidence only; continuous monitoring and full lifecycle/release/customer gates remain open.

### P91 — Private schema catalog evidence trust

**Packet status:** tested. **Mapped outcomes:** D07.

Pin presence, effective permissions and row-security catalog joins/filters to built-in operators and identifier types. Prevent substituted attribute or namespace evidence without changing supported schema policy or static diagnostics.

**Evidence:** [Private schema catalog trust](PRIVATE_SCHEMA_CATALOG_IMPLEMENTATION.md); [P91 source qualification](evidence/p91-qualification-2026-10-17.json)

**Remaining:** PR #181 merged as 6ba7bb4d after exact-commit run 39029180547 and independent main run 39031361681 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,012 passed, six existing skips; main completed in 537.219s within the unchanged 900s budget. Startup catalog observations only; complete schema/data/lifecycle and release/customer gates remain open.

### P92 — Private dependency probe catalog trust

**Packet status:** tested. **Mapped outcomes:** D07.

Bind the application dependency probe's database identity, role flags, explicit membership and TLS evidence to built-in PostgreSQL objects/operators. Preserve its stricter initial dependency policy, transport, diagnostics and helper contracts.

**Evidence:** [Private dependency probe catalog trust](PRIVATE_DEPENDENCY_PROBE_CATALOG_IMPLEMENTATION.md); [P92 source qualification](evidence/p92-qualification-2026-10-17.json)

**Remaining:** PR #182 merged as dc452684 after exact-commit run 39033495356 and independent main run 39035621284 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,019 passed, six existing skips; main completed in 685.001s within the unchanged 900s budget. Selected-controller startup attestation only; other owner/schema queries and full lifecycle/release/customer gates remain open.

### P93 — Literal PostgreSQL system-schema prefix

**Packet status:** tested. **Mapped outcomes:** D07.

Distinguish the reserved literal pg_ schema prefix from ordinary names matched by the former LIKE wildcard. Report foreign namespaces before fresh migrations or current-state acceptance while retaining genuine system schemas and existing runtime contracts.

**Evidence:** [Literal system-schema prefix](PRIVATE_SCHEMA_PREFIX_IMPLEMENTATION.md); [P93 source qualification](evidence/p93-qualification-2026-10-17.json)

**Remaining:** PR #183 merged as 03c4c906 after exact-commit run 39040606754 and independent main run 39042846145 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,028 passed, six existing skips; main completed in 505.969s within the unchanged 900s budget. Literal-prefix classification only; other catalog queries and full lifecycle/release/customer gates remain open.

### P94 — Trusted schema-state catalog evidence

**Packet status:** tested. **Mapped outcomes:** D07.

Pin initializer extension/function/event/relation/dependency evidence to built-in catalogs, functions, aggregates, operators and class/type identities. Prevent false fresh/current and fabricated foreign classifications without changing supported schema policy or migration/helper contracts.

**Evidence:** [Trusted schema-state catalogs](PRIVATE_SCHEMA_STATE_CATALOG_IMPLEMENTATION.md); [P94 source qualification](evidence/p94-qualification-2026-10-17.json)

**Remaining:** PR #184 merged as e7815f16 after exact-commit run 39045679784 and independent main run 39047373041 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,037 passed, six existing skips; main 823.702s within the unchanged 900s budget. State catalog observations only; other authority/lock SQL, continuous fencing and full lifecycle/release/customer gates remain open.

### P95 — Trusted initializer advisory lock

**Packet status:** tested. **Mapped outcomes:** D07.

Bind the initializer advisory lock to PostgreSQL's built-in function so caller-defined functions cannot falsely attest exclusion or reject healthy acquisition. Preserve lock keys, policy, lifecycle, helper and migration contracts.

**Evidence:** [Trusted initializer advisory lock](PRIVATE_SCHEMA_LOCK_IMPLEMENTATION.md); [P95 source qualification](evidence/p95-qualification-2026-10-18.json)

**Remaining:** PR #185 merged as aff3e9e6 after exact-commit run 39052844889 and independent main run 39055192528 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,047 passed, six existing skips; CI818.564s and main457.268s within the unchanged 900s budget. Trusted cooperative advisory-lock attestation only; other authority SQL, continuous fencing and full lifecycle/release/customer gates remain open.

### P96 — Trusted initializer authority observations

**Packet status:** tested. **Mapped outcomes:** D07.

Bind initializer role, membership, TLS, database owner and encoding evidence to PostgreSQL built-ins. Preserve admission policy, source/helper contracts, trusted lock, migration behavior and budgets.

**Evidence:** [Trusted initializer authority](PRIVATE_SCHEMA_AUTHORITY_IMPLEMENTATION.md); [P96 source qualification](evidence/p96-qualification-2026-10-18.json)

**Remaining:** PR #186 merged as 1bed86be after exact-commit run 39057547384 and independent main run 39059495184 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,061 passed, six existing skips; CI517.188s and main449.073s within the unchanged 900s budget. Trusted initializer authority observations only; isolated probes do not establish a full controller/verified-transport bypass or continuous fencing. Other helpers and full lifecycle/release/customer gates remain open.

### P97 — Physical metadata storage types

**Packet status:** tested. **Mapped outcomes:** D07.

Require current managed metadata columns to retain the sealed migration graph's PostgreSQL base storage types before broker/cache access. Preserve relation visibility, extra-column policy, diagnostics and read-only startup behavior.

**Evidence:** [Physical metadata storage types](PRIVATE_SCHEMA_STORAGE_TYPES_IMPLEMENTATION.md); [P97 source qualification](evidence/p97-qualification-2026-10-18.json)

**Remaining:** Sixteen native regressions fail against the predecessor while four genuine/extra-column controls pass; all twenty pass after the fix. Focused native 511 and reference/adoption 611 pass. Final-source full reference suite passes 4,081 tests with six existing skips. Exact-commit all-six/private and independent main qualification remain required. Type modifiers/constraints, later-state fencing and full lifecycle/release/customer gates remain open.

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

**Progress:** Immutable native executions, assessment receipts, candidate refits, unique bundles/batch outputs and hash verification are implemented. P03 adds UUID preprocessing versions, raw/recipe snapshots, fitted purifier replay and feature-subset raw dependencies. Focused XGBoost raw scoring/calibration, category, alignment and chunk parity are tested. Complete immutable stages/jobs, independent reproduction and concurrency/recovery qualification remain open. P05 adds input/configuration-bound native fit receipts and candidate-specific selected-feature CV with explicit post-selection limitations; exact-version acceptance preserves prior model evidence. P07 preserves tuning selection inside immutable candidate manifests and uses unique legacy refit paths; failed/stopped tuning cannot publish completion. Per-file search/job projections remain mutable. P09 binds current native early stopping to the accepted metric across initial training, fold fitting, selection/tuning and candidate refits. Per-round values, selected scoring rounds and separate surrogate loss/weights are retained; undefined criteria block without fallback. Disabled stopping excludes validation data from fitting. Historical paths, protected confirmatory protocols and full milestone qualification remain open. P10 adds source/target/final-row identity, receipt-before-read accounting and exact/overlapping/unknown reuse across executions. Failed/interrupted attempts and actor snapshots remain attributable; history reads do not deserialize outcomes. Exact assessment exports and a resumed, keyboard-operated history panel are qualified locally. All evidence remains exploratory; confirmatory protocols and complete milestone qualification remain open. P11 pins package readiness/builds to verified execution/assessment evidence and scoring/export to immutable bundle IDs. Publication is staged and current-version checked; receipts bind manifest metadata, required native artifacts and original review evidence. Historical versions remain usable; UI exposes blocked states and keyboard-accessible package/score receipts. Full distributed durability, independent reproduction and release qualification remain open. P13 prevents upload and encoded CSV collisions with UUID names/exclusive creation, blocks success when required encoding metadata fails, and removes arbitrary legacy fallback selection. Full immutable legacy stages and distributed publication/recovery remain open. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open. P15 archives native training-only numeric diagnostic matrices and method/state metadata for each execution and selected candidate subset. Detail inspection and saved-run refresh use exact execution identity with integrity checks; latest projections cannot silently replace saved evidence. Historical inputs remain unverified. P25 adds synthetic private TLS scoring recovery qualification: exact quiescent metadata/input/package/full-result restore, natural orphan leases, actual duplicate completions, changed/missing-input and current-authority blocking, plus recovered-score exports. Native application behavior and budgets are unchanged; production interrupted-scoring/live-backup/machine-loss recovery and full reproduction/release gates remain open. P26 pins optional review references to exact successful native job results and specifications. Job retention, complete scoring receipts, digest/snapshot validation and exact request replay are tested; references do not certify independent reproduction or authenticity. P27 adds method-named support-weighted rank AUC for requested multiclass stopping, retaining independent sklearn full assessment, input validation and unavailable-objective blocking. Reference callback histories, selected models and replay match across all three native boosters; private/full workflow qualification passes with unchanged budgets. No full reproduction, capacity or release claim. P28 adds immutable grouped training-input subspace GVIF with nominal category-code invariance, exact one-hot provenance, dimensional adjustment and explicit rank/precision/budget states. Exact native replay uses no fitted state or final outcomes; current reviewers may inspect both numeric and grouped reports, with revocation checks and keyboard summaries. Lossy category encodings block the conditioning set. Independent reference, full metadata and browser checks pass; paired uncertainty, SQLite worker contention, expert isolation and release/customer gates remain open. P28 final hardening validates native NumPy format, bounded header, exact dtype/shape and payload length before allocating arrays; a retained failing-before/passing-after case confirms the boundary. The final complete matrices and browser/runtime image qualify this stronger source without changing prediction calculations or budgets.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P03 implementation and limits](PURIFIER_REPLAY_IMPLEMENTATION.md); [P03 qualification](evidence/p03-qualification-2026-10-08.json); [P05 candidate evidence and limits](CANDIDATE_EVIDENCE_IMPLEMENTATION.md); [P05 source qualification](evidence/p05-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json); [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json); [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json); [P11 package handoff and limits](PACKAGE_HANDOFF_IMPLEMENTATION.md); [P11 source qualification](evidence/p11-qualification-2026-10-09.json); [Managed native storage implementation](MANAGED_STORAGE_IMPLEMENTATION.md); [P13 source qualification](evidence/p13-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json); [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json); [P27 source qualification](evidence/p27-qualification-2026-10-10.json); [Grouped input diagnostics](GROUPED_COLLINEARITY_IMPLEMENTATION.md); [P28 source qualification](evidence/p28-qualification-2026-10-11.json)

### D05 Trustworthy diagnostics

Correct categorical collinearity treatment, describe combined importance as a heuristic, and use associational terminology for sequential pattern detection.

**Acceptance:** Diagnostics are invariant to arbitrary category-code permutations; uncertainty and limitations accompany comparisons.

**Source mapping:** Claude CC-9; GPT FIX-04; Gemini C4.

**Progress:** Categorical codes no longer enter numeric VIF; combined importance is a ranking heuristic, sequential patterns are associational, and anomaly metrics are ranking-only. Unsupported multiclass SHAP/PDP is disclosed/blocked. Grouped diagnostics and paired-comparison uncertainty remain open. P04 reports undefined constant-target R² and incomplete metric aggregates explicitly, labels fold spread as descriptive, records actual adapter training metrics and exposes task-specific validation limitations. P06 aligns current native feature-selection screening, CV ranking and stopping with accepted objective semantics, complete availability and recorded search/resume evidence; historical paths remain unverified. P07 exposes failed/unusable attempts and curve gaps without invented spread; surrogate importance/range guidance is explicitly descriptive rather than causal. P09 binds current native early stopping to the accepted metric across initial training, fold fitting, selection/tuning and candidate refits. Per-round values, selected scoring rounds and separate surrogate loss/weights are retained; undefined criteria block without fallback. Disabled stopping excludes validation data from fitting. Historical paths, protected confirmatory protocols and full milestone qualification remain open. P15 centers/scales native numeric auxiliary regressions explicitly and distinguishes finite, unbounded/precision-indistinguishable, constant, excluded, solver and compute-budget states. Exact category-derived output groups are excluded; fixed VIF severity/removal thresholds are removed. Grouped categorical methods and paired uncertainty remain open. P28 adds immutable grouped training-input subspace GVIF with nominal category-code invariance, exact one-hot provenance, dimensional adjustment and explicit rank/precision/budget states. Exact native replay uses no fitted state or final outcomes; current reviewers may inspect both numeric and grouped reports, with revocation checks and keyboard summaries. Lossy category encodings block the conditioning set. Independent reference, full metadata and browser checks pass; paired uncertainty, SQLite worker contention, expert isolation and release/customer gates remain open. P28 final hardening validates native NumPy format, bounded header, exact dtype/shape and payload length before allocating arrays; a retained failing-before/passing-after case confirms the boundary. The final complete matrices and browser/runtime image qualify this stronger source without changing prediction calculations or budgets.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P04 development validation and limits](DEVELOPMENT_VALIDATION_IMPLEMENTATION.md); [P04 source qualification](evidence/p04-qualification-2026-10-08.json); [P06 feature-selection implementation and limits](FEATURE_SELECTION_IMPLEMENTATION.md); [P06 source qualification](evidence/p06-qualification-2026-10-08.json); [P07 tuning implementation and limits](TUNING_EVIDENCE_IMPLEMENTATION.md); [P07 source qualification](evidence/p07-qualification-2026-10-08.json); [P09 declared early stopping and limits](EARLY_STOPPING_IMPLEMENTATION.md); [P09 source qualification](evidence/p09-qualification-2026-10-09.json); [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json); [Grouped input diagnostics](GROUPED_COLLINEARITY_IMPLEMENTATION.md); [P28 source qualification](evidence/p28-qualification-2026-10-11.json)

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

**Progress:** Real server sessions/CSRF, route guards, protected REST/media and streaming credentials replace browser-local sign-in. Production HTTP boundary tests and browser login/reload/logout were exercised. Project roles, MCP identity, audit/retention and egress policy remain open. P02 adds disposable non-admin session/CSRF CI on every PR and repairs HPO/SFS/pipeline payload parsing under real sessions. P12 binds local MCP reads/proposals to active installation actors and explicit dataset grants, with access reservations and authority rechecks before output. Live stdio grant changes/revocation and retained audit snapshots are qualified; HTTP/SSE and unverified direct execution are blocked. REST project roles, exact approvals, expert isolation, egress/retention and deployment/security qualification remain open. P13 validates native REST file identifiers and confines table selectors/generated files to managed storage before reads, including traversal, hidden, symlink and nonregular-file rejection. This is a root boundary, not REST project/dataset authorization; roles, egress/retention and release threat-model qualification remain open. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open. P16 adds an explicit fail-closed private runtime with external secret/value-file sources, explicit hosts/HTTPS origins, secure cookies/redirects, an existing artifact root and PostgreSQL verify-full TLS. Both SQLite and PostgreSQL full marked suites pass unchanged assertions, skip and coverage budgets. Real private middleware/session/CSRF, non-superuser migrations, certificate/hostname rejection, restart persistence and a quiescent synthetic database/artifact restore are qualified; the live-reload stack rejects private mode. This is metadata/configuration support, not PostgreSQL dataset intake or qualified production deployment. Project roles, egress/retention, durable workers, expert isolation, independent reproduction and production recovery remain open. P17 shares bounded password-login admission across API/admin processes, records authentication facts without raw credentials, requires current browser-session revisions and adds retry-safe installation-operator revocation with unused typed-approval cancellation. Private TLS PostgreSQL five-process budget/revocation checks, session/audit restart/restore and marked suites on both databases pass. Development browser denial, unaffected-user access and fresh-session retry are independently checked. Historical unbound sessions require reauthentication. Operator labels are assertions, not authenticated human identity; project roles, tamper-proof audit/retention, egress and full private release qualification remain open. P18 adds explicit project membership and developer/reviewer/admin roles, durable activation, scoped native API/pipeline/table/artifact access, project-aware MCP and revision-bound typed approvals. Legacy adoption records current assertions; cross-project holdout reuse counts remain while unrelated details are withheld. Full legacy/scientific matrices, project regressions, governed browser/stdio workflows and private PostgreSQL role/retry/restart/restore fixtures are qualified with separately pinned sources. This is partial D06; unactivated development remains unqualified. Project/reviewer UI, SSO/MFA/enrollment, egress/retention, tamper-proof audit, durable job authority, expert isolation and full private release qualification remain open. P19 adds a server-backed project picker, role explanations and project-filtered dataset/pipeline records. Developer workspaces pin upload/checkpoint ownership and saved-pipeline operations to the selected project; reviewers/admins browse records and download existing reports. Fresh membership checks, canceled/stale response handling, explicit blocked states, visible selection after redirects and keyboard/browser workflows are qualified. This is partial D06/D12; full reviewer findings/approvals/reproduction, member/enrollment UI, SSO/MFA, egress/retention, durable jobs, expert isolation, comprehensive accessibility and release/customer gates remain open. P26 rechecks cited scoring-input access on discussion adoption, reads and downloads, including final HTTP response checks. A cross-project input reassignment withholds linked evidence even for an actor with both memberships; retained events remain unchanged. P28 adds immutable grouped training-input subspace GVIF with nominal category-code invariance, exact one-hot provenance, dimensional adjustment and explicit rank/precision/budget states. Exact native replay uses no fitted state or final outcomes; current reviewers may inspect both numeric and grouped reports, with revocation checks and keyboard summaries. Lossy category encodings block the conditioning set. Independent reference, full metadata and browser checks pass; paired uncertainty, SQLite worker contention, expert isolation and release/customer gates remain open. P28 final hardening validates native NumPy format, bounded header, exact dtype/shape and payload length before allocating arrays; a retained failing-before/passing-after case confirms the boundary. The final complete matrices and browser/runtime image qualify this stronger source without changing prediction calculations or budgets. P29 adds an allowlisted fixed native API/worker/dispatcher image, immutable source/runtime inventories and an exact tag-free offline handoff bound to an independently trusted manifest digest. Actual unprivileged read-only Unix WSGI session/CSRF/project checks, empty-slot image import and both complete metadata suites pass. A single API worker preserves legacy process-local search control; durable search migration, complete frontend/TLS installation, supply-chain authentication, egress/retention, production recovery, expert isolation and all release/value/customer gates remain open. P30 adds a fixed, unprivileged buffering TLS ingress with canonical headers, exact Host/SNI handling, bounded ephemeral upload storage and current Django media authorization. Real private HTTPS qualification is added to the existing PostgreSQL fixture/CI job. Complete installation, client-source attribution, comprehensive egress/retention, production recovery, expert isolation and all release/customer gates remain open. P31 adds a recorded allowlisted Angular production/private build, exact immutable TLS asset packaging, same-origin API/media credentials and explicit static/app routes with local fonts/licenses and exact-bundle browser CSP with sandboxed media attachments. Actual private HTTPS developer sign-in/reload, project selection, creation/upload/download/logout and blocked fallback/egress checks pass. Complete multi-image restricted-network installation, supply authentication, production recovery, expert isolation, independent reproduction, comprehensive accessibility and all release/value/customer gates remain open. P43 adds ordinary private account enrollment with explicit project scope, actual role/TLS/schema/broker preflight, private credential files, atomic operator-attributed account/project records and exact retry/state/collision checks. Fresh adoption preflight uses ephemeral media without customer artifact access. Actual complete fresh Linux/HTTPS acceptance is required before merge; full lifecycle/security/recovery and release/customer gates remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [P12 MCP access and limits](MCP_ACCESS_IMPLEMENTATION.md); [P12 source qualification](evidence/p12-qualification-2026-10-09.json); [Managed native storage implementation](MANAGED_STORAGE_IMPLEMENTATION.md); [P13 source qualification](evidence/p13-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json); [Explicit runtime configuration and limits](private-runtime-configuration.md); [P16 source qualification](evidence/p16-qualification-2026-10-09.json); [Authentication audit and revocation](AUTHENTICATION_GOVERNANCE.md); [P17 source qualification](evidence/p17-qualification-2026-10-09.json); [Project authorization foundation](PROJECT_AUTHORIZATION_IMPLEMENTATION.md); [P18 source qualification](evidence/p18-qualification-2026-10-10.json); [Project workspace implementation](PROJECT_WORKSPACE_IMPLEMENTATION.md); [P19 source qualification](evidence/p19-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json); [Grouped input diagnostics](GROUPED_COLLINEARITY_IMPLEMENTATION.md); [P28 source qualification](evidence/p28-qualification-2026-10-11.json); [Private native API packaging](PRIVATE_API_PACKAGING_IMPLEMENTATION.md); [P29 source qualification](evidence/p29-qualification-2026-10-11.json); [Fixed private TLS ingress](PRIVATE_TLS_INGRESS_IMPLEMENTATION.md); [P30 source qualification](evidence/p30-qualification-2026-10-11.json); [Compiled private frontend](PRIVATE_FRONTEND_IMPLEMENTATION.md); [P31 source qualification](evidence/p31-qualification-2026-10-11.json); [Private account enrollment and fresh adoption](PRIVATE_ACCOUNT_ENROLLMENT_IMPLEMENTATION.md); [P43 source qualification](evidence/p43-qualification-2026-10-12.json)

### D07 Durable execution and production packaging

PostgreSQL, dedicated Celery/Redis jobs, bounded concurrency, cancellation, recovery, monitoring and backups. Production TLS/static assets and reproducible private deployment; Django 5.2 LTS and Angular 22.

**Acceptance:** Clean install, upgrade/rollback, worker/broker recovery and coordinated data/artifact restore pass on the supported Linux profile.

**Source mapping:** Claude RM-2; GPT P04 and operations gaps; Repository development topology.

**Progress:** Django 5.2 LTS/DRF 3.16 and Angular/Material 22 with Node 24/TypeScript 6 are adopted; local framework tests/builds pass. Database/jobs remain SQLite/synchronous/local threads; production installation, PostgreSQL/Celery, offline packaging and recovery are not qualified. P02 qualifies a public-dependency core build without the optional SDK and a full marked Linux/ARM64 backend run; production deployment and locked offline supply remain open. P16 adds an explicit fail-closed private runtime with external secret/value-file sources, explicit hosts/HTTPS origins, secure cookies/redirects, an existing artifact root and PostgreSQL verify-full TLS. Both SQLite and PostgreSQL full marked suites pass unchanged assertions, skip and coverage budgets. Real private middleware/session/CSRF, non-superuser migrations, certificate/hostname rejection, restart persistence and a quiescent synthetic database/artifact restore are qualified; the live-reload stack rejects private mode. This is metadata/configuration support, not PostgreSQL dataset intake or qualified production deployment. Project roles, egress/retention, durable workers, expert isolation, independent reproduction and production recovery remain open. P22 adds one exact-package integrity job with durable request/event/result receipts, explicit dedicated Celery/Redis dispatch, database admission/lease bounds, cooperative cancellation, authority/runtime rechecks and fenced terminal publication. Actual prefork delivery, killed-worker recovery after injected lease expiry, duplicate/stale publication, active cancellation and failed broker connection recovery pass against TLS PostgreSQL metadata. Real native package keyboard queue/status/receipt handoff passes in the review workspace. This is partial D07/D12: training/search/scoring migration, private Redis TLS, complete private worker packaging, job backup/restore and production recovery, expert isolation, complete accessibility and release/customer gates remain open. P23 adds a fail-closed private launcher and actual metadata TLS/migration/broker preflight. Authenticated Redis TLS and wrong CA/hostname/credential rejection pass. Actual broker removal retains requests; a quiescent four-state native-job PostgreSQL/artifact snapshot restores exactly into a separate database with an empty broker. The actual dispatcher naturally expires the original 180-second controlled abandoned lease, fences its old token and a fresh prefork worker publishes pending results once; terminal history and original event prefixes remain intact. Both full metadata matrices pass 2032 tests and six skips with unchanged gates. This is bounded synthetic Linux qualification, not complete private packaging, live/machine-loss disaster recovery, expert isolation or D07/release/customer completion. P25 adds synthetic private TLS scoring recovery qualification: exact quiescent metadata/input/package/full-result restore, natural orphan leases, actual duplicate completions, changed/missing-input and current-authority blocking, plus recovered-score exports. Native application behavior and budgets are unchanged; production interrupted-scoring/live-backup/machine-loss recovery and full reproduction/release gates remain open. P27 adds method-named support-weighted rank AUC for requested multiclass stopping, retaining independent sklearn full assessment, input validation and unavailable-objective blocking. Reference callback histories, selected models and replay match across all three native boosters; private/full workflow qualification passes with unchanged budgets. No full reproduction, capacity or release claim. P29 adds an allowlisted fixed native API/worker/dispatcher image, immutable source/runtime inventories and an exact tag-free offline handoff bound to an independently trusted manifest digest. Actual unprivileged read-only Unix WSGI session/CSRF/project checks, empty-slot image import and both complete metadata suites pass. A single API worker preserves legacy process-local search control; durable search migration, complete frontend/TLS installation, supply-chain authentication, egress/retention, production recovery, expert isolation and all release/value/customer gates remain open. P30 adds a fixed, unprivileged buffering TLS ingress with canonical headers, exact Host/SNI handling, bounded ephemeral upload storage and current Django media authorization. Real private HTTPS qualification is added to the existing PostgreSQL fixture/CI job. Complete installation, client-source attribution, comprehensive egress/retention, production recovery, expert isolation and all release/customer gates remain open. P31 adds a recorded allowlisted Angular production/private build, exact immutable TLS asset packaging, same-origin API/media credentials and explicit static/app routes with local fonts/licenses and exact-bundle browser CSP with sandboxed media attachments. Actual private HTTPS developer sign-in/reload, project selection, creation/upload/download/logout and blocked fallback/egress checks pass. Complete multi-image restricted-network installation, supply authentication, production recovery, expert isolation, independent reproduction, comprehensive accessibility and all release/value/customer gates remain open. P32 adds one externally digest-pinned native API/compiled-ingress/PostgreSQL/Redis image handoff with staged all-before-import verification, fixed runtime inventories and repeated digest-only import. Native dependency preparation preserves trusted base identities without relaxing single-image graph checks. Both complete metadata matrices, actual private HTTPS/browser and unchanged recovery pass using exact no-pull dependencies. Complete installation, authenticated supply, fixed-image worker completion, upgrades/rollback, production recovery and release/customer gates remain open. P33 qualifies separate fixed-image native workers and dispatchers through their unchanged entrypoint, actual calibrated classification/regression scoring, protected receipts, input/authority/cancellation checks and twenty duplicate acknowledgements after warm shutdown. Dispatcher SIGTERM/SIGINT handling now ends its bounded pump cleanly. Existing recovery scenarios and budgets remain; full installation, production recovery, expert isolation and all release/customer gates remain open. P34 adds digest-bound offline application-layer installation plans with strict nonsecret operator requests, sealed authority/upload/CSP configuration matching, exact native images and explicit storage/network/secret/dependency prerequisites. Real four-image verification and Compose normalization pass without service adoption or secret reads. Complete host preflight, dependency initialization, deployment/recovery, expert isolation and all release/customer gates remain open. P35 verifies saved plan digests and rederives the supported native profile, then checks Linux filesystem prerequisites using pinned ancestor/metadata descriptors. Exact UID/GID/modes, secret member/size/link constraints and root ACL limits fail closed without reading secret values or artifact descendants. Real UID 10001 fixtures qualify five positive/fault cases. Complete initialization, network/socket preparation, adoption and release/customer gates remain open. P36 initializes only new Linux filesystem roots from operator-delivered secret files, retains exact source bytes and private ownership/modes, and publishes with atomic no-replace semantics. Seven native cases verify retry/fault/race boundaries without changing an operator installation. No dependency, network or service is adopted; complete D07 and release/customer gates remain open. P37 prepares dedicated internal native networks and an empty UID 10001 socket volume from an exact saved plan/fresh root receipt. Labels bind the plan/initialization, foreign or occupied resources are preserved, and native daemon/socket/retry/fault cases pass. Dependencies and application services remain separate adoption steps; D07/release/customer qualification remains open. P38 adds exact-plan four-role adoption after sealed private TLS/migration/non-elevated-role preflight, bound resource/profile checks and independently CA/hostname-verified HTTPS. Matching existing services are kept; conflicting or failed preflight inputs cannot start applications. Local real Compose profiles and fail-closed checks pass; hosted CI must qualify the complete fresh Linux root/repeat/elevated-grant scenario before merge. Dependency provisioning/hardening, full installation, upgrades/rollback, production recovery and all release/customer gates remain open. Hosted adoption exposed the v1 ingress bridge publication defect. P38 renders v2 plans with an internal data bridge and separate publishing ingress bridge; archived v1 plans retain verification semantics and cannot be adopted. Existing roots/resources are never rewritten. Actual port publication and HTTPS are required; host firewall/ingress egress qualification remains open. P39 rechecks all four exact active service profiles and the same container identities after verified HTTPS, then rechecks bound dependency/socket membership before publication. Stopped/paused/restarting/dead/unknown or changed states cannot inherit the earlier snapshot; failures preserve existing services. A real owned Linux pause fault is required in existing CI; no future health or installation/release/customer approval is claimed. P40 prepares only a new bound dependency filesystem, captures five delivered server/owner files, verifies selected-CA/hostname/key consistency, records fixed non-root private resource profiles and publishes atomically without replacement. Root-owned configuration cannot be rewritten by service identities; PostgreSQL/broker storage starts empty. No dependency is started or migrated. Actual initialization/startup, complete hardening, production recovery and all release/customer gates remain open. P41 starts only the exact prepared non-root PostgreSQL/TLS broker/cache profiles, initializes an absent declared app role/database without elevated authority, verifies actual TLS/authentication, and publishes a same-identity immutable startup receipt. Foreign/nonempty/unbound or altered resources and changed role/catalog authority block without repair. Managed dependencies retain full checks through application adoption. Schema migration, complete installation/recovery and release/customer gates remain open. P42 describes the exact sealed migration graph and initializes only a fresh PostgreSQL schema from an approved digest with non-elevated TLS authority, one atomic migration transaction, immutable bound intent/result publication and disclosed lost-result verification. Repeat preserves history; foreign/partial/stale/changed state blocks without repair. Account enrollment, complete hardening/installation/recovery and release/customer gates remain open. P43 adds ordinary private account enrollment with explicit project scope, actual role/TLS/schema/broker preflight, private credential files, atomic operator-attributed account/project records and exact retry/state/collision checks. Fresh adoption preflight uses ephemeral media without customer artifact access. Actual complete fresh Linux/HTTPS acceptance is required before merge; full lifecycle/security/recovery and release/customer gates remain open. P50 explicitly binds private PostgreSQL TLS/GSS/protocol policy in Django and dependency readiness; local sealed-driver controls pass. Fresh adopted-role acceptance is required before merge; selected CA-file preflight and full lifecycle gates remain open. P51 adds bounded consistent selected-public-CA preflight shared by private Django and readiness, retaining public modes and libpq path semantics. Local full and sealed-driver/preflight checks pass; complete fresh Linux and separate base-main qualification are required before merge. Full lifecycle and release/customer gates remain open. P52 hardens stored controller evidence capture with repeated bytes/full metadata and post-read ACL refusal. Local full suite and owned Linux reader faults pass; fresh Linux exact-head qualification remains required. Delivery capture and full lifecycle/release/customer gates remain open. P53 makes application/dependency/prepared-secret delivery capture compare repeated bounded bytes/full metadata and recheck ACL custody. Twenty-nine cases and real Linux owned-copy faults qualify the reader components. Exact-head full/fresh Linux and separate main qualification remain required; full lifecycle/release/customer gates stay open. P54 fixes a reproduced SQLite SFS candidate-publication write-upgrade race using early transaction reservation without extending timeout, and adds operation-correlated native failure stages plus browser error attachments. Private PostgreSQL and scientific assertions remain unchanged. Exact-head/full/private/main qualification and D07 lifecycle/release/customer gates remain required. P55 shares explicit saved SFS state validation across status, results and assistant readers. Recorded failures retain diagnostics; missing/corrupt/unknown/contradictory evidence is unavailable instead of completed or absent. Live precedence and existing history/authority remain. Exact-head/full/private/main qualification and lifecycle/release/customer gates remain required. P56 replaces current SFS checkpoints atomically after strict serialization and file synchronization, preserving previous bytes on pre-replacement failure and exposing directory-sync uncertainty. Operation IDs survive intermediate saves; no distributed ownership or cross-store transaction claim. P57 publishes operation-bound no-overwrite SFS archives and requires history retention before current-result/live completion. Identical retries reuse evidence; conflicts block. Legacy history remains inspectable. Full recovery and distributed SFS remain open. P58 makes tuning state explicit and unavailable on invalid evidence, preserves operation-correlated search/refit/publication/storage diagnostics, and saves results atomically without changing scientific contracts or operational budgets. Distributed tuning and full operation history remain open. P59 validates SFS resume state/bases/steps/features before worker creation, restores every declared direction from evidence, records active merged-direction keys and fingerprints recovery implementation. Canonical IDs and atomic process-local registration prevent divergent or duplicate owners; distributed ownership and full lifecycle remain open. P60 addresses repeated qualification timeouts by removing measured redundant binary threshold metric validation, retaining reference parity, unchanged scientific cases and operational budgets. Exact-head/private/main qualification remains mandatory; host-level timing variation is not diagnosed as a customer-runtime defect. P61 retains operation-bound terminal tuning archives before current-result/live publication, including stops and errors. Identical retries preserve bytes; conflicts and invalid evidence are blocked. Project registration gates advancement and scoped downloads; original and secondary saving failures remain distinct. Full journaling/distributed ownership and lifecycle gates remain open. P62 adds correlated and redacted worker-start failures for SFS/tuning. Known failed launches transition only their current owner to error; uncertain/terminal/stale owners are preserved so launch failure cannot release active work or overwrite another operation. Existing files and scientific execution remain. Durable/distributed ownership and lifecycle gates stay open. P63 binds SFS/tuning callbacks, stop flags and final/error progress to their accepted owner and operation UUID under the admission lock. Late/terminal callbacks cannot revive or change a later owner; SFS diagnostics are constructed before exposing error status. Process-local progress protection is not complete artifact/adoption fencing, distributed leases or durable recovery. P64 adds explicit thread-owned Django connection setup/cleanup around SFS/tuning targets. Redacted setup/execution diagnostics fail only matching running owners; separate cleanup diagnostics preserve original failures and completed evidence. Caller connections/transactions remain intact. Durable workers, process-loss diagnostics and full lifecycle/release/customer gates remain open. P65 serializes stop selection/check/signalling with admission and terminal publication. Optional canonical operation IDs reject stale requests; invalid bodies/IDs leave owners unchanged. Duplicate cancellation remains idempotent and does not release running admission. Legacy unbound requests retain current-run semantics; browser identity binding follows separately. Durable recovery and lifecycle/release/customer gates remain open. P66 binds browser cancellation to the accepted/displayed dataset and operation UUID, validates HTTP arguments at runtime, rejects history as live authority and ignores stale stop replies. Missing identity/conflicts/mismatched acknowledgements cannot trigger unbound fallback or automatic retry. Fifty-two new UI/service cases and651 frontend cases pass with unchanged coverage gates; private build passes. Backend legacy callers, durable recovery and full lifecycle/release/customer gates remain open. P67 adds shared process-local admission for at most two active SFS/tuning owners, retaining stops/uncertain launches and returning non-disclosing capacity refusals without evidence mutation. Logical admission does not bound physical cleanup or input preparation; durable/distributed search and full lifecycle/release/customer qualification remain open. P68 moves result-directory creation inside operation-bound worker preparation. Setup failures cannot strand false running owners or execute scientific work; prior evidence, stale-owner protection, cleanup diagnostics and explicit fresh retries are preserved. Durable/process-loss recovery and full lifecycle/release/customer gates remain open. P69 bounds each PostgreSQL lock wait in durable job serialization to at most five seconds,including bootstrap and later authority/metadata locks. Stricter caller limits and prior settings are preserved across success,errors,nesting and rollback. Execution budgets and SQLite behavior remain unchanged. Complete lifecycle/release/customer gates remain open. P70 refreshes expiry decisions after claim validation and publication authority/result preparation,including late authority denials,and moves reconciliation time inside serialization. Expired leases retain unchanged evidence for reconciliation; expired requests cannot adopt prepared results. Existing budgets and scientific workloads remain. Complete lifecycle/release/customer gates remain open. P71 retires obsolete/unusable database connections around standalone dispatcher cycles and handles driver InterfaceError through the existing redacted retry path. Real owned PostgreSQL session-termination cases verify reconnection in the same command. Full server/lifecycle/release/customer qualification remains open. P72 lets a standalone dispatcher finish its current publish/metadata unit and stop before further queued publishes. Remaining requests and evidence stay unchanged for subsequent dispatch; default and once-mode full-batch behavior remain. Existing execution budgets and lifecycle/release/customer gates remain. P73 repeats the existing non-elevated database-role preflight for every fixed API/worker/dispatcher launch and direct native entrypoint, closing the adoption-only authority gap before service execution. Startup observations do not provide continuous database authority monitoring. Full lifecycle/release/customer gates remain open. P74 extends the existing privileged-role membership predicate to both current_user and session_user,preventing SET ROLE from hiding elevated session authority. Existing policy,result shape,static errors and budgets remain. This is not original-authenticated-identity binding or continuous privilege monitoring; full lifecycle/release/customer gates remain open. P75 requires credentialed private broker configuration before trust or network setup,with strict credential decoding and consistent readiness/Kombu semantics. Development behavior and existing budgets remain. Complete lifecycle/release/customer gates remain open. P76 prevents decoded broker/cache passwords from being silently trimmed during dependency provisioning. Encoded trailing controls block before staging; legitimate delivered-file newlines and valid credential bytes remain supported. Lifecycle/release/customer gates remain open. P77 pins native CSV input with a nonblocking,no-follow regular-file descriptor. Special files and late final symlinks block with static diagnostics; descriptor cleanup preserves existing authority,byte and scoring contracts. Filesystem custody and wider lifecycle/release/customer gates remain open. P78 pins native package metadata,evidence and hashing reads to regular descriptors and bounds metadata allocation before parsing. Existing reason codes,hashing/checkpoint limits and CSV behavior remain. Full lifecycle/release/customer gates remain open. P79 classifies native JSON decoder overflow as invalid input and walks evidence scope iteratively without changing authorization policy. Parsed deep evidence remains reviewable;known malformed input cannot strand a native lease. Unexpected capture/execution recursion remains an uncertain failure. Lifecycle/expert/release/customer gates remain open. P80 rejects unsupported job-list offsets before native job storage access, preserving authorization precedence and valid pagination. Invalid input no longer appears as a database outage. Lifecycle/expert/release/customer gates remain open. P81 preserves the original native work deadline through successful publication, including lock/authority/digest waits. Late candidates receive the existing blocked timeout receipt without adopting results; cancellation, expiry and uncertain-failure recovery remain. Lifecycle/expert/release/customer gates remain open. P82 removes the obsolete root npm install graph and documents the shared frontend dependency path. Supported frontend manifest/lock/vendor bytes and executable sources remain unchanged. Supported development-tool advisory findings and lifecycle/expert/release/customer gates remain open. P83 blocks private startup when recorded migrations are unknown to the selected sealed image or violate dependency history. Consistent pending migrations retain their existing diagnostic. No automatic schema changes or rollback qualification; lifecycle/expert/release/customer gates remain open. P84 reserves configured service DNS names across dependency, application and temporary helper validation. Cross-role aliases, implicit names and malformed reported DNS metadata block before reuse/adoption or helper start. Valid own/generated names and existing runtime contracts remain; later Docker administration and broader lifecycle/release/customer gates remain outside this check. P85 adds read-only managed-table/column presence and relation visibility checks after migration-history validation. Lost, substituted or shadowed metadata relations block before broker access without repair. Full physical-schema, privilege, lifecycle/recovery and release/customer gates remain open. P86 checks each effective table-level CRUD permission on the current managed schema before broker/cache access. Real PostgreSQL revocation cannot silently pass startup; no grants or ownership are changed. Arbitrary ACL profiles, sequences, RLS/data visibility, later privilege changes and full lifecycle/release/customer gates remain outside this check. P87 rejects enabled or forced RLS on current private managed metadata tables so valid table CRUD rights cannot mask filtered metadata. Catalog-only checks preserve policies and earlier diagnostics. Arbitrary RLS profiles, later-state fencing and full lifecycle/release/customer gates remain open. P88 reads actual current/default metadata transaction modes after TLS, rejecting read-only settings before history and service connectivity. No write probe or mode repair occurs. Later settings changes, general write availability and full lifecycle/release/customer gates remain open. P89 pins active/session authority catalogs, membership lookups and role-name equality to pg_catalog, preventing public namespace substitutions from concealing elevated authority. Existing role policy, order and diagnostics remain; continuous authority monitoring and full lifecycle/release/customer gates remain open. P90 pins metadata TLS statistics, backend PID and comparison to pg_catalog so caller-controlled namespaces cannot falsely attest plaintext as TLS. Existing TLS policy, errors and receipts remain; continuous monitoring and full lifecycle/release/customer gates remain open. P91 pins schema-presence, effective permission and row-security catalog joins/filters to built-in operators and identifier types. Substituted columns or alternate-schema tables cannot mask a lost required public schema. Existing policy and diagnostics remain; complete schema/data/lifecycle and release/customer gates remain open. P92 pins the application dependency probe's role, membership and TLS attestation query to built-in catalogs/functions/operators. Its strict no-explicit-membership policy and verified transport remain unchanged; isolated authority-block evidence does not establish a full controller/bootstrap bypass. Continuous monitoring and full lifecycle/release/customer gates remain open. P93 requires the literal reserved pg_ schema prefix instead of a LIKE wildcard. Ordinary pg-prefixed schemas are foreign, preventing fresh migrations/current-state acceptance over unsupported preexisting data. Actual owned graph/state/migration proof and nine native/reference cases preserve system schemas, data and history. Other catalog queries and full lifecycle/release/customer gates remain open. P94 binds initializer state catalogs, aggregates, operators and dependency class identity to built-ins. Temporary catalog substitutes cannot hide unsupported public objects or fabricate foreign evidence. Actual owned graph/state/migration proof blocks before DDL while preserving data/history; genuine current state remains supported. Other authority/lock queries and full lifecycle/release/customer gates remain open. P95 pins initializer advisory-lock acquisition to the built-in function. Two-session lock ownership/contention and caller side-effect controls prevent false exclusion attestations; keys, lifetime and budgets remain unchanged. Isolated lock proof is not a full controller/migration bypass or continuous fencing. Other authority SQL and lifecycle/release/customer gates remain open. P96 pins initializer role/TLS/membership and database owner/encoding queries to built-in catalogs, functions, operators and types. Actual isolated authority-block and separate owner-statement probes reject forged authority without changing policy, privileges, transport or execution budgets. Not a full controller/verified-transport bypass or continuous fencing; other helpers and full lifecycle/release/customer gates remain open. P97 extends the existing schema guard with exact pg_catalog base-type OIDs derived from the sealed migration graph, rejecting text/width/timezone/JSON/array/domain substitutions before broker access. Healthy migrated auth through-table IDs and extra columns remain supported. Read-only startup observation only; modifiers, constraints, continuous fencing and full lifecycle/release/customer gates remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [Explicit runtime configuration and limits](private-runtime-configuration.md); [P16 source qualification](evidence/p16-qualification-2026-10-09.json); [Durable native job foundation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md); [P22 source qualification](evidence/p22-qualification-2026-10-10.json); [Private native job startup and recovery](PRIVATE_JOB_RUNTIME_IMPLEMENTATION.md); [P23 source qualification](evidence/p23-qualification-2026-10-10.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json); [P27 source qualification](evidence/p27-qualification-2026-10-10.json); [Private native API packaging](PRIVATE_API_PACKAGING_IMPLEMENTATION.md); [P29 source qualification](evidence/p29-qualification-2026-10-11.json); [Fixed private TLS ingress](PRIVATE_TLS_INGRESS_IMPLEMENTATION.md); [P30 source qualification](evidence/p30-qualification-2026-10-11.json); [Compiled private frontend](PRIVATE_FRONTEND_IMPLEMENTATION.md); [P31 source qualification](evidence/p31-qualification-2026-10-11.json); [Verified offline native image set](PRIVATE_IMAGE_SET_IMPLEMENTATION.md); [P32 source qualification](evidence/p32-qualification-2026-10-11.json); [Packaged private native jobs](PRIVATE_PACKAGED_JOBS_IMPLEMENTATION.md); [P33 source qualification](evidence/p33-qualification-2026-10-11.json); [Offline private application installation plan](PRIVATE_INSTALLATION_PLAN_IMPLEMENTATION.md); [P34 source qualification](evidence/p34-qualification-2026-10-11.json); [Private plan verification and filesystem prerequisites](PRIVATE_INSTALLATION_CHECK_IMPLEMENTATION.md); [P35 source qualification](evidence/p35-qualification-2026-10-11.json); [Fresh private filesystem initialization](PRIVATE_INSTALLATION_INIT_IMPLEMENTATION.md); [P36 source qualification](evidence/p36-qualification-2026-10-11.json); [Dedicated private networks and socket](PRIVATE_INSTALLATION_RESOURCES_IMPLEMENTATION.md); [P37 source qualification](evidence/p37-qualification-2026-10-11.json); [Controlled private application adoption](PRIVATE_INSTALLATION_ADOPT_IMPLEMENTATION.md); [P38 source qualification](evidence/p38-qualification-2026-10-11.json); [Adoption receipt readiness](PRIVATE_ADOPTION_READINESS_IMPLEMENTATION.md); [P39 source qualification](evidence/p39-qualification-2026-10-12.json); [Fresh dependency preparation](PRIVATE_DEPENDENCY_INIT_IMPLEMENTATION.md); [P40 source qualification](evidence/p40-qualification-2026-10-12.json); [Private dependency startup](PRIVATE_DEPENDENCY_START_IMPLEMENTATION.md); [P41 source qualification](evidence/p41-qualification-2026-10-12.json); [Fresh schema initialization](PRIVATE_SCHEMA_INIT_IMPLEMENTATION.md); [P42 source qualification](evidence/p42-qualification-2026-10-12.json); [Private account enrollment and fresh adoption](PRIVATE_ACCOUNT_ENROLLMENT_IMPLEMENTATION.md); [P43 source qualification](evidence/p43-qualification-2026-10-12.json); [Explicit private PostgreSQL TLS](PRIVATE_POSTGRES_TLS_IMPLEMENTATION.md); [P50 source qualification](evidence/p50-qualification-2026-10-13.json); [Selected PostgreSQL CA preflight](PRIVATE_POSTGRES_CA_IMPLEMENTATION.md); [P51 source qualification](evidence/p51-qualification-2026-10-13.json); [Stored controller capture](PRIVATE_CONTROLLER_CAPTURE_IMPLEMENTATION.md); [P52 source qualification](evidence/p52-qualification-2026-10-13.json); [Installation delivery capture](PRIVATE_DELIVERY_CAPTURE_IMPLEMENTATION.md); [P53 source qualification](evidence/p53-qualification-2026-10-13.json); [SFS async failure diagnostics](SFS_ASYNC_FAILURE_IMPLEMENTATION.md); [P54 source qualification](evidence/p54-qualification-2026-10-14.json); [Honest saved SFS state](SFS_PERSISTED_STATUS_IMPLEMENTATION.md); [P55 source qualification](evidence/p55-qualification-2026-10-14.json); [Atomic SFS checkpoints](SFS_ATOMIC_EVIDENCE_IMPLEMENTATION.md); [P56 source qualification](evidence/p56-qualification-2026-10-14.json); [Operation-bound SFS history](SFS_IMMUTABLE_HISTORY_IMPLEMENTATION.md); [P57 source qualification](evidence/p57-qualification-2026-10-14.json); [Honest tuning failures and atomic results](HYPERPARAM_FAILURE_RECOVERY_IMPLEMENTATION.md); [P58 source qualification](evidence/p58-qualification-2026-10-14.json); [Explicit SFS resume and search admission](SFS_RESUME_ADMISSION_IMPLEMENTATION.md); [P59 source qualification](evidence/p59-qualification-2026-10-14.json); [Binary threshold evaluation performance](BINARY_THRESHOLD_PERFORMANCE_IMPLEMENTATION.md); [P60 source qualification](evidence/p60-qualification-2026-10-14.json); [Operation-bound tuning history](TUNING_IMMUTABLE_HISTORY_IMPLEMENTATION.md); [P61 source qualification](evidence/p61-qualification-2026-10-14.json); [Search worker launch failures](SEARCH_WORKER_LAUNCH_IMPLEMENTATION.md); [P62 source qualification](evidence/p62-qualification-2026-10-14.json); [Search progress ownership](SEARCH_PROGRESS_OWNERSHIP_IMPLEMENTATION.md); [P63 source qualification](evidence/p63-qualification-2026-10-14.json); [Search worker database lifetime](SEARCH_WORKER_CONNECTIONS_IMPLEMENTATION.md); [P64 source qualification](evidence/p64-qualification-2026-10-15.json); [Atomic search cancellation](SEARCH_STOP_OWNERSHIP_IMPLEMENTATION.md); [P65 source qualification](evidence/p65-qualification-2026-10-15.json); [Browser operation-bound cancellation](BROWSER_SEARCH_STOP_IMPLEMENTATION.md); [P66 source qualification](evidence/p66-qualification-2026-10-15.json); [Bounded search admission](SEARCH_CAPACITY_IMPLEMENTATION.md); [P67 source qualification](evidence/p67-qualification-2026-10-15.json); [Search storage setup](SEARCH_STORAGE_SETUP_IMPLEMENTATION.md); [P68 source qualification](evidence/p68-qualification-2026-10-15.json); [Native metadata lock waits](NATIVE_JOB_LOCK_WAITS_IMPLEMENTATION.md); [P69 source qualification](evidence/p69-qualification-2026-10-15.json); [Refreshed native expiry checks](NATIVE_JOB_EXPIRY_IMPLEMENTATION.md); [P70 source qualification](evidence/p70-qualification-2026-10-15.json); [Dispatcher database recovery](DISPATCHER_DATABASE_RECOVERY_IMPLEMENTATION.md); [P71 source qualification](evidence/p71-qualification-2026-10-15.json); [Dispatcher queued-batch shutdown](DISPATCHER_BATCH_SHUTDOWN_IMPLEMENTATION.md); [P72 source qualification](evidence/p72-qualification-2026-10-15.json); [Private service startup authority](PRIVATE_SERVICE_ROLE_PREFLIGHT_IMPLEMENTATION.md); [P73 source qualification](evidence/p73-qualification-2026-10-15.json); [Session and active database authority](PRIVATE_SESSION_ROLE_AUTHORITY_IMPLEMENTATION.md); [P74 source qualification](evidence/p74-qualification-2026-10-15.json); [Private broker authentication](PRIVATE_BROKER_AUTHENTICATION_IMPLEMENTATION.md); [P75 source qualification](evidence/p75-qualification-2026-10-16.json); [Dependency credential byte preservation](DEPENDENCY_CREDENTIAL_BYTES_IMPLEMENTATION.md); [P76 source qualification](evidence/p76-qualification-2026-10-16.json); [Native CSV regular-file capture](NATIVE_CSV_INPUT_FILES_IMPLEMENTATION.md); [P77 source qualification](evidence/p77-qualification-2026-10-16.json); [Bounded native package reads](NATIVE_PACKAGE_FILES_IMPLEMENTATION.md); [P78 source qualification](evidence/p78-qualification-2026-10-16.json); [Reliable native metadata validation](NATIVE_METADATA_VALIDATION_IMPLEMENTATION.md); [P79 source qualification](evidence/p79-qualification-2026-10-16.json); [Native job pagination input bounds](NATIVE_JOB_PAGINATION_IMPLEMENTATION.md); [P80 source qualification](evidence/p80-qualification-2026-10-16.json); [Native publication work deadline](NATIVE_PUBLICATION_DEADLINE_IMPLEMENTATION.md); [P81 source qualification](evidence/p81-qualification-2026-10-16.json); [Canonical frontend dependency installation](CANONICAL_FRONTEND_DEPENDENCIES_IMPLEMENTATION.md); [P82 source qualification](evidence/p82-qualification-2026-10-16.json); [Private migration history guard](PRIVATE_MIGRATION_HISTORY_IMPLEMENTATION.md); [Private service DNS identities](PRIVATE_SERVICE_DNS_IMPLEMENTATION.md); [Private schema presence guard](PRIVATE_SCHEMA_PRESENCE_IMPLEMENTATION.md); [Private effective schema permissions](PRIVATE_SCHEMA_PRIVILEGES_IMPLEMENTATION.md); [P86 source qualification](evidence/p86-qualification-2026-10-17.json); [Private metadata row security](PRIVATE_METADATA_ROW_SECURITY_IMPLEMENTATION.md); [P87 source qualification](evidence/p87-qualification-2026-10-17.json); [Private metadata write mode](PRIVATE_METADATA_WRITE_MODE_IMPLEMENTATION.md); [P88 source qualification](evidence/p88-qualification-2026-10-17.json); [Private role catalog trust](PRIVATE_ROLE_CATALOG_IMPLEMENTATION.md); [P89 source qualification](evidence/p89-qualification-2026-10-17.json); [Private TLS catalog trust](PRIVATE_TLS_CATALOG_IMPLEMENTATION.md); [P90 source qualification](evidence/p90-qualification-2026-10-17.json); [Private schema catalog trust](PRIVATE_SCHEMA_CATALOG_IMPLEMENTATION.md); [P91 source qualification](evidence/p91-qualification-2026-10-17.json); [Private dependency probe catalog trust](PRIVATE_DEPENDENCY_PROBE_CATALOG_IMPLEMENTATION.md); [P92 source qualification](evidence/p92-qualification-2026-10-17.json); [Literal system-schema prefix](PRIVATE_SCHEMA_PREFIX_IMPLEMENTATION.md); [P93 source qualification](evidence/p93-qualification-2026-10-17.json); [Trusted schema-state catalogs](PRIVATE_SCHEMA_STATE_CATALOG_IMPLEMENTATION.md); [P94 source qualification](evidence/p94-qualification-2026-10-17.json); [Trusted initializer advisory lock](PRIVATE_SCHEMA_LOCK_IMPLEMENTATION.md); [P95 source qualification](evidence/p95-qualification-2026-10-18.json); [Trusted initializer authority](PRIVATE_SCHEMA_AUTHORITY_IMPLEMENTATION.md); [P96 source qualification](evidence/p96-qualification-2026-10-18.json); [Physical metadata storage types](PRIVATE_SCHEMA_STORAGE_TYPES_IMPLEMENTATION.md); [P97 source qualification](evidence/p97-qualification-2026-10-18.json)

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

**Progress:** Explicit declaration fields, session-aware navigation, clearer package-versus-production state and bounded keyboard/browser smoke checks are implemented. Full screen-reader and independent-review workflow qualification remains open. P02 makes the bounded keyboard/session/reload and authenticated API checks mandatory in CI; all legacy journeys and screen-reader review remain unqualified. P10 adds source/target/final-row identity, receipt-before-read accounting and exact/overlapping/unknown reuse across executions. Failed/interrupted attempts and actor snapshots remain attributable; history reads do not deserialize outcomes. Exact assessment exports and a resumed, keyboard-operated history panel are qualified locally. All evidence remains exploratory; confirmatory protocols and complete milestone qualification remain open. P11 pins package readiness/builds to verified execution/assessment evidence and scoring/export to immutable bundle IDs. Publication is staged and current-version checked; receipts bind manifest metadata, required native artifacts and original review evidence. Historical versions remain usable; UI exposes blocked states and keyboard-accessible package/score receipts. Full distributed durability, independent reproduction and release qualification remain open. P14 binds one native typed assistant dispatch to an active actor, exact prepared payload, recorded inputs/dispatcher environment, expiry and bounded payload budget. Stale/altered/missing approvals stop; consumed receipts are replayed without redispatch. UI review/approve/cancel and keyboard receipt inspection are qualified, and automatic code repair execution is removed. Downstream jobs, immutable full input/partition authority, expert isolation, project roles, independent review/reproduction and release/customer gates remain open. P15 adds expandable numeric diagnostic tables and keyboard/focus-managed dialogs with states, provenance and limitations, independent of SHAP availability. Late diagnostic/restore responses are rejected, and assistant cache forwarding retains current execution identity. Comprehensive accessibility remains open. P19 adds a server-backed project picker, role explanations and project-filtered dataset/pipeline records. Developer workspaces pin upload/checkpoint ownership and saved-pipeline operations to the selected project; reviewers/admins browse records and download existing reports. Fresh membership checks, canceled/stale response handling, explicit blocked states, visible selection after redirects and keyboard/browser workflows are qualified. This is partial D06/D12; full reviewer findings/approvals/reproduction, member/enrollment UI, SSO/MFA, egress/retention, durable jobs, expert isolation, comprehensive accessibility and release/customer gates remain open. P20 adds exact-package review discussion with attributable reviewer findings/dispositions and developer responses. Active project roles, exact retry receipts, optimistic revisions, concurrent publication, context/integrity freshness and retained historical events are qualified on both metadata engines. Browser keyboard handoff and exact package/discussion downloads pass. Finding closure never confers model or production approval; full independence rules, exceptions/approvals, clean-environment reproduction, full retention and comprehensive accessibility remain open. P21 adds input/runtime-bound full CSV scoring receipts, current-role exact downloads and installed offline native score-parity verification. Clean fixed runtimes without network or installation data reproduce 300-row XGBoost classification/regression exports across whole batches and chunk sizes 1/17/64; calibrated logistic replay and tamper/runtime/authority boundaries pass. Core modules and declared tolerances are recorded. Native serialized state requires explicit trust; full refit/assessment reproduction, independent approval and release qualification remain open. P22 adds one exact-package integrity job with durable request/event/result receipts, explicit dedicated Celery/Redis dispatch, database admission/lease bounds, cooperative cancellation, authority/runtime rechecks and fenced terminal publication. Actual prefork delivery, killed-worker recovery after injected lease expiry, duplicate/stale publication, active cancellation and failed broker connection recovery pass against TLS PostgreSQL metadata. Real native package keyboard queue/status/receipt handoff passes in the review workspace. This is partial D07/D12: training/search/scoring migration, private Redis TLS, complete private worker packaging, job backup/restore and production recovery, expert isolation, complete accessibility and release/customer gates remain open. P26 adds explicit keyboard receipt selection, removal and downloading in package review, preserves job context during writes, and retains exact references across ambiguous retries. Real browser workflows pass; comprehensive accessibility remains open. P28 adds immutable grouped training-input subspace GVIF with nominal category-code invariance, exact one-hot provenance, dimensional adjustment and explicit rank/precision/budget states. Exact native replay uses no fitted state or final outcomes; current reviewers may inspect both numeric and grouped reports, with revocation checks and keyboard summaries. Lossy category encodings block the conditioning set. Independent reference, full metadata and browser checks pass; paired uncertainty, SQLite worker contention, expert isolation and release/customer gates remain open. P28 final hardening validates native NumPy format, bounded header, exact dtype/shape and payload length before allocating arrays; a retained failing-before/passing-after case confirms the boundary. The final complete matrices and browser/runtime image qualify this stronger source without changing prediction calculations or budgets. P31 adds a recorded allowlisted Angular production/private build, exact immutable TLS asset packaging, same-origin API/media credentials and explicit static/app routes with local fonts/licenses and exact-bundle browser CSP with sandboxed media attachments. Actual private HTTPS developer sign-in/reload, project selection, creation/upload/download/logout and blocked fallback/egress checks pass. Complete multi-image restricted-network installation, supply authentication, production recovery, expert isolation, independent reproduction, comprehensive accessibility and all release/value/customer gates remain open.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [P10 holdout reuse and limits](HOLDOUT_REUSE_IMPLEMENTATION.md); [P10 source qualification](evidence/p10-qualification-2026-10-09.json); [P11 package handoff and limits](PACKAGE_HANDOFF_IMPLEMENTATION.md); [P11 source qualification](evidence/p11-qualification-2026-10-09.json); [Exact assistant action implementation](ASSISTANT_APPROVAL_IMPLEMENTATION.md); [P14 source qualification](evidence/p14-qualification-2026-10-09.json); [Immutable numeric diagnostic implementation](COLLINEARITY_IMPLEMENTATION.md); [P15 source qualification](evidence/p15-qualification-2026-10-09.json); [Project workspace implementation](PROJECT_WORKSPACE_IMPLEMENTATION.md); [P19 source qualification](evidence/p19-qualification-2026-10-10.json); [Exact-package review implementation](PACKAGE_REVIEW_IMPLEMENTATION.md); [P20 source qualification](evidence/p20-qualification-2026-10-10.json); [Offline native score verification](OFFLINE_SCORING_IMPLEMENTATION.md); [P21 source qualification](evidence/p21-qualification-2026-10-10.json); [Durable native job foundation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md); [P22 source qualification](evidence/p22-qualification-2026-10-10.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Review execution evidence](REVIEW_EXECUTION_EVIDENCE_IMPLEMENTATION.md); [P26 source qualification](evidence/p26-qualification-2026-10-10.json); [Grouped input diagnostics](GROUPED_COLLINEARITY_IMPLEMENTATION.md); [P28 source qualification](evidence/p28-qualification-2026-10-11.json); [Compiled private frontend](PRIVATE_FRONTEND_IMPLEMENTATION.md); [P31 source qualification](evidence/p31-qualification-2026-10-11.json)

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
