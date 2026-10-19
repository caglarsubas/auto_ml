# Declared metadata foreign keys

P105 extends the read-only private PostgreSQL startup guard with the sealed
migration graph's foreign-key metadata. The current graph declares 38 keys,
including nullable references and auto-created auth through tables.

The owned ordinary-role predecessor proof removes only the membership actor
foreign key. Startup accepts the schema and a direct ORM write creates an orphan
whose related user cannot be found. Every primary key, scalar UNIQUE constraint,
all 11 compound UNIQUE groups, other constraints, column storage and all 31
migration records remain intact. Rollback restores the foreign key, which rejects
the orphan at atomic commit. Fixed startup reports `job_schema_invalid` before
broker access.

## Selected contract

Use the same sealed migration loader and existing catalog query. Store each
foreign key's target table/column with its local field; require both to belong to
the managed schema contract. Ordinary `ForeignKey` and `OneToOneField` relations
with database constraints are supported. Unconstrained or other relation forms
require separate qualification and fail closed. No product migrations change.

For each declared pair, require a genuine validated single-column foreign key
with exact local and referenced column numbers and the declared ordinary public
target relation. The selected Django PostgreSQL profile uses DEFERRABLE INITIALLY
DEFERRED, MATCH SIMPLE and NO ACTION for both database update/delete actions.
Immediate/initially-immediate, alternate match/action, wrong local/target/schema,
compound and unvalidated replacements cannot silently inherit this profile.
Constraint names remain immaterial; genuine renamed/recreated keys are supported.

Django's ORM `on_delete` behavior is separate from database actions. The selected
runtime DDL and real catalog are recorded with the proof; the deferred control
tests rejection when its atomic transaction commits. Nullable relations retain
their default NULL behavior. Ordinary same-project/other-actor and
same-actor/other-project writes and existing duplicate rejection remain supported.

All catalogs, operators, casts and existing functions remain bound to pg_catalog.
The query keeps its first table-list parameter, second storage-profile parameter
and four-column result. The guard reads no application rows and performs no DDL,
repair, grant or secret/value diagnostic.

References: [PostgreSQL constraint catalog](https://www.postgresql.org/docs/17/catalog-pg-constraint.html),
[PostgreSQL foreign-key declarations](https://www.postgresql.org/docs/17/sql-createtable.html),
[Django foreign keys](https://docs.djangoproject.com/en/5.2/ref/models/fields/#foreignkey).

## Qualification and boundaries

Focused native qualification passes 869 tests; reference/adoption passes 969.
Full local native qualification passes 4,439 with six unchanged skips in
261.516s. Original case/skip identities and two-worker database/cache
isolation verify. Line/branch coverage: 75.79%/66.18%.

The 122 new direct/management-command cases cover missing keys for all 38 pairs;
wrong local/target columns, alternate schemas, compound/unvalidated constraints,
timing/match/actions and catalog/operator substitutions; genuine names/recreation
and extra keys; ordinary writes; invalid-reference rejection at commit; nullable
references; and unsupported unconstrained declarations. The frozen predecessor
misses all 110 expected denials while 12 healthy controls pass. SQLite provides
explicit denial and ordinary-write references without emulating PostgreSQL
catalog semantics. Qualification results and source hashes are retained in
[P105 source qualification](evidence/p105-qualification-2026-10-19.json).

The owned NOCREATEDB proof exercises actual history, role, write-mode, schema,
permission and RLS startup checks on its healthy/predecessor paths. Fixed invalid
state stops at the schema guard before later checks. Initial TLS and broker
responses are explicit fixtures over actual plaintext; direct ORM operations do
not establish transport, controller or endpoint admission. Actual CI transport,
private installation and recovery qualification remain separate evidence.

This is selected foreign-key catalog metadata, not complete referential-integrity
enforcement qualification. RI trigger integrity/enabled state, replication/session
modes, equality operator-class/collation semantics, extra restrictive constraints,
inheritance/partitions, full data/schema equivalence, write availability and
later-state fencing remain outside this check. These boundaries must remain
explicit even when genuine fixture writes reject invalid references.

All original tests, assertions, fixtures, scientific workloads, skip/case
inventories, resource/pool/coverage/retry budgets, 900-second native suite and
120-second per-test limits remain unchanged. Exact-head all-six CI and complete
native/private reports, guarded merge and independent main qualification remain
required. D07 remains in progress; full lifecycle, release and customer gates
remain open.
