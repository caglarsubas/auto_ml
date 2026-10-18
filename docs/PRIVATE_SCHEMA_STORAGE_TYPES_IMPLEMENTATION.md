# Physical metadata storage types (P97)

Current migration records and present column names do not establish compatible
physical storage. Eight owned PostgreSQL substitutions demonstrate this boundary:
boolean to text, integer width, varchar to text, jsonb to json, timestamp with to
without time zone, UUID to text, varchar to an array, and a same-named public
varchar domain. Sixteen API/command regressions fail against the predecessor;
four healthy/extra-column controls pass. The schema-presence guard now rejects
these substitutions with the existing `job_schema_invalid` before broker/cache
access. It does not repair schema or data.

Expected base types come from the selected sealed migration graph's final model
state, loaded without a database connection, plus the migration recorder.
Runtime auto-created auth through-model IDs can differ from historical DDL: an
initial runtime-model-only candidate falsely rejected three healthy bigint IDs.
The retained native failure prompted this authority correction, without changing
existing test assertions or fixtures. A corrected catalog diagnostic reports 232
required fields and zero mismatches. Unsupported field declarations fail closed.

The existing read-only catalog query compares exact PostgreSQL built-in type
OIDs, binding catalogs, operators and identifier types to `pg_catalog`. Domains
and arrays cannot substitute for plain storage. The four-field catalog response,
first parameter containing required table names, relation visibility, ordinary
public-table requirement and permissive extra-column policy are preserved.
Admission order, result shapes, diagnostics and execution budgets are unchanged.
Type modifiers/lengths, constraints, defaults, indexes and complete schema/data
equivalence remain outside this check.

Twenty new cases pass through both startup API and management command. Native
DDL rolls back while preserving a seed user's password/boolean and migration
history. The native pytest fixture has CREATEDB solely for disposable test
database creation. SQLite supplies explicit compatible/incompatible response
references; it does not emulate PostgreSQL OIDs, casts or domains. Focused native
checks pass 511 cases, and reference/adoption checks pass 611. The full local
reference suite passes 4,081 tests with six existing skips under unchanged limits. See
[P97 source qualification](evidence/p97-qualification-2026-10-18.json) for full
results and preliminary-failure provenance.

The separate ordinary-role owned-database probe runs actual history, write-mode,
schema, permission and row-security checks. Its initial TLS attestation and broker
are explicit response fixtures over a disposable plaintext connection. With all
31 migrations current, the predecessor accepts a boolean replaced by text and
reaches the broker fixture; the fix stops with `job_schema_invalid` before that
fixture. The ORM reads the text `"false"` as a truthy Python string; this is an
ORM observation only. Both probes preserve the original row and history. It is
neither verified transport nor full controller admission or endpoint authorization
proof. Administrative fixture setup and cleanup affect no customer installation.

All six exact-commit checks, complete private/native reports and independent
merged-main qualification remain required. Existing real-TLS installation,
rollback, adoption, failure controls and recovery receipts remain mandatory.
Scientific workloads and timeout/coverage/skip/retry/resource limits are unchanged.
This is a selected-startup observation without continuous fencing. Type modifiers,
other physical schema properties, full upgrade/rollback/coordinated restore and
release/customer gates remain open; D07 remains in progress.
