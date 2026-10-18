# Declared metadata nullability (P99)

Matching migration history, storage types and modifiers can hide incompatible
physical nullability. An ordinary-role owned PostgreSQL probe makes the nullable
`auth_user.last_login` column non-nullable while all 31 migration records remain
current. The predecessor admits startup and reaches the broker fixture, but a
valid default user write fails with an integrity error. The fix stops with the
existing `job_schema_invalid` before broker/cache access, without repairing the
column, changing data or rewriting migration history.

The disconnected sealed migration state now supplies each required column's
local-field nullability, including the non-null requirement of primary keys.
Storage types follow foreign-key targets; nullability follows the local field.
This preserves nullable actor/source references to non-null target keys. The
existing catalog-only query compares `pg_attribute.attnotnull` with that sealed
declaration. Operators, types and JSON extraction remain bound to `pg_catalog`.
Extra columns retain their existing policy, whether nullable or non-nullable.

Twenty new API/command cases cover four required columns made nullable, four
nullable columns made required, genuine migrated state and extra columns with
both declarations. All sixteen negative cases fail against the predecessor;
the four healthy controls pass. All twenty pass after the fix. Focused native
checks pass 551 cases; reference/adoption checks pass 651. Full local reference
tests pass 4,121 cases with six existing skips under unchanged limits.
Transactional DDL rolls back while preserving the seed username/password/authority/last-login
and migration history. SQLite supplies explicit denial references, without
emulating PostgreSQL catalog behavior. Existing assertions, scientific fixtures,
workloads and operational budgets are unchanged. See
[P99 source qualification](evidence/p99-qualification-2026-10-18.json).

The initial full run exposed a roadmap test fixture that used the synthetic
future packet ID P99. With P99 now real, that ID collided. The fixture now
chooses the next unused ID; all assertions are unchanged. The original failed
report is retained and the complete rerun passes.

The separate NOCREATEDB probe executes actual migration-history, write-mode,
schema, permission and row-security checks. Its initial TLS attestation and
broker connection are explicit response fixtures over an owned plaintext
connection. Its deliberate direct ORM write demonstrates the physical mismatch;
it is not full controller admission, verified transport or an endpoint bypass.
No customer installation is modified.

The four-field catalog response, first table-list parameter, required columns,
ordinary visible public relations, diagnostics and startup ordering remain.
All six exact-commit checks, complete private/native reports and independent
merged-main qualification remain required. Other constraints, defaults,
indexes, collations and complete schema/data equivalence remain outside this
check. This is a selected-startup observation without later-state fencing.
Full lifecycle/restore and release/customer gates remain open; D07 remains in
progress.
