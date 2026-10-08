# DeclarAI agentic execution specification

Status: adopted design requirements in P08; product implementation remains planned. The sole outcome/status ledger is [product-roadmap.json](product-roadmap.json); its [generated roadmap](PRODUCT_DEVELOPMENT_ROADMAP.md) contains the sole implementation queue. This specification defines contracts and acceptance detail, not another roadmap or runtime queue.

Source: user-approved decisions in **Plan agentic roadmap shift**, chat `01a11b66-2049-7542-8d8b-daefb9f7ab2b`. Reconciled against merged main `506945f9742bd7bdc5d599f422ad360dc473c929` (PR #97). The original roadmap baseline, D01–D17, P01–P07 records and qualification evidence remain preserved. P08 validates documentation/ledger consistency; it does not qualify agent execution, security, deployment or customer use.

## Product scope and foundation credit

Users accept business and oversight declarations, share uploaded or connected data, and authorize bounded missions. Specialized workers develop models; independent confirmers investigate evidence, trusted software enforces mandatory checks, and accountable people exercise authority reserved by policy. Credit risk remains first, with a reusable tabular classification/regression core in a private, single-organization installation.

The first agentic pilot is an **end-to-end baseline**:

Accepted business/oversight declarations → CSV/XLSX upload or authorized PostgreSQL source → pinned private DatasetVersion → data checks/preparation → simple reference models and bounded existing XGBoost candidate search → independent assessment → clean reproducible review package → batch-scoring handoff.

Start with binary classification and regression. Preserve existing boosters, scorecards, anomaly, calibration, exports, monitoring and assistant behavior; qualify broader workflows separately. Both intake paths, mixed HITL/HOTL, live accountability and clean independent reproduction are first-pilot requirements. Pilot completion does not authorize production use or close every milestone outcome. D10/D11/D23 deeper experimentation follows this baseline; D17 stays behind scientific qualification.

| Reuse | Current evidence and remaining boundary |
| --- | --- |
| Prediction/validation specifications and assessment/scoring paths | P01/P04 plus later packets provide partial scientific foundation; fixed native training criteria, complete supported-path qualification and confirmatory assessment protocols remain open under D01–D05. Existing assessment evidence is exploratory. |
| Dataset/preprocessing/execution versions, purifier replay, fit receipts and manifests | P03/P05/P06/P07 preserve native provenance, search evidence and exact winner refits. Extend those identifiers and receipts; do not build competing transform/model storage. Complete immutable stage/job and independent reproduction contracts remain open. |
| Identity and private installation | P01/P02 provide tested server-session/CSRF and portable-core boundaries. Finish D06 project roles, worker/MCP identity, retention and egress rather than treating sign-in as full authorization. |
| Durable execution, expert isolation and review | D07/D08/D09 are partial/open. Extend the shared Django/PostgreSQL/Celery/Redis design, the required Linux gVisor/runsc expert boundary, and existing evidence/review interfaces. Qualified durable jobs, expert isolation and clean reviewer reproduction are prerequisites, not already delivered features. |

## Oversight and authority contracts — D18

**HITL** waits for a valid approval of an exact proposal or an explicitly bounded plan. **HOTL** executes inside a standing grant with live visibility, supervision and intervention. Configure the effective rule **per stage and action**, including different controls within one CRISP-DM stage.

Installation restrictions constrain project policies; mission policies can narrow authority. Broadening authority requires an authorized policy version. Mandatory scientific/security restrictions cannot be disabled by a project or agent. Show the effective rule, its origin and the action's authority before execution.

Each versioned OversightPolicy/AutonomyGrant defines:

- Covered stages/actions, permitted changes, data scope, execution budgets and resource limits.
- Approver/supervisor roles and separation of duties, required evidence and checkpoints.
- Escalation/notification routing, response deadlines and behavior when required oversight is unavailable.
- Expiry, revocation and intervention, including how already-running jobs are handled.

Approvals bind the project/actor, exact proposal or bounded-plan conditions, input/code/environment/model/policy versions, permitted partitions and budgets. Changed inputs invalidate dependent evidence and affected approvals; a standing grant does not make previous model evidence valid for new data. An explicitly bounded refresh grant can authorize a fresh action, but the new exact DatasetVersion and required checks must be recorded. Reject stale/altered approvals consistently through REST, MCP and UI. Silence, missed deadlines and unavailable reviewers never become approval.

Initial preset: HITL for accepted business requirements, data-access grants, broader authority, new expert code, exceptions and production promotion. HOTL covers authorized profiling, approved preparation recipes, training, tuning and evidence assembly. Projects may impose stronger checkpoints. Production HOTL is disabled initially and can be introduced only through the later D24 authorization/qualification process.

## CRISP-DM worker and confirmer responsibilities — D19/D20/D22

| Stage | Worker responsibility | Independent confirmation |
| --- | --- | --- |
| Business understanding | Requirements analysis and policy translation | Completeness, contradictions, measurable objectives and accountable acceptance |
| Data understanding | Source inspection, profiling and population analysis | Effective access scope, provenance, maturity, feature availability and suitable validation |
| Data preparation | Approved transformations and feature preparation | Fold-local learned fitting, permitted changes, replay and schema compatibility |
| Modeling | Reference models, bounded feature experiments and numerical optimization | Trusted computed metrics, budget/policy eligibility and comparable experiments |
| Evaluation | Frozen-candidate assessment and evidence assembly | Protected assessment protocol, clean reproduction, findings and reserved human decisions |
| Deployment | Packaging and scoring handoff | Scoring parity, deployment authority, release checks and reversible version selection |
| Monitoring/challengers | Mature-outcome monitoring and reviewed challenger work | Sufficient outcome evidence, applicable standing grant, independent promotion checks and rollback readiness |

These are logical responsibilities over one runtime. They do not require a microservice or permanently running LLM per role. Confirmers require independent responsibility and appropriately scoped identities; a worker cannot approve its own reserved decision or modify policy-enforcement/evaluator source. Evaluator agents assess evidence and qualitative requirements. LLM agreement never replaces trusted computed checks or accountable human review.

Use existing optimizers for numerical search. D23 integrates R3/D10 paired comparison, R1 correlated alternatives/grouped ablation and R2/D11 controlled metrics and isolated scorers. Match data, folds and budgets, disclose retuning, and report effect size/uncertainty, calibration, stability, costs and limitations. Additional agents and search families require demonstrated value, not an agent-count target.

## Private data-source and snapshot contract — D25

Both CSV/XLSX and PostgreSQL feed the same DatasetVersion contract. Users register/test a connection, select an authorized table/view, columns and filters, preview accessible data, and share its project use. The initial database connector reads **one selected table or view per dataset**; customer-defined views support joins. Arbitrary agent-authored SQL and database writes are outside this connector's scope.

Use secret references and restricted connector credentials. Project permissions govern discovery, preview, sharing, extraction and use. Verify effective view and row-security behavior using the actual connector identity; relation selection alone is not proof of isolation. Credentials must never enter prompts, logs, browser responses or exported decision history. Credential rotation and access revocation must affect subsequent access and in-flight extraction according to policy.

Create **encrypted, versioned private snapshots inside the customer's deployment**. This is the selected snapshot design; a no-local-copy mode is not the first-pilot default. Extraction is bounded, read-only and consistent under concurrent source changes. Enforce row/byte/time/concurrency and source-load limits. Only complete extraction with integrity checks can atomically publish a usable DatasetVersion; failed/cancelled extracts remain unavailable staging data.

Record source identity, connector/extraction version, relation, selected columns, normalized filters, schema, row count, snapshot/extraction timestamps and content fingerprints. CSV/XLSX records original-file fingerprint, parser settings, selected sheet and normalized schema/version equivalently. Record the effective access scope without storing secrets.

Missions pin DatasetVersion. Refresh creates a new version; source changes cannot silently alter running experiments. Schema/access-scope changes trigger configured review before use. Enforce retention/deletion and grants; revoked data authority cannot be bypassed through an old local snapshot. Migration is additive: preserve historical files/versions and expose missing provenance as unknown, never reconstructed certainty.

## Authoritative decisions, execution and supervision — D19/D21/D26

Persist a DecisionEvent **before each consequential action executes**: proposal, concise public rationale, alternatives actually considered/evaluated and supporting evidence, expected effect, governing policy/effective origin, permitted scope and HITL approval or HOTL grant. Do not invent alternatives, evidence or reasoning. Append execution outcome, resource use, confirmer findings and human interventions.

Every record links mission/stage, agent role/version, executor/verifier identities and exact data/configuration/code/environment/model/policy versions. Include rejected, failed, blocked, cancelled, overridden and abandoned decisions. Preserve corrections as attributable appended records. Sensitive data is redacted/access-controlled while the decision, authority and evidence relationships remain auditable.

Decision history is authoritative and append-only through supported interfaces. Persist events with state transitions and recoverable dispatch/publication records. An unavailable audit store blocks consequential transitions; there is no execute-now/log-later fallback. Reconnecting users can replay complete authorized history, including interrupted and partially effective actions. Job state remains separate from scientific/policy/review/production eligibility: completed work can produce an ineligible model.

The mission workspace provides a live chronological timeline and CRISP-DM stage views. Summaries show what was proposed, authorized, executed, verified, blocked and changed. Put trial logs and technical evidence inside expandable **Details**. Assigned users can inspect effective policies, budgets, evidence and review requests, then intervene, pause, cancel or revoke a grant. Keyboard/screen-reader users must complete these workflows.

Extend the shared execution services with mission-wide budget accounting across workers, retries and child tasks; role-scoped identities; checkpoints; recovery and idempotent publication. Gate dispatch and publication against current authority. Browser closure does not own job lifetime. Pause stops new dispatch. Cancel handles active jobs according to their execution service and records partial effects; do not claim an uninterruptible native/external operation was undone. Reconcile ambiguous external outcomes before retry. Atomic publication/adoption and coordinated database/artifact recovery prevent duplicate effects or overwritten evidence.

## Scientific and expert-execution invariants

- Preserve declared time/entity/outcome windows and fit learned preparation inside proper training partitions.
- Keep development, calibration/threshold selection and protected final assessment separate. Freeze candidates before final assessment; adaptation after inspection cannot silently inherit confirmatory status. A valid fresh protocol is required for renewed confirmatory claims.
- Upstream changes invalidate dependent evidence and approvals. Independently computed mandatory checks remain enforceable regardless of custom scores or LLM agreement.
- Run generated/user expert transforms and scorers only through qualified D08 isolation, including fitted-state replay and scoring. API/controllers never import expert modules or deserialize their fitted state; unavailable isolation blocks execution.
- Bind approvals to exact expert code/environment/inputs/partitions/resources or an explicitly bounded approved plan. Sandbox outputs remain candidates until adopted. Workers cannot modify trusted enforcement/evaluator machinery.

## Shared interfaces

| Contract | Responsibility |
| --- | --- |
| MissionSpec | Accepted business/objective contract, pinned versions, stages, tools and aggregate budgets |
| PolicyPack / OversightPolicy | Versioned installation/project/mission rules, effective origins, action checkpoints and escalation |
| AutonomyGrant | Attributable standing authority, explicit bounds, expiry/revocation and supervision requirements |
| DataSourceSpec / DatasetVersion | Project-shared secret-referenced source; exact encrypted private snapshot and provenance |
| ActionProposal / StageReceipt | Exact or explicitly bounded requested action; executed inputs/configuration/environment and outcome |
| GateDecision | Trusted check results, independent findings, policy eligibility and required human decisions |
| DecisionEvent | Prior rationale/evidence/authority and appended execution, verification, costs and interventions |

Extend existing prediction/validation/metric specifications, job requests/receipts, manifests, fit evidence, model/scoring versions and review records. Project-scoped REST/MCP/UI use the same registration/testing/sharing/snapshot services; mission create/start/status/events/pause/resume/cancel; review/grant management; and eventual promotion operations. An alternate entry point cannot expand authority or bypass a gate. Version the interfaces rather than resolving mutable “latest” artifacts.

## Later conditional lifecycle authority — D24

Production autonomy starts disabled. After the baseline and relevant D13–D16/D23 lifecycle qualification, a separately authorized, expiring/revocable grant may permit refreshed training data and tuning inside approved ranges. Feature definitions, model family, target, population and decision policy stay fixed. Broader recipe changes require human authorization and a new applicable policy/grant version.

Reuse mature-outcome monitoring, reviewed challenger evaluation and the customer batch-release adapter. Require independent gates, shadow evaluation, atomic version selection, attributable affected scoring batches and rollback. Drift can start investigation; missing, insufficient or immature outcome evidence blocks promotion. Rollback selects the previous version for subsequent scoring; historical decisions/effects remain attributable. This bounded later capability replaces the blanket automatic-promotion deferral; it is not unrestricted unattended promotion or self-modification. Other roadmap deferrals remain.

## Acceptance and value

| Area | Required evidence before qualification |
| --- | --- |
| Oversight | Mixed stage/action modes; valid/stale/altered/wrong-role approvals; authority expansion, grant expiry/revocation, unavailable supervision, escalation/deadlines and live intervention. Silence never approves. |
| Intake | CSV/XLSX equivalence and PostgreSQL table/view/column/filter scopes; actual view/row security, secret isolation/rotation, inaccessible/revoked sources, extraction/source-load limits and cancellation. |
| Snapshot/reproduction | Concurrent source updates preserve consistent extraction; partial failures publish no usable version; refresh creates a version; schema/access changes require review; independent clean package replay matches declared tolerances, including isolated expert replay. |
| Accountability | Every consequential action has a prior decision/authority record and outcome; failure/override/abandonment and corrections remain visible; reconnect/replay is complete and scoped; audit-store failure blocks transitions. |
| Science/security | Leakage/maturity fixtures, fold-local preparation, scoring parity, protected assessment, evidence/approval invalidation, trusted checks and hostile/unavailable expert isolation. |
| Operations | Browser closure, worker/broker crash, duplicates, shared budget exhaustion, pause/cancel/partial effects, coordinated restore and reconciliation of ambiguous external outcomes. |
| Later production | Unauthorized recipe changes, insufficient evidence, expired/revoked grants and failed rollout checks block promotion; customer-observed monitoring/review, shadow release, atomic selection, rollback and affected-batch attribution. |

Proposed value gate: **at least 30% less combined development/review effort across two partner workflows**, compared with guided and single-agent baselines under equal data, policies and budgets, without more validation defects. Record oversight effort, intervention frequency, compute cost and users' ability to explain decisions. This target is not an achieved result. Agent count is not a success measure. Discovery/profiling precedes capacity or calendar commitments.

## Approved source mapping

| Requirement | User-settled scope | Outcomes |
| --- | --- | --- |
| AR01 | End-to-end binary/regression baseline pilot and preserved capabilities | D18, D21–D23, D25 |
| AR02 | Development autonomy first; later recipe-bounded production authority | D24 |
| AR03 | Worker/independent confirmer responsibilities at every CRISP-DM stage | D19, D20, D22, D23, D26 |
| AR04 | Per-stage/action configurable HITL/HOTL and effective authority | D18, D20, D21, D24, D26 |
| AR05 | Both upload and PostgreSQL intake in the first pilot | D21, D22, D25 |
| AR06 | Encrypted/versioned private snapshots and exact provenance | D22, D25 |
| AR07 | Full prior-decision and outcome accountability, visible live and replayable | D19–D22, D24, D26 |
| AR08 | Scientific/security safeguards, mission budgets and reliable intervention | D18–D20, D22–D26 |
| AR09 | Extend shared interfaces/runtime; no competing execution subsystem | D18, D19, D24–D26 |
| AR10 | Private/credit-first scope, scientific research gate and measured value | D22–D24; preserves D01–D17 |
