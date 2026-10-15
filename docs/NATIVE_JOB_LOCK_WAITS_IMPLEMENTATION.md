# Bounded native metadata lock waits (P69)

The durable job service serializes admission, cancellation, claim, publication
and reconciliation through a queue row. PostgreSQL's default unlimited lock wait
could leave one of these calls waiting indefinitely behind another transaction.

The shared `locked()` scope now selects a PostgreSQL lock-wait limit of at most
**5,000 milliseconds per acquisition** before queue-row creation or locking. An
existing nonzero limit below five seconds is preserved. The limit also applies
to authority and metadata locks acquired inside the scope. It does not change
statement timeouts, job/scoring budgets, queue capacity, attempt counts, lease
duration, Celery limits, concurrency or dispatcher polling.

The limit uses transaction-local configuration. Successful nested calls restore
the caller's exact preceding setting before its outer transaction continues.
Exceptions and explicit rollback revert the local setting with the helper's
atomic block, including concurrent first-row creation. A timed-out locked
transaction commits no partial metadata or event. Existing HTTP handling returns the
redacted `job_storage_unavailable` 503; the dispatcher retains its existing
storage-failure handling. No automatic HTTP resubmission is introduced. The same
request UUID remains the key for resolving ambiguous submission outcomes.

This follows PostgreSQL's documented [lock timeout semantics](https://www.postgresql.org/docs/17/runtime-config-client.html)
and [transaction-local SET/rollback behavior](https://www.postgresql.org/docs/17/sql-set.html).
The limit is per lock acquisition, not an end-to-end transaction deadline. It
does not bound non-locking queries, filesystem or network I/O, or SQLite's
existing development file lock. Private installations continue to require
PostgreSQL. A stricter caller limit can cause refusal sooner.

Seventeen new cases cover configuration order, disabled/longer/stricter limits,
success, Python/database errors, explicit rollback, nested callers, unchanged
statement timeouts, SQLite compatibility and real PostgreSQL contention at
bootstrap, the existing queue row and a later body row. Contention produces SQL
state `55P03`, preserves caller transaction usability, rolls back partial writes
and permits a subsequent attempt after release. Existing native request,
authority, fencing, cancellation, replay and scoring cases remain required.

Local PostgreSQL semantic checks use only owned containers on a new internal
network without published ports. They are development fixtures, not private TLS
or ordinary-application-role qualification; those remain exact-head CI gates.
Owned resources are removed afterward. The service source remains part of the
native runtime fingerprint: historical requests retain their recorded evidence,
and old-runtime work cannot silently inherit the new implementation.

Durable search migration, full installation/upgrade/rollback/restore, expert
isolation, release and customer gates remain open. D07 is still in progress.
