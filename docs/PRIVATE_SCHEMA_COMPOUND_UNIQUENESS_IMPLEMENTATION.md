# Declared metadata compound uniqueness

P104 extends the existing read-only private PostgreSQL startup guard to the
sealed migration graph's ordinary `unique_together` and field-based
`UniqueConstraint` declarations. The current graph has 11 compound groups,
covering memberships, scoped grants, auth through tables, dictionary keys,
review bundles/revisions and job event revisions.

The owned ordinary-role predecessor probe drops only project/actor uniqueness.
Startup accepts the schema; conflicting duplicate memberships are stored and
ORM lookup by project/actor becomes ambiguous. Primary keys, scalar uniqueness,
other constraints, column storage and all 31 migration records remain intact.
Rollback restores duplicate rejection and ordinary writes. Fixed startup emits
`job_schema_invalid` before broker access.

## Contract

Attach each declared group to its first local field in the existing storage
profile, using the same migration loader and catalog query. Preserve the query's
table-list parameter and four-column result shape. Each group requires a genuine
validated, nondeferrable, immediate UNIQUE constraint with exact local membership
and a live, ready, valid, unique, immediate backing index. Predicates and
expressions cannot substitute for ordinary group uniqueness.

Key membership is compared independently of order. Constraint names and non-key
INCLUDE columns remain immaterial to this selected integrity check. Default NULLS
DISTINCT is required when any member is nullable; either NULL mode is equivalent
when all members are non-null. No product nullable-field migration is introduced.

The selected declaration profile excludes conditional/expression constraints,
deferrable declarations, explicit INCLUDE/operator-class/NULL-mode declarations,
missing members and repeated members. They fail closed until separately
qualified, rather than being silently omitted. Existing non-unique model
constraints remain outside this check. Physical renamed/reordered/covering
variants of the current ordinary declarations are supported.

All catalogs, functions, comparisons, ordering operators and casts are bound to
pg_catalog. The guard performs no data read, repair, grant or schema rewrite.
P103 single-field uniqueness and earlier storage, identity, primary-key,
permission and row-security checks remain intact.

References: [Django unique constraints](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#uniqueconstraint),
[PostgreSQL constraint catalog](https://www.postgresql.org/docs/17/catalog-pg-constraint.html),
[PostgreSQL index catalog](https://www.postgresql.org/docs/17/catalog-pg-index.html).

## Evidence and limits

The 76 new direct/management-command cases cover each of the 11 groups;
wrong/smaller/larger membership, index-only, partial/expression and deferred
substitutes; catalog/operator/function forgeries; genuine renamed/reordered/
covering constraints; ordinary writes and duplicate rejection; nullable default
semantics; and unsupported sealed declarations. SQLite supplies explicit denial
and ordinary-write references, without emulating native catalog/index semantics.
The frozen predecessor misses 62 expected denials while 14 healthy controls pass.

A preliminary new catalog-shadow fixture copied a PostgreSQL pseudo-type; it now
snapshots only the required ordinary catalog columns. Retained local focused
failures also show WAL exhaustion in the old 128 MiB data tmpfs. The focused
harness now uses the existing full-qualification owned data-volume layout; CPU,
RAM, PID, original tests and test/timeout budgets are unchanged. Owned volumes
are removed after execution. Product CI resource configuration is unchanged.

Focused native qualification passes 747 tests; reference/adoption passes 847.
Full local native qualification passes 4,317 with six unchanged skips in
445.479s. Original case/skip identities and two-worker database/cache
isolation verify. Line/branch coverage: 75.79%/66.18%.

Qualification results and source hashes are retained in
[P104 source qualification](evidence/p104-qualification-2026-10-19.json).

The ordinary NOCREATEDB probe uses actual PostgreSQL history, role, write-mode,
schema, permission and RLS checks. Fixed startup stops at the schema guard before
later checks. Initial TLS and broker responses are explicit fixtures over actual
plaintext; direct ORM operations establish physical integrity loss, not verified
transport, controller or endpoint admission. Actual CI transport and private
installation/recovery qualification remain separate evidence.

This selected-startup observation does not establish index operator-class or
collation equivalence, inheritance, arbitrary foreign-key/check/default/sequence/
trigger behavior, extra restrictive constraints, full schema/data equivalence,
complete write availability or later-state fencing. Existing scientific
workloads, test/skip inventories, resource/pool/coverage/retry limits and the
900-second full-suite deadline remain unchanged. Exact-head CI/private reports,
guarded merge and independent main qualification are required. D07 remains in
progress; full lifecycle, release and customer acceptance gates remain open.
