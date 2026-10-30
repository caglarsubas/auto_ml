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

## Handoff metadata validation (P142)

Handoff export rejects unsupported exact job-state labels with `job_handoff_state_invalid` before reading events, and non-object event details with `job_event_history_invalid` before reading outcome-access history. Both use existing structured 409 responses and `Cache-Control: no-store` for GET/HEAD. No partial receipt is exported, and no history is repaired, normalized, truncated or given execution authority.

Object-shaped details retain existing reason values, including missing keys, JSON null, strings, booleans, numbers, arrays and objects. Full event sequences, receipt digests and conservative access counts remain. Authority, stale-revision and result-integrity checks retain precedence; scoped database timeouts and attributable HTTP access audits are preserved. These limited shape checks do not certify historical provenance or all specification fields.

Thirty-four additive cases cover malformed JSON detail types, unsupported state labels, actual GET/HEAD conflicts, guard precedence, valid receipts and corruption after a receipt was observed. Exact unchanged-source SQLite and PostgreSQL baselines each reproduce 18 failures and 16 compatibility passes, with zero errors/skips. All existing tests, scientific workloads, resource limits and the 900-second native suite cap remain unchanged.


## Handoff specification validation (P143)

Operational handoff export reads saved request metadata, including its kind and original attempt limit. Restored or malformed specifications previously caused unhandled exceptions or misleading exports after scanning history. Handoff now requires an object specification, one of the five supported native job kinds, object-shaped limits, and a positive integer attempt limit. Missing fields, booleans, numeric strings, fractional/nonpositive limits and unsupported kind values fail with `job_handoff_specification_invalid` before event or outcome-history reads. Existing GET/HEAD routes return a structured 409 with `Cache-Control: no-store`; HEAD remains bodyless and the native-access audit remains attributable.

Authority, result-integrity, observed-revision and supported-state guards retain precedence. Valid saved positive limits remain as recorded, including values different from current execution budgets. Full event histories, conservative possible-outcome-access counts, exact receipt digests, repeatable observations and scoped SQL timeouts remain unchanged. Invalid metadata cannot export an old receipt or erase possible accesses. The observation neither repairs records nor grants replay, recovery, review or production-use authority.

The 55 additive regressions cover 31 invalid specification variants, real GET/HEAD failure handling and audits, earlier guard precedence, all five supported kinds at two positive limits, and corruption after an earlier receipt. Exact unchanged-source SQLite and PostgreSQL baselines each reproduce 37 failures and 18 compatibility passes without errors or skips. Tests exercise actual database reads and HTTP handling; forced-authentication unit fixtures do not establish real sign-in. Existing private-profile CSRF/login and browser qualification remain separate CI requirements. All 332 inherited test/execution files, scientific workloads, resources, retries and the native 900-second cap are preserved.

This validates only fields needed by the operational receipt. It does not certify full request provenance, current runtime compatibility, correctness of optional identifiers, total request duration or capacity. Customer restore, upgrade/rollback, workload profiling and broader legacy migration remain D07 gates. See the canonical roadmap and the P143 source qualification for observed delivery status.


## Operator state comparisons (P144)

Operator queue diagnostics previously used the column collation for SQL state aggregates and incident selection, while Python row flags and offline evidence validation used exact labels. A case/accent-insensitive comparison profile could count a stored `FAILED` or `faíled` as canonical `failed`, select rows with inconsistent incident flags and displace valid jobs from the newest-first 50-row sample.

The probe now uses explicit PostgreSQL `C` collation for state and unknown aggregates and every state-dependent incident predicate. The expression uses `BINARY` when compiled for development SQLite compatibility; the operator entrypoint still requires PostgreSQL. Stored labels remain unchanged: noncanonical labels contribute to `unknown` and do not acquire known-state incident semantics. Supported labels retain their overlapping expiry/attempt/lease signals. Full installation scope, metadata-only projection, 50-row bound and ordering, totals/truncation, fixed output/evidence schema, read-only/repeatable-read transaction, five-second statement timeout and no-recovery-authority claims remain unchanged.

The 22 additive cases use a real temporary PostgreSQL ICU case/accent-insensitive state-column collation. Its behavior is asserted, and the original catalog identity and column type are restored after every case, including failures. Exact unchanged-source PostgreSQL reproduces 13 failures and nine compatibility passes, without errors or skips. SQLite passes all 22 compatibility cases; it does not simulate ICU behavior. Cases cover uppercase/accent variants, all seven supported states, canonical incident preservation under colliding labels and truncation, all-unknown observations, metadata privacy, no full model construction and offline queue-evidence consistency. All 333 inherited test/execution files remain byte-identical.

This corrects observation semantics. The probe does not change physical schema, normalize/repair labels, execute jobs, authorize recovery or assert current service health. The deliberately changed test profile is not approval of such a customer schema; installation schema checks remain independently required. SQL scan/index behavior, large-workload capacity and total command timing need separate qualification. Native suite resources, retries, scientific workloads and the 900-second cap remain unchanged. D07 customer restore and upgrade/rollback gates remain open.


## Operator read budgets (P145)

The operator snapshot requires standalone autocommit ownership. Existing Django atomic blocks and disabled-autocommit transaction contexts are refused with `operator_top_level_transaction_required` before observation SQL. The fixed CLI catches observation failures as safe unavailable metadata; this boundary prevents the probe from changing a caller transaction's isolation/read-only properties. The trusted Linux operator entrypoint and PostgreSQL requirement remain. The boundary follows Django connection state; manually manipulating driver transactions outside Django is unsupported and is not qualified here.

Within its owned read-only/repeatable-read transaction, the probe reads the effective PostgreSQL `statement_timeout` and applies the smaller positive limit and the existing 5000ms platform cap. An unlimited setting receives the 5000ms cap. A stricter database setting is never widened. Transaction-local configuration automatically restores the prior session settings on commit or rollback, including Python failures, database failures, timeout cancellation and refused writes. These are per-statement limits; the existing 20-second outer probe timeout and bounded output capture remain unchanged and do not constitute capacity qualification.

New snapshots use `native_queue_operator_snapshot_v2`. Its existing `statement_timeout_ms` field reports the actual effective positive integer in 1..5000. Fixed probe transport and offline queue-evidence validation accept versions 1 and 2, including safe unavailable receipts. Legacy v1 remains strictly 5000ms; malformed/future versions and invalid types/bounds are refused. Old evidence is retained as recorded. Consumers that understand only v1 require updating before consuming v2. The enclosing incident-evidence and handoff formats are unchanged; the nested snapshot carries its own version.

The 48 additive cases cover policy-derived limits across all metadata reads; actual PostgreSQL read-only/repeatable-read settings; restoration after success and Python/database failures; actual query cancellation and write refusal; refusal of clean/queried Django atomic and disabled-autocommit contexts before SQL; legacy/current evidence validation; and fixed probe transport/version handling. Exact unchanged-source SQLite and PostgreSQL each reproduce 20 failures and 28 compatibility passes, without errors or skips. SQLite models PostgreSQL control statements for compatibility and does not claim native enforcement.

All existing test functions, assertions, marks and parameters remain AST-identical. One inherited SQLite control adapter is expanded for the new PostgreSQL statements and transaction boundary; two production consumers intentionally change.331 of334 guarded inherited test/execution files remain byte-identical. Existing case/skip identities, schema, scientific workloads, two-worker isolation, resources, retries, coverage, native 900-second cap, exact state comparisons and metadata-only projection are preserved. Observation neither executes jobs nor grants recovery, review or production-use authority. Customer restore, upgrade/rollback and larger-workload gates remain open.

## Strict operator evidence JSON (P146)

Collection and offline verification use the same UTF-8 JSON decoder. It rejects duplicate members at any nesting level (including escaped spellings of the same key), non-standard NaN/Infinity constants, and numeric exponents that overflow to infinity. Collection checks its existing byte limit before decoding and accepts only the supported schema/status envelope. Malformed status values produce the existing sanitized `queue_incident_probe_output_invalid` error instead of an unhandled type error. A rejected observation cannot reach the collection command's export step.

Valid snapshot v1/v2 values, finite extension fields, ordinary JSON number semantics and canonical evidence hashes remain compatible. Transport still validates an envelope; the offline verifier remains responsible for the full snapshot shape, signal/count consistency and installation/digest pins. This does not authenticate evidence or make arbitrary extension fields trustworthy. The fixed UID/container command, 20-second timeout, bounded memory-only stdout, discarded stderr, unavailable-service/child-failure precedence and exclusive export are unchanged. Historical evidence is not rewritten.

P146 adds 43 cases using actual child processes and pipes, complete snapshots verified offline, malformed/ambiguous documents, pre-export refusal, byte-budget precedence and existing unavailable behavior. The exact unchanged source reproduces 22 failures and 21 compatibility passes. All inherited test files, scientific/schema workloads, CI resources, retries, skips, coverage and the native 900-second cap remain unchanged. D07 release, customer recovery/upgrade and expert-isolation gates remain open.

## Native claim specification shapes (P147)

A queued native delivery requires a JSON object specification with a string `kind`. Missing/non-string kinds and non-object roots close once as `blocked` / `job_specification_invalid` before execution-authority checks, runtime preparation, lease issuance or worker operations. Duplicate deliveries observe that terminal receipt; normal dispatch no longer selects it. Existing state/capacity, request-expiry and attempt-ceiling guards retain precedence. Unknown string kinds retain their existing authority check and `job_runtime_changed` behavior.

All terminal transitions made during claim update only state, reason, finish time, lease fields and revision, together with the existing atomic event receipt. Saved specifications, authorities, actor snapshots, results, hashes and attempt counts are preserved. This allows a stored JSON-null specification to be blocked without accidentally converting it to SQL NULL during a whole-model save. Receipt/storage failures roll back the transition; operational database failures are not reclassified as malformed input. Valid claims keep their real authority checks, original attempt accounting and 180-second lease. Other publication, checkpoint and reconciliation paths retain their existing behavior.

This guard validates the root/kind envelope, not every nested kind-specific request field or a complete restored installation. A blocked receipt authorizes neither repair nor replay. Customer recovery/restore, upgrades, workload profiling, broader migration and expert isolation remain separate gates.

P147 adds 37 cases covering malformed saved envelopes (including JSON null), real task delivery, repeat claims, dispatch exclusion, transition-only SQL, storage rollback, earlier guards and valid/denied claims. All inherited test files and guarded execution files remain byte-identical; scientific/schema workloads, resources, retries, coverage, skips and the native 900-second cap are unchanged. Qualification and current delivery state belong in the P147 evidence and canonical roadmap.

## Retained native receipts (P148)

Authorized receipt inspection handles non-object/missing-kind specifications and irregular saved results without treating them as valid scores or rewriting them. Valid score lists retain the existing 500-row preview and full-result digest. Score download requires a successful supported scoring kind, a matching digest, a result object and a score list; malformed kinds/results return the existing unavailable-result conflict. Project authorization, integrity checks, repeat authority checks and private GET/HEAD cache policy remain.

This makes preserved records inspectable after a blocked claim. It does not repair stored metadata, establish historical provenance, validate every nested score row, or authorize recovery/replay/model use. Existing native scoring parity and protected-outcome controls remain independently required.

The roadmap tracker now has versioned sources in [roadmap-tracker](roadmap-tracker/README.md). Status shares retain their real denominators: 15 planned of 26 outcomes is 57.7%; adding another tested delivery can leave the tested packet share at 100%. Delivery activity therefore displays cumulative test-qualified counts, the last-record increment and a bounded ledger-order history. Future total scope, effort and readiness are not inferred. The offline snapshot has an explicit reload control; generation remains a separate recorded step.

P148 adds receipt/HTTP/score-export regressions and pure status-math tests. Local isolated JavaScript checks cover the tracker renderer and control handlers without a browser or network. Browser rendering remains unqualified under the retained local URL-policy restriction; these source/logic checks are recorded separately. Original test files, workload/resource/skip/retry/coverage settings and the native 900-second cap remain unchanged. D07 release and customer gates stay open.

## Execution authority dataset binding (P149)

Native execution validates the relationship between saved authority and the job before kind-specific evidence checks. The primary snapshot must name the job's dataset/project and read operation. A source snapshot must name the source dataset in that project and the same actor as the primary snapshot. Dataset/actor identifiers require integer types, excluding booleans; project-wide or pipeline scopes cannot substitute for dataset authority. Fresh project authority/revision checks still run after these metadata guards.

Claim, checkpoint and publication use the same binding check. A current snapshot for a different resource cannot authorize this job. Invalid bindings stop checkpoints or create the existing blocked authority-change receipt without starting/adopting work. Publication's cancellation/expiry/budget/authority rejection paths write transition metadata only, preserving retained payloads including JSON-null authority. Successful publication and ordinary explicit terminal results retain their original behavior. Receipt failures roll back, storage failures propagate, and duplicate delivery cannot publish or append another denial.

The checkpoint still fetches only its existing authority/specification/identity/guard projection. No actor payload, result, new lazy fetch or authority query is added by binding validation. Earlier lease/cancellation/expiry guards and the original runtime, attempt and execution budgets remain. This consistency check does not authenticate historical metadata, repair a restore, introduce delegated authority or qualify customer recovery.

P149 adds regression coverage for genuine current scopes borrowed across datasets/projects, missing/malformed snapshots, mismatched source actors, strict identifier types, all native kinds, actual claim/checkpoint/publication behavior, field projection, rollback and valid/failed live authority. Original tests, schema/scientific workloads, resources, skips/retries/coverage and the native 900-second cap are unchanged. Roadmap/delivery counts update independently of outcome acceptance and release gates.


### Worker specification and reference safety (P150)

Worker checkpoints and publication now reject non-object saved specifications and missing/non-string kinds with `job_specification_invalid`. The existing claim guard retains its earlier position, so expired/exhausted/capacity/lease checks keep their original precedence. Unsupported string kinds retain live authority checks and block with `job_runtime_changed` at every execution boundary.

Training-result scoring and protected assessment validate their referenced UUID and SHA-256 syntax before ORM conversion or protected-evidence reads. A referenced training job with malformed saved kind metadata produces `job_training_result_changed`, rather than an unchecked dictionary access. Valid references still undergo the existing integrity, runtime, scientific, authority and protected-plan checks. This preflight is deliberately limited to shared shape and derived-reference safety; it does not replace each kind's full validation or authenticate restored historical metadata.

Publication checks the saved envelope before actor locking. Invalid metadata closes with one atomic blocked receipt through transition-only writes, preserving original specifications, opaque results and JSON-null payloads. Checkpoints keep their existing field projection, avoid unrelated actor/result payloads and do not publish events. Live database failures still propagate; no automatic data repair or recovery authority is introduced.

96 additive regression cases cover the new boundaries, valid references, unknown-kind authority checks, referenced-kind integrity failures and rollback/storage failures. Existing real protected-assessment, private deployment, recovery and restoration qualification remains required. The broader D07 and customer acceptance gates remain open.

### Cancellation authority and evidence safety (P151)

Cancellation requires a strict positive integer saved submitter matching the current caller, in addition to the existing developer/reviewer role and fresh dataset/project/source permissions. Malformed snapshots, missing principals and Boolean/float/string substitutions receive the existing `job_cancel_submitter_required` denial without mutation. This validates cancellation identity syntax; it does not authenticate historical records or grant broader cancellation rights.

Queued cancellation and running cancellation requests now save only `state`, `reason_code`, `finished_at` and `revision`. They preserve raw specifications, saved actor metadata, authority, results, digests, attempt counts and leases, including JSON-null retained payloads. Existing worker acknowledgement and slot/lease fencing remain unchanged. Cancellation remains available for invalid execution specifications when the submitter and current resource permissions are valid; it does not repair those specifications or authorize execution.

The response is serialized inside the transaction before the final live primary/source/actor permission checks. Revocation during serialization refuses private output and rolls back the cancellation and receipt. Terminal/repeated requests follow the same final authorization checks. Source/project/result-integrity denials and genuine database/storage failures retain their existing diagnostics and atomic rollback behavior.

74 additive service/HTTP cases cover identity shape/coercion, transition-only SQL, retained JSON-null/opaque evidence, late revocation, repeated/terminal behavior and storage/receipt failures. Existing real authentication/CSRF, native worker cancellation and private recovery qualification remains required. D07 and customer acceptance gates remain open.

### Submission and replay receipt authority (P152)

All native admission and replay paths now materialize receipts through one shared final authorization fence. Package integrity, CSV scoring, training/search, training-result scoring and protected assessment retain their early admission, role and idempotency checks, then recheck live primary/actor authority after serialization. Both scoring paths also recheck their captured source-dataset scope at that final boundary.

Receipt construction stays inside the existing queue transaction. Late revocation withholds private output and rolls back a newly created job and submission event. Replays keep the original job, result/digest, revision and history and do not repeat scientific preparation. Serialization and genuine permission-storage failures propagate and roll back; they are not converted into accepted or replayed receipts. Read and cancellation use the same helper while preserving their existing post-serialization check order.

This changes receipt exit authorization, not model execution, promotion rights, historical authenticity, metadata repair or recovery authority. Runtime/limits, protected-plan, input/result integrity and scientific checks remain required. 88 additive service/HTTP cases cover all five native kinds, new/replayed output, primary/actor/source revocation, valid status/idempotence and rollback/storage behavior. Only expensive preparation is stubbed in these boundary tests; existing real integration/private workflows remain unchanged. D07/customer acceptance gates remain open.


### Live runtime metadata parsing (P152 follow-up)

The initial P152 main qualification failed its unchanged 900-second PostgreSQL process limit. Its XML recorded all 6,018 tests passing with six unchanged skips in 897.298 seconds, but the process did not complete within the limit and the subsequent physical qualification did not run. That main run remains failed; its complete original log and report archive are retained separately from any repair qualification.

Native runtime declarations, scoring receipts and declared metrics repeatedly parsed the same installed package metadata. These three consumers now resolve the distribution on every call and read standard installed metadata afresh, then reuse only the standard library's parsed version for identical text. The cache is bounded to 64 entries; text above 256 Ki characters uses uncached parsing. Metadata fallback order, standard header semantics and lookup/read errors are preserved. Providers overriding the public distribution metadata/version properties retain their own behavior without parsing-cache reuse. A same-size change with preserved inode and timestamp still changes the returned version immediately.

The helper is included in the existing live source fingerprints for all three consumers. Runtime manifests, source bytes, permissions, scoring results and installed-state snapshots are not cached. The standalone portable native candidate reader retains its existing dependency and source checks. Existing compatibility checks continue to govern execution and replay.

Twenty-eight additional tests cover installed-version parity, legacy metadata locations, header semantics, changed metadata, failures after a cached parse, per-call lookup/read behavior, cache bounds and source-fingerprint freshness. The original receipt tests, scientific cases, workload sizes, two-worker isolation, CPU/native-thread budgets, coverage, skip/retry policies and 900-second limit remain unchanged. Source qualification and final PR/main evidence are recorded separately in the roadmap and the P152 performance repair evidence.


### Single-statement live dataset authority (P152 follow-up)

The metadata-only repair PR head also exceeded the unchanged 900-second native process cap; its final suite count was incomplete and it remained unmerged. Its failed log/archive is retained. The combined repair additionally reduces live dataset-scope lookup overhead: each check now reads the binding, active membership and active actor in one statement instead of two separately compiled ORM reads. Rechecks execute another statement; no authority data is cached.

The existing membership entrypoint remains responsible for dataset-bound resolution and retains its normal project-scoped path. A private dataset selector cannot be mixed with an explicit project scope. The joined query uses Django's routed model manager, table/column names quoted from model metadata, and bound actor/file parameters. It preserves missing-binding versus missing-membership denials, operation-specific roles, canonical revisions and current-project membership. The new source is already included in the existing runtime fingerprint for access_control/projects.py.

Seventy-five new cases compare role/active-state behavior with the existing policy, require one live statement per resolution/recheck, and exercise unknown/unbound resources, revocation, revision changes, cross-project memberships, changed bindings and conflicting scope selectors. The previous receipt and metadata tests remain byte-identical. Full local and automatic exact-head/push-main qualification remain separate gates under the original budgets.


### Final adoption receipt authority (P153)

Native adoption receipts retain their early live authority check before reading protected-input metadata and add a second check after the complete response is materialized. Proposal, independent approval, revocation, protected-input sealing and their replays all share this boundary, as do direct and HTTP detail/list reads. Late actor, membership or dataset-binding changes withhold private metadata. For write paths, denial occurs inside the existing transaction and rolls back the new proposal, event or sealed input.

Genuine materialization and final authority-storage failures also fail closed with atomic rollback; HTTP diagnostics exclude private SQL or evidence. Accepted-candidate usability, review independence, protected custody, historical digests, replay identity, early checks and scientific requirements remain unchanged. This does not grant execution, recovery or production promotion authority.

123 additive cases use actual trained candidates, independent review, sealed CSV custody, real queries and real transactions. The late hook observes a completed protected-metadata query without replacing its rows. Unchanged source produces 57 regression failures and 66 compatibility passes on SQLite and PostgreSQL; fixed-source qualification is recorded separately. The injected in-transaction revocation checks the receipt boundary and rollback, not the timing of an external concurrent commit. D07 and customer acceptance gates remain open.


### Live scope row materialization (P153 repair)

The initial P153 PR passed all six checks, but its independent main run exceeded the unchanged 900-second native process limit at 97% progress. It had no complete native report, and the standalone physical step did not run. That failed run is retained separately and does not qualify the merged revision.

Each dataset authority lookup now executes the same parameterized SELECT through the existing routed Django connection and converts the returned identifiers with their model fields. It avoids constructing a temporary ORM binding model. The membership entrypoint, active actor/member and role checks, missing-binding/access denials, canonical UUIDs, quoted model identifiers and bound actor/file values remain. Every recheck executes another statement; no permission data, source bytes or installed state is cached. The existing runtime fingerprint already includes this source.

Both profiled variants passed the same 379 real workflow cases and performed the same 33,658 authority resolutions. The cursor variant reduced authority-function profile time, but overall subset elapsed time increased from 176.624 to 208.468 seconds. An interleaved same-process PostgreSQL microbenchmark then measured median 500-lookup batches of 0.086643 seconds versus 0.066428 seconds, about 23% lower, while observing fresh membership revisions and identical scopes throughout. Those are diagnostic observations, not a whole-suite or production capacity promise. Full local, exact-head PR and independent main qualification remain required under the original budgets and inventories.


### Native qualification worker diagnostics (P153 follow-up)

Both initial P153 independent main runs exceeded the unchanged 900-second native process limit at 97% progress. Neither produced a complete native report; standalone physical qualification did not run. The successful prior PR checks do not qualify those failed main runs. Both are retained separately. The scope lookup microbenchmark did not establish an end-to-end timeout fix.

The existing PostgreSQL qualification helper now registers an observer on its two workers. Each retains one bounded atomic snapshot beside the isolation report: static case prefix, full-node-ID hash, active phase inferred from completed reports, start/finish counters, observation time, elapsed time at that snapshot and session exit state. Parameter values, report bodies, exceptions and local variables are excluded. Session shutdown never implies that an unfinished case completed. Absolute destinations and captured operation references keep fault-injected artifact functions and clocks from disabling the observer. Write failures are marked and warned once, without replacing test outcomes. Snapshots can remain available when JUnit cannot be completed.

Original test-case files, fixtures, worker/cache/database isolation, scheduling, budgets, coverage, skip/retry rules and the 900-second limit remain unchanged. The only previously guarded execution-support change registers diagnostics. Thirty-seven additive cases cover state transitions, bounded/redacted output, independent workers, interrupted exit states, atomic/short/failed writes, fault and working-directory isolation, and a real owned child killed during a case. Complete qualification must reconcile both finished worker snapshots with every JUnit case; failed runs retain their last known states without claiming completeness. These test-only diagnostics confer no model execution, installation, recovery or production-use authority.


### Native execution cost (P153 repair)

Diagnostics PR #247 passed all six exact-head checks, but its independent main run also reached the unchanged 900-second cap. Worker snapshots account for 5,958 of 6,287 cases before interruption; neither worker was observed in a long active case at its last snapshot. Both stopped during teardown and recorded interrupted session exits. There is no complete native JUnit report or standalone physical qualification. This third failed main remains retained and unqualified.

Three bounded changes address measured execution costs. Candidate export reuses the existing installed-metadata reader: every lookup resolves and reads current metadata; only parsing identical bounded text is cached. Portable scoring retains its independent standard-library version lookup. Probability-only objectives no longer evaluate an unrelated confusion matrix or threshold predictions. Complete reference metrics, metric formulas, undefined-partition behavior and business costs remain unchanged. Checkpoints read their same fixed projections with parameterized SQL through the routed Django model reader, preserving model conversion/fault boundaries, missing/duplicate identifier failures, both fresh guard reads and all authority checks. No permission, installed-state, job-state or source-byte snapshot is cached.

The same 379 workflow cases pass in all three diagnostic profiles. Observed elapsed times were 189.232 seconds at baseline, 178.480 with export/metric changes, and 174.297 with checkpoint projection reuse. These subset observations do not establish full-suite or production capacity. Existing payload and refresh guard tests also pass against the prototype. Forty-eight additive cases cover selected/full metric parity across thresholds and populations, independence from unrelated threshold calculations, and fresh export metadata/version-drift/read-failure behavior with real trained candidates. Full local, exact-head PR and independent main qualification remain required under the original inventories, resources, coverage and 900-second cap.


### Versioned binary ROC-AUC callback (P153 follow-up)

PR #248's first head passed its other five checks but exceeded the unchanged 900-second native cap after 6,278 of 6,335 cases completed. No complete native XML or standalone physical qualification exists; the raw artifacts, logs and worker snapshots remain sealed and unqualified. The PR stays open until a revised head passes every check.

Selected binary ROC-AUC now uses average ranks and the Mann–Whitney statistic, giving tied positive/negative pairs half credit. The metric specification records `binary_rank_auc_v1`, its exact-rank bound of 2^26 rows, and the sklearn ROC-integration fallback for larger partitions. This bound protects float64 half-rank and rank-sum arithmetic; it is not an installation-capacity promise or a statistical acceptance threshold. Every observation remains included. Full assessment retains independent sklearn ROC integration. Input validation, undefined-class handling, unweighted validation semantics and positive-class meaning remain. The implementation and method evidence change, so existing fit specifications cannot silently inherit the new calculation version.

Seventy-seven additive cases compare both methods across sizes, float32/float64 inputs, ties, permutations, constant/reversed probabilities, subnormal and near-one values, positive-label reversal, unavailable/invalid populations and the numerical-bound fallback. The complete prototype passes 304 focused cases, including all existing native metric-adapter and checkpoint payload/refresh guards. The same 379 diagnostic workflows pass in 164.937 seconds; observed metric CPU is 13.190 seconds versus 25.834 seconds before the rank callback. These subset observations do not qualify the full suite or promise capacity. The unchanged-source AUC baseline has two expected method/reference-path regressions and 75 compatibility passes, with no errors/skips. Full local and fresh exact-head PR/main qualification remain required under unchanged workloads, resource/thread budgets, coverage, skip/retry rules and the 900-second limit.

## Protected preview authority (P154)

The shared protected-assessment preview service rechecks live reviewer authority after constructing the entire response, including runtime metadata, the exact plan digest and sealed-input metadata. Its early checks remain. Revoked actors, changed membership or dataset-binding revisions, and an unavailable authority store cannot return a successful protected preview. Existing HTTP middleware already provided a final check; the service boundary now protects direct consumers too. This is a final observation fence, not a lock preventing later revocation.

The unchanged-source regression fixture demonstrates eight direct-service failures and ten compatibility passes. Eighteen cases exercise revocation and authority-store failure after actual runtime or digest materialization through service and HTTP entrypoints, plus deterministic valid previews. They use real training, review and sealing fixtures, and assert no job, adoption, event, sealed input or holdout-access mutation. No model execution, holdout access, permission, approval semantics or preview payload changes are introduced.

The tracker separately shows outcome and delivery done/open/blocked distributions, with signed count and percentage-point changes from a named commit-pinned baseline. An explicit reason is required to record a blocker. P154 remains open until independent merged-main qualification; source, tests, release and customer acceptance are separate states. See [P154 qualification](evidence/p154-qualification-2026-10-26.json). Fresh local browser rendering remains unverified under the retained browser policy; isolated JavaScript checks do not establish visual behavior.

The first P154 exact-head CI (40266040111, head b1113c9531c34cb62ba79c72017f44254d2d0fa8) failed the unchanged 900-second native process cap after 6,326 of 6,454 cases completed. The other five checks passed. Its raw artifacts, logs and worker snapshots are sealed and unqualified; there is no complete native JUnit or standalone physical qualification for that run.

The follow-up defers confusion-matrix construction for selected multiclass objectives. All probability/label validation, normalization and selected scalar formulas remain; complete assessment keeps the confusion matrix and independent sklearn ROC integration. Twenty-four additive cases check independent reference parity, missing classes, unused-diagnostic failures, complete assessment and malformed inputs. Unchanged source reproduces four failures and twenty compatibility passes. Existing numerical tests and all budgets remain unchanged.

The same 379-case diagnostic profile passes at baseline 169.890s and metric prototype 186.398s. Multiclass evaluator CPU falls from 9.419s to 8.003s, but the whole diagnostic run does not improve; neither profile qualifies the full-suite timeout repair or capacity. An input-matrix threading prototype (197.71s) was not adopted. New automatic exact-head CI and independent merged-main qualification are required for the follow-up.

## Scoring preview authority (P155)

Native scoring previews retain a primary dataset authority snapshot from before preparation and recheck it, together with the accepted input-dataset scope, after complete JSON parsing, plan-digest calculation and response materialization. Existing preparation checks remain. A late actor/membership/binding change or authority-store failure withholds the preview through both service and HTTP entrypoints. This is a final observation fence, not a lock preventing subsequent revocation.

The unchanged-source fixture reproduces 16 failures: twelve direct-service failures and four HTTP failures involving the scoring-input scope. Ten compatibility cases pass. Twenty-six additive cases use real trained candidates and feature-only input CSVs, cover both materialization boundaries and both dataset scopes, and verify deterministic valid plans/payloads with unchanged job, event, adoption, protected-input, holdout-access and source-file state. No execution, review, adoption or production-use authority is added; scoring and approved plan semantics remain unchanged. See the [P155 local qualification record](evidence/p155-qualification-2026-10-26.json); later PR and independent main qualification remain separate receipts in the roadmap.

The initial P155 PR (#250, exact-head CI 40282725682) passed all six checks and merged, but independent main CI 40286279261 exceeded the unchanged 900-second native process cap after 6,372 of 6,504 cases completed. Its other five checks passed. Raw failure artifacts and worker snapshots remain sealed and unqualified; there is no complete native JUnit or standalone physical qualification for that run.

The follow-up reads the two fixed checkpoint projections through fresh parameterized cursors, avoiding generic raw-queryset setup. It applies the same backend and field converters before invoking `NativeJob.from_db` in concrete-field order. Both fresh guard reads, all authority checks, referenced training-result verification, model conversion/fault hooks, missing/duplicate failures and no-output-payload boundary remain. Missing primary keys and contradictory row lengths fail closed. No persisted state or authority is cached.

Twenty-two added cases compare field values/types and deferred state with independent ORM reads, and cover committed updates, missing rows, conversion/model/storage failures, primary-key requirements and contradictory rows. All original guards and assertions remain. The same 379-case diagnostic workload passes at baseline 195.833s and prototype 201.770s; it does not show end-to-end improvement. Row-reader CPU is 13.018s versus 8.903s and checkpoint CPU 21.596s versus 18.143s. These observations are separate from fresh full-suite and independent main qualification; they are not capacity guarantees.

Follow-up PR #251's first exact-head run, 40302779885, also exceeded the unchanged 900-second native cap, after 6,017 of 6,526 cases completed. Its other five checks passed. This failure remains separately sealed and unqualified, without complete native XML or standalone physical qualification.

The revised source shares full binary summary calculations after existing validation for one-dimensional numeric 0/1 labels. It retains independent public ROC and confusion-matrix checks, reuses the resulting counts for threshold summaries, and computes finite binary probability errors directly. That revision left selected-objective calculations, multiclass/regression behavior and noncanonical-label fallback paths unchanged. Nothing is cached across calls. Eight added reference cases exercise 720 combinations of label types, populations, ties, boundary probabilities and thresholds, plus changed inputs/costs and column-label fallback. They agree with independent public metric APIs within `1e-15`. An earlier unadopted prototype failed 17 original guards despite matching numerical outputs; those guards remain unchanged. The guarded prototype passes 349 focused cases and the original 6,526-case diagnostic inventory with six original skips. Baseline 387.518s versus guarded 401.598s does not demonstrate end-to-end improvement; the sampled development-metric stack share changes from 13.36% to 6.72%. Fresh full local, exact-head CI and independent main qualification remain required. No test, resource/thread, scheduling, coverage, skip/retry or timeout relaxation is adopted.

Later exact-head CI 40324898156 reached 6,449 of 6,534 cases before the same cap; five other checks passed. That raw failure remains sealed and unqualified. The added reference matrix now reports 38 cases by population/type and computes threshold-independent public probability references once per input group. A data-only matrix comparison verifies identical values, dtypes, shapes, costs, thresholds and assertion nodes for all 720 combinations. Every candidate comparison remains, while identical probability-reference groups reduce from 720 to 180. This diagnostic does not replace independent numeric checks or full qualification. Original test files, model workloads, worker/file-group scheduling policy, resources, threads, coverage, skips, retries and the 900-second limit remain unchanged.

Exact-head CI 40340619353 reached 6,487 of 6,564 cases before that cap, with five other checks green. The failure stays sealed and unqualified. Qualification workers now emit separate bounded CPU diagnostics alongside their original progress records. A 25Hz process-CPU timer samples static main-thread code locations; periodic atomic snapshots record CPU/wall time and explicit truncation/unavailability. This is approximate operational evidence, separate from model or capacity qualification. No arguments, locals, parameters or source text are serialized, no threads are added, and preexisting timers/handlers are respected. Code labels use bounded weak identity references, avoiding equal-code aliasing and retention of generated code/constants. Original progress schema, case outcomes and all test workloads/limits remain; one attributed qualification-support update leaves 352 of 353 guarded files byte-identical, with every original test-case file unchanged. Twenty-five additive cases cover privacy, bounds, timer ownership/restoration, output faults, independent captured operations and a real killed sampler retaining partial evidence.

The diagnostic head (CI 40357220943) reached 6,385 of 6,589 cases before the unchanged 900-second cap; its five other checks passed. Both partial CPU records were retained, but their interrupted exits do not qualify the suite. Samples show work across model evaluation and database fixtures; they do not establish a single hung case or a capacity limit.

The revised selected binary stopping path calculates seven unweighted losses/count metrics directly after validating the existing row alignment, shape, class mapping and finite/range boundaries. Numeric 0/1 membership and two-class availability use boolean masks rather than repeated generic uniqueness work. Full summaries keep independent public ROC and confusion checks. Empty and noncanonical inputs retain their public fallback, and multiclass/regression behavior remains. No values or input state persist between calls. Implementation fingerprints change with the source. Ninety-nine additive cases check independent public metric parity within `1e-15`, populations and label dtypes, ties and probability boundaries, single-class conventions, mutated labels/predictions/costs/thresholds, read-only strided arrays, column-label fallback, and invalid/missing/nonfinite data. All original tests and the 900-second cap remain.

The selected-metric head (CI 40365850271) reported all 6,688 cases and both worker session statuses zero, but exceeded the unchanged 900-second process cap before final native XML was produced. This narrows the remaining gap to the finishing/shutdown window; it does not qualify the suite. The other five checks passed, and the raw failure remains sealed.

Complete binary assessment now reuses the established threshold-table count formulas for six scalar statistics. Public ROC/AP, clipped log loss, Brier error and the final independent confusion-matrix check remain. Multiclass F1 aliases share one public result; regression MSE/RMSE share one raw public result while preserving extended-precision square-root ordering. Reuse is confined to one call and never carries state between assessments. Forty-nine additive cases check independent public references, diagnostic curves, invalid and column-label fallbacks, one public alias calculation and changed inputs. Separate complete-report comparisons cover 64 binary, three multiclass and three regression cases within `1e-14`, including curves, tables and calibration. The same 80 binary calls use baseline CPU 0.339–0.369s versus revised 0.154–0.158s over three alternating rounds. These diagnostics do not qualify full-suite timing or production capacity.

Complete-assessment CI 40375041137 stopped at 6,237 of 6,737 cases under the unchanged 900-second cap; its other five checks passed. That failure stays sealed and unqualified. A full-inventory local profile completed all cases in about 479 seconds, with profiling overhead. Matching CI's NumPy/coverage versions measured 356.256s versus 351.175s; passive OpenMP waiting measured about 379s. Both preserve the original inventory, and neither configuration is adopted as a timeout fix.

Qualification workers now retain bounded per-case JSONL costs beside the existing progress/CPU snapshots. They record static case names and full-node-ID hashes, phase outcomes/durations, whole-case wall time, and worker-process CPU (including its threads, excluding child processes). Arguments, parameter values, reports, exceptions, locals and source text are excluded. The original progress schema/counters remain; no execution, workload, resource/thread allocation, coverage, skip/retry or timeout rule changes. The journal retains at most 10,000 cases per worker with 2,048-byte records; limits and incomplete cases are explicit and do not stop tests. A preexisting journal is preserved rather than overwritten.

Forty-nine additive cases cover privacy, real killed-process retention, bounds, short/failed writes, captured operations, independent workers and strict metadata parsing. The reader refuses stale, malformed, inconsistent or incomplete evidence for qualification; partial mode reports interruption/truncation without claiming success. Inspect a retained failed run with `cd backend && python -m tests.native_case_costs /absolute/path/cost-gw0.jsonl --partial`. This reads test metadata only and grants no model, installation, repair or production-use authority. Fresh PR and independent main qualification remain required.


### Compact immutable metadata encoding (P155 follow-up)

The per-case diagnostic head completed 6,660 of 6,786 cases before the unchanged 900-second cap. Its failure and partial worker journals are retained separately and remain unqualified; five other checks passed. A matched-case report compares those 6,660 completed identities without estimating the remaining 126 cases.

New execution status, assessment/model-card and associated manifest JSON now use compact standard encoding instead of an indented Python generator. Consumers receive the same decoded values, including escapes, numeric types and assessment default conversions. Nonfinite and cyclic inputs still fail; exclusive creation and exact raw-byte hashes/sizes remain. Existing indented artifacts remain readable and are never reformatted. Native runtime manifests bind the metadata writer source, invalidating incompatible prior runtime evidence. No data, authority, source-byte or installed-state cache is added.

Twenty-four additive cases exercise round trips, invalid/cyclic values, collisions, existing indented inputs, raw-byte whitespace tampering, assessment parent preservation and runtime binding. A covered 77-case diagnostic observed 38 artifact writes with identical decoded values: CPU 0.218052s for indented streaming versus 0.004675s for compact encoding. Encoding stages a compact JSON string in memory; existing native output/process limits remain, and larger-workload memory/capacity profiling stays open. These measurements are diagnostic, not full-suite qualification. The original workload, assertions, scheduling, resources/threads, coverage, skips/retries and 900-second limit remain. Full local and fresh automatic exact-head/main qualification are pending.


## Training preview authority (P156)

Training/search preview captures the initially accepted project/dataset scope before preparation and rechecks it after the entire response, including the plan digest, has been constructed. Existing preparation and HTTP authorization remain. Late actor deactivation, membership or dataset-binding revisions, and authority storage failures cannot return preview evidence through the service. HTTP denials continue to withhold private diagnostics.

Eighteen cases use real declaration inputs, SQL state, service and authenticated HTTP entrypoints. Before the fix, eight service cases fail; ten compatibility cases pass, including existing HTTP defenses. The checks cover both the prepared-plan and final-digest boundaries, verify unchanged plan semantics on success, and preserve source bytes, jobs/events, adoption state and protected-outcome access. Runtime fingerprints bind the changed source; historical evidence is not upgraded implicitly. Full qualification and subsequent PR/main evidence are tracked in the roadmap ledger.


<a id="csv-input-authority-p157"></a>

### Complete CSV input authority (P157)

P157 retains the accepted CSV input authority through fingerprinting and complete byte/receipt construction, then rechecks it before returning any input or receipt. Existing path/descriptor, input-size, expected-fingerprint and early authority checks remain. Fifteen real-input cases reproduce eight service-level failures before the fix, with seven compatibility passes (the HTTP boundary already denied late changes). Actor deactivation, membership/binding revisions and authority outages withhold input evidence; private SQL remains private. Source bytes, jobs/events, adoption and protected-outcome records remain unchanged.

The read helper materializes the complete return tuple and rechecks its original authority before releasing it. The HTTP boundary retains its own check. Existing descriptor pinning, bounded reads, expected-input comparisons and read-only behavior remain. This changes no queue, worker, scorer, adoption or protected-assessment semantics.

The new regression file covers the byte reader, service preview and authenticated input API. Real hashing runs before actor deactivation or membership/dataset-binding revision; an injected authority outage withholds success and private SQL diagnostics. Authorized repeated calls preserve exact bytes, receipt fields, budget and authority. Local and automatic PR/main qualification are tracked separately in the roadmap. Broader D07 customer recovery/restore, upgrade/rollback, workload sizing and legacy training/search migration remain open.

The first P157 automatic PR run (40478475844) timed out at the unchanged 900-second native-suite cap after 6,703 completed cases; all 15 new authority cases passed and five other jobs passed. Shared completed cases used more wall and CPU time than the previous qualified run; causation was not established. The failure records are retained and sealed. A genuine correction adds call-local MSE/RMSE/MAE arithmetic for already-validated numeric regression vectors. Existing row, dimensionality and finite checks remain; full assessments, R2 and noncanonical labels retain public implementations. Forty-two additional cases check independent public results, invalid/empty inputs, dtype and shape fallbacks, mutation and read-only inputs. The isolated benchmark compares both implementations on identical inputs and budgets; it does not qualify end-to-end CI capacity. No CI rerun or test, workload, thread, coverage, skip or 900-second-limit change is made.

The second source head (CI40486898722) also reached the unchanged native cap, after 6,847/6,885 completed cases. The current correction uses native array prediction only for exact native XGBoost CPU gbtree models with dense, native float32/float64 DataFrames, after feature alignment and fresh model-name/type/configuration checks. Other dtypes, categories, empty inputs, unnamed/tampered metadata, DART/linear boosters and device profiles retain the previous DMatrix path. Native errors are not masked by retries. Thirty-nine new cases compare bitwise scores to the DMatrix reference, saved replay, selected iteration zero, reordered columns, row chunks, missing values and representable values around split thresholds. The native array probe is diagnostic evidence; full automatic CI and independent main gates remain required.

A pre-publication compatibility probe found that native inplace prediction accepts infinity and float32 overflow where DMatrix rejects them. The final path explicitly routes such ranges to DMatrix; three additional cases preserve those failures. NaNs remain supported missing values.

## History read bounds (P158)

Native keyset history now applies a PostgreSQL statement timeout of at most five seconds to counts, signals, page and cursor queries and final authority checks. A stricter caller timeout is retained. A transaction/savepoint scopes the setting: successful nested calls restore the exact caller value, and errors or cancellation roll back the local setting before the connection is reused. SQLite retains its existing query behavior.

History does not acquire the execution queue lock or change jobs, events, protected input or outcome-access records. Authorization still precedes job storage; final authority rechecks, cursor binding and expiry, 50-row pages, filters and observational queue signals are unchanged. Query cancellation returns the existing uncached `job_storage_unavailable` HTTP 503 without partial evidence or driver diagnostics; HEAD returns no body. This per-statement limit is separate from the unchanged 900-second qualification-suite cap and does not guarantee total endpoint latency or installation capacity.

Twenty-one additive tests cover real PostgreSQL limits/cancellation, stricter settings, nested success/error/rollback, connection reuse, GET/HEAD failures, metadata preservation and authority/parameter precedence. The initial twenty-case regression run retained seven failures and thirteen compatibility passes against original source. All original test files and workload settings remain unchanged. D07 customer restore/recovery, upgrade/rollback, larger workloads and broader legacy training/search remain open. See the packet qualification record for local evidence; PR and independent main CI are qualified separately.

## Job list read bounds (P159)

The native directory used by candidate/adoption screens now shares the existing keyset-history PostgreSQL statement ceiling: at most five seconds, retaining any stricter caller setting. Count and offset-page queries, metadata construction and final authority checks complete inside the scoped transaction. Success restores the caller setting; failures and cancellation roll back the savepoint. Initial authorization and offset validation still precede the bound and job-storage queries.

The endpoint keeps its metadata-only 50-row pages, ordering, total/next-offset response and mandatory project-access audit events. It acquires no execution queue lock and does not modify jobs, job events, protected input or outcome-access records. A cancelled count or page query returns the existing uncached HTTP503 without partial results or driver diagnostics; HEAD has no body. The shared bound itself is unchanged. This per-statement product bound is separate from the unchanged900-second suite cap and does not promise total endpoint latency or installation capacity.

Fifteen additive cases cover effective/default limits, actual PostgreSQL cancellation, caller/connection restoration, nested reads, private GET/HEAD failures and guard precedence. Existing pagination and history cases remain unchanged. Local, exact-head PR, merged-main, release and customer acceptance are separate qualification states; see the packet record and ledger for current evidence.

P159 also removes repeated evidence-generation work identified after the first source head exceeded the unchanged900-second native CI process cap. Full binary CV summaries retain public ROC-AUC, ROC/PR curves and confusion checks. Average precision uses the unweighted decreasing-recall step sum from the public PR curve; ROC integration remains independent. A single CV invocation can reuse its completed fold curves only when owned readonly input snapshots match labels, probabilities, dtype and row order. Changed or incomplete evidence falls back to public recomputation. Selected metrics, noncanonical inputs, multiclass and regression preserve their existing paths. No authority, source approval or model state is cached across calls.

New initial/candidate and legacy lineage writes use compact JSON. Decoded fields/default conversions, exclusive initial-run writes, historical readability and raw-byte artifact hashes are preserved. Existing artifacts are never rewritten as a migration. Three additional lineage and34curve cases bring P159 to52new cases. The failed workflow evidence remains unqualified and retained; genuine new source requires fresh local and automatic exact-head/main qualification. Microbenchmarks describe only their measured calculation and establish no end-to-end capacity promise.

The follow-up to PR255 retains its52published cases and adds44cases after independent main CI exceeded the unchanged900-second process cap. It reduces selected-metric work through exact tie-group U statistics (half credit for ties and the existing binary row ceiling), validated multiclass accuracy/log-loss/weighted-F1 formulas, and per-call sorted float64 threshold counts. Full multiclass assessment retains public metric/confusion implementations. Full binary assessment retains public ROC-AUC, AP and confusion checks, reuses successful ROC evidence for KS/Gini/curves, and uses validated count/loss formulas with the original clipping convention. Unsupported, nonfinite and legacy shapes/types retain their fallbacks. No model training budget or validation partition changes.

The standalone calculation helper is included in both metric implementation and native runtime source fingerprints. Changing its bytes invalidates dependent approvals through existing comparisons. No package, source or authority snapshot is cached. The original PR success and failed independent-main evidence remain separate; the follow-up requires fresh full local, exact-head PR and independent push-main qualification.

Native qualification now installs the repository's unchanged private-runtime dependency lock plus a pinned test-only execnet/xdist overlay and checks every active version, conditional platform marker and lock digest before running. Its cache keys use these files. The separate serial backend job retains latest permitted dependencies. This is an explicit correction of host/deployment dependency drift; cases, assertions, workload, scheduling, resources/threads, coverage, skips/retries and the900-second limit remain unchanged. Eighteen additional tests cover exact pins, platform markers, duplicates, drift after success and unavailable metadata. Qualification receipts identify the new native environment; historical failed runs remain retained.


## Adoption list and detail read bounds (P160)

Native adoption list and detail GET/HEAD handlers use the existing scoped history SQL bound. PostgreSQL record materialization, evidence metadata and final authority rechecks have a five-second statement ceiling, or preserve a stricter caller limit. Settings restore after success, cancellation and nested requests. SQLite retains the shared transactional path. This is a statement limit, not an overall request or capacity guarantee.

HTTP authorization precedes the bound; mandatory project access audit events remain outside it. Existing receipt/source validation, private no-store errors, list ordering and 50-row limit stay unchanged. Reads do not acquire the execution queue lock or fetch protected outcome payloads. Reference lookup cancellation retains its authority-unavailable diagnostic; later metadata/configuration failures retain storage-unavailable responses.

Twenty-six additive cases exercise both routes, default and caller limits, nested/repeated reads, real PostgreSQL cancellation, GET/HEAD privacy, authorization precedence, audit persistence, connection reuse and immutable evidence. CI/dependency/workload/coverage/resource/retry/skip controls and the 900-second full native cap remain unchanged. D07 release and customer recovery/upgrade acceptance remain open.

The first P160 head reached the unchanged 900-second native suite cap without final XML. All 26 adoption cases completed, but the workflow remains unqualified. Its raw evidence and earlier passing local run are retained separately. The follow-up source preserves those published cases and adds 32 calculation regressions: exact tie-group AUC avoids repeated index-trick dispatch; small selected many-class AUC uses average-rank matrices capped at 4,096 rows, 256 classes and 262,144 cells; native float64 threshold queries share two vector searches. Larger matrices and other scalar types keep their prior paths. Independent public full-assessment checks, source fingerprints, dependencies and every test/coverage/worker/resource/retry/skip/900-second control remain. Paired CPU microbenchmarks do not establish end-to-end capacity.

The second head also exceeded the same cap without final XML; it remains a sealed failed attempt. A further source correction accelerates fresh native metadata decoding using the optional `pydantic-core` parser already present in the unchanged locked image. Native JSON fields retain the base JSONField storage and migration declaration. Only whole string inputs up to 1,048,576 characters with stock decoder and integer-limit settings take the compiled path, with string caching disabled. Malformed, nonstandard, unsupported, custom-decoder and unavailable-extension cases retain Django/stdlib values and errors. Unexpected failures propagate. No row values, authority or approvals are cached; runtime receipts bind the helper source and freshly obtained parser version.

Freshly created submission receipts update only revision. Claim, finish and reconciliation writes name their transition fields instead of rewriting immutable request metadata. Generic `record()` behavior remains unchanged: existing tests rejected an overbroad shortcut, whose evidence is retained. Sixty-six additive metadata cases cover exact numeric/Unicode/error semantics, parser customization, fresh reads/provenance, SQL column sets, immutable inputs and unchanged migration state. Together P160 adds 124 cases; all original and previously published cases remain byte-identical. Both failed CI attempts remain distinct from subsequent qualification. No dependencies, schema, tests, workloads, resource limits, retries, skips, coverage requirements or 900-second cap were weakened.

The merged first PR passed its exact-head qualification, but independent main again exceeded 900 seconds without a final report. Its failure and successful prior-source evidence remain distinct. A corrective revision reduces repeated selected-metric multiclass label mapping work: native numeric arrays use fresh range/integrality checks within an exactly representable contiguous class domain; unsupported dtypes, byte order and class counts keep general NumPy membership. Selected ROC availability uses class counts after validated integer conversion. Complete assessments retain their public membership/ROC/confusion checks. No label, prediction, authority or result state survives a call. Sixty-two additional cases cover independent metric parity, malformed/fractional/unknown labels, missing classes, unusual-profile fallback and fresh input changes. Existing published tests and all workload, dependency, resource, coverage, retry, skip and 900-second controls remain unchanged. Primitive and selected-metric CPU probes remain diagnostic, not capacity qualification.

## Native detail polling statement bounds (P161)

The job-detail GET/HEAD handler wraps `service.read` in the shared metadata read transaction. PostgreSQL applies a five-second statement timeout or a stricter caller setting, restoring the exact setting after successful, cancelled or nested reads. Full job loading, serialized queue-lock acquisition, event loading and final receipt-authority verification share that budget. Existing receipt serialization and locking remain unchanged. Initial HTTP routing/authorization and mandatory access-audit writes stay outside this transaction. This bounds individual statements, not total request latency; the routing metadata lookup and HTTP authority boundary have their own operating behavior.

Database failures return the existing private `job_storage_unavailable` response with `Cache-Control: no-store`. Authentication, current authority, immutable evidence and connection recovery retain independent tests. Lock-free detail/download reads need revision-fenced consistency qualification and remain separate backlog work; this packet does not remove the serialization guard. Supported-profile installation, upgrade/rollback, coordinated restore, remaining legacy execution, capacity and customer acceptance remain open in the canonical task backlog.

### Numeric input preparation and fixed-cap correction (P161)

The first P161 PR passed all six exact-head checks, but its independent main run reached the unchanged 900-second native suite limit. That failed run remains unqualified and separately retained; it was not rerun. Corrective qualification includes all original workloads and the 62 published P161 cases unchanged.

XGBoost 2.1.4 with pandas 3.0.6 and NumPy 2.5.3 can construct native matrices from a homogeneous, single-block numeric view. The view shares current dataframe storage, and explicit feature types match the original pandas route. The native constructor still validates every matrix. Mixed, extension, categorical, fragmented, custom and other-version representations retain the original path. Numeric category detection and input receipts reuse fresh dtype information within their invocation. Row, feature, label and category hashing, fitter budgets, full public assessment references and runtime/source provenance remain intact; no input or fitted state is cached.

Forty-two additive cases compare native CSR data, model bytes, predictions and receipt hashes against independent original paths, including mutations, read-only/strided inputs and fallbacks. Separate boundary observations preserve missing-value acceptance and rejection of infinities/float32 overflow. Synthetic paired process-CPU observations demonstrate less preparation work; they do not establish supported capacity. The complete PostgreSQL suite, all six corrective PR checks and independent main qualification remain mandatory.

### Objective-only SFS screening (P161)

The first corrective head also reached the original 900-second native cap. All104 published additions passed, but the incomplete workflow remains unqualified and sealed. No failed workflow was rerun.

Candidate screening now requests only its accepted ranking metric from the existing validated metric path. Full top-K cross-validation, selected-candidate train/validation reports, independent public assessment failures, fitted parameters, budgets, partitions and evidence remain unchanged. ROC screening additionally retains the original public integrator after validated availability checks so floating-point rounding cannot reorder near-tied candidates. A new regression caught this rounding difference before publication; the corrected implementation preserves the old selection.

Thirty-nine additive cases compare complete forward/backward steps against the full-metric reference across all supported objectives, including exact top-K membership, fold metrics/provenance, fitter inputs/budgets, stable serial/parallel ties, invalid or unavailable screening and full-assessment failures. All104 previously published additions remain byte-identical. Paired process-CPU probes characterize only the calculation; full local, automatic exact-head and independent main qualification remain required.

### Compact checkpoint and newly generated package metadata (P161)

The SFS screening head also hit the original900-second native cap (6,843/7,388cases completed;128/143published additions completed withoutfailure;15unverified). Its incomplete attempt and earlier valid local source are separately sealed, not rerun or counted as qualification.

New SFS/HPO checkpoints and newly generated score-package metadata use compact standard-library JSON. Serializer options and decoded values remain unchanged. Atomic staging, file/directory synchronization, exclusive publication, strict duplicate-key readers, final source/authority checks and exact published-byte hashes remain. Copied historical evidence and previously published archives/packages retain their original bytes.

Thirteen additive cases cover Unicode and numeric/key semantics, malformed output refusal before staging, immutable legacy/new archive retries and strict duplicate-key rejection. All143 previously published cases remain unchanged. Synthetic paired CPU observations show less serialization work and smaller records; they do not establish supported capacity or resolve CI qualification by themselves. Full native, six-check exact-head and independent main gates remain mandatory.

### Revision-fenced read snapshot evaluation (P162)

D07-T09 evaluates an opt-in interface before changing existing detail/download
serialization. `GET` or `HEAD /api/jobs/{id}/snapshot/` supports:

- `representation=receipt` (default), optionally pinned with `revision=0` or
  another canonical nonnegative integer. The JSON envelope has schema
  `native_job_snapshot_v1`, observation time, revision, `read_only: true` and the
  existing public receipt, including its established 500-score preview limit.
- `representation=candidate&sha256={result_digest}` or
  `representation=scores&sha256={result_digest}`, optionally revision-pinned.
  Downloads preserve the corresponding existing export/score bytes, filenames
  and checksum conventions. `project_id` may narrow an already-authorized scope.

Unknown/repeated parameters and invalid digests/revisions fail explicitly.
Every GET/HEAD response, including permission and storage failures, uses
`Cache-Control: no-store`. Successful responses identify their observed revision
and `optimistic-read-committed-v1` mode in exposed headers. HEAD has no body.

The evaluator requires PostgreSQL **READ COMMITTED**; SQLite and stronger caller
isolation return explicit unsupported conflicts. A repeatable-read transaction
would conceal late authority changes. Within the existing five-second SQL
statement ceiling (or a stricter caller setting), it authorizes routing metadata
before loading job material, collects a full row plus at most 257 events, validates
contiguous history, encodes the complete public bytes, then recollects the row and
events. Any change to concrete fields, full-precision timestamps, typed JSON or
event content makes the read stale. Private row fingerprints never leave the
service. It finally rechecks captured actor, project and source-dataset authority.

A snapshot accepts at most **256 events**. Larger histories return
`job_snapshot_budget_exceeded` rather than a truncated receipt; existing serialized
routes remain available for those histories. Elapsed-time checks around collection,
encoding and authority validation also refuse over-budget results. These checks
and per-statement timeouts do not promise a hard total HTTP latency or preempt
Python encoding. Initial HTTP permission/audit work precedes the service budget.
Callers receive structured `409` stale/history/budget/unsupported diagnostics,
`403` authority denials or `503` unavailable storage, without partial public bytes.

This is a bounded optimistic observation of a coherent revision, not a
linearizable latest-state guarantee, an authenticated event-chain proof, or new
execution/recovery/review authority. Normal writers advance revisions atomically;
privileged out-of-band A-to-B-to-A changes cannot generally be detected by double
collection. Authority changes after the final check belong to a subsequent
observation. Failed reads do not retry silently. No queue/row lock, result cache,
expert deserialization or publication is introduced. Existing serialized routes,
writer transactions, approval controls and UI remain unchanged.

Acceptance evaluation includes real independent PostgreSQL connections: an
execution writer commits while response encoding is paused, and the reader
returns stale rather than holding the queue lock. Additional cases cover exact
legacy candidate/score parity, same-revision field/event edits, late revocation,
source/binding changes, unsupported transaction isolation, caller timeout
restoration/cancellation, event bounds and private uncached GET/HEAD errors.
P162 qualification evidence and the canonical ledger distinguish implementation,
local testing, exact-head CI, independently qualified main and release acceptance.

The first P162 CI head reached the unchanged 900-second full-suite cap. Its
incomplete raw reports and the successful local source are retained separately;
that workflow was not rerun. The corrective source explicitly opts native
training into small mixed numeric/categorical matrix preparation for the exact
XGBoost 2.1.4 / pandas 3.0.6 / NumPy 2.5.3 profile. This reads current cells into
at most 1 MiB of float32 storage, matching native feature types and categorical
missing codes. Every matrix still goes through native `DMatrix` validation.
Default helper dispatch remains unchanged; unsupported representations, versions,
size, disabled category flags and overflow keep the original pandas route.
No source input, fitted state, authority or result cache is introduced.

Thirty-seven differential cases cover native matrix contents, signed/unsigned
integer and float boundaries, missing/category ordering, exact fitted model bytes,
fit receipts, predictions, round budgets, mutations and native refusals. All
55 published snapshot tests remain unchanged, as do public full metric checks.
A paired synthetic preparation probe used approximately half the original
process CPU; it does not establish workload capacity or a delivery guarantee.

### Native qualification resource observations (P162)

Two P162 heads reached the unchanged full-native 900-second cap with incomplete
case inventories. The qualification controller now records bounded read-only
observations immediately before and after its existing pytest invocation,
including timeout paths. Its original control flow, arguments, worker/thread
settings, resource limits, fixtures, and exit/timeout behavior are preserved;
CI configuration is unchanged. Diagnostics do not replace successful test exit,
complete XML/case accounting, coverage, or the original qualification gates.

The records contain OS/architecture, CPU model and observed frequencies/affinity,
host CPU counters, current cgroup quota/cpuset/throttling/memory counters,
system memory/pressure and allowlisted limits for exact owned fixture containers.
They omit environment variables, credentials, host/container identifiers and
cgroup paths. Missing/unsupported observations remain explicit. Host and current
cgroup facts have their stated scopes; they do not establish effective capacity,
a hardware cause, a supported workload or customer installation acceptance.
No process, service or limit is changed. Diagnostic failure does not alter the
original pytest return or timeout; unavailable output is reported explicitly.


## Mac-hosted P162 reference qualification

After three exact-head native timeouts at the unchanged 900-second cap, the
owner approved a bounded reference-host pilot and explicitly selected this Mac
variant. It uses a separate disposable Ubuntu 24.04 amd64 VM on the ARM64 Mac,
four emulated guest vCPUs, 16 GiB RAM and at least 100 GB free disk. Existing Mac
services and workspaces are preserved. The earlier 389.671-second local report
used Linux ARM64 images and does not qualify this emulated x86_64 profile.

PR #261 and its marked automatic main push are the only routed workflows. A
host controller verifies exact GitHub run/source/actor facts and arms a root-owned
pre-worker admission policy. A signed profile binds the emulated execution facts
to the exact run and revision. The personal runner-administration credential and
signing key remain outside the guest. Network, workspace and Docker isolation are
externally enforced; package downloads use a bounded allowlist proxy. See
[the controller boundary](../scripts/ci_reference/README.md).

All original application tests, assertions, fixtures, coverage, skips, retries,
two-worker/thread settings and the 900-second child cap remain. Every original
native step and the other five CI jobs are preserved. Pilot controller checks
supplement application tests. One automatic PR qualification is allowed; only
complete success permits guarded merge and one independent automatic main
qualification on a fresh matching guest. Failure stops the pilot without a
rerun. Emulated success does not establish native-amd64 hardware or customer
capacity. D07-T09 stays open until both qualifications pass; the 66-task done
share remains 3.0% until then, with an intended 4.5% after proven closure.
