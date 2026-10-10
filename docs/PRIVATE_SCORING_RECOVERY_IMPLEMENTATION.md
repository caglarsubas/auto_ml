# Private native scoring recovery (P25)

P25 qualifies a bounded part of **D04/D07/D09**: P24 native CSV scoring through a coordinated, quiescent PostgreSQL/artifact restore and recovery from an empty authenticated TLS Redis broker. It adds an executable recovery regression to the existing private fixture. Product request, scoring, authorization and publication behavior are unchanged.

## Qualification workflow

Run `python scripts/qualify_postgres_fixture.py` in a supported Python test environment with Docker and OpenSSL. The optional `--runner-image <local-test-image>` runs the same checks inside an installed test runtime. The owning fixture creates its own PostgreSQL, cache, TLS job broker, network and temporary state; it requires no access to an existing customer installation. CI runs this owner as part of **PostgreSQL runtime and metadata**.

The new `scripts/qualify_private_scoring.py` runs only with explicit disposable-installation authorization, the private profile and a fixture-named PostgreSQL database. It verifies that the database connection uses TLS. Its phase commands are invoked by the owner; they are not standalone customer backup/restore commands.

API checks use Django's HTTP test client with real login, session and CSRF validation. PostgreSQL and broker TLS use actual network connections; this packet does not qualify a deployed HTTPS ingress or a new browser journey.

1. Create real server-side login/CSRF sessions for a developer, reviewer, second developer and outsider. Through the governed API, train and assess a native logistic classifier and XGBoost regressor, freeze exact packages, and register separate 650-row inputs. The classifier must produce calibrated scores.
2. Record ten scoring jobs: queued, completed and cancelled jobs for both tasks; an orphaned classifier lease; and queued jobs reserved for changed-input, missing-input and revoked-submitter checks. Complete two jobs using an actual prefork worker. Retain the orphan lease without a worker. Together with the existing integrity orphan, it occupies the unchanged two active slots.
3. Quiesce the owned processes, remove the real broker and its AOF volume, and verify that failed delivery preserves the requests and full results. Restore a PostgreSQL dump and the matching media tree into a separate disposable database/artifact root. Start a new empty broker.
4. Compare exact job specifications, both authority snapshots, request hashes, lease state, full results, events and artifact/input hashes before any recovery. Verify restored sessions and reviewer downloads through the actual HTTP routes; outsiders are denied. The preview is not used as the reference for the full result.
5. In the restored fixture, change one queued input, remove another, and revoke the second developer through the supported attributable operator interface. Start the independent dispatcher and native workers. Valid jobs recover; the three negative jobs block without scores. The orphan uses natural lease expiry, followed by a second attempt and exactly one successful publication.
6. Attempt a stale-token publication and deliver two additional Celery messages for each of the ten terminal jobs. Observe twenty actual task completions in the owned worker log before comparing unchanged terminal results, attempts and history. Successful restored scores must match the independently computed pre-backup native reference at `atol=rtol=1e-12`.
7. Download complete, digest-matched 650-row receipts and inspect the 500-row detail previews. Revoked members and outsiders cannot download them. Inject a separate unsupported source-binding change in the disposable database: a reviewer can still read the model dataset, but source, job-detail and score-receipt access is denied while recorded history remains unchanged. This is fault injection, not a supported product reassignment operation.
8. Retain only synthetic package/input/full-receipt exports in ignored reports. Passwords, sessions, lease tokens, TLS keys and database dumps remain outside the checkout and are destroyed by the owner. Stop only owned process groups and remove only the invocation's exact resource names.

The owner retains all existing P17/P18 private identity/project checks, P22 killed-worker integrity checks, P23 TLS/preflight/quiescent restore checks, and the full PostgreSQL regression/coverage suite. Dataset sizes, model rounds, assertions, timeouts, skip limits and coverage gates are unchanged. P25's scoring orphan is an abandoned metadata lease; it does **not** claim that a running native scoring process was killed.

## Independent recovered-score replay

After a successful owner run, `recovered-scoring/classification` and `recovered-scoring/regression` contain synthetic exports from recovered jobs. Run the existing verifier against a fixed image that exactly matches their recorded native scoring source, Python and dependencies:

```sh
python scripts/qualify_offline_scoring.py \
  --runtime-image <matching-fixed-native-runtime> \
  --inputs test-reports/postgresql/recovered-scoring \
  --reports test-reports/recovered-scoring-offline
```

This replay uses no network, a read-only runtime, an unprivileged user, explicit CPU/memory/PID limits and an empty installation-media mount. It compares whole batches and chunk sizes 1/17/64 at the same `1e-12` tolerances. Native serialized state is trusted only because these models were generated by the disposable fixture. This remains score reproduction, not complete training or final-assessment reproduction.

## Scope and remaining work

The [P25 qualification record](evidence/p25-qualification-2026-10-10.json) binds evidence to exact source. P25 is synthetic Linux-container qualification on the specified local runtime plus the existing CI profile. A successful restore requires the matching metadata, raw inputs, packages and installed runtime; an empty broker is rebuilt from durable requests rather than from Celery result state. An unavailable or changed input cannot be silently replaced.

No migration, new endpoint, policy approval or production promotion is introduced. Existing synchronous and queued scoring APIs remain compatible. All release/value/customer gates stay open. Production live backups, supervisor/machine-loss/clock/hard-timeout and actual interrupted-scoring recovery, full offline installation/dependency locking, training/search migration, artifact authenticity/retention/egress, full refit/assessment reproduction, expert gVisor isolation and comprehensive accessibility still require their own implementation and qualification.
