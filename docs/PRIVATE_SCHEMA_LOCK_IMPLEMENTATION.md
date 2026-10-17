# Trusted initializer advisory lock (P95)

The initializer previously resolved `pg_try_advisory_lock(integer,integer)` through
its caller's search path. An owned ordinary NOCREATEDB database role can define a
public function returning true: the actual production lock statement and
acceptance assertion then succeed without holding PostgreSQL's real lock, even
while a competing session holds it. This is an isolated lock-attestation proof;
runtime/manifest verification, other role/TLS authority checks, schema state,
migrations and controller publication are outside that proof. In particular,
existing state checks can reject public functions later; this evidence does not
claim a complete migration-concurrency or controller bypass.

The initializer now calls `pg_catalog.pg_try_advisory_lock` explicitly. The
session-level lock keys, acceptance assertion, connection lifetime, phase errors,
helper identity binding, migration behavior and resource budgets remain unchanged.
The actual caller search path is retained. This observes cooperative advisory
exclusion; it does not fence arbitrary concurrent database administrators or
later schema changes.

Ten new cases compile the actual production lock statement and its assertion.
Two real PostgreSQL sessions verify both free and held states, with no substitute
and with caller functions that accept, deny, raise or write a retained effect
row before forwarding to the real lock. Independently inspected `pg_locks` must
support each acceptance; substitute functions must not produce effects. Against
the predecessor five regressions fail and five controls pass; all ten pass with
the fix. The focused native matrix passes 477 cases; the reference/adoption
matrix passes 577. SQLite uses explicit real-lock response references only and
does not emulate PostgreSQL locks or namespace semantics. Native DDL rolls back;
the owned seed row and recorded migration history remain intact.

An additional ordinary-role reproduction confirms false acceptance with no real
lock before the fix, then genuine ownership when free and rejection when held.
Its original row and empty migration history are preserved. See
[P95 source qualification](evidence/p95-qualification-2026-10-18.json).

All six exact-commit checks, complete native/private receipts and independent
merged-main qualification remain required. Existing scientific workloads,
fixtures and timeout/coverage/skip/retry/resource limits are unchanged. No
customer installation is modified. Other initializer authority SQL and the full
upgrade/rollback, coordinated restore, release and customer gates remain open;
D07 remains in progress.
