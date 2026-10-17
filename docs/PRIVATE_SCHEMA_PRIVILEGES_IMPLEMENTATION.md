# Private managed-schema privilege guard (P86)

Current migration records and physical tables do not establish that the runtime
role can use them after a restore or grant change. An owned PostgreSQL fixture
reproduces all four failures: the non-elevated application owner loses SELECT,
INSERT, UPDATE or DELETE, PostgreSQL denies the corresponding operation, yet the
preceding full startup preflight accepts the database. TLS/broker transport is
stubbed in this local reproduction; history, catalogs and permission denials are
actual PostgreSQL behavior.

The shared private API/worker/dispatcher preflight now requires effective
table-level SELECT, INSERT, UPDATE and DELETE on the current profile's managed
nonproxy tables, automatic many-to-many tables and migration recorder. Presence
and permissions share one required-schema discovery function. Four independent
PostgreSQL predicates require every operation, including effective inherited
rights; one available operation cannot satisfy the others. Required public
relations must all appear in the result. Earlier history and physical-presence
checks retain precedence.

A permission mismatch at this phase blocks before broker/cache contact with
`job_schema_privileges_invalid`. Catalog/driver errors retain the redacted
`job_storage_unavailable` diagnostic. Positive preflight receipt fields remain
unchanged. The check reads catalogs only; it never grants/revokes privileges,
changes ownership, repairs schema, modifies migration history or reads model rows.
The current supported installation uses a non-elevated application owner.
Column-only/custom service ACL profiles are not introduced by this change. Use
`check_job_runtime` for the detailed static diagnostic; the fixed service
launcher's existing generic preflight-failure wrapper remains.

Thirty new direct/command cases cover each revoked operation on native
jobs, events and an automatic auth relationship, healthy permissions, redacted
catalog failure and actual relation loss between presence and permission reads. Actual PostgreSQL tests require a non-superuser test owner and
roll back real REVOKE statements. SQLite has no PostgreSQL grants: its explicitly
identified development references supply catalog responses for existing tables,
not a production fallback or a claim of real permission enforcement. Existing
history, presence and transport fixtures isolate the independent privilege phase
without changing their assertions. The separate P87 RLS phase is also isolated
here and exercised by its own actual PostgreSQL tests. P88 write-mode checks
are similarly isolated and independently exercised. Full hosted native/private qualification
independently checks the packaged roles and fresh Linux installation.

See [P86 source evidence](evidence/p86-qualification-2026-10-17.json).
Initial reproduction-harness import, broker-initialization and column-name errors
are retained separately; the final full-startup reproduction completed with four
actual permission denials. Exact-commit all-six checks, complete retained
private/native reports and independent merged-main qualification remain required.

These startup observations do not fence later privilege changes or establish full
ACL equivalence, sequence access, row-level-security behavior, data visibility,
types/defaults/constraints/indexes, complete restore or upgrade/rollback safety.
Existing role-authority checks remain independent. D07 remains in progress,
including supported dependency findings, durable search, full lifecycle/recovery,
expert execution and release/customer gates. Existing scientific, timeout,
coverage, skip, retry and resource budgets remain unchanged.
