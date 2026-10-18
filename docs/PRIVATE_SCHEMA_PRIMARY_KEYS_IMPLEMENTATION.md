# Declared metadata primary keys (P102)

Dropping a primary-key constraint leaves its column type, modifier, nullability,
generation and identity flags intact. An owned ordinary NOCREATEDB PostgreSQL
probe drops the manual queue-lock key: predecessor startup succeeds, a duplicate
key insert succeeds and ordinary ORM lookup becomes ambiguous. Fixed startup
returns `job_schema_invalid` before broker/cache access. The read-only guard does
not repair constraints, indexes, data or migration history.

Each managed model in the sealed migration graph, including auth through models
and the migration recorder, must declare exactly one concrete local primary key.
Composite declarations are unsupported by this profile and fail explicitly;
support requires a versioned contract and separate qualification. Foreign-key
primary keys use their local column. Runtime through-model auto-field widths
continue to be governed by their historical migration declarations.

The existing catalog-only query binds the key to the actual table OID and exactly
one declared column number. It requires a validated, nondeferrable, initially
immediate `pg_constraint` primary key, joined to its actual `pg_index` row. That
index must be primary, unique, valid, ready, live and immediate, with one key
attribute and no expression or predicate. Catalog names, array comparisons and
identifier types are explicitly bound to `pg_catalog`. Constraint/index names
are not prescribed. Extra included index attributes and extra columns remain
permitted; a UNIQUE constraint alone is not a declared primary key.

The response remains four fields with the table list as its first parameter.
Existing visibility, relation kind, storage type/modifier, nullability,
non-generated storage and identity checks retain their meaning and startup order.

Thirty-eight new API/command cases cover missing manual/auth/through/recorder/
bigint/UUID/text/relation keys; unique-only, wrong-column, composite and deferred
substitutes; forged catalog and array-operator evidence; unsupported sealed
composite declarations; and healthy genuine, renamed and covering-index keys.
Healthy controls exercise implicit keys, foreign-key writes, manual-key lookup
and duplicate rejection. Native tests execute actual transactional DDL and
namespace substitutions; dependent foreign keys removed by fixture CASCADE return
on rollback. Reference tests supply explicit denials and ordinary extra columns,
without emulating PostgreSQL constraint, index, namespace or operator behavior.
Original rows and all migration records survive rollback. All 32 predecessor
denials fail while six healthy controls pass; fixture SQL errors are not counted
as defect evidence. Existing tests, fixtures, assertions, scientific workloads,
dependencies and execution/coverage/skip/retry limits remain unchanged.

Focused native checks pass 635 cases and reference/adoption checks pass 735.
Full local reference tests pass 4,205 cases with six existing skips under unchanged
limits. Local qualification results are retained in
[P102 source qualification](evidence/p102-qualification-2026-10-18.json).

The separate ordinary-role probe runs actual predecessor history, write-mode,
schema, permissions and row-security checks. Fixed startup stops at the schema
guard before later guards and broker access. Initial TLS and broker responses
are explicit fixtures over plaintext. Deliberate direct ORM operations establish
the physical mismatch; they do not demonstrate verified transport, full controller
admission or an endpoint bypass. Rollback restores one key constraint and one
original key row; ordinary lookup succeeds and duplicate insertion is rejected.
No customer installation is modified.

This is a selected-startup observation. Other unique/foreign-key/check/default/
sequence/trigger semantics, index operator classes/collations, complete schema/
data equivalence, general write availability and later-state fencing remain
outside this check. All six exact-head checks, complete native/private reports
and independent merged-main qualification remain required. Full lifecycle/
restore, release and customer gates remain open; D07 remains in progress.
