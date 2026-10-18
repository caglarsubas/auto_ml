# Required metadata generation (P100)

A required ordinary column can be replaced by a generated expression without
changing its storage type, modifier, nullability or migration history. An owned
NOCREATEDB PostgreSQL probe replaces `auth_user.password` with matching generated
storage, preserving the original password in an extra column. The predecessor
admits startup; a normal ORM password update then fails at the database. The fix
returns the existing `job_schema_invalid` before broker/cache access. It does
not repair the column or change data or migration history.

The current sealed private profile supports ordinary fields and identity-backed
keys. The migration-state contract now explicitly rejects generated model
fields: Django's `GeneratedField.get_internal_type()` reports its output field's
ordinary type, so the existing storage-type mapping cannot establish this
distinction. Both stored and virtual declarations are unsupported by this
profile; future generation support requires an explicit contract and separate
qualification.

The existing catalog-only query requires an empty `pg_attribute.attgenerated`
on each required column, using the built-in internal `pg_catalog."char"` type
and catalog equality operator. PostgreSQL identity keys use `attidentity`, so
genuine keys remain supported. Extra columns keep their existing policy,
including generated extras. The query retains its four-field response, first
table-list parameter, required-column/visibility/type/modifier/nullability
checks, diagnostic and startup order.

Twenty new API/command cases cover generated varchar, boolean, small integer,
nullable JSON, nullable timestamp and text columns; unsupported stored/virtual
model declarations; and genuine schema with identity inserts, ordinary updates
and generated extras. All sixteen denials fail against the predecessor while
four healthy controls pass. After the fix, focused native checks pass 571 cases
and reference/adoption checks pass 671. Full local reference tests pass 4,141
cases with six existing skips under unchanged limits. Native tests execute
actual transactional generated DDL; reference tests supply explicit denials and ordinary extra columns without
emulating PostgreSQL generation or identity semantics. Original rows and all
migration records survive rollback. Existing tests, assertions, scientific
workloads and operational budgets are unchanged. See
[P100 source qualification](evidence/p100-qualification-2026-10-18.json).

The ordinary-role predecessor probe executes actual history, write-mode,
schema, permissions and row-security checks. Fixed startup stops at schema
validation before later guards and broker access. Initial TLS attestation and
broker connection are explicit response fixtures over an owned plaintext
connection; the deliberate direct ORM update is physical mismatch evidence,
not full controller admission, verified transport or an endpoint bypass. No
customer installation is modified.

All six exact-commit checks, complete private/native reports and independent
merged-main qualification remain required. Identity modes, defaults, other
constraints, triggers, collations, complete schema/data equivalence and general
write availability remain outside this check. This is a selected-startup
observation without later-state fencing. Full lifecycle/restore and release/
customer gates remain open; D07 remains in progress.
