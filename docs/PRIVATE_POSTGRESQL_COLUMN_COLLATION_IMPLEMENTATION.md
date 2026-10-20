# P115 — PostgreSQL column collation hardening

D07 remains in progress. This packet closes a startup column-contract gap: a
required text/varchar column could retain its type, length and constraints while
using a different collation, changing ordinary Django ORM comparisons.

## Contract

The selected sealed migration graph currently declares database-default
collation. Admission now requires `pg_catalog."default"` for required text and
varchar columns, and collation OID zero for supported noncollatable types. The
catalog predicate binds built-in types, casts and operators explicitly. Explicit
`db_collation` declarations, including foreign-key target declarations, fail
closed until a separate contract is qualified. No migration or customer schema
is rewritten. Extra columns remain permitted.

Schema mismatch retains `job_schema_invalid` through runtime and management
command entrypoints and stops before the broker probe. Direct schema checks use
the same physical evidence. Existing migration, privilege, row-security,
replication, role and foreign-key/RI-trigger checks remain intact.

## Evidence

An owned PostgreSQL 17 fixture demonstrates valid DDL changing project-name
(varchar) and session-data (text) comparisons from case-sensitive to
case-insensitive using a nondeterministic ICU collation. The stored values do
not change. The old guard admits both altered columns through schema, runtime
and command entrypoints. Separate administrator-only catalog-corruption
controls exercise nonzero collation on an integer and zero on text.

The physical qualifier adds 33 cases to the original 764. Twelve denial cases
reproduce on frozen main; the remaining original cases and positive controls
pass. Restoration verifies required column metadata, fixture rows, migration
history and the original role/constraint/trigger controls. Privileged injection
stays in the host controller; the application receives neither administrator
credentials nor a Docker socket. This fixture does not establish TLS trust.

Sixteen new pytest cases cover altered text/varchar collations, unsupported
sealed declarations, startup failure before broker access, and supported default
collation/extra columns. New fixture fields are cloned before modification to
preserve migration-state isolation. The SQLite denial adapter is a development
reference; PostgreSQL executes real DDL and the production catalog query.

Original test assertions, workloads, skip identities, concurrency, coverage,
120-second test timeout and 900-second native-suite limit are preserved. PR and
automatic push-main CI must be qualified independently using complete reports.
The [source qualification receipt](evidence/p115-qualification-2026-10-20.json)
and [roadmap ledger](product-roadmap.json) distinguish delivery states.

## Limits

This is admission-time evidence, not continuous schema fencing or a historical
integrity audit. Database-default provider, locale, library/version changes and
index/operator-class equivalence require separate qualification. D07 recovery,
release and customer-acceptance gates remain open.
