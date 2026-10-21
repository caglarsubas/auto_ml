# Operator-facing native queue incident triage

P124 adds a read-only command for the Linux root operator of a managed private installation. Its independently trusted plan digest, initialization binding, native image IDs and exact application profiles establish installation authority. Developer, reviewer and project-admin permissions do not grant installation-wide access through HTTP or MCP.

Run from the trusted installation tool checkout on the supported Linux host:

```sh
python3 scripts/private_queue_incidents.py /secure/plan \
  --expected-plan-sha256 TRUSTED_PLAN_MANIFEST_SHA256 \
  --output /secure/operator-evidence/incident.json
```

The output directory must already exist, be root-owned `0700`, have no ACLs and have trusted non-writable ancestors. The command publishes a root-only `0600` JSON file atomically without overwriting an existing path, including a symlink. Failures print a neutral diagnostic rather than raw engine, driver, SQL or credential errors. Stdout returns the evidence SHA-256; record it outside the exported file before sharing the file with an authorized investigator.

The file wraps `evidence` plus `sha256`. Verify the latter against UTF-8 JSON encoding of `evidence` with sorted keys, separators `(',', ':')`, and no non-finite values. It is a checksum against a separately trusted digest, not a signature or an approval. All reports contain installation-confidential project, dataset and job identifiers; follow the customer's retention and controlled-egress policy.

## What an operator observes

The existing managed-operation lock is acquired without creating a lock, changing installation receipts or starting services. Four application roles and three managed dependency profiles are checked against the exact plan and native images before and after collection; private-network membership is verified. Missing, stopped, paused, restarting, dead and OOM states remain visible. A changed sample is explicitly marked unstable. Direct Docker actions and running workers can bypass this cooperative lock; it is not a stop-the-world snapshot.

An active, verified API container runs one fixed probe as UID/GID 10001. The packaged runtime manifest is verified before Django setup. The command accepts no user code, SQL, environment overrides or additional mounts. PostgreSQL queries run in a read-only repeatable-read transaction with a five-second per-statement timeout. All counts and selected rows share its database snapshot. The transport has a 20-second deadline and bounded memory capture. A missing/inactive API or unavailable database produces an explicit unavailable observation, never an empty or healthy queue.

The report contains current state counts, overlapping signal counts and at most 50 newest matching jobs by creation time and UUID. It discloses total matches and truncation. Signals cover recorded failures/blocks, expired unfinished requests, overdue/missing active leases and exhausted attempts. Historical terminal failures need not indicate a current incident. Routine queued work is not labelled a failure. Rows include only IDs, revision, state, known kind, attempts and timestamps. Full specifications, models, results, actor names, raw reasons/logs, event payloads, protected inputs, outcomes and predictions are not fetched. The probe never deserializes fitted state.

## Investigation and authority

Use the signal-specific guidance to correlate the exact project job receipt with worker, dispatcher, broker and database availability. Broker delivery, dependency health and HTTPS health are explicitly untested here. The project owner can inspect the existing revision-pinned operational handoff and conservative protected-access counts under current project authority. An interrupted, failed or cancelled assessment retains possible outcome access and remains exploratory.

Observation does not dispatch, reconcile, retry, cancel, recreate requests, change limits, repair services or approve models. Normal dispatcher recovery stays within the immutable request's existing expiry, attempt, source, runtime and authority limits. Any maintenance, new request, deployment or promotion uses its separate approved workflow. The report does not qualify coordinated recovery, backup/restore, upgrade/rollback, customer acceptance or the whole D07 outcome.

## Qualification

Additive backend cases exercise overlapping incidents, bounded metadata-only selection, unsupported storage, operator identity/plan/image/runtime boundaries, actual cooperative locks, safe degraded observations, unavailable transport and exclusive digest-checked exports. The existing managed Linux fixture additionally verifies real PostgreSQL collection, paused-worker diagnosis, paused-API unavailability, lock denial, export permissions/non-overwrite and unchanged service identities/states/installation history. All inherited execution, cancellation, recovery, restore, physical-schema and browser workloads remain required with unchanged budgets.
