# Declared metadata type modifiers (P98)

The base-type guard can accept changed varchar lengths or timestamp precision
because their PostgreSQL type OIDs remain unchanged. An owned ordinary-role
probe narrows `auth_user.username` from its sealed length 150 to length 1 while
all 31 migration records remain current. The predecessor accepts startup and
reaches the broker fixture; an owned ORM write within the model's declared length
then fails at the database. The fix stops with the existing `job_schema_invalid`
before broker/cache access. It does not repair the physical column or data.

The same disconnected sealed migration state now declares both base storage type
and modifier. Varchar(n) uses PostgreSQL's n-plus-four header representation;
unbounded varchar and the other supported declarations use modifier -1. The
catalog-only query compares both built-in type identity and exact modifier,
with catalog operators, types and JSON extraction bound to `pg_catalog`.
Unknown field declarations and invalid declared varchar lengths fail closed.
Historical auth through-table IDs still follow their migration declarations.

This initial private profile requires exact selected declarations, rather than
inferring general schema compatibility: wider/unbounded varchar and explicit
timestamp precision 6 are also different from the sealed declarations. Explicit
precision 6 can have the same representable precision as default -1; it is still
a different recorded modifier. Such changes require a versioned migration and
qualification. Constraints, defaults, indexes, collations and complete schema/data
equivalence remain outside this check.

Twenty new API/command cases cover shorter/wider/unbounded varchar, timestamps
with explicit precision 0/3/6, genuine migrated state and permitted extra
varchar(1) columns. Sixteen regressions fail against the predecessor while four
controls pass; all twenty pass after the fix. Focused native checks pass 531
cases; reference/adoption checks pass 631. Full local reference tests pass 4,101
cases with six existing skips under unchanged limits. Native DDL rolls back while preserving
the seed username/password/boolean and migration history. Existing fixtures,
assertions and scientific workloads are unchanged. SQLite supplies explicit
modifier-denial references without emulating native typmods or coercions. See
[P98 source qualification](evidence/p98-qualification-2026-10-18.json).

The separate NOCREATEDB probe executes actual PostgreSQL history, write mode,
schema, permissions and row-security checks. Initial TLS attestation and broker
are explicit response fixtures over an owned plaintext connection. The direct
ORM write deliberately demonstrates the physical mismatch even after blocked
startup; it is not controller admission, verified transport or an endpoint
bypass. No customer installation is modified.

The four-field catalog response, first table-list parameter, required columns,
ordinary visible public tables, extra-column policy, error/result shapes and
startup order are preserved. All six exact-commit checks, complete private/native
reports and independent merged-main qualification remain required. Existing
installation/TLS/failure/recovery and cleanup receipts, plus timeout/coverage/
skip/retry/resource budgets, remain unchanged. This is a selected-startup
observation without later-state fencing. Full lifecycle/restore and release/
customer gates remain open; D07 remains in progress.
