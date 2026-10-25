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
