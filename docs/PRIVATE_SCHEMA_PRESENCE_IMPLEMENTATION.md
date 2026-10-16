# Private managed-schema presence guard (P85)

Current Django migration records do not establish that a restored database still
contains the relations required by the selected image. The prior private startup
preflight accepted renamed/lost managed tables and columns, views substituted for
tables, and public tables shadowed by the active search path.

The shared private API/worker/dispatcher preflight now checks the physical presence
of every managed, nonproxy model table, including automatic many-to-many tables,
and the migration recorder. Required local concrete columns must exist in visible
ordinary public tables. A read-only PostgreSQL catalog query checks names, relation
kind, visibility and columns; it never queries model rows or substituted views.
Additional columns are permitted: this is a required-presence check, not an exact
physical-schema equivalence test. Model/migration history checks retain precedence.

A mismatch blocks before broker/cache access with `job_schema_invalid`. Catalog
storage errors retain the redacted `job_storage_unavailable` diagnostic. Existing
positive preflight receipt fields are unchanged. The command never migrates,
repairs, drops, grants privileges, changes search paths or edits migration history.
Use the direct `check_job_runtime` command to inspect these static diagnostics;
the fixed service launcher's existing generic preflight-failure wrapper remains.

Twenty-eight new cases exercise direct and management-command paths. Actual
PostgreSQL DDL is enclosed in rolled-back transactions and actual production
catalog SQL checks the resulting schema. The predecessor fails twenty-four cases
and passes four healthy/additive-column references. SQLite's development reference
adapts actual SQLite metadata after the corresponding DDL; the product has no
SQLite catalog fallback. Physical catalog SQL remains actual PostgreSQL. TLS/broker transport and the
independent P86 privilege phase are isolated in these focused tests. Existing migration-history/connectivity fixtures explicitly isolate this
new physical check, preserving all their previous assertions. Full private hosted
qualification independently checks TLS and fresh Linux installation/service use.

See [P85 source evidence](evidence/p85-qualification-2026-10-16.json).
Exact-commit six checks, complete private/native reports and independent main
qualification remain required. Checks observe startup state; they do not fence
later DDL or prove types, defaults, constraints, indexes, effective privileges,
data integrity, complete recovery or upgrade/rollback compatibility. D07 remains
in progress, including supported dependency findings, durable search, full
lifecycle/recovery, expert execution and release/customer gates. All existing
scientific, test, runtime and resource budgets remain unchanged.
