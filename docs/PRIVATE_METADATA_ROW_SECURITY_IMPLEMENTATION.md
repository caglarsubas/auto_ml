# Private metadata row-security guard (P87)

Migration history, physical presence and table CRUD rights do not establish that
metadata rows remain visible. In an owned PostgreSQL fixture, a non-elevated
application owner retains all four CRUD rights while forced row-level security
hides an existing group row. The preceding full startup preflight still accepts
the database. Rollback makes the same row visible again. The reproduction uses
actual PostgreSQL history, presence, permission and RLS behavior; only TLS/broker
transport is stubbed.

The initial single-organization private installation expects unfiltered managed
metadata tables. Its shared API/worker/dispatcher preflight now requires both
`relrowsecurity` and `relforcerowsecurity` to be false on every required managed
nonproxy table, automatic many-to-many table and migration recorder. Required
relations must all appear in a read-only PostgreSQL catalog result. Discovery
uses the same required-schema definition as the preceding checks.

Enabled RLS is unsupported even when the current owner bypasses it; a force-only
flag is also outside the fixed profile even while RLS is inactive. These states
are not all claims of current row loss. RLS-based metadata deployments require a
separately designed and qualified product profile. This check never disables RLS,
changes policies, grants privileges, repairs schema or reads model rows.

A mismatch at this phase blocks before broker/cache contact with
`job_schema_row_security_invalid`; catalog failures retain the redacted
`job_storage_unavailable` diagnostic. Earlier history, presence and permission
checks retain precedence. Positive receipt fields and fixed launcher's generic
preflight-failure wrapper are unchanged; use `check_job_runtime` for the detailed
static diagnostic.

Thirty new direct/command cases cover enabled, enabled-and-forced and force-only
states across job, event, auth-group and automatic relationship tables; ordinary
metadata, redacted errors and between-query relation loss are included. Actual
PostgreSQL tests require a non-superuser owner without RLS bypass and roll back
their DDL. Forced auth-group cases prove the row is hidden before rejection and
visible after rollback. SQLite has no PostgreSQL RLS: explicitly identified
catalog-response references provide development coverage, not a product fallback
or real RLS qualification. Existing independent-phase fixtures preserve all their
assertions while isolating this new phase. The P88 write-mode check is also
isolated in RLS-specific cases and independently tested.

See [P87 source evidence](evidence/p87-qualification-2026-10-17.json).
Exact-commit all-six checks, complete private/native reports and independent
merged-main qualification remain required. Existing scientific, test, timeout,
coverage, skip, retry and resource budgets remain unchanged.

This is a startup observation, not continuous state fencing, a general policy
interpreter, arbitrary ACL/RLS support or proof of sequence permissions, complete
schema/data equivalence, restore or upgrade/rollback safety. D07 remains in
progress, including supported dependency findings, durable training/search,
full lifecycle/recovery, expert execution and release/value/customer gates.
