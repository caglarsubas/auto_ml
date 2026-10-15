# Dispatcher queued-batch shutdown (P72)

A continuous dispatcher previously observed its stop flag only after an entire
outbox batch. An actual SIGTERM or SIGINT delivered during the first synthetic
publish in an owned Linux PID-1 process still allowed all three queued publishes.
That extended shutdown across work not yet started.

The command now supplies its lock-free stop predicate to `dispatch_once()` in
continuous mode. The pump checks it before work and before each queued publish.
Reconciliation already underway completes its transaction. A publish already
underway completes its existing metadata scheduling update, then no additional
publish starts. Remaining requests, attempts, revisions, events and results stay
unchanged for a later dispatcher. Failure diagnostics retain their existing
redacted counts, and broker publication still occurs outside metadata locks.

Default direct calls and `--once` retain full-batch behavior. Once mode does not
install signal handlers. Continuous shutdown still restores caller handlers and
cleans database connections through P71's lifecycle boundary. Existing signal,
lease, runtime, scoring and cancellation assertions remain; test dispatch doubles
now accept the optional predicate, with explicit once/continuous forwarding
checks. Runtime fingerprints continue to bind the changed service source.

Nine new cases cover stop before work, after reconciliation, during publication
and its metadata update; unchanged default delivery; failures before/after a
successful publish; and actual operating-system SIGTERM/SIGINT delivery with
handler restoration. The latter uses a separate process with synthetic broker/
storage seams, not a real broker/database recovery claim. Additional owned
Linux PID-1 probes retain the before/after receipt: three publishes before the
fix, one publish and one metadata update after it. Existing full private native
qualification still exercises actual broker, database and dispatcher services.

These are cooperative observation points: a signal arriving immediately after
a check can belong to the next unit. This does not preempt the current broker
call/transaction or guarantee a total wall-clock shutdown deadline.
No queue, retry, worker, lease, time, coverage, skip or scientific budget changes.
Durable search, full installation/server recovery, upgrade/rollback/restore,
expert isolation, release and customer acceptance remain open. All-six exact-head
checks, complete private/native receipts and independent main remain required.
