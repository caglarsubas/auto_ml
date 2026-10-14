# Search worker database lifetime (P64)

SFS and tuning run outside Django's request lifecycle. Their background threads
can open metadata connections during candidate publication and evidence
registration, but previously had no explicit connection cleanup. Django documents
that [each thread owns its connection and work outside the request lifecycle
requires explicit connection management](https://docs.djangoproject.com/en/5.2/ref/databases/#connection-management).

## Worker boundary

The shared launch boundary now wraps the accepted target. In a separate worker
thread it closes old/unusable connections before execution and closes that
thread's initialized connections in `finally`, after successful completion,
stopping or an ordinary execution error. An inline thread factory retains the
caller-owned connection and active transaction; cleanup must not close a
request's connection.

Setup and otherwise unhandled execution exceptions produce redacted,
operation-correlated `worker_setup` / `worker_execution` diagnostics. They fail
only the matching running owner using the existing progress guard. Cleanup
exceptions produce a separate `worker_cleanup` diagnostic and `cleanup_failure`
progress field. They preserve prior computation status and the original failure.
Stale, missing and retokened owners cannot be modified. Cleanup uncertainty is
not permission to replay work or discard completed evidence.

## Qualification and limits

Seventeen regressions exercise real thread connections, completion/stop/error,
caller isolation, inline transactions, setup/execution/cleanup failures, redaction
and replacement/retokened/missing owners. The real connection proof retains the
wrapper and raw connection after thread exit, preventing garbage collection from
standing in for explicit cleanup. SQLite uses a file-backed connection because
Django deliberately keeps its in-memory test database open; PostgreSQL uses the
same TLS database configuration as the qualification suite through a separate
thread connection. The closure and caller-isolation assertions are identical.

All 172 focused checks pass. Full SQLite, negative-before and exact-head private
PostgreSQL qualification are recorded in associated evidence; independent main
qualification remains required. Scientific execution, assertions, resource
bounds and timeout/coverage/skip/browser-retry budgets are unchanged.

This controls connection lifetime at the existing process-local thread boundary.
It does not migrate searches to durable workers, add distributed leases, persist
lifecycle diagnostics across process loss or provide forced-process cleanup.
Cleanup failure does not invalidate a completed model or authorize automatic
retry. Full D07 lifecycle/upgrade/restore, expert isolation and release/value/
customer gates remain open.
