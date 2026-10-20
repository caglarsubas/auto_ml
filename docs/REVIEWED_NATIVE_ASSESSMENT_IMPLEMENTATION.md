# Reviewed native candidate adoption and protected assessment (P121)

P121 extends P118–P120 with an independent review decision and a protected
assessment workflow. Adoption accepts one immutable native development candidate
**for protected assessment only**. It neither changes a legacy champion nor grants
production use. The original training result and portable export remain immutable.

## Observable workflow

1. A project developer proposes the exact successful native training result and
   export, with a rationale. The proposal records the prediction contract, metric,
   features, actor, project authority and content digests.
2. A project reviewer, distinct from both proposer and original training actor,
   reviews that proposal and explicitly accepts its observed revision and digest.
   Changing roles does not allow a developer to review their own candidate.
   Decisions are append-only; revocation blocks subsequent execution/publication.
3. The accepting reviewer seals a separate outcome CSV, declares an assessment
   as-of with timezone, and attests population and maturity with a rationale.
   Sealing is custody and header/shape validation, not analytical evaluation.
4. A separate preview displays the pinned assessment and resource budget. Explicit
   confirmation queues a durable job. The worker reserves a common outcome-access
   record before reading labels, scores the frozen model, and publishes aggregate
   trusted metrics. Job history supports progress, cancellation and receipt download.

The UI retains the exact request UUID and body for an explicit retry after an
uncertain response, including the same multipart file. Context changes invalidate
the prepared action. Server admission and publication recheck current authority,
candidate/source digests, approval revision, runtime and limits.

## Protected evidence and scientific limits

Protected bytes live in a dedicated non-null PostgreSQL `bytea` column (SQLite
binary in development), not a generic dataset, shared artifact, scoring input or
MCP dataset. Project APIs return custody metadata only. Controller preview/admission
does not load the native model or protected bytes. Only a worker reads a bounded
payload after reserving outcome access. Results contain aggregate metrics and a
score digest, with no per-row scores, labels, raw CSV or model state.

This profile supports the existing numeric binary-classification and regression
candidates: 1–32 features, 30–1000 protected rows and at most 5 MiB. Headers contain
exactly frozen features, target and declared validation controls; order may vary.
Missing predictors reuse the original fitted means. Unknown labels and invalid
numeric outcomes fail; an undefined primary metric fails explicitly. Positive-class
mapping, primary metric, costs and existing trusted thresholds stay frozen. No
calibration, tuning or threshold selection uses protected outcomes.

Grouped assessment rejects missing, type-incompatible or overlapping entities.
Temporal assessment requires protected dates after the latest development outcome
end, valid ordered outcome windows, and maturity by the declared as-of. Random
splits carry reviewer-declared separation only: matching feature values cannot prove
independent population identity. The original pinned development source must still
be available and unchanged. Unsupported combinations stop with actionable reasons.

**Every assessment remains exploratory.** An upload or reviewer attestation cannot
establish unknown external history, independent population identity or maturity.
Completed, failed and interrupted attempts retain common outcome-access records;
repeated evaluations disclose prior related accesses. Post-inspection changes cannot
inherit confirmation. Common evidence accounting can block fresh-development
training on the same dataset; continue through an explicit new version, with prior
history disclosed. Reordered/modified imports are not automatically linked.

## Durable boundaries and interfaces

- `GET/POST /api/jobs/{job}/adoptions/`: project inspection / developer proposal.
- `GET/POST /api/native-adoptions/{id}/`: inspection / reviewer approval or revocation.
- `POST /api/native-adoptions/{id}/protected-inputs/`: accepting reviewer custody.
- `POST /api/native-protected-inputs/{id}/preview/`: accepting reviewer preview.
- Existing dataset job admission accepts `native_protected_assessment_v1`, a request
  UUID, protected-input ID and the exact preview digest. Existing job read/cancel/
  receipt interfaces apply; protected jobs cannot become package review selections.

Proposals, decisions and custody records are additive migration-backed models.
Admission is idempotent; attempts use existing fencing, expiration, cancellation
and publication checks. Limits remain two active / 100 pending jobs, 120 seconds
of work, three attempts, a 180-second lease and one-hour request expiry. Scoring
uses chunks of 500 and the existing single-thread native model profile. Retries
do not erase label access or double-publish a result. Historical receipts describe
the authority at execution; current adoption metadata separately reports usability.
The initial list shows the latest 50 proposals; retained IDs remain inspectable.

## Qualification and remaining scope

Additive backend cases cover independent authority, stale/tampered evidence,
classification label reversal/regression, population constraints, malformed labels,
outcome reservation before parsing, replay, cancellation, late revocation, expired
leases, crash/recovery and controller separation. Frontend cases cover explicit
review/seal/preview/submit, context invalidation and exact uncertain retries. Two
real browser workflows use independent accounts and actual queued workers; one
loses an accepted upload response and retries it without duplicating custody.

The private PostgreSQL fixture additionally checks physical `bytea`, TLS,
real CSRF/session actions, prefork/dispatcher execution for both tasks, single
publication and coordinated restoration of sealed bytes, decisions, access records
and result digests. Original test inventories, assertions, workloads, retries,
resources and the native 900-second cap are preserved. Source qualification and
exact-head/main qualification are distinct evidence states in the roadmap ledger.

The RI-fixture controller retains its legacy 31-migration/152-trigger guard and
adds a strict 32-migration/164-trigger profile with an exact per-table inventory.
It runs all 797 original physical scenarios plus twelve additional foreign-key
trigger-role cases. Raw full-schema snapshots must restore exactly. Historical
verifiers consume an explicitly labeled legacy inventory projection only after
all 809 raw expectations and the expanded schema's restoration have verified.

Database operators remain trusted. This packet does not itself implement storage
encryption, new retention policy, immutable external audit storage or protection
against a privileged database administrator rewriting all data and hashes. Sealed
outcomes must follow the installation's database backup, retention, deletion,
authorization and encryption policies; hashes are integrity checks, not signatures.
Broader D06/D07 operational and coordinated recovery gates remain open.

Legacy synchronous training/SFS/broad HPO, larger workloads, multiclass native
execution, trial checkpoints, verified confirmatory protocols, expert Python,
production promotion and customer deployment/acceptance remain separate work.
