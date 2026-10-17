# Trusted schema-state catalog evidence (P94)

The initializer's state function previously resolved several catalogs, aggregates,
operators and relation-class identifiers through caller-controlled namespaces.
Temporary `pg_class`/`pg_depend` substitutes can coherently hide an unapproved
public table. An owned ordinary NOCREATEDB-role probe executes the actual graph,
state and migration branch: the predecessor reports fresh, executes 31 migrations
and accepts current state while the foreign table and its row remain present.
The fix reports partial/foreign state and blocks fresh apply and current
verification before any migration call. An outer fixture rollback preserves the
original row and empty history. Runtime/manifest verification, authority, TLS and
controller receipt publication are outside this local proof.

Five state queries now bind extension, function, event-trigger, relation and
dependency catalogs to `pg_catalog`. Counts, owner lookup, comparison operators
and identifier/kind types use built-ins. The dependency class refers explicitly
to the catalog's `pg_class` OID, so a temporary relation named `pg_class` cannot
redefine that identity. Supported relation/dependency kinds, schema/owner policy,
state names, graph pins, atomic migrations, phase diagnostics, helper profiles
and resource limits remain unchanged. The actual caller search path is retained.

Nine new cases execute the actual state function against owned native objects.
Six reproduce hidden unsupported tables, orphan sequences, fabricated ownership
dependencies, functions, a zero-count aggregate and an OID join operator. Two
additional cases reject forged extension/event evidence as classification
authority while retaining genuine current state; a healthy temporary-object
control remains current. Against the predecessor, eight regressions fail and the
healthy control passes; all nine pass after the fix. Source DDL rolls back with
the owned row and recorded migrations preserved. SQLite cases are explicit
genuine-state response references, not PostgreSQL catalog/substitution semantics.
Focused native tests pass 467 cases; reference and adoption tests pass 567.

See [P94 source qualification](evidence/p94-qualification-2026-10-17.json).
Final-source full tests, all six exact-commit checks, complete retained
private/native reports and independent merged-main qualification are required.
Existing scientific workloads, fixtures and timeout/coverage/skip/retry/resource
budgets remain unchanged. Existing real-TLS schema initialization, rollback,
account/adoption and recovery receipts remain mandatory. No customer installation
is modified.

This hardens state-catalog observations by the selected controller. It is not
continuous fencing or full physical-schema/data equivalence. Other authority and
advisory-lock SQL remains outside this change. D07 remains in progress, including
durable training/search, supported dependency findings, complete upgrade/rollback
and coordinated restore. Release/customer acceptance remains separate.
