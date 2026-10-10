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

[Native process fixture](../scripts/qualify_native_jobs.py) refuses non-test installations. It uses synthetic, deliberately non-deserializable model bytes. It launches actual prefork Celery/Redis work against TLS PostgreSQL metadata, kills only its own active worker process group, injects lease expiry without shortening production budgets, restarts a fresh worker, checks stale publication/duplicate delivery, active cancellation and a real failed broker connection with retained-request recovery. It is an injected process/clock/connection fixture, not a private Redis TLS, machine-loss, broker restart, coordinated job backup/restore or production recovery drill. Real native package integrity is covered separately by HTTP tests and the browser workflow.

Qualification results and source hashes belong in the P22 evidence record and canonical ledger. Training/search/batch-score migration, durable assistant grants, complete private worker packaging/TLS/recovery/restore, artifact authenticity, retained data policies, expert isolation and release/customer gates remain open. Runtime checks bind the listed native job modules and package versions, not every transitive dependency or an authenticated image digest. Hash receipts detect changes relative to the recorded package; they do not prove artifact authenticity or statistical/model validity.
