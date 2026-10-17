# Private role catalog trust (P89)

The startup authority check previously resolved `pg_roles`, `pg_has_role` and
equality operators through the connection search path. An owned PostgreSQL probe
demonstrates three bypasses with `public,pg_catalog`: a public role view masking elevated attributes,
a public membership function hiding an elevated session after `SET ROLE`, and
both together. These three probes retain actual session `CREATEDB` authority
while the preceding check accepts it. A separate ordinary-role probe hides membership in
`pg_read_all_data` through a public equality operator, even after catalog and
function qualification. This requires caller-controlled database objects
and search-path configuration; it does not establish an HTTP privilege exploit.

The shared check now pins role-name equality with `OPERATOR(pg_catalog.=)` and
an explicitly typed built-in name array, preserving the existing restricted-role
list. It explicitly uses `pg_catalog.pg_roles` for both catalog
references and `pg_catalog.pg_has_role` for both active/session membership checks.
The existing role policy, static redacted errors, successful receipts and service
launch behavior remain unchanged. There are no grants, role changes, schema
repairs, search-path changes or additional connections in the product check.

Twenty-four new cases cover the four substitution families through direct checks,
`check_job_runtime --require-application-role`, and fixed API, worker, dispatcher
and preflight launchers. Native PostgreSQL fixtures create real transactional
substitutes, verify the genuine elevated session and falsified unqualified
responses, and roll back their objects and `SET ROLE`. All 24 fail against the
preceding source; six operator-trap cases expose untrusted SQL execution as a
wrong diagnostic rather than claiming to hide the elevated `CREATEDB` fixture.
The separate ordinary-role proof establishes the membership bypass and its fix.
Focused native PostgreSQL passes 288 cases; SQLite references plus existing
adoption cases pass 388. SQLite provides explicit elevated-response references,
not PostgreSQL namespace semantics or a product fallback. The superseded local
full run was stopped before the operator fix and retained as incomplete; a fresh
final frozen-source full run passes 3,996 tests with six existing skips and no
failures or errors. Existing healthy, redaction and
session-role cases remain unchanged.

Management commands retain their existing transport/schema-before-role order;
the role denial blocks service execution. A draft test incorrectly required the
transport seam to remain unused for these command paths. Its 15 failures in each
focused matrix are retained separately, and the corrected tests assert the
existing order. No product ordering or prior assertion was changed.

See [P89 source evidence](evidence/p89-qualification-2026-10-17.json).
Exact-commit all-six checks, complete retained native/private reports and separate
merged-main verification remain required. Scientific workloads and existing
timeout, coverage, skip, retry and resource budgets are preserved.

This protects authority evidence at startup. It does not continuously monitor
privileges, establish original authenticated identity after privileged session
changes, qualify every database query or prove complete lifecycle/recovery.
D07 remains in progress; durable training/search, supported dependency findings,
upgrade/rollback/coordinated restore and release/customer gates remain open.
