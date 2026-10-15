# Dispatcher database connection recovery (P71)

The standalone durable outbox command previously lacked Django's connection
lifecycle cleanup. A connection that became unusable outside an atomic rollback
could remain attached to the command, and driver `InterfaceError` escaped the
existing storage retry handler. Long-running commands do not receive HTTP
request connection-management hooks. Django documents the explicit cleanup in
its [database connection caveats](https://docs.djangoproject.com/en/5.2/ref/databases/#caveats).

Each dispatch cycle now calls `close_old_connections()` before work and in its
`finally` block. Obsolete or unusable connections are retired; healthy persistent
connections retain Django's configured lifetime. Both `DatabaseError` and
`InterfaceError` use the existing static `job_storage_unavailable` diagnostic.
Continuous mode retains its five-second retry cadence; once mode still returns
a redacted command error. Fatal policy and unexpected failures still propagate,
with cleanup and signal-handler restoration.

Eleven new cases cover every exit path, retry order, expired connections and
real termination of the test's own PostgreSQL session, with health checks both
enabled and disabled. The latter observes the driver error outside an atomic
block and verifies that the same command subsequently reads the real durable
queue using a different backend PID. SQLite exercises development compatibility
without claiming server-session recovery. Existing shutdown assertions remain;
their signal mocks are isolated from pytest's SIGALRM timeout handler and their
storage cleanup is stubbed because those tests deliberately do not use a DB.

The owned development PostgreSQL fixture uses an internal network with no host
ports and removes only its own resources. It is separate from the required
private TLS, ordinary-role and full native installation qualification. Initial
local failures are retained: uncaught InterfaceError, SQLite's intentionally
retained in-memory test connection, and signal/DB mock isolation. No timeout,
coverage, scientific workload, lease, attempt, queue or worker budget changed.

This hardens the dispatcher connection lifecycle, not full database-server
restart/recovery, installation upgrade/rollback or coordinated production
restore. Durable search, expert isolation, release and customer acceptance
remain open. Exact-head all-six checks and independent main verification are
required before advancing.
