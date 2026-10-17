# Private schema catalog evidence trust (P91)

Caller-defined PostgreSQL operators can substitute evidence even when catalog
relations and functions are qualified. An owned ordinary-role probe demonstrates
four accepted startup states: a missing `auth_group.name` column supplied through
a forged attribute join, an alternate-schema table standing in for a missing
public table, and the same substitution after presence or permission validation.
An actual ORM read of the lost column fails with SQLSTATE `42703`. Migration
history remains current, so it cannot independently detect this physical damage.
TLS/broker transport is stubbed in the local proof; role, migration history,
catalogs, permissions, row-security flags and connection modes are actual.

Presence, permission and row-security queries now pin catalog joins and filters
to built-in `pg_catalog` operators and identifier types. The presence query also
pins the attribute-number comparison. The supported required public schema and
effective permission/RLS policies are unchanged. Visibility still describes the
actual caller search path; the product never changes it or repairs database
objects, grants, policies, history or data.

Eight new direct/management cases fail against the predecessor and pass after the
fix. The first two scenarios retain `job_schema_invalid`; substitutions between
phases retain `job_schema_privileges_invalid` or
`job_schema_row_security_invalid`. All denials precede broker contact. Native
fixtures use transactional owned DDL, verify real missing columns/tables, and
preserve recorded migrations and an owned row after rollback. SQLite cases are
explicit phase-denial references, not PostgreSQL namespace semantics or a
product fallback. Existing healthy, catalog-error and phase-specific cases remain
unchanged. Focused PostgreSQL passes 304 cases; SQLite/reference and existing
adoption cases pass 404. The final frozen-source full local suite passes 4,012
tests with six existing skips and no failures or errors.

See [P91 source evidence](evidence/p91-qualification-2026-10-17.json).
Exact-commit all-six checks, complete retained private/native reports and
independent main verification remain required. Existing scientific workloads,
fixtures and timeout, coverage, skip, retry and resource budgets are preserved.

These are startup observations for the current supported schema. They are not
atomic fencing of subsequent changes, complete constraint/data/restore proof or
every-query namespace hardening. D07 remains in progress, including durable
training/search, supported dependency findings, complete upgrade/rollback and
coordinated recovery. Release/customer acceptance remains separate.
