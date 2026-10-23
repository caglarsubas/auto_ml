# Durable native package checks (P22)

This is partial **D07/D12**. The first worker operation is `package_integrity_v1`: verify an exact, already published native package's manifest and artifact bytes without deserializing a model. It does not train, refit, assess final labels, reproduce scores, approve review, deploy or authorize production. Existing modeling/search/scoring routes remain unchanged. Expert Python remains blocked; this worker is not the D08 sandbox.

## Request, authority and receipts

Authenticated developer/reviewer sessions submit `POST /api/jobs/datasets/{file_id}/` with exactly `request_id`, `kind`, `bundle_id`, `manifest_sha256`. The displayed button is authorization for this bounded read-only check. Admission pins package/execution/assessment UUIDs, exact manifest SHA-256, current actor/project/binding/membership revisions, installed code/package versions, fixed budgets and one-hour expiry. Missing governance or disabled service fails closed. Small metadata is checked during admission; artifact hashing runs in the worker.

The database commits a request and attributable event before any broker publication. A matching request UUID replays its receipt; altered reuse conflicts. `GET` on the dataset lists 50 requests per page; `GET /api/jobs/{uuid}/` exposes current status, original specification and event/result receipts. Active developer/reviewer/admin project members may read. Only the submitting developer/reviewer may cancel with `POST {"action":"cancel"}`. Native HTTP project registry, real session/CSRF and final authority/output rechecks apply. There is no MCP or assistant job mutation or delegated/automatic mission authority in this packet.

Cancellation is idempotent. Queued work becomes cancelled immediately. Running work retains its slot as `cancel_requested` until the worker acknowledges or the lease expires; completed reads are not undone. Hashing and publication enforce request expiry; hashing checks authority, token, time and cancellation between 1 MiB chunks. Revocation blocks further work/publication; it cannot undo a previously completed chunk. Results and requests do not expose broker URLs, lease tokens, raw outcomes, serialized state or host paths. A protected event history survives account deletion through retained actor snapshots.

## Durable dispatch and fencing

Django metadata, not Celery result state, owns status and publication. A singleton PostgreSQL lock serializes queue admission, claim, cancellation, reconciliation and terminal publication. Membership/binding locks also protect publication against concurrent changes. SQLite is development compatibility only and uses a cross-process local file lock; the private profile continues to require PostgreSQL.

Budgets: at most **100 queued/active checks**, **2 active leases**, **256 artifacts / 1 GiB** per attempt, **120 seconds** of cooperative work, **3 attempts**, a **180-second lease** and **one-hour request expiry**. The dedicated worker uses prefork, 130-second soft and 150-second hard Celery limits, prefetch one, JSON-only messages, no remote control and no result backend. Its trusted broker receives only the recorded job UUID. These settings follow the [Celery configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html), [Redis transport](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html) and [broker security guidance](https://docs.celeryq.dev/en/stable/userguide/security.html). Native workers and the broker are trusted infrastructure; JSON is not hostile-code isolation.

`python backend/manage.py dispatch_jobs` is the independent outbox/reconciliation loop (five seconds); `--once` runs one bounded pass. Publish succeeds or the committed request remains queued. Requests not claimed within 30 seconds are republished; duplicate delivery is harmless because an atomic lease controls execution. Expired attempts are recorded and recomputed within their original budget, with a new fencing token. An old worker cannot publish after cancellation, lease expiry, requeue or completion. No partial result is adopted. Lost metadata access leaves uncertain work leased for reconciliation rather than inventing success. Terminal requests never automatically rerun.

The global bound is on active metadata leases; use external Linux memory/PID/CPU/process limits as well. Hard-timeout and clock/process behavior still require qualification on the supported private deployment. Exact publication fencing does not promise exactly-once task execution or instantaneous interruption of blocked I/O.

## Installation and visible workflow

The service is disabled unless the API, worker and dispatcher receive the same explicit `DECLARAI_JOB_BROKER_URL` (or `_FILE` secret source), an explicit Redis database URL. It never reuses `REDIS_URL` implicitly or falls back to in-process/eager dispatch. Private mode requires `rediss://`, an existing absolute non-symlink `DECLARAI_JOB_BROKER_CA_FILE`, required certificate verification and hostname checks. Invalid configuration stops startup without printing secrets. Broker credentials belong in external secret files/access-controlled deployment configuration.

[Optional development composition](../docker-compose.jobs.yml) starts a dedicated Redis broker with AOF, two worker processes and a separate dispatcher. Start/migrate the backend before launching worker/dispatcher; their entrypoint requires existing migrations. Both development entrypoints reject private mode. The composition has memory/CPU/PID limits and is **not production packaging**. The CI override enables only its disposable installation; the optional worker services do not alter existing development services by default.

Example development startup (set the private engine key through the existing secret handoff first):

```sh
export DECLARAI_JOB_BROKER_URL=redis://job-broker:6379/1
docker compose -f docker-compose.yml -f docker-compose.jobs.yml up -d --build backend job-broker
docker compose -f docker-compose.yml -f docker-compose.jobs.yml exec backend python backend/manage.py migrate --noinput
docker compose -f docker-compose.yml -f docker-compose.jobs.yml up -d --build job-worker job-dispatcher
```

The package-review workspace shows the selected package/digest and budget, an explicit queue action, job history, refresh/status, submitter cancellation and freshly authorized receipt downloads. A failed/ambiguous response retains the exact request for retry. Switching project/dataset clears local evidence and cancels obsolete browser requests; existing server jobs remain recorded. Refresh/history restores access to them. This packet includes keyboard workflows, not a complete accessibility qualification.

## Qualification and remaining scope

[Native process fixture](../scripts/qualify_native_jobs.py) refuses non-test installations. It uses synthetic, deliberately non-deserializable model bytes. It launches actual prefork Celery/Redis work against TLS PostgreSQL metadata, kills only its own active worker process group, injects lease expiry without shortening production budgets, restarts a fresh worker, checks stale publication/duplicate delivery, active cancellation and a real failed broker connection with retained-request recovery. It is an injected process/clock/connection fixture. [P23 private startup and recovery](PRIVATE_JOB_RUNTIME_IMPLEMENTATION.md) separately qualifies authenticated Redis TLS, actual broker removal/empty-broker recovery and a quiescent native-job database/artifact restore with natural lease expiry. Machine-loss and complete production recovery remain open. Real native package integrity is covered separately by HTTP tests and the browser workflow.

Qualification results and source hashes belong in the P22 evidence record and canonical ledger. Training/search/batch-score migration, durable assistant grants, complete private worker packaging and production recovery, artifact authenticity, retained data policies, expert isolation and release/customer gates remain open; P23 provides bounded private TLS/quiescent-restore evidence, not completion of D07. Runtime checks bind the listed native job modules and package versions, not every transitive dependency or an authenticated image digest. Hash receipts detect changes relative to the recorded package; they do not prove artifact authenticity or statistical/model validity.

## Metadata-only lease reconciliation (P133)

Lease reconciliation loads only job identity, state, revision, attempt count, lease token/deadline, next dispatch, request expiry, reason and finish time. Both expired-active and expired-queued queries retain row locks; Django saves these deferred instances using only their loaded metadata fields. Recovery does not fetch, interpret or rewrite specification, authority, actor snapshot, result, hashes or related-object identifiers. Payload validation remains at its existing execution boundary.

The queue lock, clock sampled after locking, cancellation precedence, exact terminal/requeue reasons, attempt limit, event revisions, atomic receipt/state rollback and oldest-first due-ID query with its 100-item limit are unchanged. This reduces unnecessary application-side payload materialization and updates; it does not establish a capacity benchmark, make database page reads payload-free, change scheduling limits or provide expert-code isolation.

Additive regression coverage inspects real SQL and ORM materialization in SQLite and PostgreSQL, including mapping, larger opaque and non-mapping historical payloads. It checks payload preservation, recovery/expiry/cancellation transitions, repeat reconciliation, untouched rows, rollback after a receipt insert and mixed-queue ordering. All existing test files, CI workloads, resources, retries, skips, coverage and the native 900-second limit remain unchanged. PR/main qualification belongs in the canonical ledger and P133 evidence; D07 release and customer recovery/upgrade gates remain open.

## Checkpoint refresh after authority validation (P134)

A successful worker checkpoint now refreshes the recorded state, lease token, lease deadline and request expiry after authority validation, then repeats the existing guards and monotonic work deadline check. A cancellation, requeue/token replacement, expiry or exhausted work budget observed across that validation boundary stops the checkpoint before it returns to the next worker operation. The initial guards retain their order, and authority/storage failures propagate through their existing handling.

The final query is nonlocking and loads only these guards plus job identity. Checkpoints write no job state or events; cancellation acknowledgement, uncertain storage recovery and terminal publication remain in the existing finish/reconciliation paths. Attempts, the 180-second lease, 120-second cooperative work budget, queue bounds and other runtime limits are unchanged. This is cooperative fencing, not atomic interruption or a kernel-I/O/authority-query deadline; cancellation or revocation can still occur after the last observation.

Additive tests use real primary/source project authority and database transitions, clock changes at validation and metadata-read return boundaries, initial-denial and authority/storage failure compatibility, and real claim/execute/finish receipts with downstream training instrumented. All existing tests and CI resources, workloads, retries, skips, coverage and the native 900-second cap remain unchanged. Qualification belongs in P134 evidence and the canonical ledger; D07, release and customer gates remain open.

### Claim attempt-budget enforcement (P135)

Every native delivery now enforces the existing three-attempt ceiling while holding the queue/job locks. A queued row at or above that ceiling closes as `failed` / `job_attempts_exhausted` before authority/runtime validation or worker work, without incrementing attempts or issuing a lease. This covers inconsistent/restored queued metadata that never passes through expired-lease reconciliation. Duplicate deliveries observe the terminal state and cannot append a second exhaustion receipt.

Existing nonqueued-state, capacity and request-expiry precedence remains. Queued requests below the ceiling still undergo the original authority/runtime checks and receive the original 180-second lease. The close and its event share the existing transaction: receipt storage failure rolls back the transition, and retained specification/result payloads are preserved. Reconciliation, retry counts, resource budgets, cancellation and publication rules are unchanged. This safeguard does not validate a customer restore or authorize automatic metadata repair.

P135 adds 32 regressions: all five native kinds at/above the ceiling, actual task delivery stopping before package work, duplicate receipts, eligible retry leases, existing guard precedence and storage-failure rollback. The exact additive test on the unchanged service reproduces 19 failures and 13 compatibility passes. Source/local qualification is recorded separately from PR/main, release and customer evidence.

### Incomplete-lease fencing (P136)

Native checkpoints and result publication require a non-null caller token, a matching stored token and a non-null live expiry. A missing token pair is not ownership. A missing expiry stops safely rather than raising `TypeError`. The same checkpoint guard applies after authority validation and the final metadata read.

A rejected checkpoint raises `JobStopped`; finish leaves the inconsistent row and its payloads/events unchanged, including when asked to acknowledge cancellation or publish a terminal failure. Existing operator guidance still requires investigating inconsistent active metadata with the installation owner. This safeguard does not repair metadata, replay work or qualify a customer restore. Valid leases, cancellation acknowledgement, authority checks, deadlines, reconciliation, attempts and resource limits retain their existing behavior.

P136 adds 34 cases covering initial/refreshed metadata reads, all terminal finish requests, cancellation, actual worker delivery after committed lease metadata loss, and valid publication/cancellation. The unchanged-service baseline reproduces 21 failures and 13 compatibility passes. Source/local qualification remains distinct from PR/main, release and customer acceptance evidence.

### Checkpoint payload isolation (P137)

Worker checkpoints load only job identity, state, lease token/deadline, request expiry, authority, specification and project/dataset identifiers. Stored outputs, output digests, actor snapshots and unrelated publication/dispatch history are excluded from the initial query. The final guard refresh remains unchanged. Checkpoints neither write state/events nor lazy-load those deferred payload fields.

Real primary/source authority checks still run. Scoring checkpoints intentionally fetch and verify the referenced training job's result: that evidence is an execution input, so its integrity check is retained. Protected-assessment validation also remains at its existing boundary. Cancellation, missing/stale leases, expiry, monotonic deadlines, claim, finish and reconciliation semantics are unchanged. This narrows application-side data materialization per checkpoint; it does not establish throughput or total-memory capacity, guarantee payload-free database page reads, or change cooperative fencing into atomic interruption.

P137 adds 25 regressions for exact SQL and ORM projections, no lazy fetch, large/non-mapping historical payloads, rejected guards, real binding-revision changes, referenced training-result tampering and actual worker cancellation with downstream training instrumented. All 25 fail on the exact unchanged service. All existing tests, workloads, resources, retries, skips, coverage and the native 900-second cap remain unchanged. Source/local evidence, PR/main checks, release qualification and customer acceptance remain separate.

### Deterministic dispatch order (P138)

Due native requests sort by creation timestamp and UUID before the existing 100-ID slice. Requests sharing a creation time therefore have a stable batch prefix, including after an expired lease is requeued or queued metadata is restored. Creation time remains the primary order; kind does not add scheduling priority.

Eligibility, expiry, cancellation, attempt limits, recovery transitions and receipts, broker failure/backoff, duplicate delivery and worker/publication fences are unchanged. A repeat selection without a transition writes nothing. This defines selection order, not worker start/completion order, starvation prevention, throughput, capacity or customer recovery qualification.

P138 adds 16 regressions: all five native kinds, tied batches of 2/50/100/103, repeated selection, recovered leases alongside unchanged future/expired/terminal filters, actual outbox publication and broker failure/backoff, and distinct-timestamp compatibility. The exact unchanged service reproduces 13 failures and three compatibility passes. All existing tests, workloads, resources, retries, skips, coverage and the native 900-second cap remain unchanged. PR/main evidence, D07 release and customer acceptance remain separate.

### Handoff history-counter validation (P139)

Operational handoff rejects a mismatch between the stored revision and actual event count before comparing sequence values. It then enumerates recorded events to verify contiguous revisions from one. An inconsistent counter no longer sizes a range/list allocation while the queue lock is held.

The event query is unchanged. This removes allocation driven solely by a counter; it does not impose a history cap, truncate valid historical evidence, bound actual event-query size, repair metadata, grant execution authority or establish capacity. Valid handoff fields/digests, `no-store` responses, stale/project-authority precedence, gap detection and read-only behavior remain unchanged.

P139 adds 27 cases. A module-local range tripwire safely intercepts the original allocation for inconsistent counters up to 2^31-1. Direct reads and real GET/HEAD routes reject invalid histories before outcome-history queries, returning structured uncached conflicts without exports. Stale/real-project denials keep precedence. Contiguous 0/1/8/32-event histories retain full receipts and repeatable digests, while matching counts cannot hide missing/gapped revisions. The exact unchanged source reproduces 13 failures and 14 compatibility passes. Existing tests, workloads, resources, retries, skips, coverage and the native 900-second cap remain unchanged. PR/main, release and customer qualification remain separate.

### Handoff access-summary aggregation (P140)

Operational handoff obtains started, failed, completed and unknown access-state counts in one database aggregate. It no longer materializes one state value per matching outcome-access record while holding the queue lock. Explicit `C` (PostgreSQL) / `BINARY` (development SQLite) collation preserves exact state-label comparisons. Any included unknown state still blocks export; valid counts, receipt fields and digests remain unchanged.

Dataset, exact job and protected-assessment scope filters remain. All started, failed and completed reservations still count as possible outcome access. State changes invalidate stale handoff digests; reads do not remove or repair access records, modify job/event state, or authorize recovery, review or production use. Event-history/result-integrity checks, real project authority and uncached GET/HEAD responses remain.

P140 adds 31 cases. A queryset tripwire rejects individual access-row materialization while real SQL aggregation and authority queries execute. Counts from zero through mixed larger histories, unknown labels, excluded scopes, GET/HEAD responses, earlier guards and changed access states are covered. The exact unchanged-source baseline reproduces 27 failures and four compatibility passes, with zero errors/skips. Returned access-summary cardinality is constant; database scan cost, actual event-query size, capacity and customer recovery/upgrade remain separate open gates. Existing tests, workloads, resources, retries, skips, coverage and the native 900-second cap remain unchanged. PR/main, release and customer qualification remain separate.

## Handoff database-read timeout (P141)

Operational handoff export now sets a transaction-local PostgreSQL `statement_timeout` before acquiring the queue lock. Each SQL statement is limited to five seconds or the caller's stricter nonzero setting. The existing lock-wait bound remains independent; training, search, scoring and recovery execution budgets do not change.

Successful nested calls restore the previous statement setting before the caller continues. Atomic rollback restores it on Python errors, database errors and cancellation. Query cancellation uses the existing safe `job_storage_unavailable` 503 response with `Cache-Control: no-store`; no partial receipt is exported. Full receipt digests, conservative access counts, authority rechecks, result-integrity and event-history guards remain. Development SQLite retains its file lock and transaction behavior.

Twenty-six additive regressions cover ordering and minimum limits, actual PostgreSQL settings, nested success/error/explicit rollback, server cancellation (`57014`) of a six-second query under the default five-second limit, GET/HEAD failures, earlier guards and repeatable receipts. The native PostgreSQL suite executes production-specific branches; SQLite checks development compatibility. Exact unchanged-source baselines reproduce four failures / 22 compatibility passes on SQLite and 12 failures / 14 compatibility passes on PostgreSQL, both with zero errors/skips. Existing tests and the 900-second native suite cap are unchanged.

This is a per-statement limit. It does not bound total request duration, Python processing, event-history size or overall installation capacity, and does not qualify customer recovery/restore. The separate local roadmap listener was restored as a loopback-only launchd service with verified automatic restart; that is local tracker operation, not a customer deployment qualification.
