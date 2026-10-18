# Declared metadata field uniqueness

P103 extends the existing read-only private startup schema guard. The sealed
migration graph currently declares two non-primary unique fields:
`auth_group.name` and `auth_user.username`. Neither declaration is nullable.
An owned ordinary-role predecessor probe removed only username uniqueness:
startup accepted the state, duplicate usernames were stored, and ORM lookup by
username became ambiguous. Primary keys, column storage and migration history
remained intact; rollback restored uniqueness and duplicate rejection.

## Contract

Derive uniqueness from each sealed local field, independently of a foreign
key's target. Primary keys retain their separate contract and do not need a
second UNIQUE constraint. Require the exact local field membership of a
validated, nondeferrable, immediate UNIQUE constraint with a live, ready,
valid, unique, immediate backing index, one key column and no predicate or
expression. Catalogs, identifiers, type casts and comparisons remain pinned to
pg_catalog in the existing single query. Names may differ and INCLUDE columns
remain supported. Index-only, wrong-column, compound, partial, expression or
deferred substitutes cannot satisfy this selected declaration contract.

[Django primary keys imply uniqueness](https://docs.djangoproject.com/en/5.2/ref/models/fields/#primary-key).
[PostgreSQL normally permits multiple NULLs in a unique field](https://www.postgresql.org/docs/17/indexes-unique.html).
For an explicitly nullable field declaration, require that default NULLS
DISTINCT behavior. NULL modes are equivalent for a non-null field, so both
remain supported there. No production nullable-field migration is introduced;
complete changed migration states and actual transactional PostgreSQL DDL test
these semantics. Extra columns remain permitted.

Mismatch keeps the static `job_schema_invalid` diagnostic and blocks before
broker/cache access. No runtime repair, schema rewrite or extra data read is
introduced. Existing identity, generated-column, nullability, modifier, type,
primary-key, permission, row-security and namespace checks remain in place.

## Evidence and limits

The 36 new direct/management-command cases include 24 expected denials and
12 genuine controls. Native cases use actual DDL, catalog shadowing and public
operator substitutions. Controls exercise renamed/covering constraints,
non-null NULLS NOT DISTINCT, extra unique columns, ordinary duplicate rejection,
shared non-unique email values and multiple foreign-key rows per user. Nullable
controls permit two NULL values while rejecting duplicate named values.
SQLite supplies explicit denial and ordinary-write/extra-column references;
it does not emulate native index, constraint, namespace or NULL-mode semantics.

The initial new nullable fixture mutated a shallowly shared migration Field;
wider checks exposed the leak. Its failed native report is retained. The fixture
now clones that field; no original test, fixture, assertion, scientific workload
or execution/coverage/skip/retry budget changes. The two-worker isolation receipt
and one 900-second full-suite deadline remain mandatory.

Focused native tests pass 671 cases; reference/adoption tests pass 771. Full local
native tests pass 4,241 with the same six existing skips in 216.181s.
Every original case/skip identity is preserved; worker isolation verifies. Line
coverage is 75.77%, branch coverage 66.12%.

The initial PR workflow passed all six checks, but its browser report retained
one failed keyboard-review attempt before a passing retry. The snapshot showed
review attempted before a dataset was loaded. Add an explicit assertion that the
saved pipeline is active before entering that flow. Existing authority assertions,
timeouts and retry limits stay intact; the original report is retained and the
zero-flaky qualification gate still applies to the revised exact head.

Results and source hashes are retained in
[P103 source qualification](evidence/p103-qualification-2026-10-18.json).
The separate ordinary NOCREATEDB probe exercises actual history, role,
write-mode, schema, privilege and row-security checks on the predecessor.
Fixed startup stops at the schema guard before later checks and broker access.
Initial TLS and broker responses are explicit fixtures over plaintext. Direct
ORM inserts establish physical integrity loss; they are not verified transport,
full controller admission or endpoint evidence. Rollback restores constraints,
original rows and all migration history; no customer installation is modified.

This is a selected-startup observation of declared field constraints, not full
schema or data equivalence. Arbitrary model/compound/foreign-key/check/default/
sequence/trigger constraints, index operator classes/collations, inherited
relations, extra restrictive constraints, complete write availability and
later-state fencing remain outside scope. Exact-head all-six/private reports,
guarded merge and independently qualified main remain required. Full lifecycle,
release and customer gates stay open; D07 remains in progress.
