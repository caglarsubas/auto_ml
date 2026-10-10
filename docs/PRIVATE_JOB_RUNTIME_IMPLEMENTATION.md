# Private native job startup and recovery (P23)

This extends partial **D07** for the P22 `package_integrity_v1` operation. It supplies a private startup preflight/launcher and a repeatable synthetic Linux qualification with TLS PostgreSQL metadata and an authenticated TLS Redis broker. It does not qualify a complete production installation, expert sandbox, model-job migration, disaster recovery service or customer deployment.

## Private startup

Use the same fixed installed native runtime, dependency versions, configuration and exact artifact root in the API, worker and dispatcher. Supply the existing private settings documented in [private runtime configuration](private-runtime-configuration.md), plus an explicit `DECLARAI_JOB_BROKER_URL_FILE` holding a dedicated `rediss://` database URL and `DECLARAI_JOB_BROKER_CA_FILE` holding its trusted CA. Do not also set the direct URL. The broker must require authentication; the qualified fixture uses password authentication with its URL stored only in a disposable external mode-0600 file. Network access to the trusted broker and metadata service must be restricted by the deployment operator. This packet does not configure customer Redis ACLs, mTLS or network policy.

`python backend/manage.py check_job_runtime` runs a bounded operator preflight. It opens the actual metadata connection, checks its PostgreSQL TLS session, refuses unapplied Django migrations, then opens the actual configured Celery broker connection with zero connection retries. TLS verification, hostname checking and authentication follow the configured broker transport. It never publishes a task, reads a model, creates a request or applies migrations. It returns only neutral verification fields or an error code (`job_private_configuration_required`, `job_private_postgresql_required`, `job_metadata_tls_required`, `job_migrations_required`, `job_storage_unavailable`, `job_broker_unavailable`); connection exceptions and credentials are withheld. Passing this check is connectivity/startup evidence, not a release gate or continuous health guarantee.

In an installed runtime, from `/app/backend`, launch each separate service with:

```sh
sh /app/docker/private-job-entrypoint.sh worker
sh /app/docker/private-job-entrypoint.sh dispatcher
```

The launcher requires the private profile, accepts exactly one fixed role, executes the preflight and then uses the existing native worker/dispatcher commands. It neither migrates automatically nor falls back to development, SQLite, local threads or eager execution. The worker uses prefork with two processes, no gossip/mingle/heartbeat and no remote control; existing task limits, request expiry, authority checks and publication fencing remain in force. A supervisor must restart failed services and enforce Linux memory/PID/CPU limits. Install the script with the application image; source bind mounts and the live-reload development composition remain unsuitable for private deployment. This packet deliberately does not claim a locked offline image, an installation/upgrading/rollback package or a qualified production supervisor.

After startup, a broker outage leaves committed requests in PostgreSQL. The dispatcher can retry; loss of broker queue/AOF data is recoverable from this outbox. Metadata loss remains a separate problem. Native runtime/source changes invalidate queued work pinned to the old runtime; an operator must inspect the blocked receipt and submit a newly reviewed request rather than rewriting its pinned specification.

## Quiescent backup and restore discipline

The tested restore is a consistent, quiescent database/artifact snapshot. An installation operator must first block new job admission and stop the dispatcher and all native workers. The API can disable job submission by removing its explicit broker configuration and restarting it, while authorized historical receipt access remains available. Quiesce other artifact/metadata writers as well. Record which requests were pending or leased and preserve the exact runtime used by those requests.

Back up PostgreSQL metadata and the corresponding versioned artifact root together, preserving job IDs, project/binding/membership revisions, specifications, request hashes, actor snapshots, leases, events and result hashes. The broker queue is reconstructible and is not the status authority. Keep deployment secrets and the runtime outside the evidence export; protect backups according to the customer's retention/access policy. Restore into a stopped installation with the matching native runtime and artifact paths. Verify snapshot metadata and artifact digests before starting services, and never run both the old and restored installations against duplicated authority.

An abandoned active lease stays active until its original expiry. The dispatcher then records requeue, and a new worker can acquire a new token and recompute within the unchanged attempt budget. A token from the old attempt cannot publish into the recovered database. Completed/cancelled requests remain terminal; duplicate messages cannot rerun them or add a second successful publication.

Fencing is against the authoritative live database. A historical restore cannot fence a second independently running copy of that database or recover updates made after the snapshot. This drill does not establish live concurrent backup consistency, cross-installation fencing, recovery point/time objectives, machine loss, power failure, storage encryption, clock/resource faults or high availability. Those remain D07 release requirements.

## Reproducible qualification

Run [the owning disposable fixture](../scripts/qualify_postgres_fixture.py) with Docker/OpenSSL and the application's Python dependencies; `--runner-image` uses a local fixed Linux core image. The same fixture runs in the existing PostgreSQL CI job, without changing the six-job pipeline, test scope, coverage gate or skip budget. All services have random invocation-owned names. Secrets, private fixture state, worker logs, dumps and artifacts live in a temporary directory outside the checkout and are removed on exit. Ignored reports contain neutral outcomes. The TLS broker receives only its own certificate/key/configuration, not the fixture's database credentials/session state.

[The private job helper](../scripts/qualify_private_jobs.py) refuses non-test/non-private/non-fixture PostgreSQL installations. It creates four synthetic requests with deliberately non-deserializable model bytes: queued, controlled abandoned metadata lease, completed through an actual prefork worker, and cancelled. The private launcher is used by the real worker and dispatcher.

The owning fixture proves that the configured authenticated TLS broker works and wrong CA, hostname and credentials block the real preflight. It stops/removes the actual broker and its AOF volume, checks that dispatch failure leaves the committed requests unchanged, then snapshots PostgreSQL and artifacts while its job processes are stopped. It restores to a separate database/artifact root and starts an empty broker. Both original and restored snapshots match every recorded request, authority/specification, lease, result/event receipt and artifact hash.

The recovered installation runs the actual dispatcher, waits for the original **180-second** abandoned lease to expire (no time/budget injection), fences the old token, starts a fresh prefork worker and verifies both pending requests complete once. Original event prefixes, authority and request hashes survive; terminal receipts remain byte-equivalent at the JSON-field level and duplicate deliveries cannot alter them. The abandoned lease was created through the native claim API as a controlled fixture state; this packet does not claim an additional killed-active-worker drill. P22 separately retains its actual worker-kill qualification with injected expiry. Only process groups created by the helper are eligible for termination.

Results belong in [P23 evidence](evidence/p23-qualification-2026-10-10.json) and the canonical roadmap ledger. Complete production packaging/operations/recovery, training/search/scoring job migration, expert isolation, retained-data policy, accessibility and all release/value/customer gates remain open.
