# DeclarAI product development roadmap

Updated 2026-10-25. Generated from `product-roadmap.json`; edit the ledger and run `python3 scripts/render_product_roadmap.py`.

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

**Remaining:** PR #187 merged as 4911c242 after exact-commit run 39090887372 and independent same-head main scheduled run 39092856246 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,081 passed, six existing skips; CI839.806s and main714.377s within the unchanged 900s budget. Initial push run39092748547 was cancelled when the scheduled run began under the existing shared concurrency rule; its receipt is retained separately and not counted as passed. Base-type observations only; modifiers/constraints, continuous fencing and full lifecycle/release/customer gates remain open.

### P98 — Declared metadata type modifiers

**Packet status:** tested. **Mapped outcomes:** D07.

Extend read-only schema admission to exact sealed varchar lengths and timestamp/default modifiers before broker/cache access. Retain base-type identity, required-column/visibility and extra-column policies without schema/data repair.

**Evidence:** [Declared metadata type modifiers](PRIVATE_SCHEMA_TYPE_MODIFIERS_IMPLEMENTATION.md); [P98 source qualification](evidence/p98-qualification-2026-10-18.json)

**Remaining:** PR #188 merged as d66d2aaf after exact-commit run 39095205895 and independent main run 39097090758 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,101 passed, six existing skips; CI839.009s and main834.383s within the unchanged 900s budget. First artifact transfer failed; read-only collection retry succeeded without rerunning CI. Nullability/other constraints, later-state fencing and full lifecycle/release/customer gates remain open.

### P99 — Declared metadata nullability

**Packet status:** tested. **Mapped outcomes:** D07.

Require sealed local-field nullability on required physical metadata columns before broker/cache access, including nullable foreign keys. Preserve type/modifier/visibility and extra-column policy without schema/data repair.

**Evidence:** [Declared metadata nullability](PRIVATE_SCHEMA_NULLABILITY_IMPLEMENTATION.md); [P99 source qualification](evidence/p99-qualification-2026-10-18.json)

**Remaining:** PR #189 merged as 86f279fc after exact-commit run 39100325719 and independent main run 39102151611 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,121 passed, six existing skips; CI848.141s and main852.259s within the unchanged 900s budget. Initial local roadmap-fixture ID collision and GitHub status-read EOFs are retained separately; the fixture chooses an unused ID without changing assertions, and read-only retries did not rerun CI. Generation/other constraints/defaults/indexes/collations, later-state fencing and full lifecycle/release/customer gates remain open.

### P100 — Required metadata generation

**Packet status:** tested. **Mapped outcomes:** D07.

Reject generated physical replacements for required ordinary metadata and unsupported generated declarations in the sealed migration state before broker/cache access. Preserve identity-backed keys, extra-column policy, existing diagnostics and read-only behavior.

**Evidence:** [Required metadata generation](PRIVATE_SCHEMA_GENERATED_COLUMNS_IMPLEMENTATION.md); [P100 source qualification](evidence/p100-qualification-2026-10-18.json)

**Remaining:** PR #190 merged as a46af09f after exact-commit run 39105661100 and independent main run 39107625351 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,141 passed, six existing skips; CI849.503s and main748.783s within the unchanged 900s budget. Read-only GitHub status retries retained original failures without CI reruns. Identity modes/defaults/other constraints/triggers/collations, later-state fencing and full lifecycle/release/customer gates remain open.

### P101 — Declared metadata identity generation

**Packet status:** tested. **Mapped outcomes:** D07.

Require selected-backend BY DEFAULT identity on sealed local auto fields and no identity on ordinary required fields, including foreign keys. Preserve extra columns and existing diagnostics with a read-only catalog check before broker/cache access.

**Evidence:** [Declared metadata identity generation](PRIVATE_SCHEMA_IDENTITY_IMPLEMENTATION.md); [P101 source qualification](evidence/p101-qualification-2026-10-18.json)

**Remaining:** PR #191 merged as e6a0c40e after exact-head run 39111434547 and independent main run 39113003908 passed all six checks on attempt one with complete private/native reports. Full PostgreSQL: 4,167 passed, six existing skips; CI490.171s and main852.185s within the unchanged 900s test budget. Two status-read EOFs are retained; read-only retries did not rerun CI. Sequence state/privileges/defaults/other constraints, later-state fencing and full lifecycle/release/customer gates remain open.

### P102 — Declared metadata primary keys

**Packet status:** tested. **Mapped outcomes:** D07.

Require sealed local single-column primary keys with validated nondeferrable constraints and valid immediate backing indexes before broker/cache access. Preserve legitimate names, included extra columns, ordinary writes and existing read-only diagnostics.

**Evidence:** [Declared metadata primary keys](PRIVATE_SCHEMA_PRIMARY_KEYS_IMPLEMENTATION.md); [P102 source qualification](evidence/p102-qualification-2026-10-18.json); [PostgreSQL suite execution budget](POSTGRESQL_SUITE_RUNTIME_IMPLEMENTATION.md)

**Remaining:** P102 source remains qualified. Its original main run 39118117480 failed at 900 seconds and stays retained. Follow-up PR #193 merged as bd7bf71a after exact-head run 39129613322 and independent main run 39131552309 passed all six checks on attempt 1 with complete native/private reports. PostgreSQL: 4,205 passes/six identical skips in 533.355s and 522.953s under the unchanged 900s deadline, with original test hashes/inventory preserved and worker database/cache isolation verified. Other constraints, later-state fencing and full lifecycle/release/customer gates remain open.

### P103 — Declared metadata field uniqueness

**Packet status:** tested. **Mapped outcomes:** D07.

Require genuine immediate single-column UNIQUE constraints and valid backing indexes for sealed non-primary unique fields before broker/cache access. Preserve local foreign-key semantics, default nullable uniqueness, genuine names/covering indexes, ordinary writes and extra columns.

**Evidence:** [Declared metadata field uniqueness](PRIVATE_SCHEMA_UNIQUE_FIELDS_IMPLEMENTATION.md); [P103 source qualification](evidence/p103-qualification-2026-10-18.json)

**Remaining:** PR #194 merged as 7bdada8a after revised exact-head run 39140231829 and independent main run 39142173604 passed all six checks on attempt 1 with complete native/private reports. PostgreSQL: 4,241 passes/six identical skips in 441.456s and 532.547s under the unchanged 900s deadline, with original test inventory and worker isolation preserved. Initial run 39137969852 had one browser retry and was not accepted as zero-flaky qualification; its reports remain retained. The keyboard fixture now asserts the exact saved pipeline is active before review. Other constraints, later-state fencing and full lifecycle/release/customer gates remain open.

### P104 — Declared metadata compound uniqueness

**Packet status:** tested. **Mapped outcomes:** D07.

Require genuine immediate constraints and valid backing indexes for sealed ordinary compound UNIQUE declarations, preserving exact local membership, default NULL semantics, equivalent ordering/names/INCLUDE and ordinary writes. Unsupported declaration forms fail closed before broker/cache access.

**Evidence:** [Declared metadata compound uniqueness](PRIVATE_SCHEMA_COMPOUND_UNIQUENESS_IMPLEMENTATION.md); [P104 source qualification](evidence/p104-qualification-2026-10-19.json)

**Remaining:** PR #195 exact head cbcfe31d314f583bfbf4c8fa14719733ce7d84a9 passed all six and complete native/private reports in CI 39146379410 on attempt 1. Guarded merge bdd1fedacea292f7d8b467abac0f1d7a4f56ad65 matches its qualified tree; independent main CI 39148062920 passed all six on attempt 1, native 4,317 passed/six unchanged skips in 479.542s, all 76 new cases in both matrices, frontend 651/browser 37 without retries. Original case/skip identities, worker isolation and complete native/private reports verify. Other constraint/index/collation/inheritance equivalence, later-state fencing and lifecycle/release/customer gates remain open.

### P105 — Declared metadata foreign-key contract

**Packet status:** tested. **Mapped outcomes:** D07.

Check genuine validated foreign-key metadata for each sealed local-to-target column pair, exact public target identities and the selected Django deferred/match/action profile before broker/cache access. Preserve names, nullable references and ordinary writes; unsupported unconstrained relation declarations fail closed.

**Evidence:** [Declared metadata foreign keys](PRIVATE_SCHEMA_FOREIGN_KEYS_IMPLEMENTATION.md); [P105 source qualification](evidence/p105-qualification-2026-10-19.json)

**Remaining:** PR #196 exact head 709d61f8e585bfd886052b5a92b943ea295767d3 passed all six and complete native/private reports in CI 39182891428 on attempt 1. Guarded merge 76ad605907cfbe3e6c2acd399385323c7db48128 matches its qualified tree; independent main CI 39185092208 passed all six on attempt 1, native 4,439 passed/six unchanged skips in 574.258s. Both matrices pass all 122 foreign-key cases; frontend 651/browser 37 pass without retries/flakes/skips. Original case/skip identities, worker isolation and complete native/private reports verify. RI trigger/session-state enforcement, full schema/data equivalence, later-state fencing and lifecycle/release/customer gates remain open.

### P106 — PostgreSQL RI-trigger profile

**Packet status:** tested. **Mapped outcomes:** D07.

Require four genuine enabled internal enforcement roles per declared foreign key, exact built-in function/event/constraint/relation/index linkage and the selected deferred NO ACTION profile. Preserve normal and always-enabled modes, arbitrary names and existing diagnostics. Qualify privileged corruption through a separate owned fault controller and non-elevated application process.

**Evidence:** [PostgreSQL RI triggers](PRIVATE_SCHEMA_RI_TRIGGERS_IMPLEMENTATION.md); [P106 source qualification](evidence/p106-qualification-2026-10-19.json)

**Remaining:** PR #197 exact head 21beacfe995917569c82e5bac32964468b1fed2a passed all six and complete original/new native/private reports in CI 39190265351 on attempt 1: native 4,439 passed/six unchanged skips in 565.526s, additional RI matrix 392. Guarded merge ab5e07393c3bfddc141f093aff9e81a1465187ce matches its qualified tree; independent scheduled main CI 39193789662 passed all six on attempt 1, native 4,439/six skips in 585.675s, full serial backend 4,439/six skips, additional RI matrix 392, frontend 651/browser 37 without retries. Original native/reference case and skip identities, worker isolation, complete private reports and owned cleanup verify. Push CI 39192698962 was canceled when the scheduled same-commit run began; no rerun was requested. Connection replication modes, historical integrity, later-state fencing and lifecycle/release/customer gates remain open.

### P107 — Current metadata connection replication mode

**Packet status:** tested. **Mapped outcomes:** D07.

Require actual origin/local replication mode in the existing read-only schema query before broker/cache access. Preserve genuine RI metadata, query shape and redacted diagnostics. Qualify reconnect/default disagreement, ordinary-role committed-data controls, forged lookup namespaces and real unavailable lookup evidence.

**Evidence:** [Metadata replication mode](PRIVATE_METADATA_REPLICATION_MODE_IMPLEMENTATION.md); [P107 source qualification](evidence/p107-qualification-2026-10-19.json)

**Remaining:** PR #198 exact head 8d2700dd07263a384f4dfe911d33ab75dd0e47ee passed all six and complete native/private receipts in CI 39198249456 on attempt 1: native 4,439/six unchanged skips in 488.654s, physical cases 440. Guarded merge 653711f4d4f7f23ee37ae2dcaea6ddcc51a3ba99 matches its qualified tree; independent push main CI 39200639141 passed all six on attempt 1: native 4,439/six skips in 335.548s, full serial backend 4,439/six skips, physical cases 440, frontend 651/browser 37 without retries. Original native/reference/physical case and skip identities, worker isolation, complete private receipts and owned cleanup verify. No CI rerun was requested. Parameter authority, historical integrity, later-state fencing and full lifecycle/release/customer gates remain open.

### P108 — PostgreSQL replication-parameter authority

**Packet status:** tested. **Mapped outcomes:** D07.

Reject SET/ALTER SYSTEM authority for the replication parameter in existing role admission, including effective/PUBLIC and current/session direct or indirect membership paths. Preserve six-column query shape, builtin evidence, static errors and existing command order. Qualify delegated capability faults through the separately owned physical controller.

**Evidence:** [Parameter authority](PRIVATE_PARAMETER_AUTHORITY_IMPLEMENTATION.md); [P108 source qualification](evidence/p108-qualification-2026-10-19.json)

**Remaining:** PR #199 exact head c8671b5b734dd13ae7a81d5917485581f7226574 passed all six and complete native/private receipts in CI 39204338073 on attempt 1. Guarded merge 46eaf5e1a75f70f17cd4670ff29eb82e5c4529cd matches its qualified tree; independent push main CI 39206748784 passed all six on attempt 1: native 4,439/six unchanged skips in 582.240s, full serial backend 4,439/six skips, physical cases 510, frontend 651/browser 37 without retries. Original case/skip identities, worker isolation, complete reports and owned cleanup verify. Other parameter/predefined-role authority, historical integrity, later-state fencing and full lifecycle/release/customer gates remain open.

### P109 — PostgreSQL checkpoint-role authority

**Packet status:** tested. **Mapped outcomes:** D07.

Exclude pg_checkpoint authority from the existing six-column application-role admission query, retaining current/session conservative membership, built-in catalog evidence, static redaction and runtime-before-role command order. Append separately administered physical qualification without changing prior cases.

**Evidence:** [Checkpoint-role authority](PRIVATE_CHECKPOINT_AUTHORITY_IMPLEMENTATION.md); [P109 source qualification](evidence/p109-qualification-2026-10-19.json)

**Remaining:** PR #200 exact head 10a9f80fc23a70f9211ceeb74430427dbfea6a05 passed all six and complete native/private receipts in CI 39218919217 on attempt 1: native 4,439/six unchanged skips in 584.515s, physical cases 560. Guarded merge ccf670d27351efdcdc36c199197cba952c9a1bc8 matches its qualified tree; independent push main CI 39222299623 passed all six on attempt 1: native 4,439/six skips in 479.842s, full serial backend 4,439/six skips, physical cases 560, frontend 651/browser 37 without retries. Original case/skip identities, worker isolation, complete reports and owned cleanup verify. P110 maintenance-role implementation is merged and independently main-qualified as PR #201; its bounded evidence is tracked separately. Other predefined-role authority, historical integrity, later-state fencing and full lifecycle/release/customer gates remain open.

### P110 — PostgreSQL maintenance-role authority

**Packet status:** tested. **Mapped outcomes:** D07.

Exclude pg_maintain authority from the existing current/session application-role admission profile, preserving built-in evidence, the six-column query, conservative membership and command order. Qualify the supported boundary through separately administered physical controls.

**Evidence:** [Maintenance-role authority](PRIVATE_MAINTAIN_AUTHORITY_IMPLEMENTATION.md); [P110 source qualification](evidence/p110-qualification-2026-10-19.json); [P110 PR #201](https://github.com/caglarsubas/auto_ml/pull/201); [P110 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39231539363); [P110 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39234645971)

**Remaining:** Local source qualification: native 4,439/six unchanged skips, focused PostgreSQL/reference 869/969, 610 physical cases including all 560 original cases and 50 maintenance-role cases, frontend 651, lint, original inventories and worker isolation pass. PR #201 exact-head CI 39231539363 passed all six on attempt 1 at b7d8c6b8a7e7dc03418d31e03ff69c776f143b10: native 4,439/six unchanged skips in 324.359s, 610 physical cases, frontend 651 and browser 37 first-attempt passes. Complete native/private receipts and original inventories verify. Merged as b6277b1c3f0596eab4170dadda5d44a4c9f49fe0, matching the qualified PR tree. Independent push main CI 39234645971 passed all six on attempt 1: native 4,439/six unchanged skips in 579.431s, full serial backend 4,439/six skips, 610 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, worker isolation and source hashes verify. Other authority, historical integrity, continuous fencing and full D07 lifecycle/release/customer acceptance remain open.

### P111 — PostgreSQL subscription-role authority

**Packet status:** tested. **Mapped outcomes:** D07.

Exclude pg_create_subscription authority through the existing current/session application-role admission query, preserving built-in evidence, six-column shape, conservative membership and command order. Qualify disconnected subscription catalog creation with a separate fixture administrator.

**Evidence:** [Subscription-role authority scope](PRIVATE_SUBSCRIPTION_AUTHORITY_IMPLEMENTATION.md); [P111 source qualification](evidence/p111-qualification-2026-10-19.json); [P111 PR #202](https://github.com/caglarsubas/auto_ml/pull/202); [P111 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39254037903); [P111 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39257782850)

**Remaining:** Local source qualification: native 4,439/six unchanged skips, focused PostgreSQL/reference 869/969, all 660 physical cases (610 original plus 50 subscription-role cases), frontend 651/build, lint, original inventories and isolation pass. PR #202 exact-head CI 39254037903 passed all six on attempt 1 at 5be31b25a84cef6231e5bd3988a69130110ad072: native 4,439/six unchanged skips in 562.083s, 660 physical cases, frontend 651 and browser 37 first-attempt passes. Complete native/private reports and original inventories verify. Merged as 315c33e4190fd05ac41462b47845b1cc6d691c7b, matching the qualified PR tree. Independent push main CI 39257782850 passed all six on attempt 1: native 4,439/six unchanged skips in 469.989s, full serial backend 4,439/six skips, 660 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and source hashes verify. Other authority, historical definitions, actual replication/egress, continuous fencing and full D07/lifecycle/release/customer acceptance remain open.

### P112 — PostgreSQL statistics-role authority

**Packet status:** tested. **Mapped outcomes:** D07.

Exclude pg_read_all_stats from current/session private application-role admission, including pg_monitor membership. Preserve the existing built-in-qualified, read-only six-column predicate, conservative membership policy and runtime-before-role command order. Qualify real synthetic cross-principal query visibility and restoration with a separate fixture administrator.

**Evidence:** [Statistics-role authority scope](PRIVATE_STATISTICS_AUTHORITY_IMPLEMENTATION.md); [P112 source qualification](evidence/p112-qualification-2026-10-19.json); [P112 PR #203](https://github.com/caglarsubas/auto_ml/pull/203); [P112 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39267125686); [P112 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39270531813)

**Remaining:** Local source qualification: native 4,439/six unchanged skips, focused PostgreSQL/reference 869/969, all 714 physical cases (660 original plus 54 statistics-role cases), frontend 651/build, unchanged lint, original inventories and worker isolation pass. PR #203 exact-head CI 39267125686 passed all six on attempt 1 at d61153ccb5e14c59927e677072c791d17f0a8fcf: native 4,439/six unchanged skips in 336.834s, 714 physical cases, frontend 651/browser 37 first-attempt passes. Complete native/private reports and original inventories verify. Merged as fad193efc1f535eab38bbc9d76be32f5b197afb9, matching the qualified PR tree. Independent push main CI 39270531813 passed all six on attempt 1: native 4,439/six unchanged skips in 567.088s, full serial backend 4,439/six skips, 714 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and source hashes verify. Other authority, custom view/function grants, historical access, continuous fencing and full D07/lifecycle/release/customer gates remain open.

### P113 — PostgreSQL settings-role authority

**Packet status:** tested. **Mapped outcomes:** D07.

Exclude pg_read_all_settings from current/session private application-role admission. Preserve the built-in-qualified, read-only six-column query, conservative membership and runtime-before-role command order. Qualify protected configuration visibility using only owned server paths, without configuration changes or file reads.

**Evidence:** [Settings-role authority scope](PRIVATE_SETTINGS_AUTHORITY_IMPLEMENTATION.md); [P113 source qualification](evidence/p113-qualification-2026-10-20.json); [P113 PR #204](https://github.com/caglarsubas/auto_ml/pull/204); [P113 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39360440984); [P113 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39363175020); [P113 superseded push main CI (cancelled)](https://github.com/caglarsubas/auto_ml/actions/runs/39363097400)

**Remaining:** Local source qualification: native 4,439/six unchanged skips, focused PostgreSQL/reference 869/969, all 764 physical cases (714 original plus 50 settings-role cases), frontend 651/build, unchanged lint, original inventories and worker isolation pass. PR #204 exact-head CI 39360440984 passed all six on attempt 1 at 46ab522939a3e9fc394a8c6c2463b6bcc32d1870: native 4,439/six unchanged skips in 559.865s, 764 physical cases, frontend 651/browser 37 first-attempt passes. Complete native/private reports and original inventories verify. Merged as 3d87a8654cc7718c40a25cd45b8f6a45002194f3, matching the qualified PR tree. Independent scheduled main CI 39363175020 passed all six on attempt 1: native 4,439/six unchanged skips in 350.403s, full serial backend 4,439/six skips, 764 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and source hashes verify. Original push main CI 39363097400 was superseded by the automatic nightly run on the same commit through the unchanged concurrency group; cancellation is retained and supplies no passing result. No CI rerun was requested. Other authority, custom view/function grants, historical access, continuous fencing and full D07/lifecycle/release/customer gates remain open.

### P114 — CI trigger isolation

**Packet status:** tested. **Mapped outcomes:** D07.

Separate push, scheduled and manual CI concurrency groups by workflow/ref/trigger. Preserve within-trigger supersession, six existing jobs and all test budgets; add an automated data-only policy guard.

**Evidence:** [CI trigger isolation scope](CI_TRIGGER_ISOLATION_IMPLEMENTATION.md); [P114 source qualification](evidence/p114-qualification-2026-10-20.json); [P114 PR #205](https://github.com/caglarsubas/auto_ml/pull/205); [P114 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39367238291); [P114 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39369876550)

**Remaining:** P114 isolates CI triggers while retaining within-trigger supersession. Local policy: 21 comparisons and eight negative controls pass; three old trigger collisions reproduce. Product runtime and original test workloads/budgets remain unchanged. PR #205 exact-head CI 39367238291 passed all six on attempt 1 at 3e53cd5ba331e38debe50f62612b00ba3f09127b: native 4,439/six unchanged skips in 566.782s, all 764 original physical cases, frontend 651/browser 37 first-attempt passes. Complete reports, policy guard, inventories and isolation verify. Merged as 1911805095ee1b0d74e9f42354787dc8eaa28475, matching the qualified PR tree. Independent push main CI 39369876550 passed all six on attempt 1: native 4,439/six unchanged skips in 557.821s, full serial backend 4,439/six skips, all 764 original physical cases, frontend 651/browser 37 without retries. Policy guard, complete reports, unchanged inventories, isolation and source hashes verify. Live post-fix push/nightly overlap and GitHub scheduling/account limits are not claimed. D07/release/customer gates remain open.

### P115 — PostgreSQL column collation hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Bind required text/varchar columns to the sealed default collation and require zero for noncollatable types; reject unsupported explicit db_collation declarations. Preserve ordinary comparisons, existing qualification and startup redaction.

**Evidence:** [Column collation implementation](PRIVATE_POSTGRESQL_COLUMN_COLLATION_IMPLEMENTATION.md); [P115 source qualification](evidence/p115-qualification-2026-10-20.json); [P115 PR #206](https://github.com/caglarsubas/auto_ml/pull/206); [P115 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39378985057); [P115 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39381235360)

**Remaining:** P115 enforces the sealed default column collation and rejects unsupported explicit declarations. Owned PostgreSQL reproduction changes two ORM comparisons; 12 old denial gaps now close. Local qualification passes 16 new PostgreSQL tests, 985 SQLite references, all 797 physical cases (764 original plus 33 new), and the full native suite with original workloads and limits preserved. PR #206 exact-head CI 39378985057 passed all six on attempt 1 at 600420d21a83e00fcd0a1801fad82228902c2828: native 4,455/six unchanged skips in 341.971s; all 797 physical cases; frontend 651/browser 37 first-attempt passes. Complete private reports, original inventories, policy guard and worker isolation verify. Merged as bb61076f626e3dca169c68404107fa76ebf95064, matching the qualified PR tree. Independent push-main CI 39381235360 passed all six on attempt 1: native 4,455/six unchanged skips in 603.708s; full serial backend 4,455/six skips; all 797 physical cases; frontend 651/browser 37 without retries. Complete reports, source hashes, original inventories, policy guard and worker isolation verify. Admission-time column evidence does not establish historical integrity, continuous fencing or default-provider/version equivalence. D07, release and customer gates remain open.

### P116 — Managed adoption operation serialization

**Packet status:** tested. **Mapped outcomes:** D07.

Join managed application adoption to the existing dependency/schema operation lock; retain it through final HTTPS and receipt checks. Preserve historical unmanaged scope without a new serialization claim.

**Evidence:** [Managed operation serialization](PRIVATE_OPERATION_SERIALIZATION_IMPLEMENTATION.md); [P116 source qualification](evidence/p116-qualification-2026-10-20.json); [P116 PR #207](https://github.com/caglarsubas/auto_ml/pull/207); [P116 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39391145117); [P116 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39394672026)

**Remaining:** P116 serializes managed adoption with dependency startup and schema initialization through final HTTPS/receipt checks. Two old lock bypasses reproduce; 14 new guard cases and 305 focused cases pass. Full local native qualification passes 4,469 with six unchanged skips under the original 900-second limit. PR #207 exact-head CI 39391145117 passed all six on attempt 1: native 4,469/six unchanged skips in 575.551s; all 797 original physical cases; frontend 651/browser 37 without retries. Complete reports, original inventories, worker isolation and actual Linux-root shared-lock/HTTPS/history checks verify. Merged as f2862caa9e4d941a840e94d98efaecc3923ca0a0, matching the qualified PR tree. Independent push-main CI 39394672026 passed all six on attempt 1: native 4,469/six unchanged skips in 568.735s; full serial backend 4,469/six skips; physical 797; frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and host-operation proofs verify. The advisory guard covers cooperating managed controllers, not administrators or legacy unmanaged serialization. D07/lifecycle/release/customer gates remain open.

### P117 — Read-only lifecycle readiness and operator review

**Packet status:** tested. **Mapped outcomes:** D07.

Observe a managed installation through exact profiles, stable service identities and selected-CA HTTPS without service execution or repair. Provide explicit operator inputs before choosing a real maintenance/recovery profile.

**Evidence:** [Lifecycle operator review](PRIVATE_LIFECYCLE_OPERATOR_REVIEW.md); [P117 source qualification](evidence/p117-qualification-2026-10-20.json); [P117 PR #208](https://github.com/caglarsubas/auto_ml/pull/208); [P117 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39395174601); [P117 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39398628762)

**Remaining:** P117 adds read-only managed-installation observation: seven exact service profiles/identities, stable state around selected-CA HTTPS, existing-lock contention, redacted output and explicit operator review inputs. No service execution/repair or fresh database preflight is performed. All 32 new cases and 337 focused cases pass. Full local native qualification passes 4,501 with six unchanged skips under the original 900-second limit. PR #208 exact-head CI 39395174601 passed all six on attempt 1: native 4,501/six unchanged skips in 541.101s; all 797 original physical cases; frontend 651/browser 37 without retries. Complete reports, original inventories, worker isolation and actual Linux-root read-only/held-lock/paused-worker/no-repair/history checks verify. Merged as 394e0707a36adf12291ddd8f9537d4830acd3391, matching the qualified PR tree. Independent push-main CI 39398628762 passed all six on attempt 1: native 4,501/six unchanged skips in 589.240s; full serial backend 4,501/six skips; physical 797; frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and actual host observation proofs verify. Operator checkpoint: review the actual deployment target/trusted plan and CA, maintenance window/permitted downtime, RPO/RTO, backup storage/encryption/retention and external network controls before selecting a real lifecycle drill. D07 durable training/search, coordinated recovery and upgrade/rollback gates remain open; no release/customer acceptance is claimed.

### P118 — Durable bounded native training and search

**Packet status:** tested. **Mapped outcomes:** D07.

Run bounded native numeric CSV binary/regression training, paired development-fold search and final refit through durable queue leases; publish JSON model and reproducible evidence only through fenced DB completion.

**Evidence:** [Durable development training/search](DURABLE_TRAINING_SEARCH_IMPLEMENTATION.md); [P118 source qualification](evidence/p118-qualification-2026-10-20.json); [P118 PR #209](https://github.com/caglarsubas/auto_ml/pull/209); [P118 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39409186389); [P118 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39412958093)

**Remaining:** P118 adds bounded native numeric CSV binary/regression training and two-candidate search through the durable queue. Accepted declarations, input bytes, features, matched folds, trusted objectives, runtimes and complete budgets are bound to the preview digest; fold-local imputation and final refit publish a native JSON model/evidence only through fenced DB completion. Existing split/model or known assessment-source history blocks this fresh development-only profile. PR #209 exact-head CI 39409186389 passed all six on attempt 1: native 4,543/six unchanged skips in 616.613s; all 797 original physical cases; frontend 651/browser 37 without retries. Complete private training/actual-host receipts, original inventories, worker isolation and source hashes verify. Merged as 474cc69528d58d714b30bb356146e0a5ce464215, matching the qualified PR tree. Independent automatic push-main CI 39412958093 passed all six on attempt 1: native 4,543/six unchanged skips in 546.976s; full serial backend 4,543/six skips; physical 797; frontend 651/browser 37 without retries. Complete training, private/host reports, inventories and isolation verify. Legacy training/SFS/broad HPO and their launch UI remain unmigrated. Dedicated launch controls, larger profiles, immutable trial checkpoints, export/scoring and reviewed candidate adoption remain open. Source copies must still match their pins; modified/reordered imports and unknown history are not automatically linked. Real customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open.

### P119 — Inspectable durable training/search launch UI

**Packet status:** tested. **Mapped outcomes:** D07.

Declare, preview, explicitly review and queue the bounded native training/search profile from the governed workspace; inspect durable status and download evidence with role/context and exact-request protections.

**Evidence:** [Reviewed training/search launch UI](TRAINING_SEARCH_LAUNCH_UI_IMPLEMENTATION.md); [P119 source qualification](evidence/p119-qualification-2026-10-20.json); [P119 PR #210](https://github.com/caglarsubas/auto_ml/pull/210); [P119 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39420541174); [P119 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39424272366)

**Remaining:** P119 adds an explicit developer launch panel for the bounded durable training/search profile. A form declares task, target/positive label, ordered numeric predictors, objective and validation controls; the server preview exposes exact input/plan/folds/runtime/budget before a separate confirmation and submission. Edits/context changes invalidate review; uncertain admission retries the identical UUID/body. Existing durable history/cancellation/refreshed evidence downloads remain available to authorized readers. PR #210 exact-head CI 39420541174 passed all six on attempt 1: native 4,543/six unchanged skips in 574.515s; physical 797; frontend 674/browser 40 without retries, preserving all original 37 browser identities. Full private/host receipts and inventories verify. Merged as d1f9fd210ca1d06a8153859d7998699b22686514, matching the qualified PR tree. Independent automatic push-main CI 39424272366 passed all six on attempt 1: native 4,543/six unchanged skips in 594.969s; full serial backend 4,543/six skips; physical 797; frontend 674/browser 40 without retries. Complete private training, host reports, original inventories and isolation verify. The new launch panel covers only the bounded P118 development profile. Legacy synchronous training/SFS/broad HPO remain unmigrated. Larger profiles, trial checkpoints, native export/scoring, final assessment and reviewed candidate adoption remain open. Unknown history and modified/reordered imports are not automatically linked; input bytes must still match their pins. Customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open.

### P120 — Native training-result export and durable scoring

**Packet status:** tested. **Mapped outcomes:** D07.

Export native training candidates and score pinned feature-only CSVs through the durable queue or external-digest offline runner, preserving fitted preprocessing and unapproved exploratory scope.

**Evidence:** [Native training candidate export/scoring](NATIVE_TRAINING_CANDIDATE_IMPLEMENTATION.md); [P120 source qualification](evidence/p120-qualification-2026-10-20.json); [P120 PR #211](https://github.com/caglarsubas/auto_ml/pull/211); [P120 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39433627919); [P120 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39437055061)

**Remaining:** P120 exports exact native development candidates and queues feature-only numeric CSV scoring with frozen means/order, complete receipts and an external-digest offline runner. Separate preview/approval pins model, source, runtime and budget; context edits and stale dependencies block. No adoption, outcome evaluation or production approval occurs. PR #211 exact-head CI 39433627919 passed all six on attempt 1: native 4,582/six unchanged skips in 353.007s; physical 797; frontend 689/browser 42 without retries, preserving all original 40 browser identities. Full private/host receipts and inventories verify. Merged as b2feaa7f3af68b7ffc3de208b282104770f279de, matching the qualified PR tree. Independent automatic push-main CI 39437055061 passed all six on attempt 1: native 4,582/six unchanged skips in 621.808s; full serial backend 4,582/six skips; physical 797; frontend 689/browser 42 without retries. Complete private candidate/training, host reports, original inventories and isolation verify. Export/scoring covers only the bounded P118 native development profile and feature-only numeric inputs. Legacy synchronous training/SFS/broad HPO remain unmigrated. Larger profiles, trial checkpoints, final assessment and reviewed candidate adoption remain open. Unknown history and modified/reordered imports are not automatically linked; input bytes must still match their pins. Customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open.

### P121 — Reviewed native candidate adoption and protected assessment

**Packet status:** tested. **Mapped outcomes:** D07.

Independently accept exact native candidates, seal protected outcomes outside generic datasets and evaluate frozen models through access-accounted durable jobs with aggregate-only exploratory evidence.

**Evidence:** [Reviewed native candidate assessment](REVIEWED_NATIVE_ASSESSMENT_IMPLEMENTATION.md); [P121 source qualification](evidence/p121-qualification-2026-10-21.json); [P121 PR #212](https://github.com/caglarsubas/auto_ml/pull/212); [P121 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39465579127); [P121 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39470251700)

**Remaining:** P121 adds attributable independent review of exact native development candidates, private reviewer-only outcome custody and access-accounted durable protected assessment. Frozen preprocessing, task/positive-label mapping and trusted metrics are reused without refitting or production approval. Reuse, failed accesses and upstream-history limitations remain explicit; all assessments are exploratory. PR #212 exact-head CI 39465579127 passed all six on attempt 1: native 4,617/six unchanged skips in 586.642s; physical 809 (797 original + 12 additive); frontend 701/browser 44 without retries, preserving all original 42 browser identities. Full private/host receipts and inventories verify. Merged as 6e385586180df6ce073b99e6ca01a76c18eabb74, matching the qualified PR tree. Independent automatic push-main CI 39470251700 passed all six on attempt 1: native 4,617/six unchanged skips in 400.639s; full serial backend 4,617/six skips; physical 809 (797 original + 12 additive); frontend 701/browser 44 without retries. Complete private assessment/restore/candidate/training, host reports, original inventories and isolation verify. Assessment covers the bounded numeric binary/regression P118 native profile: 30–1000 protected rows, 5 MiB, exact validation controls and frozen trusted metrics. Reviewer attestation does not prove unknown external history, population independence or maturity. Legacy synchronous training/SFS/broad HPO, larger profiles, trial checkpoints, confirmatory protocols and production promotion remain open. Private outcome bytes require coordinated database backup, retention and access controls; infrastructure administrators remain trusted. Customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open.

### P122 — Native cancellation, recovery and operational review handoff

**Packet status:** tested. **Mapped outcomes:** D07.

Qualify native cancellation and natural lease recovery; hand off exact operational evidence and conservative outcome-access accounting for independent review.

**Evidence:** [Native operational handoff](NATIVE_OPERATIONAL_HANDOFF_IMPLEMENTATION.md); [P122 source qualification](evidence/p122-qualification-2026-10-21.json); [P122 PR #213](https://github.com/caglarsubas/auto_ml/pull/213); [P122 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39535626205); [P122 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39538976423)

**Remaining:** P122 adds a read-only revision/digest-pinned operational handoff: attributable history, lease/retry guidance and conservative protected-access counts without outcomes or model state. Native cancellation retains exact-request identity and fences publication; recovery retains unresolved accesses and all exploratory limits. PR #213 exact-head CI 39535626205 passed all six at attempt 1: native 4,640/six unchanged skips in 577.353s; 809 physical cases; 710 frontend units and 45 first-attempt browsers, retaining all original inventories. Private TLS cancellation, natural lease recovery and exact coordinated restore verify. Merged as 19742beb42b9e49e64aea8e290465a6e98c0bdd3, exact qualified tree. Independent automatic push-main CI 39538976423 passed all six at attempt 1: native 4,640/six unchanged skips in 716.565s, full serial backend 4,640/six skips, 809 physical, 710 frontend and 45 browsers. Full original reports, policy, host/lifecycle, inventories and worker isolation verify. Bounded numeric binary/regression native jobs only; unresolved/failed access remains possible inspection, all assessments exploratory. No trial checkpoints, legacy training/SFS/broad HPO migration, confirmatory or production approval. The handoff does not test live service health or grant recovery authority. Customer installation recovery, coordinated backup/restore, upgrade/rollback, larger workloads and expert isolation remain open. D07, release and customer acceptance remain open.

### P123 — Native queue observability and bounded history navigation

**Packet status:** tested. **Mapped outcomes:** D07.

Observe dataset queue metadata and navigate/filter durable history in bounded pages without execution or recovery side effects.

**Evidence:** [Native queue observability and history](NATIVE_QUEUE_HISTORY_IMPLEMENTATION.md); [P123 source qualification](evidence/p123-qualification-2026-10-21.json); [P123 PR #214](https://github.com/caglarsubas/auto_ml/pull/214); [P123 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39548153768); [P123 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39551164042)

**Remaining:** P123 adds read-only dataset queue observations with state counts, dispatch/lease/expiry signals, observed time and explicit unobserved worker/broker health. Signed user/project/dataset/filter-bound cursors navigate both directions with at most 50 metadata rows per page; the UI replaces pages and clears stale snapshots on errors or context changes. PR #214 exact-head CI 39548153768 passed all six at attempt 1: native 4,678/six unchanged skips in 507.090s; all 809 inherited physical cases; 720 frontend units and 46 first-attempt browsers, retaining every original inventory and private recovery/restore proof. Merged as 3fc5e225cae78f565d89aabf6b5e88c36e8d31fd, exact qualified tree. Independent automatic push-main CI 39551164042 passed all six at attempt 1: native 4,678/six unchanged skips in 514.195s, full serial backend 4,678/six skips, 809 physical, 720 frontend and 46 browsers. Full raw reports, policy, host/lifecycle, original inventories and two-worker isolation verify. Queue observation never dispatches, reconciles, retries or grants recovery/review authority. Dataset counts do not measure installation occupancy, queue position or live service health. State filters remain live within a submission-time cutoff; cursors expire after one hour and refresh starts a new view. Legacy list API remains compatible. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. Assessments stay exploratory; no production approval.

### P124 — Operator-facing native queue incident triage and evidence export

**Packet status:** tested. **Mapped outcomes:** D07.

Triage installation-native queue incidents and export bounded operator evidence without changing jobs, services or approval authority.

**Evidence:** [Operator native queue incident triage](NATIVE_QUEUE_INCIDENT_TRIAGE.md); [P124 source qualification](evidence/p124-qualification-2026-10-21.json); [P124 PR #215](https://github.com/caglarsubas/auto_ml/pull/215); [P124 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39561335243); [P124 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39565033935)

**Remaining:** P124 adds Linux-root installation-operator native queue incident triage, bound to the trusted plan, native images and exact service profiles. Degraded/missing service states and bounded read-only repeatable-read PostgreSQL metadata are exported atomically to a private, non-overwriting, digest-checked evidence file. Unavailable observations, overlapping historical signals and unstable service samples remain explicit. Receipt refresh now withdraws stale evidence immediately, preventing keyboard actions against controls about to be replaced. The tracker now explains outcome-state percentages and shows dynamic tested-packet and D07 delivery counts. PR #215 exact-head CI 39561335243 passed all six at attempt 1: native 4,715/six unchanged skips in 445.018s; all 809 inherited physical cases; 722 frontend units and 47 first-attempt browsers. All original inventories and private recovery/restore/host proofs plus actual managed Linux incident collection/export verify. Merged as e63c2a615076f79d50a17b7ffe5b72de30bb5cd7, exact qualified tree. Independent automatic push-main CI 39565033935 passed all six at attempt 1: native 4,715/six unchanged skips in 463.721s; full serial backend 4,715/six skips; 809 physical, 722 frontend, 47 first-attempt browsers. Full raw reports, original inventories, policy, host/lifecycle, incident export and two-worker isolation verify. Operator authority is Linux root with a trusted managed plan; project roles receive no global API/MCP access. Triage never dispatches, reconciles, retries, cancels, repairs or approves work. No models, outcomes or event payloads are fetched; credentials and raw reasons/logs are never exported. Counts and signals are observations, not broker delivery or live health. Reports are installation-confidential point-in-time evidence, not signatures or recovery approval. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. Assessments remain exploratory.

### P125 — Incident evidence verification and operator runbook handoff

**Packet status:** tested. **Mapped outcomes:** D07.

Verify retained incident evidence and export a bounded operator investigation runbook without live runtime access or new execution authority.

**Evidence:** [Incident evidence verification and operator runbook handoff](NATIVE_QUEUE_EVIDENCE_HANDOFF.md); [P125 source qualification](evidence/p125-qualification-2026-10-21.json); [P125 PR #216](https://github.com/caglarsubas/auto_ml/pull/216); [P125 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39573130413); [P125 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39578077835)

**Remaining:** P125 adds bounded offline Linux-root verification of incident evidence against independently trusted evidence/plan digests and installation/initialization pins. Strict schema, private descriptor-based input and explicit age/availability/sample limits feed an atomic private, non-overwriting runbook handoff with fixed investigation guidance and revision-pinned references. No plan/credential, service, database or network observation occurs during verification; no recovery or approval is granted. PR #216 exact-head CI 39573130413 passed all six at attempt 1: native 4,755/six unchanged skips in 556.289s; all 809 inherited physical cases; 722 frontend units and 47 inherited first-attempt browsers. All original inventories and private recovery/restore/host proofs plus actual managed Linux incident verification/handoff verify. Merged as 59e63c61736f8bef1f7bf27149e7a94afc85b70e, exact qualified tree. Independent automatic push-main CI 39578077835 passed all six at attempt 1: native 4,755/six unchanged skips in 693.712s; full serial backend 4,755/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Full raw reports, original inventories, policy, host/lifecycle, incident verification/handoff and two-worker isolation verify. Verification and a matching checksum do not authenticate the creator, certify live health or authorize recovery. Root-only incident metadata remains installation-confidential. Human incident ownership/findings and any maintenance, new request, review or production use require separate records and authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. Assessments remain exploratory.

### P126 — Incident snapshot consistency and bounded coverage hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Cross-check incident counts, row semantics, sample coverage and observation intervals before operator handoff; disclose sample-order limitations.

**Evidence:** [Incident snapshot consistency and operator handoff](NATIVE_QUEUE_EVIDENCE_HANDOFF.md); [P126 source qualification](evidence/p126-qualification-2026-10-21.json); [P126 PR #217](https://github.com/caglarsubas/auto_ml/pull/217); [P126 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39595273389); [P126 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39600294336)

**Remaining:** P126 cross-checks incident snapshot counts, overlapping signal feasibility, row flags and bounded sample coverage before offline handoff. Queue observation time must fit its enclosing collection interval; sampled order is checked and any discrepancy is disclosed without rewriting evidence. Consistency is distinct from digest integrity, authenticity, live health and recovery approval. PR #217 exact-head CI 39595273389 passed all six at attempt 1: native 4,792/six unchanged skips in 692.841s; all 809 inherited physical cases; 722 frontend units and 47 inherited first-attempt browsers. All original inventories and private recovery/restore/host proofs plus actual managed Linux incident consistency checks and CLI refusal verify. Merged as 7b0fd8ec453c630a8ba16585bf37ca338e480c72, exact qualified tree. Independent automatic push-main CI 39600294336 passed all six at attempt 1: native 4,792/six unchanged skips in 642.486s; full serial backend 4,792/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Full raw reports, original inventories, policy, host/lifecycle, incident consistency and two-worker isolation verify. Verification and a matching checksum do not authenticate the creator, certify live health or authorize recovery. Root-only incident metadata remains installation-confidential. Human incident ownership/findings and any maintenance, new request, review or production use require separate records and authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. Assessments remain exploratory.

### P127 — Native job list metadata and cache hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Fetch only selected job metadata for legacy list pages; prevent caching of successful and denied operational reads while preserving authority and pagination.

**Evidence:** [Native job list metadata and queue history](NATIVE_QUEUE_HISTORY_IMPLEMENTATION.md); [P127 source qualification](evidence/p127-qualification-2026-10-21.json); [P127 PR #218](https://github.com/caglarsubas/auto_ml/pull/218); [P127 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39624516161); [P127 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39632072764)

**Remaining:** P127 restricts the legacy native-job list to selected scalar metadata and JSON keys, avoiding full request/result/authority/model materialization in the controller. GET/HEAD responses are no-store, including early authentication/project denials. Existing page fields, ordering, offset forms, project scoping and final authority rechecks remain compatible. PR #218 exact-head CI 39624516161 passed all six at attempt 1: native 4,821/six unchanged skips in 655.299s; 809 inherited physical cases, 722 frontend units and 47 inherited first-attempt browsers. Full original inventories and private recovery/restore/host/incident proofs verify. Merged as 8775d25eaeaaca1733fb0f442735c621b30c8476, exact qualified tree. Independent automatic push-main CI 39632072764 passed all six at attempt 1: native 4,821/six unchanged skips in 691.024s; full serial backend 4,821/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. List metadata remains observational; it does not execute, cancel, retry, recover, approve or authenticate a model/result. No capacity benchmark or whole-installation readiness claim is made. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. Assessments remain exploratory.

### P128 — Native job read cache boundary

**Packet status:** tested. **Mapped outcomes:** D07.

Prevent caching across native-job reads, including private evidence/downloads and early denials, while preserving payloads, authority and execution semantics.

**Evidence:** [Native job read cache boundary and queue history](NATIVE_QUEUE_HISTORY_IMPLEMENTATION.md); [P128 source qualification](evidence/p128-qualification-2026-10-22.json); [P128 PR #219](https://github.com/caglarsubas/auto_ml/pull/219); [P128 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39648650555); [P128 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39653822271)

**Remaining:** P128 applies a shared HTTP no-store boundary to every native-job GET/HEAD response, including result details, input metadata, history, review records, candidate/scoring downloads and operational handoffs. Authentication/project denials, safe service errors and unsupported reads receive the same policy. Status, response/download bytes and digests, project authority, job state and mutation semantics remain unchanged. PR #219 exact-head CI 39648650555 passed all six at attempt 1: native 4,884/six unchanged skips in 577.487s; 809 inherited physical cases, 722 frontend units and 47 inherited first-attempt browsers. Full original inventories and private recovery/restore/host/incident proofs verify. Merged as 4b698d1aa71de4f7f1296bafba71430b79060f58, exact qualified tree. Independent automatic push-main CI 39653822271 passed all six at attempt 1: native 4,884/six unchanged skips in 554.839s; full serial backend 4,884/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Cache protection is an HTTP response directive; it does not purge previously retained copies, authenticate evidence or authorize execution, recovery, review or production use. No capacity benchmark or whole-installation readiness claim is made. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. Assessments remain exploratory.

### P129 — Bounded operator probe output capture

**Packet status:** tested. **Mapped outcomes:** D07.

Bound operator probe stdout capture without temporary files, preserving fixed command, timeout, metadata and safe failure semantics

**Evidence:** [Bounded operator probe capture and incident triage](NATIVE_QUEUE_INCIDENT_TRIAGE.md); [P129 source qualification](evidence/p129-qualification-2026-10-22.json); [P129 PR #220](https://github.com/caglarsubas/auto_ml/pull/220); [P129 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39693765932); [P129 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39697300946)

**Remaining:** P129 replaces file-backed installation-operator probe stdout with a bounded pipe: at most 128 KiB plus one over-budget sentinel is retained; excess is drained and discarded during the unchanged 20-second child deadline. Cleanup does not wait for inherited writers to close. Command, stderr suppression, accepted JSON limit, evidence schema and sanitized failure semantics remain unchanged. PR #220 exact-head CI 39693765932 passed all six at attempt 1: native 4,921/six unchanged skips in 604.880s; 809 inherited physical cases, 722 frontend units and 47 inherited first-attempt browsers. Full original inventories and private recovery/restore/host/incident proofs verify. Merged as a5b63c39925e4a4e60ea1abe4293ccb27bff4044, exact qualified tree. Independent automatic push-main CI 39697300946 passed all six at attempt 1: native 4,921/six unchanged skips in 620.604s; full serial backend 4,921/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. The bound applies to retained probe output, not total process memory or a capacity benchmark. Excess output may still flow until the fixed command exits or its original timeout. Read-only triage does not grant recovery, review or production authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P130 — Native authorization metadata projection

**Packet status:** tested. **Mapped outcomes:** D07.

Project native resource authority from scalar dataset metadata before reading payloads, preserving access and diagnostic contracts

**Evidence:** [Native authorization metadata projection](PROJECT_AUTHORIZATION_IMPLEMENTATION.md); [P130 source qualification](evidence/p130-qualification-2026-10-22.json); [P130 PR #221](https://github.com/caglarsubas/auto_ml/pull/221); [P130 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39704835857); [P130 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39708321616)

**Remaining:** P130 resolves native job, adoption and protected-input resource authority through dataset-ID-only queries. Native request/result/authority/proposal/sealed-input data is not fetched or materialized before project checks. Existing roles, resource/selector bindings, audit/rechecks, cache policy and sanitized adoption lookup failures remain compatible. PR #221 exact-head CI 39704835857 passed all six at attempt 1: native 4,978/six unchanged skips in 676.484s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 2b7761f9388feb0c6cda2b3e4dd88d6136c3a8e7, exact qualified tree. Independent automatic push-main CI 39708321616 passed all six at attempt 1: native 4,978/six unchanged skips in 479.913s; full serial backend 4,978/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This bounds the authorization routing projection, not total request memory. Authorized services retain their existing data reads and execution authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P131 — Native CSV parent descriptor hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Capture native CSVs through pinned parent directory descriptors, closing late symlink redirection while preserving input contracts

**Evidence:** [Native CSV parent descriptor capture](NATIVE_CSV_INPUT_FILES_IMPLEMENTATION.md); [P131 source qualification](evidence/p131-qualification-2026-10-22.json); [P131 PR #222](https://github.com/caglarsubas/auto_ml/pull/222); [P131 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39719458774); [P131 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39723229515)

**Remaining:** P131 lexically normalizes trailing root separators/dot components and pins the configured storage root and each native CSV parent with no-follow directory descriptors, then opens the final file relative to its pinned parent. Late symlinks are rejected; renaming an opened parent cannot redirect capture through its old path. Original missing-file, regular-file, digest, budget, cancellation, receipt and scoring behavior remains. PR #222 exact-head CI 39719458774 passed all six at attempt 1: native 5,032/six unchanged skips in 798.645s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 39b34b60d94a387d8e5cffaf8de75b329dc95f3a, exact qualified tree. Independent automatic push-main CI 39723229515 passed all six at attempt 1: native 5,032/six unchanged skips in 762.218s; full serial backend 5,032/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Configured-root/ancestor custody remains trusted; this is not an atomic filesystem snapshot or a bound on kernel I/O. No hostile root-ancestor/mount-namespace qualification is claimed. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P132 — Native package parent descriptor hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Capture native package metadata, evidence and worker hashes through pinned parents; preserve limits, digests and job diagnostics

**Evidence:** [Native package parent descriptor capture](NATIVE_PACKAGE_FILES_IMPLEMENTATION.md); [P132 source qualification](evidence/p132-qualification-2026-10-22.json); [P132 PR #223](https://github.com/caglarsubas/auto_ml/pull/223); [P132 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39729086232); [P132 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39733381879)

**Remaining:** P132 pins native package metadata, evidence and worker hashing to no-follow storage-root and parent directory descriptors, reusing P131 capture. Late symlinks reject; already-opened parents retain original files after path replacement. Out-of-root/traversing paths reject before open. Existing digest/change fences, metadata and evidence limits, hash budgets, authority, cancellation and job diagnostics remain. PR #223 exact-head CI 39729086232 passed all six at attempt 1: native 5,135/six unchanged skips in 798.478s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 6df42cfd2a5cc3bc5c09fe5b04783d69ba96ff57, exact qualified tree. Independent automatic push-main CI 39733381879 passed all six at attempt 1: native 5,135/six unchanged skips in 783.709s; full serial backend 5,135/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Configured-root/ancestor custody remains trusted; this is not an atomic filesystem snapshot, model-deserialization isolation or a bound on kernel I/O. No hostile root-ancestor/mount-namespace qualification is claimed. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P133 — Native lease reconciliation metadata hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Reconcile expired native leases and queued work using transition metadata only; preserve payloads and recovery behavior

**Evidence:** [Metadata-only native lease reconciliation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#metadata-only-lease-reconciliation-p133); [P133 source qualification](evidence/p133-qualification-2026-10-22.json); [P133 PR #224](https://github.com/caglarsubas/auto_ml/pull/224); [P133 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39750105030); [P133 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39754097699)

**Remaining:** P133 projects only state, revision, attempts, lease, dispatch, expiry and terminal metadata during expired-lease/queued reconciliation. Locked SELECTs and deferred UPDATEs exclude opaque payloads, digests and related-object identifiers; no lazy payload fetch occurs. Cancellation precedence, exact reasons, revisions, rollback, sampled clock and due ordering/100 limit remain. PR #224 exact-head CI 39750105030 passed all six at attempt 1: native 5,172/six unchanged skips in 472.563s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 1bb14805f2d63405e5676594b16ca283119d21d1, exact qualified tree. Independent automatic push-main CI 39754097699 passed all six at attempt 1: native 5,172/six unchanged skips in 799.651s; full serial backend 5,172/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Metadata projection is not a capacity benchmark, a new scheduling bound or expert isolation. Database internals may still read storage pages containing payloads. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P134 — Native post-authority checkpoint fencing

**Packet status:** tested. **Mapped outcomes:** D07.

Refresh native checkpoint guards after authority validation; preserve lease budgets, error precedence and recovery behavior

**Evidence:** [Checkpoint refresh after authority validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#checkpoint-refresh-after-authority-validation-p134); [P134 source qualification](evidence/p134-qualification-2026-10-22.json); [P134 PR #225](https://github.com/caglarsubas/auto_ml/pull/225); [P134 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39775447667); [P134 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39780525058)

**Remaining:** P134 refreshes job state, lease token and lease/request expiry metadata after successful authority validation and repeats the existing checkpoint guards, including the monotonic work deadline. Late cancellation, token replacement, expiry or budget exhaustion stops return to worker work. The final read is nonlocking and metadata-only; initial guard precedence, authority/storage failures, receipts and recovery semantics remain. PR #225 exact-head CI 39775447667 passed all six at attempt 1: native 5,221/six unchanged skips in 726.774s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 2714d7c2533ecdc4cfc35d964c5b635c6815996a, exact qualified tree. Independent automatic push-main CI 39780525058 passed all six at attempt 1: native 5,221/six unchanged skips in 725.215s; full serial backend 5,221/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Checkpoint fencing is cooperative; it is not atomic interruption, expert isolation or a deadline on kernel I/O or authority validation itself. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P135 — Native claim attempt-budget enforcement

**Packet status:** tested. **Mapped outcomes:** D07.

Enforce native claim attempt ceiling; preserve eligible retries, receipts, payloads and recovery behavior

**Evidence:** [Claim attempt-budget enforcement](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#claim-attempt-budget-enforcement-p135); [P135 source qualification](evidence/p135-qualification-2026-10-22.json); [P135 PR #226](https://github.com/caglarsubas/auto_ml/pull/226); [P135 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39794611077); [P135 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39801653753)

**Remaining:** P135 enforces the existing three-attempt ceiling at native claim time. Exhausted queued rows close with failed/job_attempts_exhausted before authority/runtime or work; duplicate deliveries cannot append a second receipt. Nonqueued/capacity/expiry precedence, eligible retry leases, payloads and transactional rollback remain. PR #226 exact-head CI 39794611077 passed all six at attempt 1: native 5,253/six unchanged skips in 809.755s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 9d5a56bd3336b7212dfd01e75dfadf1bca696271, exact qualified tree. Independent automatic push-main CI 39801653753 passed all six at attempt 1: native 5,253/six unchanged skips in 775.143s; full serial backend 5,253/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This guards inconsistent/restored queued metadata; it neither qualifies a customer restore nor authorizes automatic repair. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P136 — Native incomplete-lease fencing

**Packet status:** tested. **Mapped outcomes:** D07.

Fence incomplete native leases without publishing results or repairing metadata; preserve valid execution and recovery behavior

**Evidence:** [Incomplete-lease fencing](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#incomplete-lease-fencing-p136); [P136 source qualification](evidence/p136-qualification-2026-10-23.json); [P136 PR #227](https://github.com/caglarsubas/auto_ml/pull/227); [P136 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39814513505); [P136 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39819297022)

**Remaining:** P136 rejects missing lease tokens or expiries at native checkpoint and finish fences. A null token pair cannot authorize work or publication; absent expiry stops safely without TypeError. Invalid metadata, payloads and receipts remain untouched for operator review. Valid leases, cancellation, deadlines and recovery semantics remain. PR #227 exact-head CI 39814513505 passed all six at attempt 1: native 5,287/six unchanged skips in 609.715s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 8f1a51b81881b82ce99ad673fed7fdc178f1297e, exact qualified tree. Independent automatic push-main CI 39819297022 passed all six at attempt 1: native 5,287/six unchanged skips in 808.837s; full serial backend 5,287/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This is fail-closed fencing, not automatic metadata repair or customer restore qualification. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P137 — Native checkpoint payload isolation

**Packet status:** tested. **Mapped outcomes:** D07.

Exclude unrelated stored outputs from checkpoint reads while preserving execution guards and authority validation

**Evidence:** [Checkpoint payload isolation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#checkpoint-payload-isolation-p137); [P137 source qualification](evidence/p137-qualification-2026-10-23.json); [P137 PR #228](https://github.com/caglarsubas/auto_ml/pull/228); [P137 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39904440597); [P137 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39907937634)

**Remaining:** P137 limits native checkpoint reads to required guards and execution authority/specification fields, excluding unrelated stored outputs, actor snapshots and publication/dispatch history. Both guard reads, real primary/source authority, referenced training-result integrity, cancellation and deadlines remain enforced. No checkpoint writes or lazy payload fetches are introduced. PR #228 exact-head CI 39904440597 passed all six at attempt 1: native 5,312/six unchanged skips in 777.446s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as f5fa85dbcda86722f0bca180b3aaa1763d15cf71, exact qualified tree. Independent automatic push-main CI 39907937634 passed all six at attempt 1: native 5,312/six unchanged skips in 594.098s; full serial backend 5,312/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This qualifies checkpoint data access; throughput, total memory and customer restore remain unmeasured. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P138 — Deterministic native dispatch order

**Packet status:** tested. **Mapped outcomes:** D07.

Select tied due requests deterministically while preserving queue limits, recovery transitions and dispatch behavior

**Evidence:** [Deterministic dispatch order](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#deterministic-dispatch-order-p138); [P138 source qualification](evidence/p138-qualification-2026-10-23.json); [P138 PR #229](https://github.com/caglarsubas/auto_ml/pull/229); [P138 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39914069091); [P138 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39917709010)

**Remaining:** P138 orders due native jobs by creation timestamp and UUID before the existing 100-ID slice. Tied requests and recovered leases have a stable batch prefix across native kinds. Oldest-first priority, eligibility filters, recovery transitions, broker backoff and worker/publication guards remain unchanged. PR #229 exact-head CI 39914069091 passed all six at attempt 1: native 5,328/six unchanged skips in 478.078s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 3de53563cbdcef90cb9796c5be8c015a677e143b, exact qualified tree. Independent automatic push-main CI 39917709010 passed all six at attempt 1: native 5,328/six unchanged skips in 811.162s; full serial backend 5,328/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This qualifies deterministic selection, not execution-completion order, starvation prevention, capacity or customer restore. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P139 — Operational handoff history-counter hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Validate recorded event history without allocation proportional to an inconsistent stored revision counter

**Evidence:** [Handoff history-counter validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-history-counter-validation-p139); [P139 source qualification](evidence/p139-qualification-2026-10-23.json); [P139 PR #230](https://github.com/caglarsubas/auto_ml/pull/230); [P139 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39925757216); [P139 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39931319968)

**Remaining:** P139 rejects operational handoff event-count mismatches before sequence comparison and validates recorded events by enumeration. Inconsistent stored revision counters cannot drive a proportional range allocation under the queue lock. Structured read failures, valid receipts/digests, stale and project-authority precedence, gap detection and read-only behavior remain. PR #230 exact-head CI 39925757216 passed all six at attempt 1: native 5,355/six unchanged skips in 839.998s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 48f816e2e4d31ff2e5c700a665767c337ade78c2, exact qualified tree. Independent automatic push-main CI 39931319968 passed all six at attempt 1: native 5,355/six unchanged skips in 800.385s; full serial backend 5,355/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This removes counter-driven allocation; actual event-query size, total capacity and customer restore remain unqualified. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P140 — Operational handoff access-summary hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Aggregate scoped outcome-access counts without materializing individual access rows

**Evidence:** [Handoff access-summary aggregation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-access-summary-aggregation-p140); [P140 source qualification](evidence/p140-qualification-2026-10-23.json); [P140 PR #231](https://github.com/caglarsubas/auto_ml/pull/231); [P140 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39940975742); [P140 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39945544738)

**Remaining:** P140 summarizes outcome accesses with one scalar database aggregate instead of materializing individual access-state rows under the queue lock. Exact state labels, conservative counts, scoped filtering, unknown-state refusal, valid receipts/digests, earlier authority/history guards and read-only no-store behavior remain. PR #231 exact-head CI 39940975742 passed all six at attempt 1: native 5,386/six unchanged skips in 801.786s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as ba269ec3948c885264757ad78301097367394923, exact qualified tree. Independent automatic push-main CI 39945544738 passed all six at attempt 1: native 5,386/six unchanged skips in 807.929s; full serial backend 5,386/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Access-summary return cardinality is constant; database scan cost, actual event-query size, total capacity and customer restore remain unqualified. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P141 — Operational handoff database-read timeout hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Bound handoff database statements without leaking or relaxing caller settings

**Evidence:** [Handoff database-read timeout](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-database-read-timeout-p141); [P141 source qualification](evidence/p141-qualification-2026-10-23.json); [P141 PR #232](https://github.com/caglarsubas/auto_ml/pull/232); [P141 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39953198637); [P141 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39958252915)

**Remaining:** P141 bounds each PostgreSQL handoff SQL statement to at most five seconds, retaining stricter caller limits. The transaction-scoped setting is applied before queue acquisition and restored after success or rollback. Slow queries fail closed with safe uncached API errors; full receipts, authority/history/result checks, conservative accesses and execution budgets remain. PR #232 exact-head CI 39953198637 passed all six at attempt 1: native 5,412/six unchanged skips in 824.405s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as a556ae2d23fdcc72f3a135783d94a4041770b9e1, exact qualified tree. Independent automatic push-main CI 39958252915 passed all six at attempt 1: native 5,412/six unchanged skips in 510.632s; full serial backend 5,412/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. The limit applies to each SQL statement, not the total request duration or Python processing. SQLite retains its development file lock; production timeout behavior is separately verified on PostgreSQL. Total capacity, actual event-query size and customer restore remain unqualified. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P142 — Operational handoff metadata validation

**Packet status:** tested. **Mapped outcomes:** D07.

Reject malformed handoff metadata without partial exports or history repair

**Evidence:** [Handoff metadata validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-metadata-validation-p142); [P142 source qualification](evidence/p142-qualification-2026-10-23.json); [P142 PR #233](https://github.com/caglarsubas/auto_ml/pull/233); [P142 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39968430283); [P142 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39973475526)

**Remaining:** P142 rejects unsupported job states and non-object event details with structured handoff conflicts before reading outcome history. Valid receipt fields, reason values, full event sequences, digests, conservative access accounting, earlier authority/revision/result guards, scoped SQL timeouts and read-only no-store behavior remain. PR #233 exact-head CI 39968430283 passed all six at attempt 1: native 5,446/six unchanged skips in 646.560s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 6607808c1d846c2cecad6cd9cc986e01f6155c46, exact qualified tree. Independent automatic push-main CI 39973475526 passed all six at attempt 1: native 5,446/six unchanged skips in 679.120s; full serial backend 5,446/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. These checks validate supported state labels and object-shaped event details; they do not certify historical provenance, every specification field, installation capacity or customer restore. Existing per-statement limits are not total request or Python-processing bounds. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P143 — Operational handoff specification validation

**Packet status:** tested. **Mapped outcomes:** D07.

Refuse invalid saved specification fields without partial handoff exports or repair

**Evidence:** [Handoff specification validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-specification-validation-p143); [P143 source qualification](evidence/p143-qualification-2026-10-24.json); [P143 PR #234](https://github.com/caglarsubas/auto_ml/pull/234); [P143 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39986672566); [P143 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39993166059)

**Remaining:** P143 refuses malformed saved specification objects, unsupported job kinds and invalid attempt limits before handoff history reads, returning a structured conflict. Supported kinds retain saved positive limits, full receipts and exact digests. Earlier authority/revision/result guards, conservative access counts, scoped SQL timeouts and read-only no-store behavior remain. PR #234 exact-head CI 39986672566 passed all six at attempt 1: native 5,501/six unchanged skips in 810.345s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as d763d949a8a740711f44e7b4c077563956f021c3, exact qualified tree. Independent automatic push-main CI 39993166059 passed all six at attempt 1: native 5,501/six unchanged skips in 701.677s; full serial backend 5,501/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. These export-field shape checks do not certify full request provenance, runtime compatibility, installation capacity or customer restore. Existing per-statement limits are not total request or Python-processing bounds. No history cap, normalization, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P144 — Exact operator queue-state comparisons

**Packet status:** tested. **Mapped outcomes:** D07.

Keep operator state aggregates, incident filters and bounded samples consistent under insensitive database collation

**Evidence:** [Operator state comparisons](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#operator-state-comparisons-p144); [P144 source qualification](evidence/p144-qualification-2026-10-24.json); [P144 PR #235](https://github.com/caglarsubas/auto_ml/pull/235); [P144 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40050323800); [P144 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40053222055)

**Remaining:** P144 preserves exact operator queue-state counts and incident selection with explicit collation. Case/accent variants stay unknown rather than becoming known states or displacing canonical incidents. Existing metadata projection, row bounds/order, offline consistency checks, read-only transaction and timeout behavior remain. PR #235 exact-head CI 40050323800 passed all six at attempt 1: native 5,523/six unchanged skips in 806.470s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as d9077b41b855cc1f972ff4f9541ee4da752e2567, exact qualified tree. Independent automatic push-main CI 40053222055 passed all six at attempt 1: native 5,523/six unchanged skips in 842.870s; full serial backend 5,523/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This is an observational query correction, not approval of a changed physical schema or proof of database capacity or current service health. Labels are not normalized or repaired and no execution or recovery authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P145 — Operator snapshot transaction and SQL budgets

**Packet status:** tested. **Mapped outcomes:** D07.

Preserve database timeout policy and transaction ownership with truthful versioned operator snapshots

**Evidence:** [Operator read budgets](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#operator-read-budgets-p145); [P145 source qualification](evidence/p145-qualification-2026-10-24.json); [P145 PR #236](https://github.com/caglarsubas/auto_ml/pull/236); [P145 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40063993357); [P145 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40066378384)

**Remaining:** P145 requires standalone autocommit ownership for operator reads, honors stricter database SQL budgets and emits snapshot v2 with its effective timeout. Version-aware consumers retain strict legacy v1 verification. Read-only/repeatable-read behavior, failure restoration, metadata/state semantics and fixed probe/resource limits remain. PR #236 exact-head CI 40063993357 passed all six at attempt 1: native 5,571/six unchanged skips in 694.477s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 1501d815747cd39fbde704075c0c979607308358, exact qualified tree. Independent automatic push-main CI 40066378384 passed all six at attempt 1: native 5,571/six unchanged skips in 565.341s; full serial backend 5,571/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. These are per-statement SQL limits, not a whole-command or capacity guarantee; the existing outer20-second probe timeout remains. Consumers limited to snapshot v1 require updating before reading v2. Old evidence is retained unchanged, and no execution/recovery/review authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification.

### P146 — Strict operator evidence JSON decoding

**Packet status:** tested. **Mapped outcomes:** D07.

Reject ambiguous/non-finite operator JSON before evidence export; share decoding with offline verification

**Evidence:** [Strict operator evidence JSON](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#strict-operator-evidence-json-p146); [P146 source qualification](evidence/p146-qualification-2026-10-24.json); [P146 PR #237](https://github.com/caglarsubas/auto_ml/pull/237); [P146 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40074300985); [P146 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40076825788)

**Remaining:** P146 shares strict UTF-8 JSON decoding between operator collection and offline verification, refusing duplicate keys and non-finite numbers; malformed status values fail through the sanitized transport error. Existing byte limits precede decoding. Valid v1/v2 snapshots and finite extensions remain compatible. PR #237 exact-head CI 40074300985 passed all six at attempt1: native 5,614/six unchanged skips in 833.852s;809 physical,722 frontend units and47 original first-attempt browsers. Original inventories/private recovery/restore/host/incident proofs verify. Merged as 38f2d50d91b6b804b8789de627de9846fe206042, exact qualified tree. Independent automatic push-main CI 40076825788 passed all six at attempt1: native 5,614/six unchanged skips in 773.787s; full serial backend5614/six skips;809 physical,722 frontend and47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Transport validates the envelope; the offline verifier retains full snapshot/pin/consistency validation. No evidence authenticity, execution/recovery/review authority or historical rewriting is introduced. D07 release/customer gates remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation require separate qualification.

### P147 — Native delivery specification-shape hardening

**Packet status:** tested. **Mapped outcomes:** D07.

Block malformed native request envelopes with atomic metadata-only terminal receipts

**Evidence:** [Native claim specification shapes](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#native-claim-specification-shapes-p147); [P147 source qualification](evidence/p147-qualification-2026-10-24.json); [P147 PR #238](https://github.com/caglarsubas/auto_ml/pull/238); [P147 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40084770754); [P147 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40087432409)

**Remaining:** P147 blocks malformed saved specification roots/kinds once before native execution, preserving claim guard precedence and duplicate-delivery fencing. Claim terminal writes update transition fields only, retaining opaque payloads including JSON null; receipt/storage rollback remains atomic. PR #238 exact-head CI 40084770754 passed all six at attempt1: native 5,651/six unchanged skips in 850.193s;809 physical,722 frontend units and47 original first-attempt browsers. Original inventories/private recovery/restore/host/incident proofs verify. Merged as 053859de3d1acbb5bc3467c5051bac74ba815c07, exact qualified tree. Independent automatic push-main CI 40087432409 passed all six at attempt1: native 5,651/six unchanged skips in 827.027s; full serial backend5651/six skips;809 physical,722 frontend and47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This validates the saved root/kind envelope; nested kind-specific validation and full installation restore remain separate. No repair/replay/review authority or historical rewriting is introduced. D07 release/customer gates remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation require separate qualification.

### P148 — Retained native receipts and truthful roadmap progress

**Packet status:** tested. **Mapped outcomes:** D07.

Preserve inspectable retained receipts and show truthful status denominators plus delivery activity

**Evidence:** [Retained native receipts](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#retained-native-receipts-p148); [Tracker status semantics](roadmap-tracker/README.md); [P148 source qualification](evidence/p148-qualification-2026-10-24.json); [P148 PR #239](https://github.com/caglarsubas/auto_ml/pull/239); [P148 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40107492460); [P148 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40109715786)

**Remaining:** P148 keeps irregular retained job receipts inspectable under existing project/digest controls, preserves valid score previews, and refuses malformed score exports. Versioned tracker sources explain stable status shares and show cumulative tested-delivery counts and the latest increment, without inventing future scope completion. PR #239 exact-head CI 40107492460 passed all six at attempt1: native 5,705/six unchanged skips in 469.014s;809 physical,722 frontend units and47 original first-attempt product browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as bac0faaef0f8d1ba8aca3b0ba2a4949227823b0a, exact qualified tree. Independent automatic push-main CI 40109715786 passed all six at attempt1: native 5,705/six unchanged skips in 896.971s; full serial backend5705/six skips;809 physical,722 frontend and47 original first-attempt product browsers. Inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Receipt inspection does not repair metadata or establish historical provenance; score checks are structural, not full row validation. Tracker source/isolated logic checks do not claim browser rendering. Outcome shares stay42.3% in progress/57.7% planned until outcome states change; packet shares may stay100% while counts grow. D07 release/customer recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation remain separate open gates.

### P149 — Native execution authority dataset binding

**Packet status:** tested. **Mapped outcomes:** D07.

Bind native primary/source authority to exact job resources before execution and publication

**Evidence:** [Execution authority dataset binding](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#execution-authority-dataset-binding-p149); [P149 source qualification](evidence/p149-qualification-2026-10-25.json)

**Remaining:** P149 binds native execution snapshots to the job dataset/project/read operation and source dataset/primary actor before kind-specific checks. Shared claim/checkpoint/publication guards reject borrowed or malformed scopes; publication denials preserve opaque payloads through transition-only writes. Fresh authority/revision checks and original budgets remain. Local 1565 focused and full 5,760 native/six unchanged skips pass; exact-CI Ruff, policy21/0 and tracker isolatedJS checks pass.55 additive cases pass; exact unchanged-source SQLite/PostgreSQL baselines each reproduce44 failures/11 compatibility passes. All339 inherited guarded files, original tests and CI workloads/settings remain unchanged. Exact-head CI, merge and main pending. This is snapshot/job consistency, not authentication of historical metadata, restore repair, delegated authority or customer recovery qualification. Delivery counters and last-record activity update separately from the26 outcome statuses; D07 remains in progress. Customer recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation remain open gates. Tracker source/isolated logic checks do not claim fresh browser rendering.

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

**Progress:** Django 5.2 LTS/DRF 3.16 and Angular/Material 22 with Node 24/TypeScript 6 are adopted; local framework tests/builds pass. Database/jobs remain SQLite/synchronous/local threads; production installation, PostgreSQL/Celery, offline packaging and recovery are not qualified. P02 qualifies a public-dependency core build without the optional SDK and a full marked Linux/ARM64 backend run; production deployment and locked offline supply remain open. P16 adds an explicit fail-closed private runtime with external secret/value-file sources, explicit hosts/HTTPS origins, secure cookies/redirects, an existing artifact root and PostgreSQL verify-full TLS. Both SQLite and PostgreSQL full marked suites pass unchanged assertions, skip and coverage budgets. Real private middleware/session/CSRF, non-superuser migrations, certificate/hostname rejection, restart persistence and a quiescent synthetic database/artifact restore are qualified; the live-reload stack rejects private mode. This is metadata/configuration support, not PostgreSQL dataset intake or qualified production deployment. Project roles, egress/retention, durable workers, expert isolation, independent reproduction and production recovery remain open. P22 adds one exact-package integrity job with durable request/event/result receipts, explicit dedicated Celery/Redis dispatch, database admission/lease bounds, cooperative cancellation, authority/runtime rechecks and fenced terminal publication. Actual prefork delivery, killed-worker recovery after injected lease expiry, duplicate/stale publication, active cancellation and failed broker connection recovery pass against TLS PostgreSQL metadata. Real native package keyboard queue/status/receipt handoff passes in the review workspace. This is partial D07/D12: training/search/scoring migration, private Redis TLS, complete private worker packaging, job backup/restore and production recovery, expert isolation, complete accessibility and release/customer gates remain open. P23 adds a fail-closed private launcher and actual metadata TLS/migration/broker preflight. Authenticated Redis TLS and wrong CA/hostname/credential rejection pass. Actual broker removal retains requests; a quiescent four-state native-job PostgreSQL/artifact snapshot restores exactly into a separate database with an empty broker. The actual dispatcher naturally expires the original 180-second controlled abandoned lease, fences its old token and a fresh prefork worker publishes pending results once; terminal history and original event prefixes remain intact. Both full metadata matrices pass 2032 tests and six skips with unchanged gates. This is bounded synthetic Linux qualification, not complete private packaging, live/machine-loss disaster recovery, expert isolation or D07/release/customer completion. P25 adds synthetic private TLS scoring recovery qualification: exact quiescent metadata/input/package/full-result restore, natural orphan leases, actual duplicate completions, changed/missing-input and current-authority blocking, plus recovered-score exports. Native application behavior and budgets are unchanged; production interrupted-scoring/live-backup/machine-loss recovery and full reproduction/release gates remain open. P27 adds method-named support-weighted rank AUC for requested multiclass stopping, retaining independent sklearn full assessment, input validation and unavailable-objective blocking. Reference callback histories, selected models and replay match across all three native boosters; private/full workflow qualification passes with unchanged budgets. No full reproduction, capacity or release claim. P29 adds an allowlisted fixed native API/worker/dispatcher image, immutable source/runtime inventories and an exact tag-free offline handoff bound to an independently trusted manifest digest. Actual unprivileged read-only Unix WSGI session/CSRF/project checks, empty-slot image import and both complete metadata suites pass. A single API worker preserves legacy process-local search control; durable search migration, complete frontend/TLS installation, supply-chain authentication, egress/retention, production recovery, expert isolation and all release/value/customer gates remain open. P30 adds a fixed, unprivileged buffering TLS ingress with canonical headers, exact Host/SNI handling, bounded ephemeral upload storage and current Django media authorization. Real private HTTPS qualification is added to the existing PostgreSQL fixture/CI job. Complete installation, client-source attribution, comprehensive egress/retention, production recovery, expert isolation and all release/customer gates remain open. P31 adds a recorded allowlisted Angular production/private build, exact immutable TLS asset packaging, same-origin API/media credentials and explicit static/app routes with local fonts/licenses and exact-bundle browser CSP with sandboxed media attachments. Actual private HTTPS developer sign-in/reload, project selection, creation/upload/download/logout and blocked fallback/egress checks pass. Complete multi-image restricted-network installation, supply authentication, production recovery, expert isolation, independent reproduction, comprehensive accessibility and all release/value/customer gates remain open. P32 adds one externally digest-pinned native API/compiled-ingress/PostgreSQL/Redis image handoff with staged all-before-import verification, fixed runtime inventories and repeated digest-only import. Native dependency preparation preserves trusted base identities without relaxing single-image graph checks. Both complete metadata matrices, actual private HTTPS/browser and unchanged recovery pass using exact no-pull dependencies. Complete installation, authenticated supply, fixed-image worker completion, upgrades/rollback, production recovery and release/customer gates remain open. P33 qualifies separate fixed-image native workers and dispatchers through their unchanged entrypoint, actual calibrated classification/regression scoring, protected receipts, input/authority/cancellation checks and twenty duplicate acknowledgements after warm shutdown. Dispatcher SIGTERM/SIGINT handling now ends its bounded pump cleanly. Existing recovery scenarios and budgets remain; full installation, production recovery, expert isolation and all release/customer gates remain open. P34 adds digest-bound offline application-layer installation plans with strict nonsecret operator requests, sealed authority/upload/CSP configuration matching, exact native images and explicit storage/network/secret/dependency prerequisites. Real four-image verification and Compose normalization pass without service adoption or secret reads. Complete host preflight, dependency initialization, deployment/recovery, expert isolation and all release/customer gates remain open. P35 verifies saved plan digests and rederives the supported native profile, then checks Linux filesystem prerequisites using pinned ancestor/metadata descriptors. Exact UID/GID/modes, secret member/size/link constraints and root ACL limits fail closed without reading secret values or artifact descendants. Real UID 10001 fixtures qualify five positive/fault cases. Complete initialization, network/socket preparation, adoption and release/customer gates remain open. P36 initializes only new Linux filesystem roots from operator-delivered secret files, retains exact source bytes and private ownership/modes, and publishes with atomic no-replace semantics. Seven native cases verify retry/fault/race boundaries without changing an operator installation. No dependency, network or service is adopted; complete D07 and release/customer gates remain open. P37 prepares dedicated internal native networks and an empty UID 10001 socket volume from an exact saved plan/fresh root receipt. Labels bind the plan/initialization, foreign or occupied resources are preserved, and native daemon/socket/retry/fault cases pass. Dependencies and application services remain separate adoption steps; D07/release/customer qualification remains open. P38 adds exact-plan four-role adoption after sealed private TLS/migration/non-elevated-role preflight, bound resource/profile checks and independently CA/hostname-verified HTTPS. Matching existing services are kept; conflicting or failed preflight inputs cannot start applications. Local real Compose profiles and fail-closed checks pass; hosted CI must qualify the complete fresh Linux root/repeat/elevated-grant scenario before merge. Dependency provisioning/hardening, full installation, upgrades/rollback, production recovery and all release/customer gates remain open. Hosted adoption exposed the v1 ingress bridge publication defect. P38 renders v2 plans with an internal data bridge and separate publishing ingress bridge; archived v1 plans retain verification semantics and cannot be adopted. Existing roots/resources are never rewritten. Actual port publication and HTTPS are required; host firewall/ingress egress qualification remains open. P39 rechecks all four exact active service profiles and the same container identities after verified HTTPS, then rechecks bound dependency/socket membership before publication. Stopped/paused/restarting/dead/unknown or changed states cannot inherit the earlier snapshot; failures preserve existing services. A real owned Linux pause fault is required in existing CI; no future health or installation/release/customer approval is claimed. P40 prepares only a new bound dependency filesystem, captures five delivered server/owner files, verifies selected-CA/hostname/key consistency, records fixed non-root private resource profiles and publishes atomically without replacement. Root-owned configuration cannot be rewritten by service identities; PostgreSQL/broker storage starts empty. No dependency is started or migrated. Actual initialization/startup, complete hardening, production recovery and all release/customer gates remain open. P41 starts only the exact prepared non-root PostgreSQL/TLS broker/cache profiles, initializes an absent declared app role/database without elevated authority, verifies actual TLS/authentication, and publishes a same-identity immutable startup receipt. Foreign/nonempty/unbound or altered resources and changed role/catalog authority block without repair. Managed dependencies retain full checks through application adoption. Schema migration, complete installation/recovery and release/customer gates remain open. P42 describes the exact sealed migration graph and initializes only a fresh PostgreSQL schema from an approved digest with non-elevated TLS authority, one atomic migration transaction, immutable bound intent/result publication and disclosed lost-result verification. Repeat preserves history; foreign/partial/stale/changed state blocks without repair. Account enrollment, complete hardening/installation/recovery and release/customer gates remain open. P43 adds ordinary private account enrollment with explicit project scope, actual role/TLS/schema/broker preflight, private credential files, atomic operator-attributed account/project records and exact retry/state/collision checks. Fresh adoption preflight uses ephemeral media without customer artifact access. Actual complete fresh Linux/HTTPS acceptance is required before merge; full lifecycle/security/recovery and release/customer gates remain open. P50 explicitly binds private PostgreSQL TLS/GSS/protocol policy in Django and dependency readiness; local sealed-driver controls pass. Fresh adopted-role acceptance is required before merge; selected CA-file preflight and full lifecycle gates remain open. P51 adds bounded consistent selected-public-CA preflight shared by private Django and readiness, retaining public modes and libpq path semantics. Local full and sealed-driver/preflight checks pass; complete fresh Linux and separate base-main qualification are required before merge. Full lifecycle and release/customer gates remain open. P52 hardens stored controller evidence capture with repeated bytes/full metadata and post-read ACL refusal. Local full suite and owned Linux reader faults pass; fresh Linux exact-head qualification remains required. Delivery capture and full lifecycle/release/customer gates remain open. P53 makes application/dependency/prepared-secret delivery capture compare repeated bounded bytes/full metadata and recheck ACL custody. Twenty-nine cases and real Linux owned-copy faults qualify the reader components. Exact-head full/fresh Linux and separate main qualification remain required; full lifecycle/release/customer gates stay open. P54 fixes a reproduced SQLite SFS candidate-publication write-upgrade race using early transaction reservation without extending timeout, and adds operation-correlated native failure stages plus browser error attachments. Private PostgreSQL and scientific assertions remain unchanged. Exact-head/full/private/main qualification and D07 lifecycle/release/customer gates remain required. P55 shares explicit saved SFS state validation across status, results and assistant readers. Recorded failures retain diagnostics; missing/corrupt/unknown/contradictory evidence is unavailable instead of completed or absent. Live precedence and existing history/authority remain. Exact-head/full/private/main qualification and lifecycle/release/customer gates remain required. P56 replaces current SFS checkpoints atomically after strict serialization and file synchronization, preserving previous bytes on pre-replacement failure and exposing directory-sync uncertainty. Operation IDs survive intermediate saves; no distributed ownership or cross-store transaction claim. P57 publishes operation-bound no-overwrite SFS archives and requires history retention before current-result/live completion. Identical retries reuse evidence; conflicts block. Legacy history remains inspectable. Full recovery and distributed SFS remain open. P58 makes tuning state explicit and unavailable on invalid evidence, preserves operation-correlated search/refit/publication/storage diagnostics, and saves results atomically without changing scientific contracts or operational budgets. Distributed tuning and full operation history remain open. P59 validates SFS resume state/bases/steps/features before worker creation, restores every declared direction from evidence, records active merged-direction keys and fingerprints recovery implementation. Canonical IDs and atomic process-local registration prevent divergent or duplicate owners; distributed ownership and full lifecycle remain open. P60 addresses repeated qualification timeouts by removing measured redundant binary threshold metric validation, retaining reference parity, unchanged scientific cases and operational budgets. Exact-head/private/main qualification remains mandatory; host-level timing variation is not diagnosed as a customer-runtime defect. P61 retains operation-bound terminal tuning archives before current-result/live publication, including stops and errors. Identical retries preserve bytes; conflicts and invalid evidence are blocked. Project registration gates advancement and scoped downloads; original and secondary saving failures remain distinct. Full journaling/distributed ownership and lifecycle gates remain open. P62 adds correlated and redacted worker-start failures for SFS/tuning. Known failed launches transition only their current owner to error; uncertain/terminal/stale owners are preserved so launch failure cannot release active work or overwrite another operation. Existing files and scientific execution remain. Durable/distributed ownership and lifecycle gates stay open. P63 binds SFS/tuning callbacks, stop flags and final/error progress to their accepted owner and operation UUID under the admission lock. Late/terminal callbacks cannot revive or change a later owner; SFS diagnostics are constructed before exposing error status. Process-local progress protection is not complete artifact/adoption fencing, distributed leases or durable recovery. P64 adds explicit thread-owned Django connection setup/cleanup around SFS/tuning targets. Redacted setup/execution diagnostics fail only matching running owners; separate cleanup diagnostics preserve original failures and completed evidence. Caller connections/transactions remain intact. Durable workers, process-loss diagnostics and full lifecycle/release/customer gates remain open. P65 serializes stop selection/check/signalling with admission and terminal publication. Optional canonical operation IDs reject stale requests; invalid bodies/IDs leave owners unchanged. Duplicate cancellation remains idempotent and does not release running admission. Legacy unbound requests retain current-run semantics; browser identity binding follows separately. Durable recovery and lifecycle/release/customer gates remain open. P66 binds browser cancellation to the accepted/displayed dataset and operation UUID, validates HTTP arguments at runtime, rejects history as live authority and ignores stale stop replies. Missing identity/conflicts/mismatched acknowledgements cannot trigger unbound fallback or automatic retry. Fifty-two new UI/service cases and651 frontend cases pass with unchanged coverage gates; private build passes. Backend legacy callers, durable recovery and full lifecycle/release/customer gates remain open. P67 adds shared process-local admission for at most two active SFS/tuning owners, retaining stops/uncertain launches and returning non-disclosing capacity refusals without evidence mutation. Logical admission does not bound physical cleanup or input preparation; durable/distributed search and full lifecycle/release/customer qualification remain open. P68 moves result-directory creation inside operation-bound worker preparation. Setup failures cannot strand false running owners or execute scientific work; prior evidence, stale-owner protection, cleanup diagnostics and explicit fresh retries are preserved. Durable/process-loss recovery and full lifecycle/release/customer gates remain open. P69 bounds each PostgreSQL lock wait in durable job serialization to at most five seconds,including bootstrap and later authority/metadata locks. Stricter caller limits and prior settings are preserved across success,errors,nesting and rollback. Execution budgets and SQLite behavior remain unchanged. Complete lifecycle/release/customer gates remain open. P70 refreshes expiry decisions after claim validation and publication authority/result preparation,including late authority denials,and moves reconciliation time inside serialization. Expired leases retain unchanged evidence for reconciliation; expired requests cannot adopt prepared results. Existing budgets and scientific workloads remain. Complete lifecycle/release/customer gates remain open. P71 retires obsolete/unusable database connections around standalone dispatcher cycles and handles driver InterfaceError through the existing redacted retry path. Real owned PostgreSQL session-termination cases verify reconnection in the same command. Full server/lifecycle/release/customer qualification remains open. P72 lets a standalone dispatcher finish its current publish/metadata unit and stop before further queued publishes. Remaining requests and evidence stay unchanged for subsequent dispatch; default and once-mode full-batch behavior remain. Existing execution budgets and lifecycle/release/customer gates remain. P73 repeats the existing non-elevated database-role preflight for every fixed API/worker/dispatcher launch and direct native entrypoint, closing the adoption-only authority gap before service execution. Startup observations do not provide continuous database authority monitoring. Full lifecycle/release/customer gates remain open. P74 extends the existing privileged-role membership predicate to both current_user and session_user,preventing SET ROLE from hiding elevated session authority. Existing policy,result shape,static errors and budgets remain. This is not original-authenticated-identity binding or continuous privilege monitoring; full lifecycle/release/customer gates remain open. P75 requires credentialed private broker configuration before trust or network setup,with strict credential decoding and consistent readiness/Kombu semantics. Development behavior and existing budgets remain. Complete lifecycle/release/customer gates remain open. P76 prevents decoded broker/cache passwords from being silently trimmed during dependency provisioning. Encoded trailing controls block before staging; legitimate delivered-file newlines and valid credential bytes remain supported. Lifecycle/release/customer gates remain open. P77 pins native CSV input with a nonblocking,no-follow regular-file descriptor. Special files and late final symlinks block with static diagnostics; descriptor cleanup preserves existing authority,byte and scoring contracts. Filesystem custody and wider lifecycle/release/customer gates remain open. P78 pins native package metadata,evidence and hashing reads to regular descriptors and bounds metadata allocation before parsing. Existing reason codes,hashing/checkpoint limits and CSV behavior remain. Full lifecycle/release/customer gates remain open. P79 classifies native JSON decoder overflow as invalid input and walks evidence scope iteratively without changing authorization policy. Parsed deep evidence remains reviewable;known malformed input cannot strand a native lease. Unexpected capture/execution recursion remains an uncertain failure. Lifecycle/expert/release/customer gates remain open. P80 rejects unsupported job-list offsets before native job storage access, preserving authorization precedence and valid pagination. Invalid input no longer appears as a database outage. Lifecycle/expert/release/customer gates remain open. P81 preserves the original native work deadline through successful publication, including lock/authority/digest waits. Late candidates receive the existing blocked timeout receipt without adopting results; cancellation, expiry and uncertain-failure recovery remain. Lifecycle/expert/release/customer gates remain open. P82 removes the obsolete root npm install graph and documents the shared frontend dependency path. Supported frontend manifest/lock/vendor bytes and executable sources remain unchanged. Supported development-tool advisory findings and lifecycle/expert/release/customer gates remain open. P83 blocks private startup when recorded migrations are unknown to the selected sealed image or violate dependency history. Consistent pending migrations retain their existing diagnostic. No automatic schema changes or rollback qualification; lifecycle/expert/release/customer gates remain open. P84 reserves configured service DNS names across dependency, application and temporary helper validation. Cross-role aliases, implicit names and malformed reported DNS metadata block before reuse/adoption or helper start. Valid own/generated names and existing runtime contracts remain; later Docker administration and broader lifecycle/release/customer gates remain outside this check. P85 adds read-only managed-table/column presence and relation visibility checks after migration-history validation. Lost, substituted or shadowed metadata relations block before broker access without repair. Full physical-schema, privilege, lifecycle/recovery and release/customer gates remain open. P86 checks each effective table-level CRUD permission on the current managed schema before broker/cache access. Real PostgreSQL revocation cannot silently pass startup; no grants or ownership are changed. Arbitrary ACL profiles, sequences, RLS/data visibility, later privilege changes and full lifecycle/release/customer gates remain outside this check. P87 rejects enabled or forced RLS on current private managed metadata tables so valid table CRUD rights cannot mask filtered metadata. Catalog-only checks preserve policies and earlier diagnostics. Arbitrary RLS profiles, later-state fencing and full lifecycle/release/customer gates remain open. P88 reads actual current/default metadata transaction modes after TLS, rejecting read-only settings before history and service connectivity. No write probe or mode repair occurs. Later settings changes, general write availability and full lifecycle/release/customer gates remain open. P89 pins active/session authority catalogs, membership lookups and role-name equality to pg_catalog, preventing public namespace substitutions from concealing elevated authority. Existing role policy, order and diagnostics remain; continuous authority monitoring and full lifecycle/release/customer gates remain open. P90 pins metadata TLS statistics, backend PID and comparison to pg_catalog so caller-controlled namespaces cannot falsely attest plaintext as TLS. Existing TLS policy, errors and receipts remain; continuous monitoring and full lifecycle/release/customer gates remain open. P91 pins schema-presence, effective permission and row-security catalog joins/filters to built-in operators and identifier types. Substituted columns or alternate-schema tables cannot mask a lost required public schema. Existing policy and diagnostics remain; complete schema/data/lifecycle and release/customer gates remain open. P92 pins the application dependency probe's role, membership and TLS attestation query to built-in catalogs/functions/operators. Its strict no-explicit-membership policy and verified transport remain unchanged; isolated authority-block evidence does not establish a full controller/bootstrap bypass. Continuous monitoring and full lifecycle/release/customer gates remain open. P93 requires the literal reserved pg_ schema prefix instead of a LIKE wildcard. Ordinary pg-prefixed schemas are foreign, preventing fresh migrations/current-state acceptance over unsupported preexisting data. Actual owned graph/state/migration proof and nine native/reference cases preserve system schemas, data and history. Other catalog queries and full lifecycle/release/customer gates remain open. P94 binds initializer state catalogs, aggregates, operators and dependency class identity to built-ins. Temporary catalog substitutes cannot hide unsupported public objects or fabricate foreign evidence. Actual owned graph/state/migration proof blocks before DDL while preserving data/history; genuine current state remains supported. Other authority/lock queries and full lifecycle/release/customer gates remain open. P95 pins initializer advisory-lock acquisition to the built-in function. Two-session lock ownership/contention and caller side-effect controls prevent false exclusion attestations; keys, lifetime and budgets remain unchanged. Isolated lock proof is not a full controller/migration bypass or continuous fencing. Other authority SQL and lifecycle/release/customer gates remain open. P96 pins initializer role/TLS/membership and database owner/encoding queries to built-in catalogs, functions, operators and types. Actual isolated authority-block and separate owner-statement probes reject forged authority without changing policy, privileges, transport or execution budgets. Not a full controller/verified-transport bypass or continuous fencing; other helpers and full lifecycle/release/customer gates remain open. P97 extends the existing schema guard with exact pg_catalog base-type OIDs derived from the sealed migration graph, rejecting text/width/timezone/JSON/array/domain substitutions before broker access. Healthy migrated auth through-table IDs and extra columns remain supported. Read-only startup observation only; modifiers, constraints, continuous fencing and full lifecycle/release/customer gates remain open. P98 checks exact declared varchar lengths and PostgreSQL type modifiers in the existing catalog-only guard. Shorter, wider, unlimited or explicitly changed timestamp declarations block before broker/cache access; genuine migrated state and arbitrary extra columns remain supported. No repair or compatibility inference; constraints/defaults/indexes/collations, later-state fencing and full lifecycle/release/customer gates remain open. P99 requires exact sealed local-field nullability in the existing catalog-only check, including nullable foreign keys whose target keys are non-null. Undeclared SET/DROP NOT NULL blocks before broker/cache access; healthy state and extra columns remain supported. No repair or later-state fencing; other constraints and full lifecycle/release/customer gates remain open. P100 rejects generated storage on required ordinary metadata columns and explicitly excludes generated model declarations whose output types otherwise look ordinary. Genuine identity keys, ordinary writes and generated extras remain supported. Catalog-only startup observation without repair; identity modes/defaults/other constraints and full lifecycle/release/customer gates remain open. P101 checks exact sealed local-field identity modes: BY DEFAULT for auto keys and no identity for ordinary integers or foreign keys. Lost generation, ALWAYS replacements and added ordinary-field identity block before broker/cache access. Implicit/explicit inserts, manual keys, foreign keys and extra-column policy remain supported. Read-only startup observation only; sequence state/privileges/defaults/other constraints and full lifecycle/release/customer gates remain open. P102 requires a validated, nondeferrable single-column primary-key constraint and its live, ready, valid, unique, immediate primary index on each sealed local key. Missing, wrong/composite/deferred keys and forged catalog/operator evidence block before broker/cache access. Renamed constraints, included extra columns and ordinary writes remain supported. No repair or general unique/foreign-key/check/default/sequence/trigger equivalence or later-state fencing; full lifecycle/release/customer gates remain open. P103 extends the sealed local-field contract with immediate single-column UNIQUE constraints and valid backing indexes before broker/cache access. Nullable declarations preserve default distinct-NULL semantics; non-null NULL modes, renamed/covering constraints, ordinary writes and extra columns remain supported. No repair or full schema/index/inheritance equivalence or later-state fencing; full lifecycle/release/customer gates remain open. P104 checks sealed ordinary compound UNIQUE declarations in the existing catalog-only query, preserving equivalent key order, names, INCLUDE and default NULL semantics. Unsupported declaration forms fail closed; other constraint/index/collation/inheritance equivalence, later-state fencing and full lifecycle/release/customer gates remain open. P105 checks sealed single-column foreign-key metadata against exact local and public target column identities, validation, deferred timing, SIMPLE match and NO ACTION update/delete semantics. Genuine renamed/recreated keys, nullable references and ordinary writes remain supported; unconstrained relation declarations fail closed. RI trigger/session-state enforcement, full schema/data equivalence, later-state fencing and lifecycle/release/customer gates remain open. P106 checks all four built-in enforcement roles per declared FK, exact linkage/events/timing and enabled modes plus relation trigger flags before broker/cache access. Separate administrator fault injection never elevates the application process; normal/always modes and arbitrary names remain supported. Session modes, historical integrity, later-state fencing and full lifecycle/release/customer gates remain open. P107 binds the actual connection replication mode to built-in evidence in the existing schema query, accepting origin/local and rejecting replica before broker/cache access even after login-default repair. Additive physical cases preserve earlier RI coverage and budgets. Broad parameter authority, historical integrity, later-state fencing and full lifecycle/release/customer gates remain open. P108 extends existing role admission with built-in SET/ALTER SYSTEM authority for the replication parameter, including effective/PUBLIC and current/session membership paths. Original query shape, command ordering, mode guard and budgets remain. This is bounded role-profile observation; other parameter/predefined-role authority, historical integrity, later-state fencing and full lifecycle/release/customer gates remain open. P109 excludes pg_checkpoint membership from the existing current/session application-role profile. All 560 separately administered physical cases pass, preserving 510 original cases and adding 50 role/command cases with real checkpoint, namespace, unavailable-lookup and restoration controls. Native 4,439/six unchanged skips and reference/native focused regressions pass without changing original scientific files, limits or budgets. Other predefined-role authority, full lifecycle and release/customer qualification remain open. P109 exact-head CI 39218919217 and independent merged-main CI 39222299623 pass all six with complete reports, original inventories and worker isolation. P110 excludes pg_maintain membership through the existing six-column current/session admission query. PR #201 exact-head CI 39231539363 passed all six on attempt 1 at b7d8c6b8a7e7dc03418d31e03ff69c776f143b10: native 4,439/six unchanged skips in 324.359s, 610 physical cases, frontend 651 and browser 37 first-attempt passes. Complete native/private receipts and original inventories verify. Merged as b6277b1c3f0596eab4170dadda5d44a4c9f49fe0, matching the qualified PR tree. Independent push main CI 39234645971 passed all six on attempt 1: native 4,439/six unchanged skips in 579.431s, full serial backend 4,439/six skips, 610 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, worker isolation and source hashes verify. D07, lifecycle, release and customer acceptance remain open. P111 excludes pg_create_subscription membership through the existing six-column current/session query. PR #202 exact-head CI 39254037903 passed all six on attempt 1 at 5be31b25a84cef6231e5bd3988a69130110ad072: native 4,439/six unchanged skips in 562.083s, 660 physical cases, frontend 651 and browser 37 first-attempt passes. Complete native/private reports and original inventories verify. Merged as 315c33e4190fd05ac41462b47845b1cc6d691c7b, matching the qualified PR tree. Independent push main CI 39257782850 passed all six on attempt 1: native 4,439/six unchanged skips in 469.989s, full serial backend 4,439/six skips, 660 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and source hashes verify. D07/lifecycle/release/customer gates remain open. P112 excludes pg_read_all_stats through the existing six-column current/session query, including pg_monitor membership. PR #203 exact-head CI 39267125686 passed all six on attempt 1 at d61153ccb5e14c59927e677072c791d17f0a8fcf: native 4,439/six unchanged skips in 336.834s, 714 physical cases, frontend 651/browser 37 first-attempt passes. Complete native/private reports and original inventories verify. Merged as fad193efc1f535eab38bbc9d76be32f5b197afb9, matching the qualified PR tree. Independent push main CI 39270531813 passed all six on attempt 1: native 4,439/six unchanged skips in 567.088s, full serial backend 4,439/six skips, 714 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and source hashes verify. D07/lifecycle/release/customer gates remain open. P113 excludes pg_read_all_settings through the existing six-column current/session query. PR #204 exact-head CI 39360440984 passed all six on attempt 1 at 46ab522939a3e9fc394a8c6c2463b6bcc32d1870: native 4,439/six unchanged skips in 559.865s, 764 physical cases, frontend 651/browser 37 first-attempt passes. Complete native/private reports and original inventories verify. Merged as 3d87a8654cc7718c40a25cd45b8f6a45002194f3, matching the qualified PR tree. Independent scheduled main CI 39363175020 passed all six on attempt 1: native 4,439/six unchanged skips in 350.403s, full serial backend 4,439/six skips, 764 physical cases, frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and source hashes verify. Original push main CI 39363097400 was superseded by the automatic nightly run on the same commit through the unchanged concurrency group; cancellation is retained and supplies no passing result. No CI rerun was requested. D07/lifecycle/release/customer gates remain open. P114 isolates CI triggers while retaining within-trigger supersession. Local policy: 21 comparisons and eight negative controls pass; three old trigger collisions reproduce. Product runtime and original test workloads/budgets remain unchanged. PR #205 exact-head CI 39367238291 passed all six on attempt 1 at 3e53cd5ba331e38debe50f62612b00ba3f09127b: native 4,439/six unchanged skips in 566.782s, all 764 original physical cases, frontend 651/browser 37 first-attempt passes. Complete reports, policy guard, inventories and isolation verify. Merged as 1911805095ee1b0d74e9f42354787dc8eaa28475, matching the qualified PR tree. Independent push main CI 39369876550 passed all six on attempt 1: native 4,439/six unchanged skips in 557.821s, full serial backend 4,439/six skips, all 764 original physical cases, frontend 651/browser 37 without retries. Policy guard, complete reports, unchanged inventories, isolation and source hashes verify. Live post-fix push/nightly overlap and GitHub scheduling/account limits are not claimed. D07/release/customer gates remain open. P115 enforces the sealed default column collation and rejects unsupported explicit declarations. Owned PostgreSQL reproduction changes two ORM comparisons; 12 old denial gaps now close. Local qualification passes 16 new PostgreSQL tests, 985 SQLite references, all 797 physical cases (764 original plus 33 new), and the full native suite with original workloads and limits preserved. PR #206 exact-head CI 39378985057 passed all six on attempt 1 at 600420d21a83e00fcd0a1801fad82228902c2828: native 4,455/six unchanged skips in 341.971s; all 797 physical cases; frontend 651/browser 37 first-attempt passes. Complete private reports, original inventories, policy guard and worker isolation verify. Merged as bb61076f626e3dca169c68404107fa76ebf95064, matching the qualified PR tree. Independent push-main CI 39381235360 passed all six on attempt 1: native 4,455/six unchanged skips in 603.708s; full serial backend 4,455/six skips; all 797 physical cases; frontend 651/browser 37 without retries. Complete reports, source hashes, original inventories, policy guard and worker isolation verify. Admission-time column evidence does not establish historical integrity, continuous fencing or default-provider/version equivalence. D07, release and customer gates remain open. P116 serializes managed adoption with dependency startup and schema initialization through final HTTPS/receipt checks. Two old lock bypasses reproduce; 14 new guard cases and 305 focused cases pass. Full local native qualification passes 4,469 with six unchanged skips under the original 900-second limit. PR #207 exact-head CI 39391145117 passed all six on attempt 1: native 4,469/six unchanged skips in 575.551s; all 797 original physical cases; frontend 651/browser 37 without retries. Complete reports, original inventories, worker isolation and actual Linux-root shared-lock/HTTPS/history checks verify. Merged as f2862caa9e4d941a840e94d98efaecc3923ca0a0, matching the qualified PR tree. Independent push-main CI 39394672026 passed all six on attempt 1: native 4,469/six unchanged skips in 568.735s; full serial backend 4,469/six skips; physical 797; frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and host-operation proofs verify. The advisory guard covers cooperating managed controllers, not administrators or legacy unmanaged serialization. D07/lifecycle/release/customer gates remain open. P117 adds read-only managed-installation observation: seven exact service profiles/identities, stable state around selected-CA HTTPS, existing-lock contention, redacted output and explicit operator review inputs. No service execution/repair or fresh database preflight is performed. All 32 new cases and 337 focused cases pass. Full local native qualification passes 4,501 with six unchanged skips under the original 900-second limit. PR #208 exact-head CI 39395174601 passed all six on attempt 1: native 4,501/six unchanged skips in 541.101s; all 797 original physical cases; frontend 651/browser 37 without retries. Complete reports, original inventories, worker isolation and actual Linux-root read-only/held-lock/paused-worker/no-repair/history checks verify. Merged as 394e0707a36adf12291ddd8f9537d4830acd3391, matching the qualified PR tree. Independent push-main CI 39398628762 passed all six on attempt 1: native 4,501/six unchanged skips in 589.240s; full serial backend 4,501/six skips; physical 797; frontend 651/browser 37 without retries. Complete reports, original inventories, isolation and actual host observation proofs verify. Operator checkpoint: review the actual deployment target/trusted plan and CA, maintenance window/permitted downtime, RPO/RTO, backup storage/encryption/retention and external network controls before selecting a real lifecycle drill. D07 durable training/search, coordinated recovery and upgrade/rollback gates remain open; no release/customer acceptance is claimed. P118 adds bounded native numeric CSV binary/regression training and two-candidate search through the durable queue. Accepted declarations, input bytes, features, matched folds, trusted objectives, runtimes and complete budgets are bound to the preview digest; fold-local imputation and final refit publish a native JSON model/evidence only through fenced DB completion. Existing split/model or known assessment-source history blocks this fresh development-only profile. PR #209 exact-head CI 39409186389 passed all six on attempt 1: native 4,543/six unchanged skips in 616.613s; all 797 original physical cases; frontend 651/browser 37 without retries. Complete private training/actual-host receipts, original inventories, worker isolation and source hashes verify. Merged as 474cc69528d58d714b30bb356146e0a5ce464215, matching the qualified PR tree. Independent automatic push-main CI 39412958093 passed all six on attempt 1: native 4,543/six unchanged skips in 546.976s; full serial backend 4,543/six skips; physical 797; frontend 651/browser 37 without retries. Complete training, private/host reports, inventories and isolation verify. Legacy training/SFS/broad HPO and their launch UI remain unmigrated. Dedicated launch controls, larger profiles, immutable trial checkpoints, export/scoring and reviewed candidate adoption remain open. Source copies must still match their pins; modified/reordered imports and unknown history are not automatically linked. Real customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open. P119 adds an explicit developer launch panel for the bounded durable training/search profile. A form declares task, target/positive label, ordered numeric predictors, objective and validation controls; the server preview exposes exact input/plan/folds/runtime/budget before a separate confirmation and submission. Edits/context changes invalidate review; uncertain admission retries the identical UUID/body. Existing durable history/cancellation/refreshed evidence downloads remain available to authorized readers. PR #210 exact-head CI 39420541174 passed all six on attempt 1: native 4,543/six unchanged skips in 574.515s; physical 797; frontend 674/browser 40 without retries, preserving all original 37 browser identities. Full private/host receipts and inventories verify. Merged as d1f9fd210ca1d06a8153859d7998699b22686514, matching the qualified PR tree. Independent automatic push-main CI 39424272366 passed all six on attempt 1: native 4,543/six unchanged skips in 594.969s; full serial backend 4,543/six skips; physical 797; frontend 674/browser 40 without retries. Complete private training, host reports, original inventories and isolation verify. The new launch panel covers only the bounded P118 development profile. Legacy synchronous training/SFS/broad HPO remain unmigrated. Larger profiles, trial checkpoints, native export/scoring, final assessment and reviewed candidate adoption remain open. Unknown history and modified/reordered imports are not automatically linked; input bytes must still match their pins. Customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open. P120 exports exact native development candidates and queues feature-only numeric CSV scoring with frozen means/order, complete receipts and an external-digest offline runner. Separate preview/approval pins model, source, runtime and budget; context edits and stale dependencies block. No adoption, outcome evaluation or production approval occurs. PR #211 exact-head CI 39433627919 passed all six on attempt 1: native 4,582/six unchanged skips in 353.007s; physical 797; frontend 689/browser 42 without retries, preserving all original 40 browser identities. Full private/host receipts and inventories verify. Merged as b2feaa7f3af68b7ffc3de208b282104770f279de, matching the qualified PR tree. Independent automatic push-main CI 39437055061 passed all six on attempt 1: native 4,582/six unchanged skips in 621.808s; full serial backend 4,582/six skips; physical 797; frontend 689/browser 42 without retries. Complete private candidate/training, host reports, original inventories and isolation verify. Export/scoring covers only the bounded P118 native development profile and feature-only numeric inputs. Legacy synchronous training/SFS/broad HPO remain unmigrated. Larger profiles, trial checkpoints, final assessment and reviewed candidate adoption remain open. Unknown history and modified/reordered imports are not automatically linked; input bytes must still match their pins. Customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open. P121 adds attributable independent review of exact native development candidates, private reviewer-only outcome custody and access-accounted durable protected assessment. Frozen preprocessing, task/positive-label mapping and trusted metrics are reused without refitting or production approval. Reuse, failed accesses and upstream-history limitations remain explicit; all assessments are exploratory. PR #212 exact-head CI 39465579127 passed all six on attempt 1: native 4,617/six unchanged skips in 586.642s; physical 809 (797 original + 12 additive); frontend 701/browser 44 without retries, preserving all original 42 browser identities. Full private/host receipts and inventories verify. Merged as 6e385586180df6ce073b99e6ca01a76c18eabb74, matching the qualified PR tree. Independent automatic push-main CI 39470251700 passed all six on attempt 1: native 4,617/six unchanged skips in 400.639s; full serial backend 4,617/six skips; physical 809 (797 original + 12 additive); frontend 701/browser 44 without retries. Complete private assessment/restore/candidate/training, host reports, original inventories and isolation verify. Assessment covers the bounded numeric binary/regression P118 native profile: 30–1000 protected rows, 5 MiB, exact validation controls and frozen trusted metrics. Reviewer attestation does not prove unknown external history, population independence or maturity. Legacy synchronous training/SFS/broad HPO, larger profiles, trial checkpoints, confirmatory protocols and production promotion remain open. Private outcome bytes require coordinated database backup, retention and access controls; infrastructure administrators remain trusted. Customer lifecycle choices, coordinated recovery and upgrade/rollback remain separate gates. D07, release and customer acceptance remain open. P122 adds a read-only revision/digest-pinned operational handoff: attributable history, lease/retry guidance and conservative protected-access counts without outcomes or model state. Native cancellation retains exact-request identity and fences publication; recovery retains unresolved accesses and all exploratory limits. PR #213 exact-head CI 39535626205 passed all six at attempt 1: native 4,640/six unchanged skips in 577.353s; 809 physical cases; 710 frontend units and 45 first-attempt browsers, retaining all original inventories. Private TLS cancellation, natural lease recovery and exact coordinated restore verify. Merged as 19742beb42b9e49e64aea8e290465a6e98c0bdd3, exact qualified tree. Independent automatic push-main CI 39538976423 passed all six at attempt 1: native 4,640/six unchanged skips in 716.565s, full serial backend 4,640/six skips, 809 physical, 710 frontend and 45 browsers. Full original reports, policy, host/lifecycle, inventories and worker isolation verify. Bounded numeric binary/regression native jobs only; unresolved/failed access remains possible inspection, all assessments exploratory. No trial checkpoints, legacy training/SFS/broad HPO migration, confirmatory or production approval. The handoff does not test live service health or grant recovery authority. Customer installation recovery, coordinated backup/restore, upgrade/rollback, larger workloads and expert isolation remain open. D07, release and customer acceptance remain open. P123 adds read-only dataset queue observations with state counts, dispatch/lease/expiry signals, observed time and explicit unobserved worker/broker health. Signed user/project/dataset/filter-bound cursors navigate both directions with at most 50 metadata rows per page; the UI replaces pages and clears stale snapshots on errors or context changes. PR #214 exact-head CI 39548153768 passed all six at attempt 1: native 4,678/six unchanged skips in 507.090s; all 809 inherited physical cases; 720 frontend units and 46 first-attempt browsers, retaining every original inventory and private recovery/restore proof. Merged as 3fc5e225cae78f565d89aabf6b5e88c36e8d31fd, exact qualified tree. Independent automatic push-main CI 39551164042 passed all six at attempt 1: native 4,678/six unchanged skips in 514.195s, full serial backend 4,678/six skips, 809 physical, 720 frontend and 46 browsers. Full raw reports, policy, host/lifecycle, original inventories and two-worker isolation verify. Queue observation never dispatches, reconciles, retries or grants recovery/review authority. Dataset counts do not measure installation occupancy, queue position or live service health. State filters remain live within a submission-time cutoff; cursors expire after one hour and refresh starts a new view. Legacy list API remains compatible. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. Assessments stay exploratory; no production approval. P124 adds Linux-root installation-operator native queue incident triage, bound to the trusted plan, native images and exact service profiles. Degraded/missing service states and bounded read-only repeatable-read PostgreSQL metadata are exported atomically to a private, non-overwriting, digest-checked evidence file. Unavailable observations, overlapping historical signals and unstable service samples remain explicit. Receipt refresh now withdraws stale evidence immediately, preventing keyboard actions against controls about to be replaced. The tracker now explains outcome-state percentages and shows dynamic tested-packet and D07 delivery counts. PR #215 exact-head CI 39561335243 passed all six at attempt 1: native 4,715/six unchanged skips in 445.018s; all 809 inherited physical cases; 722 frontend units and 47 first-attempt browsers. All original inventories and private recovery/restore/host proofs plus actual managed Linux incident collection/export verify. Merged as e63c2a615076f79d50a17b7ffe5b72de30bb5cd7, exact qualified tree. Independent automatic push-main CI 39565033935 passed all six at attempt 1: native 4,715/six unchanged skips in 463.721s; full serial backend 4,715/six skips; 809 physical, 722 frontend, 47 first-attempt browsers. Full raw reports, original inventories, policy, host/lifecycle, incident export and two-worker isolation verify. Operator authority is Linux root with a trusted managed plan; project roles receive no global API/MCP access. Triage never dispatches, reconciles, retries, cancels, repairs or approves work. No models, outcomes or event payloads are fetched; credentials and raw reasons/logs are never exported. Counts and signals are observations, not broker delivery or live health. Reports are installation-confidential point-in-time evidence, not signatures or recovery approval. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. Assessments remain exploratory. P125 adds bounded offline Linux-root verification of incident evidence against independently trusted evidence/plan digests and installation/initialization pins. Strict schema, private descriptor-based input and explicit age/availability/sample limits feed an atomic private, non-overwriting runbook handoff with fixed investigation guidance and revision-pinned references. No plan/credential, service, database or network observation occurs during verification; no recovery or approval is granted. PR #216 exact-head CI 39573130413 passed all six at attempt 1: native 4,755/six unchanged skips in 556.289s; all 809 inherited physical cases; 722 frontend units and 47 inherited first-attempt browsers. All original inventories and private recovery/restore/host proofs plus actual managed Linux incident verification/handoff verify. Merged as 59e63c61736f8bef1f7bf27149e7a94afc85b70e, exact qualified tree. Independent automatic push-main CI 39578077835 passed all six at attempt 1: native 4,755/six unchanged skips in 693.712s; full serial backend 4,755/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Full raw reports, original inventories, policy, host/lifecycle, incident verification/handoff and two-worker isolation verify. Verification and a matching checksum do not authenticate the creator, certify live health or authorize recovery. Root-only incident metadata remains installation-confidential. Human incident ownership/findings and any maintenance, new request, review or production use require separate records and authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. Assessments remain exploratory. P126 cross-checks incident snapshot counts, overlapping signal feasibility, row flags and bounded sample coverage before offline handoff. Queue observation time must fit its enclosing collection interval; sampled order is checked and any discrepancy is disclosed without rewriting evidence. Consistency is distinct from digest integrity, authenticity, live health and recovery approval. PR #217 exact-head CI 39595273389 passed all six at attempt 1: native 4,792/six unchanged skips in 692.841s; all 809 inherited physical cases; 722 frontend units and 47 inherited first-attempt browsers. All original inventories and private recovery/restore/host proofs plus actual managed Linux incident consistency checks and CLI refusal verify. Merged as 7b0fd8ec453c630a8ba16585bf37ca338e480c72, exact qualified tree. Independent automatic push-main CI 39600294336 passed all six at attempt 1: native 4,792/six unchanged skips in 642.486s; full serial backend 4,792/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Full raw reports, original inventories, policy, host/lifecycle, incident consistency and two-worker isolation verify. Verification and a matching checksum do not authenticate the creator, certify live health or authorize recovery. Root-only incident metadata remains installation-confidential. Human incident ownership/findings and any maintenance, new request, review or production use require separate records and authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. Assessments remain exploratory. P127 restricts the legacy native-job list to selected scalar metadata and JSON keys, avoiding full request/result/authority/model materialization in the controller. GET/HEAD responses are no-store, including early authentication/project denials. Existing page fields, ordering, offset forms, project scoping and final authority rechecks remain compatible. PR #218 exact-head CI 39624516161 passed all six at attempt 1: native 4,821/six unchanged skips in 655.299s; 809 inherited physical cases, 722 frontend units and 47 inherited first-attempt browsers. Full original inventories and private recovery/restore/host/incident proofs verify. Merged as 8775d25eaeaaca1733fb0f442735c621b30c8476, exact qualified tree. Independent automatic push-main CI 39632072764 passed all six at attempt 1: native 4,821/six unchanged skips in 691.024s; full serial backend 4,821/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. List metadata remains observational; it does not execute, cancel, retry, recover, approve or authenticate a model/result. No capacity benchmark or whole-installation readiness claim is made. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. Assessments remain exploratory. P128 applies a shared HTTP no-store boundary to every native-job GET/HEAD response, including result details, input metadata, history, review records, candidate/scoring downloads and operational handoffs. Authentication/project denials, safe service errors and unsupported reads receive the same policy. Status, response/download bytes and digests, project authority, job state and mutation semantics remain unchanged. PR #219 exact-head CI 39648650555 passed all six at attempt 1: native 4,884/six unchanged skips in 577.487s; 809 inherited physical cases, 722 frontend units and 47 inherited first-attempt browsers. Full original inventories and private recovery/restore/host/incident proofs verify. Merged as 4b698d1aa71de4f7f1296bafba71430b79060f58, exact qualified tree. Independent automatic push-main CI 39653822271 passed all six at attempt 1: native 4,884/six unchanged skips in 554.839s; full serial backend 4,884/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Cache protection is an HTTP response directive; it does not purge previously retained copies, authenticate evidence or authorize execution, recovery, review or production use. No capacity benchmark or whole-installation readiness claim is made. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger-workload profiling, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. Assessments remain exploratory. P129 replaces file-backed installation-operator probe stdout with a bounded pipe: at most 128 KiB plus one over-budget sentinel is retained; excess is drained and discarded during the unchanged 20-second child deadline. Cleanup does not wait for inherited writers to close. Command, stderr suppression, accepted JSON limit, evidence schema and sanitized failure semantics remain unchanged. PR #220 exact-head CI 39693765932 passed all six at attempt 1: native 4,921/six unchanged skips in 604.880s; 809 inherited physical cases, 722 frontend units and 47 inherited first-attempt browsers. Full original inventories and private recovery/restore/host/incident proofs verify. Merged as a5b63c39925e4a4e60ea1abe4293ccb27bff4044, exact qualified tree. Independent automatic push-main CI 39697300946 passed all six at attempt 1: native 4,921/six unchanged skips in 620.604s; full serial backend 4,921/six skips; 809 physical, 722 frontend, 47 inherited first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. The bound applies to retained probe output, not total process memory or a capacity benchmark. Excess output may still flow until the fixed command exits or its original timeout. Read-only triage does not grant recovery, review or production authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P130 resolves native job, adoption and protected-input resource authority through dataset-ID-only queries. Native request/result/authority/proposal/sealed-input data is not fetched or materialized before project checks. Existing roles, resource/selector bindings, audit/rechecks, cache policy and sanitized adoption lookup failures remain compatible. PR #221 exact-head CI 39704835857 passed all six at attempt 1: native 4,978/six unchanged skips in 676.484s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 2b7761f9388feb0c6cda2b3e4dd88d6136c3a8e7, exact qualified tree. Independent automatic push-main CI 39708321616 passed all six at attempt 1: native 4,978/six unchanged skips in 479.913s; full serial backend 4,978/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This bounds the authorization routing projection, not total request memory. Authorized services retain their existing data reads and execution authority. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P131 lexically normalizes trailing root separators/dot components and pins the configured storage root and each native CSV parent with no-follow directory descriptors, then opens the final file relative to its pinned parent. Late symlinks are rejected; renaming an opened parent cannot redirect capture through its old path. Original missing-file, regular-file, digest, budget, cancellation, receipt and scoring behavior remains. PR #222 exact-head CI 39719458774 passed all six at attempt 1: native 5,032/six unchanged skips in 798.645s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 39b34b60d94a387d8e5cffaf8de75b329dc95f3a, exact qualified tree. Independent automatic push-main CI 39723229515 passed all six at attempt 1: native 5,032/six unchanged skips in 762.218s; full serial backend 5,032/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Configured-root/ancestor custody remains trusted; this is not an atomic filesystem snapshot or a bound on kernel I/O. No hostile root-ancestor/mount-namespace qualification is claimed. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P132 pins native package metadata, evidence and worker hashing to no-follow storage-root and parent directory descriptors, reusing P131 capture. Late symlinks reject; already-opened parents retain original files after path replacement. Out-of-root/traversing paths reject before open. Existing digest/change fences, metadata and evidence limits, hash budgets, authority, cancellation and job diagnostics remain. PR #223 exact-head CI 39729086232 passed all six at attempt 1: native 5,135/six unchanged skips in 798.478s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 6df42cfd2a5cc3bc5c09fe5b04783d69ba96ff57, exact qualified tree. Independent automatic push-main CI 39733381879 passed all six at attempt 1: native 5,135/six unchanged skips in 783.709s; full serial backend 5,135/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Configured-root/ancestor custody remains trusted; this is not an atomic filesystem snapshot, model-deserialization isolation or a bound on kernel I/O. No hostile root-ancestor/mount-namespace qualification is claimed. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P133 projects only state, revision, attempts, lease, dispatch, expiry and terminal metadata during expired-lease/queued reconciliation. Locked SELECTs and deferred UPDATEs exclude opaque payloads, digests and related-object identifiers; no lazy payload fetch occurs. Cancellation precedence, exact reasons, revisions, rollback, sampled clock and due ordering/100 limit remain. PR #224 exact-head CI 39750105030 passed all six at attempt 1: native 5,172/six unchanged skips in 472.563s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 1bb14805f2d63405e5676594b16ca283119d21d1, exact qualified tree. Independent automatic push-main CI 39754097699 passed all six at attempt 1: native 5,172/six unchanged skips in 799.651s; full serial backend 5,172/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Metadata projection is not a capacity benchmark, a new scheduling bound or expert isolation. Database internals may still read storage pages containing payloads. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P134 refreshes job state, lease token and lease/request expiry metadata after successful authority validation and repeats the existing checkpoint guards, including the monotonic work deadline. Late cancellation, token replacement, expiry or budget exhaustion stops return to worker work. The final read is nonlocking and metadata-only; initial guard precedence, authority/storage failures, receipts and recovery semantics remain. PR #225 exact-head CI 39775447667 passed all six at attempt 1: native 5,221/six unchanged skips in 726.774s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 2714d7c2533ecdc4cfc35d964c5b635c6815996a, exact qualified tree. Independent automatic push-main CI 39780525058 passed all six at attempt 1: native 5,221/six unchanged skips in 725.215s; full serial backend 5,221/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Checkpoint fencing is cooperative; it is not atomic interruption, expert isolation or a deadline on kernel I/O or authority validation itself. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P135 enforces the existing three-attempt ceiling at native claim time. Exhausted queued rows close with failed/job_attempts_exhausted before authority/runtime or work; duplicate deliveries cannot append a second receipt. Nonqueued/capacity/expiry precedence, eligible retry leases, payloads and transactional rollback remain. PR #226 exact-head CI 39794611077 passed all six at attempt 1: native 5,253/six unchanged skips in 809.755s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 9d5a56bd3336b7212dfd01e75dfadf1bca696271, exact qualified tree. Independent automatic push-main CI 39801653753 passed all six at attempt 1: native 5,253/six unchanged skips in 775.143s; full serial backend 5,253/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This guards inconsistent/restored queued metadata; it neither qualifies a customer restore nor authorizes automatic repair. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P136 rejects missing lease tokens or expiries at native checkpoint and finish fences. A null token pair cannot authorize work or publication; absent expiry stops safely without TypeError. Invalid metadata, payloads and receipts remain untouched for operator review. Valid leases, cancellation, deadlines and recovery semantics remain. PR #227 exact-head CI 39814513505 passed all six at attempt 1: native 5,287/six unchanged skips in 609.715s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 8f1a51b81881b82ce99ad673fed7fdc178f1297e, exact qualified tree. Independent automatic push-main CI 39819297022 passed all six at attempt 1: native 5,287/six unchanged skips in 808.837s; full serial backend 5,287/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This is fail-closed fencing, not automatic metadata repair or customer restore qualification. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P137 limits native checkpoint reads to required guards and execution authority/specification fields, excluding unrelated stored outputs, actor snapshots and publication/dispatch history. Both guard reads, real primary/source authority, referenced training-result integrity, cancellation and deadlines remain enforced. No checkpoint writes or lazy payload fetches are introduced. PR #228 exact-head CI 39904440597 passed all six at attempt 1: native 5,312/six unchanged skips in 777.446s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as f5fa85dbcda86722f0bca180b3aaa1763d15cf71, exact qualified tree. Independent automatic push-main CI 39907937634 passed all six at attempt 1: native 5,312/six unchanged skips in 594.098s; full serial backend 5,312/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This qualifies checkpoint data access; throughput, total memory and customer restore remain unmeasured. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P138 orders due native jobs by creation timestamp and UUID before the existing 100-ID slice. Tied requests and recovered leases have a stable batch prefix across native kinds. Oldest-first priority, eligibility filters, recovery transitions, broker backoff and worker/publication guards remain unchanged. PR #229 exact-head CI 39914069091 passed all six at attempt 1: native 5,328/six unchanged skips in 478.078s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 3de53563cbdcef90cb9796c5be8c015a677e143b, exact qualified tree. Independent automatic push-main CI 39917709010 passed all six at attempt 1: native 5,328/six unchanged skips in 811.162s; full serial backend 5,328/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This qualifies deterministic selection, not execution-completion order, starvation prevention, capacity or customer restore. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P139 rejects operational handoff event-count mismatches before sequence comparison and validates recorded events by enumeration. Inconsistent stored revision counters cannot drive a proportional range allocation under the queue lock. Structured read failures, valid receipts/digests, stale and project-authority precedence, gap detection and read-only behavior remain. PR #230 exact-head CI 39925757216 passed all six at attempt 1: native 5,355/six unchanged skips in 839.998s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 48f816e2e4d31ff2e5c700a665767c337ade78c2, exact qualified tree. Independent automatic push-main CI 39931319968 passed all six at attempt 1: native 5,355/six unchanged skips in 800.385s; full serial backend 5,355/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This removes counter-driven allocation; actual event-query size, total capacity and customer restore remain unqualified. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P140 summarizes outcome accesses with one scalar database aggregate instead of materializing individual access-state rows under the queue lock. Exact state labels, conservative counts, scoped filtering, unknown-state refusal, valid receipts/digests, earlier authority/history guards and read-only no-store behavior remain. PR #231 exact-head CI 39940975742 passed all six at attempt 1: native 5,386/six unchanged skips in 801.786s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as ba269ec3948c885264757ad78301097367394923, exact qualified tree. Independent automatic push-main CI 39945544738 passed all six at attempt 1: native 5,386/six unchanged skips in 807.929s; full serial backend 5,386/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Access-summary return cardinality is constant; database scan cost, actual event-query size, total capacity and customer restore remain unqualified. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P141 bounds each PostgreSQL handoff SQL statement to at most five seconds, retaining stricter caller limits. The transaction-scoped setting is applied before queue acquisition and restored after success or rollback. Slow queries fail closed with safe uncached API errors; full receipts, authority/history/result checks, conservative accesses and execution budgets remain. PR #232 exact-head CI 39953198637 passed all six at attempt 1: native 5,412/six unchanged skips in 824.405s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as a556ae2d23fdcc72f3a135783d94a4041770b9e1, exact qualified tree. Independent automatic push-main CI 39958252915 passed all six at attempt 1: native 5,412/six unchanged skips in 510.632s; full serial backend 5,412/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. The limit applies to each SQL statement, not the total request duration or Python processing. SQLite retains its development file lock; production timeout behavior is separately verified on PostgreSQL. Total capacity, actual event-query size and customer restore remain unqualified. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P142 rejects unsupported job states and non-object event details with structured handoff conflicts before reading outcome history. Valid receipt fields, reason values, full event sequences, digests, conservative access accounting, earlier authority/revision/result guards, scoped SQL timeouts and read-only no-store behavior remain. PR #233 exact-head CI 39968430283 passed all six at attempt 1: native 5,446/six unchanged skips in 646.560s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 6607808c1d846c2cecad6cd9cc986e01f6155c46, exact qualified tree. Independent automatic push-main CI 39973475526 passed all six at attempt 1: native 5,446/six unchanged skips in 679.120s; full serial backend 5,446/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. These checks validate supported state labels and object-shaped event details; they do not certify historical provenance, every specification field, installation capacity or customer restore. Existing per-statement limits are not total request or Python-processing bounds. No history cap, truncation, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P143 refuses malformed saved specification objects, unsupported job kinds and invalid attempt limits before handoff history reads, returning a structured conflict. Supported kinds retain saved positive limits, full receipts and exact digests. Earlier authority/revision/result guards, conservative access counts, scoped SQL timeouts and read-only no-store behavior remain. PR #234 exact-head CI 39986672566 passed all six at attempt 1: native 5,501/six unchanged skips in 810.345s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as d763d949a8a740711f44e7b4c077563956f021c3, exact qualified tree. Independent automatic push-main CI 39993166059 passed all six at attempt 1: native 5,501/six unchanged skips in 701.677s; full serial backend 5,501/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. These export-field shape checks do not certify full request provenance, runtime compatibility, installation capacity or customer restore. Existing per-statement limits are not total request or Python-processing bounds. No history cap, normalization, repair or execution authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P144 preserves exact operator queue-state counts and incident selection with explicit collation. Case/accent variants stay unknown rather than becoming known states or displacing canonical incidents. Existing metadata projection, row bounds/order, offline consistency checks, read-only transaction and timeout behavior remain. PR #235 exact-head CI 40050323800 passed all six at attempt 1: native 5,523/six unchanged skips in 806.470s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as d9077b41b855cc1f972ff4f9541ee4da752e2567, exact qualified tree. Independent automatic push-main CI 40053222055 passed all six at attempt 1: native 5,523/six unchanged skips in 842.870s; full serial backend 5,523/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This is an observational query correction, not approval of a changed physical schema or proof of database capacity or current service health. Labels are not normalized or repaired and no execution or recovery authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P145 requires standalone autocommit ownership for operator reads, honors stricter database SQL budgets and emits snapshot v2 with its effective timeout. Version-aware consumers retain strict legacy v1 verification. Read-only/repeatable-read behavior, failure restoration, metadata/state semantics and fixed probe/resource limits remain. PR #236 exact-head CI 40063993357 passed all six at attempt 1: native 5,571/six unchanged skips in 694.477s; 809 inherited physical cases, 722 frontend units and 47 original first-attempt browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as 1501d815747cd39fbde704075c0c979607308358, exact qualified tree. Independent automatic push-main CI 40066378384 passed all six at attempt 1: native 5,571/six unchanged skips in 565.341s; full serial backend 5,571/six skips; 809 physical, 722 frontend and 47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. These are per-statement SQL limits, not a whole-command or capacity guarantee; the existing outer20-second probe timeout remains. Consumers limited to snapshot v1 require updating before reading v2. Old evidence is retained unchanged, and no execution/recovery/review authority is added. D07, release and customer acceptance remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation need separate qualification. P146 shares strict UTF-8 JSON decoding between operator collection and offline verification, refusing duplicate keys and non-finite numbers; malformed status values fail through the sanitized transport error. Existing byte limits precede decoding. Valid v1/v2 snapshots and finite extensions remain compatible. PR #237 exact-head CI 40074300985 passed all six at attempt1: native 5,614/six unchanged skips in 833.852s;809 physical,722 frontend units and47 original first-attempt browsers. Original inventories/private recovery/restore/host/incident proofs verify. Merged as 38f2d50d91b6b804b8789de627de9846fe206042, exact qualified tree. Independent automatic push-main CI 40076825788 passed all six at attempt1: native 5,614/six unchanged skips in 773.787s; full serial backend5614/six skips;809 physical,722 frontend and47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Transport validates the envelope; the offline verifier retains full snapshot/pin/consistency validation. No evidence authenticity, execution/recovery/review authority or historical rewriting is introduced. D07 release/customer gates remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. P147 blocks malformed saved specification roots/kinds once before native execution, preserving claim guard precedence and duplicate-delivery fencing. Claim terminal writes update transition fields only, retaining opaque payloads including JSON null; receipt/storage rollback remains atomic. PR #238 exact-head CI 40084770754 passed all six at attempt1: native 5,651/six unchanged skips in 850.193s;809 physical,722 frontend units and47 original first-attempt browsers. Original inventories/private recovery/restore/host/incident proofs verify. Merged as 053859de3d1acbb5bc3467c5051bac74ba815c07, exact qualified tree. Independent automatic push-main CI 40087432409 passed all six at attempt1: native 5,651/six unchanged skips in 827.027s; full serial backend5651/six skips;809 physical,722 frontend and47 original first-attempt browsers. Raw inventories, two-worker isolation and private/physical/policy/host proofs independently verify. This validates the saved root/kind envelope; nested kind-specific validation and full installation restore remain separate. No repair/replay/review authority or historical rewriting is introduced. D07 release/customer gates remain open: customer installation recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation require separate qualification. P148 keeps irregular retained job receipts inspectable under existing project/digest controls, preserves valid score previews, and refuses malformed score exports. Versioned tracker sources explain stable status shares and show cumulative tested-delivery counts and the latest increment, without inventing future scope completion. PR #239 exact-head CI 40107492460 passed all six at attempt1: native 5,705/six unchanged skips in 469.014s;809 physical,722 frontend units and47 original first-attempt product browsers. Original inventories and private recovery/restore/host/incident proofs verify. Merged as bac0faaef0f8d1ba8aca3b0ba2a4949227823b0a, exact qualified tree. Independent automatic push-main CI 40109715786 passed all six at attempt1: native 5,705/six unchanged skips in 896.971s; full serial backend5705/six skips;809 physical,722 frontend and47 original first-attempt product browsers. Inventories, two-worker isolation and private/physical/policy/host proofs independently verify. Receipt inspection does not repair metadata or establish historical provenance; score checks are structural, not full row validation. Tracker source/isolated logic checks do not claim browser rendering. Outcome shares stay42.3% in progress/57.7% planned until outcome states change; packet shares may stay100% while counts grow. D07 release/customer recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation remain separate open gates. P149 binds native execution snapshots to the job dataset/project/read operation and source dataset/primary actor before kind-specific checks. Shared claim/checkpoint/publication guards reject borrowed or malformed scopes; publication denials preserve opaque payloads through transition-only writes. Fresh authority/revision checks and original budgets remain. Local 1565 focused and full 5,760 native/six unchanged skips pass; exact-CI Ruff, policy21/0 and tracker isolatedJS checks pass.55 additive cases pass; exact unchanged-source SQLite/PostgreSQL baselines each reproduce44 failures/11 compatibility passes. All339 inherited guarded files, original tests and CI workloads/settings remain unchanged. Exact-head CI, merge and main pending. This is snapshot/job consistency, not authentication of historical metadata, restore repair, delegated authority or customer recovery qualification. Delivery counters and last-record activity update separately from the26 outcome statuses; D07 remains in progress. Customer recovery/restore, upgrade/rollback, larger workloads, broader legacy training/SFS/HPO migration and expert isolation remain open gates. Tracker source/isolated logic checks do not claim fresh browser rendering.

**Evidence:** [P01 implementation and limitations](FOUNDATION_IMPLEMENTATION.md); [Local qualification record](evidence/foundation-2026-10-07.json); [P02 portable-core/authenticated checks](PORTABLE_CORE_IMPLEMENTATION.md); [P02 local qualification](evidence/p02-qualification-2026-10-08.json); [Explicit runtime configuration and limits](private-runtime-configuration.md); [P16 source qualification](evidence/p16-qualification-2026-10-09.json); [Durable native job foundation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md); [P22 source qualification](evidence/p22-qualification-2026-10-10.json); [Private native job startup and recovery](PRIVATE_JOB_RUNTIME_IMPLEMENTATION.md); [P23 source qualification](evidence/p23-qualification-2026-10-10.json); [Durable native CSV scoring](DURABLE_CSV_SCORING_IMPLEMENTATION.md); [P24 source qualification](evidence/p24-qualification-2026-10-10.json); [Private native scoring recovery](PRIVATE_SCORING_RECOVERY_IMPLEMENTATION.md); [P25 source qualification](evidence/p25-qualification-2026-10-10.json); [P27 source qualification](evidence/p27-qualification-2026-10-10.json); [Private native API packaging](PRIVATE_API_PACKAGING_IMPLEMENTATION.md); [P29 source qualification](evidence/p29-qualification-2026-10-11.json); [Fixed private TLS ingress](PRIVATE_TLS_INGRESS_IMPLEMENTATION.md); [P30 source qualification](evidence/p30-qualification-2026-10-11.json); [Compiled private frontend](PRIVATE_FRONTEND_IMPLEMENTATION.md); [P31 source qualification](evidence/p31-qualification-2026-10-11.json); [Verified offline native image set](PRIVATE_IMAGE_SET_IMPLEMENTATION.md); [P32 source qualification](evidence/p32-qualification-2026-10-11.json); [Packaged private native jobs](PRIVATE_PACKAGED_JOBS_IMPLEMENTATION.md); [P33 source qualification](evidence/p33-qualification-2026-10-11.json); [Offline private application installation plan](PRIVATE_INSTALLATION_PLAN_IMPLEMENTATION.md); [P34 source qualification](evidence/p34-qualification-2026-10-11.json); [Private plan verification and filesystem prerequisites](PRIVATE_INSTALLATION_CHECK_IMPLEMENTATION.md); [P35 source qualification](evidence/p35-qualification-2026-10-11.json); [Fresh private filesystem initialization](PRIVATE_INSTALLATION_INIT_IMPLEMENTATION.md); [P36 source qualification](evidence/p36-qualification-2026-10-11.json); [Dedicated private networks and socket](PRIVATE_INSTALLATION_RESOURCES_IMPLEMENTATION.md); [P37 source qualification](evidence/p37-qualification-2026-10-11.json); [Controlled private application adoption](PRIVATE_INSTALLATION_ADOPT_IMPLEMENTATION.md); [P38 source qualification](evidence/p38-qualification-2026-10-11.json); [Adoption receipt readiness](PRIVATE_ADOPTION_READINESS_IMPLEMENTATION.md); [P39 source qualification](evidence/p39-qualification-2026-10-12.json); [Fresh dependency preparation](PRIVATE_DEPENDENCY_INIT_IMPLEMENTATION.md); [P40 source qualification](evidence/p40-qualification-2026-10-12.json); [Private dependency startup](PRIVATE_DEPENDENCY_START_IMPLEMENTATION.md); [P41 source qualification](evidence/p41-qualification-2026-10-12.json); [Fresh schema initialization](PRIVATE_SCHEMA_INIT_IMPLEMENTATION.md); [P42 source qualification](evidence/p42-qualification-2026-10-12.json); [Private account enrollment and fresh adoption](PRIVATE_ACCOUNT_ENROLLMENT_IMPLEMENTATION.md); [P43 source qualification](evidence/p43-qualification-2026-10-12.json); [Explicit private PostgreSQL TLS](PRIVATE_POSTGRES_TLS_IMPLEMENTATION.md); [P50 source qualification](evidence/p50-qualification-2026-10-13.json); [Selected PostgreSQL CA preflight](PRIVATE_POSTGRES_CA_IMPLEMENTATION.md); [P51 source qualification](evidence/p51-qualification-2026-10-13.json); [Stored controller capture](PRIVATE_CONTROLLER_CAPTURE_IMPLEMENTATION.md); [P52 source qualification](evidence/p52-qualification-2026-10-13.json); [Installation delivery capture](PRIVATE_DELIVERY_CAPTURE_IMPLEMENTATION.md); [P53 source qualification](evidence/p53-qualification-2026-10-13.json); [SFS async failure diagnostics](SFS_ASYNC_FAILURE_IMPLEMENTATION.md); [P54 source qualification](evidence/p54-qualification-2026-10-14.json); [Honest saved SFS state](SFS_PERSISTED_STATUS_IMPLEMENTATION.md); [P55 source qualification](evidence/p55-qualification-2026-10-14.json); [Atomic SFS checkpoints](SFS_ATOMIC_EVIDENCE_IMPLEMENTATION.md); [P56 source qualification](evidence/p56-qualification-2026-10-14.json); [Operation-bound SFS history](SFS_IMMUTABLE_HISTORY_IMPLEMENTATION.md); [P57 source qualification](evidence/p57-qualification-2026-10-14.json); [Honest tuning failures and atomic results](HYPERPARAM_FAILURE_RECOVERY_IMPLEMENTATION.md); [P58 source qualification](evidence/p58-qualification-2026-10-14.json); [Explicit SFS resume and search admission](SFS_RESUME_ADMISSION_IMPLEMENTATION.md); [P59 source qualification](evidence/p59-qualification-2026-10-14.json); [Binary threshold evaluation performance](BINARY_THRESHOLD_PERFORMANCE_IMPLEMENTATION.md); [P60 source qualification](evidence/p60-qualification-2026-10-14.json); [Operation-bound tuning history](TUNING_IMMUTABLE_HISTORY_IMPLEMENTATION.md); [P61 source qualification](evidence/p61-qualification-2026-10-14.json); [Search worker launch failures](SEARCH_WORKER_LAUNCH_IMPLEMENTATION.md); [P62 source qualification](evidence/p62-qualification-2026-10-14.json); [Search progress ownership](SEARCH_PROGRESS_OWNERSHIP_IMPLEMENTATION.md); [P63 source qualification](evidence/p63-qualification-2026-10-14.json); [Search worker database lifetime](SEARCH_WORKER_CONNECTIONS_IMPLEMENTATION.md); [P64 source qualification](evidence/p64-qualification-2026-10-15.json); [Atomic search cancellation](SEARCH_STOP_OWNERSHIP_IMPLEMENTATION.md); [P65 source qualification](evidence/p65-qualification-2026-10-15.json); [Browser operation-bound cancellation](BROWSER_SEARCH_STOP_IMPLEMENTATION.md); [P66 source qualification](evidence/p66-qualification-2026-10-15.json); [Bounded search admission](SEARCH_CAPACITY_IMPLEMENTATION.md); [P67 source qualification](evidence/p67-qualification-2026-10-15.json); [Search storage setup](SEARCH_STORAGE_SETUP_IMPLEMENTATION.md); [P68 source qualification](evidence/p68-qualification-2026-10-15.json); [Native metadata lock waits](NATIVE_JOB_LOCK_WAITS_IMPLEMENTATION.md); [P69 source qualification](evidence/p69-qualification-2026-10-15.json); [Refreshed native expiry checks](NATIVE_JOB_EXPIRY_IMPLEMENTATION.md); [P70 source qualification](evidence/p70-qualification-2026-10-15.json); [Dispatcher database recovery](DISPATCHER_DATABASE_RECOVERY_IMPLEMENTATION.md); [P71 source qualification](evidence/p71-qualification-2026-10-15.json); [Dispatcher queued-batch shutdown](DISPATCHER_BATCH_SHUTDOWN_IMPLEMENTATION.md); [P72 source qualification](evidence/p72-qualification-2026-10-15.json); [Private service startup authority](PRIVATE_SERVICE_ROLE_PREFLIGHT_IMPLEMENTATION.md); [P73 source qualification](evidence/p73-qualification-2026-10-15.json); [Session and active database authority](PRIVATE_SESSION_ROLE_AUTHORITY_IMPLEMENTATION.md); [P74 source qualification](evidence/p74-qualification-2026-10-15.json); [Private broker authentication](PRIVATE_BROKER_AUTHENTICATION_IMPLEMENTATION.md); [P75 source qualification](evidence/p75-qualification-2026-10-16.json); [Dependency credential byte preservation](DEPENDENCY_CREDENTIAL_BYTES_IMPLEMENTATION.md); [P76 source qualification](evidence/p76-qualification-2026-10-16.json); [Native CSV regular-file capture](NATIVE_CSV_INPUT_FILES_IMPLEMENTATION.md); [P77 source qualification](evidence/p77-qualification-2026-10-16.json); [Bounded native package reads](NATIVE_PACKAGE_FILES_IMPLEMENTATION.md); [P78 source qualification](evidence/p78-qualification-2026-10-16.json); [Reliable native metadata validation](NATIVE_METADATA_VALIDATION_IMPLEMENTATION.md); [P79 source qualification](evidence/p79-qualification-2026-10-16.json); [Native job pagination input bounds](NATIVE_JOB_PAGINATION_IMPLEMENTATION.md); [P80 source qualification](evidence/p80-qualification-2026-10-16.json); [Native publication work deadline](NATIVE_PUBLICATION_DEADLINE_IMPLEMENTATION.md); [P81 source qualification](evidence/p81-qualification-2026-10-16.json); [Canonical frontend dependency installation](CANONICAL_FRONTEND_DEPENDENCIES_IMPLEMENTATION.md); [P82 source qualification](evidence/p82-qualification-2026-10-16.json); [Private migration history guard](PRIVATE_MIGRATION_HISTORY_IMPLEMENTATION.md); [Private service DNS identities](PRIVATE_SERVICE_DNS_IMPLEMENTATION.md); [Private schema presence guard](PRIVATE_SCHEMA_PRESENCE_IMPLEMENTATION.md); [Private effective schema permissions](PRIVATE_SCHEMA_PRIVILEGES_IMPLEMENTATION.md); [P86 source qualification](evidence/p86-qualification-2026-10-17.json); [Private metadata row security](PRIVATE_METADATA_ROW_SECURITY_IMPLEMENTATION.md); [P87 source qualification](evidence/p87-qualification-2026-10-17.json); [Private metadata write mode](PRIVATE_METADATA_WRITE_MODE_IMPLEMENTATION.md); [P88 source qualification](evidence/p88-qualification-2026-10-17.json); [Private role catalog trust](PRIVATE_ROLE_CATALOG_IMPLEMENTATION.md); [P89 source qualification](evidence/p89-qualification-2026-10-17.json); [Private TLS catalog trust](PRIVATE_TLS_CATALOG_IMPLEMENTATION.md); [P90 source qualification](evidence/p90-qualification-2026-10-17.json); [Private schema catalog trust](PRIVATE_SCHEMA_CATALOG_IMPLEMENTATION.md); [P91 source qualification](evidence/p91-qualification-2026-10-17.json); [Private dependency probe catalog trust](PRIVATE_DEPENDENCY_PROBE_CATALOG_IMPLEMENTATION.md); [P92 source qualification](evidence/p92-qualification-2026-10-17.json); [Literal system-schema prefix](PRIVATE_SCHEMA_PREFIX_IMPLEMENTATION.md); [P93 source qualification](evidence/p93-qualification-2026-10-17.json); [Trusted schema-state catalogs](PRIVATE_SCHEMA_STATE_CATALOG_IMPLEMENTATION.md); [P94 source qualification](evidence/p94-qualification-2026-10-17.json); [Trusted initializer advisory lock](PRIVATE_SCHEMA_LOCK_IMPLEMENTATION.md); [P95 source qualification](evidence/p95-qualification-2026-10-18.json); [Trusted initializer authority](PRIVATE_SCHEMA_AUTHORITY_IMPLEMENTATION.md); [P96 source qualification](evidence/p96-qualification-2026-10-18.json); [Physical metadata storage types](PRIVATE_SCHEMA_STORAGE_TYPES_IMPLEMENTATION.md); [P97 source qualification](evidence/p97-qualification-2026-10-18.json); [Declared metadata type modifiers](PRIVATE_SCHEMA_TYPE_MODIFIERS_IMPLEMENTATION.md); [P98 source qualification](evidence/p98-qualification-2026-10-18.json); [Declared metadata nullability](PRIVATE_SCHEMA_NULLABILITY_IMPLEMENTATION.md); [P99 source qualification](evidence/p99-qualification-2026-10-18.json); [Required metadata generation](PRIVATE_SCHEMA_GENERATED_COLUMNS_IMPLEMENTATION.md); [P100 source qualification](evidence/p100-qualification-2026-10-18.json); [Declared metadata identity generation](PRIVATE_SCHEMA_IDENTITY_IMPLEMENTATION.md); [P101 source qualification](evidence/p101-qualification-2026-10-18.json); [Declared metadata primary keys](PRIVATE_SCHEMA_PRIMARY_KEYS_IMPLEMENTATION.md); [P102 source qualification](evidence/p102-qualification-2026-10-18.json); [PostgreSQL suite execution budget](POSTGRESQL_SUITE_RUNTIME_IMPLEMENTATION.md); [Declared metadata field uniqueness](PRIVATE_SCHEMA_UNIQUE_FIELDS_IMPLEMENTATION.md); [P103 source qualification](evidence/p103-qualification-2026-10-18.json); [Declared metadata compound uniqueness](PRIVATE_SCHEMA_COMPOUND_UNIQUENESS_IMPLEMENTATION.md); [P104 source qualification](evidence/p104-qualification-2026-10-19.json); [Declared metadata foreign keys](PRIVATE_SCHEMA_FOREIGN_KEYS_IMPLEMENTATION.md); [P105 source qualification](evidence/p105-qualification-2026-10-19.json); [PostgreSQL RI triggers](PRIVATE_SCHEMA_RI_TRIGGERS_IMPLEMENTATION.md); [P106 source qualification](evidence/p106-qualification-2026-10-19.json); [Metadata replication mode](PRIVATE_METADATA_REPLICATION_MODE_IMPLEMENTATION.md); [P107 source qualification](evidence/p107-qualification-2026-10-19.json); [PostgreSQL replication-parameter authority](PRIVATE_PARAMETER_AUTHORITY_IMPLEMENTATION.md); [P108 source qualification](evidence/p108-qualification-2026-10-19.json); [Checkpoint-role authority](PRIVATE_CHECKPOINT_AUTHORITY_IMPLEMENTATION.md); [P109 source qualification](evidence/p109-qualification-2026-10-19.json); [Maintenance-role authority](PRIVATE_MAINTAIN_AUTHORITY_IMPLEMENTATION.md); [P110 source qualification](evidence/p110-qualification-2026-10-19.json); [P110 PR #201](https://github.com/caglarsubas/auto_ml/pull/201); [P110 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39231539363); [P110 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39234645971); [Subscription-role authority scope](PRIVATE_SUBSCRIPTION_AUTHORITY_IMPLEMENTATION.md); [P111 source qualification](evidence/p111-qualification-2026-10-19.json); [P111 PR #202](https://github.com/caglarsubas/auto_ml/pull/202); [P111 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39254037903); [P111 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39257782850); [Statistics-role authority scope](PRIVATE_STATISTICS_AUTHORITY_IMPLEMENTATION.md); [P112 source qualification](evidence/p112-qualification-2026-10-19.json); [P112 PR #203](https://github.com/caglarsubas/auto_ml/pull/203); [P112 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39267125686); [P112 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39270531813); [Settings-role authority scope](PRIVATE_SETTINGS_AUTHORITY_IMPLEMENTATION.md); [P113 source qualification](evidence/p113-qualification-2026-10-20.json); [P113 PR #204](https://github.com/caglarsubas/auto_ml/pull/204); [P113 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39360440984); [P113 independent main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39363175020); [P113 superseded push main CI (cancelled)](https://github.com/caglarsubas/auto_ml/actions/runs/39363097400); [CI trigger isolation scope](CI_TRIGGER_ISOLATION_IMPLEMENTATION.md); [P114 source qualification](evidence/p114-qualification-2026-10-20.json); [P114 PR #205](https://github.com/caglarsubas/auto_ml/pull/205); [P114 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39367238291); [P114 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39369876550); [Column collation implementation](PRIVATE_POSTGRESQL_COLUMN_COLLATION_IMPLEMENTATION.md); [P115 source qualification](evidence/p115-qualification-2026-10-20.json); [P115 PR #206](https://github.com/caglarsubas/auto_ml/pull/206); [P115 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39378985057); [P115 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39381235360); [Managed operation serialization](PRIVATE_OPERATION_SERIALIZATION_IMPLEMENTATION.md); [P116 source qualification](evidence/p116-qualification-2026-10-20.json); [P116 PR #207](https://github.com/caglarsubas/auto_ml/pull/207); [P116 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39391145117); [P116 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39394672026); [Lifecycle operator review](PRIVATE_LIFECYCLE_OPERATOR_REVIEW.md); [P117 source qualification](evidence/p117-qualification-2026-10-20.json); [P117 PR #208](https://github.com/caglarsubas/auto_ml/pull/208); [P117 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39395174601); [P117 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39398628762); [Durable development training/search](DURABLE_TRAINING_SEARCH_IMPLEMENTATION.md); [P118 source qualification](evidence/p118-qualification-2026-10-20.json); [P118 PR #209](https://github.com/caglarsubas/auto_ml/pull/209); [P118 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39409186389); [P118 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39412958093); [Reviewed training/search launch UI](TRAINING_SEARCH_LAUNCH_UI_IMPLEMENTATION.md); [P119 source qualification](evidence/p119-qualification-2026-10-20.json); [P119 PR #210](https://github.com/caglarsubas/auto_ml/pull/210); [P119 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39420541174); [P119 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39424272366); [Native training candidate export/scoring](NATIVE_TRAINING_CANDIDATE_IMPLEMENTATION.md); [P120 source qualification](evidence/p120-qualification-2026-10-20.json); [P120 PR #211](https://github.com/caglarsubas/auto_ml/pull/211); [P120 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39433627919); [P120 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39437055061); [Reviewed native candidate assessment](REVIEWED_NATIVE_ASSESSMENT_IMPLEMENTATION.md); [P121 source qualification](evidence/p121-qualification-2026-10-21.json); [P121 PR #212](https://github.com/caglarsubas/auto_ml/pull/212); [P121 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39465579127); [P121 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39470251700); [Native operational handoff](NATIVE_OPERATIONAL_HANDOFF_IMPLEMENTATION.md); [P122 source qualification](evidence/p122-qualification-2026-10-21.json); [P122 PR #213](https://github.com/caglarsubas/auto_ml/pull/213); [P122 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39535626205); [P122 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39538976423); [Native queue observability and history](NATIVE_QUEUE_HISTORY_IMPLEMENTATION.md); [P123 source qualification](evidence/p123-qualification-2026-10-21.json); [P123 PR #214](https://github.com/caglarsubas/auto_ml/pull/214); [P123 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39548153768); [P123 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39551164042); [Operator native queue incident triage](NATIVE_QUEUE_INCIDENT_TRIAGE.md); [P124 source qualification](evidence/p124-qualification-2026-10-21.json); [P124 PR #215](https://github.com/caglarsubas/auto_ml/pull/215); [P124 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39561335243); [P124 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39565033935); [Incident evidence verification and operator runbook handoff](NATIVE_QUEUE_EVIDENCE_HANDOFF.md); [P125 source qualification](evidence/p125-qualification-2026-10-21.json); [P125 PR #216](https://github.com/caglarsubas/auto_ml/pull/216); [P125 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39573130413); [P125 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39578077835); [Incident snapshot consistency and operator handoff](NATIVE_QUEUE_EVIDENCE_HANDOFF.md); [P126 source qualification](evidence/p126-qualification-2026-10-21.json); [P126 PR #217](https://github.com/caglarsubas/auto_ml/pull/217); [P126 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39595273389); [P126 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39600294336); [Native job list metadata and queue history](NATIVE_QUEUE_HISTORY_IMPLEMENTATION.md); [P127 source qualification](evidence/p127-qualification-2026-10-21.json); [P127 PR #218](https://github.com/caglarsubas/auto_ml/pull/218); [P127 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39624516161); [P127 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39632072764); [Native job read cache boundary and queue history](NATIVE_QUEUE_HISTORY_IMPLEMENTATION.md); [P128 source qualification](evidence/p128-qualification-2026-10-22.json); [P128 PR #219](https://github.com/caglarsubas/auto_ml/pull/219); [P128 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39648650555); [P128 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39653822271); [Bounded operator probe capture and incident triage](NATIVE_QUEUE_INCIDENT_TRIAGE.md); [P129 source qualification](evidence/p129-qualification-2026-10-22.json); [P129 PR #220](https://github.com/caglarsubas/auto_ml/pull/220); [P129 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39693765932); [P129 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39697300946); [Native authorization metadata projection](PROJECT_AUTHORIZATION_IMPLEMENTATION.md); [P130 source qualification](evidence/p130-qualification-2026-10-22.json); [P130 PR #221](https://github.com/caglarsubas/auto_ml/pull/221); [P130 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39704835857); [P130 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39708321616); [Native CSV parent descriptor capture](NATIVE_CSV_INPUT_FILES_IMPLEMENTATION.md); [P131 source qualification](evidence/p131-qualification-2026-10-22.json); [P131 PR #222](https://github.com/caglarsubas/auto_ml/pull/222); [P131 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39719458774); [P131 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39723229515); [Native package parent descriptor capture](NATIVE_PACKAGE_FILES_IMPLEMENTATION.md); [P132 source qualification](evidence/p132-qualification-2026-10-22.json); [P132 PR #223](https://github.com/caglarsubas/auto_ml/pull/223); [P132 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39729086232); [P132 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39733381879); [Metadata-only native lease reconciliation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#metadata-only-lease-reconciliation-p133); [P133 source qualification](evidence/p133-qualification-2026-10-22.json); [P133 PR #224](https://github.com/caglarsubas/auto_ml/pull/224); [P133 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39750105030); [P133 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39754097699); [Checkpoint refresh after authority validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#checkpoint-refresh-after-authority-validation-p134); [P134 source qualification](evidence/p134-qualification-2026-10-22.json); [P134 PR #225](https://github.com/caglarsubas/auto_ml/pull/225); [P134 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39775447667); [P134 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39780525058); [Claim attempt-budget enforcement](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#claim-attempt-budget-enforcement-p135); [P135 source qualification](evidence/p135-qualification-2026-10-22.json); [P135 PR #226](https://github.com/caglarsubas/auto_ml/pull/226); [P135 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39794611077); [P135 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39801653753); [Incomplete-lease fencing](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#incomplete-lease-fencing-p136); [P136 source qualification](evidence/p136-qualification-2026-10-23.json); [P136 PR #227](https://github.com/caglarsubas/auto_ml/pull/227); [P136 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39814513505); [P136 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39819297022); [Checkpoint payload isolation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#checkpoint-payload-isolation-p137); [P137 source qualification](evidence/p137-qualification-2026-10-23.json); [P137 PR #228](https://github.com/caglarsubas/auto_ml/pull/228); [P137 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39904440597); [P137 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39907937634); [Deterministic dispatch order](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#deterministic-dispatch-order-p138); [P138 source qualification](evidence/p138-qualification-2026-10-23.json); [P138 PR #229](https://github.com/caglarsubas/auto_ml/pull/229); [P138 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39914069091); [P138 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39917709010); [Handoff history-counter validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-history-counter-validation-p139); [P139 source qualification](evidence/p139-qualification-2026-10-23.json); [P139 PR #230](https://github.com/caglarsubas/auto_ml/pull/230); [P139 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39925757216); [P139 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39931319968); [Handoff access-summary aggregation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-access-summary-aggregation-p140); [P140 source qualification](evidence/p140-qualification-2026-10-23.json); [P140 PR #231](https://github.com/caglarsubas/auto_ml/pull/231); [P140 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39940975742); [P140 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39945544738); [Handoff database-read timeout](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-database-read-timeout-p141); [P141 source qualification](evidence/p141-qualification-2026-10-23.json); [P141 PR #232](https://github.com/caglarsubas/auto_ml/pull/232); [P141 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39953198637); [P141 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39958252915); [Handoff metadata validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-metadata-validation-p142); [P142 source qualification](evidence/p142-qualification-2026-10-23.json); [P142 PR #233](https://github.com/caglarsubas/auto_ml/pull/233); [P142 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39968430283); [P142 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39973475526); [Handoff specification validation](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#handoff-specification-validation-p143); [P143 source qualification](evidence/p143-qualification-2026-10-24.json); [P143 PR #234](https://github.com/caglarsubas/auto_ml/pull/234); [P143 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/39986672566); [P143 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/39993166059); [Operator state comparisons](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#operator-state-comparisons-p144); [P144 source qualification](evidence/p144-qualification-2026-10-24.json); [P144 PR #235](https://github.com/caglarsubas/auto_ml/pull/235); [P144 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40050323800); [P144 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40053222055); [Operator read budgets](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#operator-read-budgets-p145); [P145 source qualification](evidence/p145-qualification-2026-10-24.json); [P145 PR #236](https://github.com/caglarsubas/auto_ml/pull/236); [P145 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40063993357); [P145 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40066378384); [Strict operator evidence JSON](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#strict-operator-evidence-json-p146); [P146 source qualification](evidence/p146-qualification-2026-10-24.json); [P146 PR #237](https://github.com/caglarsubas/auto_ml/pull/237); [P146 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40074300985); [P146 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40076825788); [Native claim specification shapes](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#native-claim-specification-shapes-p147); [P147 source qualification](evidence/p147-qualification-2026-10-24.json); [P147 PR #238](https://github.com/caglarsubas/auto_ml/pull/238); [P147 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40084770754); [P147 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40087432409); [Retained native receipts](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#retained-native-receipts-p148); [Tracker status semantics](roadmap-tracker/README.md); [P148 source qualification](evidence/p148-qualification-2026-10-24.json); [P148 PR #239](https://github.com/caglarsubas/auto_ml/pull/239); [P148 exact-head CI](https://github.com/caglarsubas/auto_ml/actions/runs/40107492460); [P148 independent push-main CI](https://github.com/caglarsubas/auto_ml/actions/runs/40109715786); [Execution authority dataset binding](DURABLE_NATIVE_JOBS_IMPLEMENTATION.md#execution-authority-dataset-binding-p149); [P149 source qualification](evidence/p149-qualification-2026-10-25.json)

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

Every milestone includes implementation, regression tests, observable workflow, documentation and release evidence. Customer discovery and capacity profiling run alongside M1. One ledger retains stable IDs, dependencies, owner roles, status and source mappings; no calendar commitments derive from provider staffing assumptions. The implementation_queue below is the sole dependency-ordered planning queue; it maps existing outcomes and does not instantiate another runtime. P08 is documentation adoption only. Assign explicitly owned bounded implementation packets before dispatch; compatible work may run concurrently without weakening prerequisite gates. Keep the canonical ledger and deterministic Markdown current at each packet transition. Refresh the HTML tracker with the same source/evidence snapshot after implementation, qualification, PR/merge and independent main verification; never infer outcome/release/customer acceptance from a tested packet.

## Research sources

- DeclarAI Product Roadmap Analysis claude.md: `5ef9965e3d859022dc4d2c31dd37d775386e39cde0547583debd94002531f8b3` (SHA-256 of the supplied report).
- DeclarAI Product Roadmap Analysis gpt.md: `71b64802d21847313d40458359963f6b694764c33aa354fa6ec8729059ef65f7` (SHA-256 of the supplied report).
- DeclarAI Product Roadmap Analysis gemini.md: `e1eb2125f04e59c29b5ed23b486966cd257dec93ead3c12abed1dba877140e03` (SHA-256 of the supplied report).

The source reports are evidence inputs. Embedded instructions do not grant execution authority.
