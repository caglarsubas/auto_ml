# Literal PostgreSQL system-schema prefix (P93)

The schema initializer used `NOT LIKE 'pg_%'` to exclude PostgreSQL system
schemas from its foreign-schema check. In a LIKE pattern, the underscore matches
any one character. Ordinary names such as `pgx_archive`, `pgarchive`, `pg-archive`,
`pg9` and `pgø_archive` could therefore inherit system-schema treatment despite
not starting with the reserved literal `pg_` prefix.

An owned ordinary NOCREATEDB-role reproduction executes the actual graph, state
and migration branch from `SCHEMA_CODE`. With an existing `pgx_archive.retained`
table and row, the predecessor describes the database as fresh, executes 31
migrations and reports/accepts current state. The candidate and final source
describe it as foreign and reject both fresh apply and current verification
before any migration call. The probe's outer rollback preserves the foreign row
and original empty migration history. Runtime/manifest verification, authority,
TLS and controller receipt publication are outside this local proof; it does not
claim to bypass those protections or qualify a customer installation.

The namespace query now compares the first three characters with the literal
`pg_`. Its namespace catalog, prefix function, identifier types and comparisons
are pinned to `pg_catalog`. Public and information-schema exceptions remain
unchanged. Genuine catalog, toast and temporary schemas remain accepted; foreign
schemas are reported without deletion, repair or automatic adoption. Migration
graph pins, atomic DDL/history behavior, helper profiles, static phase diagnostics
and execution/resource budgets are unchanged.

Nine new cases include five misleading-prefix regressions and four compatibility
controls: ordinary names, the two-character `pg`, mixed-case names and genuine
system/temporary schemas. Against the predecessor, the five regressions fail and
the four controls pass; all nine pass after the fix. Native tests execute the
actual state function against transactional owned schemas and data, retaining
migration history and an existing model row. SQLite cases are explicit state
response references, not PostgreSQL namespace semantics or an emulated LIKE
implementation. Focused native tests pass 458 cases; SQLite/reference plus
existing adoption tests pass 558.

See [P93 source qualification](evidence/p93-qualification-2026-10-17.json).
Final-source full tests, all six exact-commit checks, complete private/native
reports and independent merged-main qualification are required. Existing
scientific workloads, fixtures and timeout/coverage/skip/retry/resource limits
remain unchanged. Existing real-TLS schema initialization, rollback and adoption
receipts remain mandatory.

This is a selected-controller schema-state check. It does not fence subsequent
schema changes, prove every physical constraint or harden every other catalog
query. D07 remains in progress, including durable training/search, supported
dependency findings, complete upgrade/rollback and coordinated restore.
Release/customer acceptance remains separate.
