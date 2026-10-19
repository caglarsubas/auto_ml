# PostgreSQL referential-integrity trigger profile

P106 extends the existing read-only startup query with the enforcement-trigger
profile of the selected PostgreSQL 17 / Django 5.2 deferred NO ACTION foreign
keys. Valid constraint metadata alone does not establish that its triggers fire.

The predecessor proof uses an ordinary NOCREATEDB, non-elevated application
owner in `origin` mode. PostgreSQL denies that owner's attempt to disable an
internal trigger with SQLSTATE 42501. A separate administrator of the disposable
fixture then disables only the membership actor INSERT check. Startup accepts
this state although an application write commits an orphan. A second ordinary
connection observes the committed row; related-user lookup fails. The proof
removes that orphan before restoring the exact original trigger. Original rows,
all 31 migration records, column storage and all constraint metadata survive.
Restored deferred enforcement rejects an orphan when its transaction commits.
The candidate blocks the corrupted state with `job_schema_invalid` before broker
access. This is privileged maintenance/corruption evidence, not an ordinary-owner
trigger-disable exploit.

## Selected contract

For each of the 38 declared foreign keys, require four internal AFTER ROW roles:
child INSERT and UPDATE checks and parent DELETE and UPDATE NO ACTION checks.
Bind each to its exact `pg_catalog` built-in function, event bits, genuine
constraint, supporting referenced index, local relation and opposite relation.
Both relations must report that triggers exist. Require non-cloned,
non-column-specific triggers, no WHEN predicate or arguments, and the selected
initially deferred timing. Trigger names are immaterial. Normal (`O`) and always
(`A`) modes are supported; disabled (`D`) and replica-only (`R`) modes are rejected.

These timing requirements describe the observed selected NO ACTION profile.
They are not a general rule for every PostgreSQL foreign-key action: a deferrable
constraint can have some nondeferrable triggers. Built-in function identities,
catalogs, operators and types are schema-qualified. Keep the original two query
parameters and four-column result. Startup performs no row scan, DDL, repair,
privilege change or secret-bearing diagnostic.

References: [PostgreSQL trigger catalog](https://www.postgresql.org/docs/17/catalog-pg-trigger.html),
[trigger enable/disable behavior](https://www.postgresql.org/docs/17/sql-altertable.html).

## Physical regression qualification

A new standalone qualifier runs after the unchanged full PostgreSQL/private
fixture in the existing CI job. Its host controller owns a fresh internal Docker
network and PostgreSQL container and injects faults through `docker exec`.
A separate read-only, unprivileged application container receives only the
ordinary application's password; it receives neither the administrator password
nor a Docker socket. PostgreSQL network authentication uses distinct passwords.
No public ports or customer installation are used. Existing CPU, memory and PID
caps are retained. Cleanup removes only the resources this invocation created.

The qualifier retains JSON, JUnit and application logs inside the existing
PostgreSQL artifact. Its 392 physical cases include:

- Individual disablement of all 152 required trigger roles.
- Direct schema, runtime and management-command checks of four representative
  roles: disabled/replica-only modes, missing constraint linkage, substituted
  relation/index/function/event/timing, clone metadata, column restriction,
  arguments, namespace impostor and WHEN predicate.
- Child/parent relation trigger flags, genuine arbitrary trigger names, normal
  and always-enabled modes, and restored healthy startup.

ALTER TABLE supplies real mode changes. Other malformed attributes are explicit
administrator catalog-corruption injections, not supported migration operations
or ordinary-owner authority. Each attribute is restored before ordinary writes.
The detailed fixture also independently observes a committed orphan while the
INSERT check is disabled, removes it, restores the exact catalog state and
rechecks deferred rejection and existing compound uniqueness. The 30 healthy
controls pass on the frozen predecessor; all 362 expected denials fail there.
All 392 pass with the candidate.

Initial TLS and broker responses in this qualifier and the separate semantic
proof are explicit response fixtures over plaintext. Actual private TLS,
installation, workers, recovery and browser receipts remain separately required.
The original pytest inventory remains intact: these 392 physical cases are
additional qualification, not new cases hidden in the original backend totals.
All 162 original tests/execution files other than the CI workflow are byte
identical. The workflow changes only by adding this qualifier and its lint
targets; removing those additions restores the original workflow byte for byte.
Original workloads, assertions, fixtures, skip identities, retry/coverage/pool
budgets, 900-second native suite and 120-second per-test limits remain unchanged.

Source hashes and local results are retained in
[P106 qualification](evidence/p106-qualification-2026-10-19.json). Exact-head all-six
CI, complete original and new native/private artifacts, guarded merge and
independent merged-main qualification remain required.

This is a startup observation of a selected catalog profile. Session replication
settings, arbitrary user triggers, built-in implementation tampering, equality
operator-class/collation semantics, extra restrictive constraints, partitions,
complete historical row integrity, ongoing enforcement after startup and full
schema/restore equivalence remain outside this qualification. Re-enabling a
trigger does not certify rows written while it was disabled. D07 remains in
progress; lifecycle, release and customer acceptance gates remain open.
