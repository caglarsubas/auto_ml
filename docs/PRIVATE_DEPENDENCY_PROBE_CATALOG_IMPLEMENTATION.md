# Private dependency probe catalog trust (P92)

The application dependency probe previously resolved PostgreSQL authority and
TLS evidence through caller-controlled namespaces. An owned reproduction of the
actual source query, fetch and assertion demonstrates seven false acceptances:
substituted role flags or role-name equality, hidden explicit membership through
a relation or OID comparison, and public/temporary TLS statistics or a substituted
backend PID. Separate owned profiles have an actual CREATEDB flag, an explicit
membership, or plaintext transport. The qualified candidate and final source
report the genuine fields and reject every scenario; transactional substitutions
roll back and the original owned role flags/membership remain intact.

This proof isolates the application's SQL and predicate. It does **not** establish
a bypass of the earlier administrator bootstrap or the helper's CA/hostname
verified transport. Those protections remain unchanged. No customer installation
is modified.

The query now binds `current_database`, `pg_stat_ssl`, `pg_backend_pid`,
`pg_roles`, `pg_auth_members` and its PID/OID/name comparisons to `pg_catalog`.
The nine-field result and Python predicate remain unchanged. The initial
dependency profile still prohibits every explicit role membership; the runtime
role helper has a different policy and is deliberately not substituted here.
Configured endpoints, TLS options, connection timeout, administrator checks,
static phase diagnostics, exact helper attestation, broker/cache behavior and
resource limits are preserved. No search-path, role, grant or database repair is
performed.

Seven new regressions execute the production authority block, rather than a
copied SQL/policy implementation. All seven fail against the predecessor and pass
after the fix. Native fixtures use a separate plaintext connection to the owned
CREATEDB test database, retaining the original connection/settings and rolling
back substitute objects. Its membership-view case fabricates incorrect evidence,
and its OID operator traps untrusted execution; actual hidden-membership
acceptance is independently established by the separate owned membership
profile. SQLite cases are explicit unsafe-authority response references, not
PostgreSQL semantics or a product fallback. Focused native tests pass 407 cases;
SQLite/reference and existing adoption cases pass 507.

See [P92 source qualification](evidence/p92-qualification-2026-10-17.json).
Final-source full tests, all six exact-commit checks, complete retained
private/native reports and independent merged-main qualification are required.
Existing scientific workloads, fixtures and timeout/coverage/skip/retry/resource
budgets remain unchanged. Existing real TLS dependency startup/adoption and
failure-control receipts remain mandatory.

This is a startup observation by the selected controller, not continuous
authority monitoring or every-query namespace hardening. Other owner/schema
initialization queries are outside this bounded change. D07 remains in progress,
including durable training/search, supported dependency findings, complete
upgrade/rollback and coordinated restore. Release/customer acceptance remains
separate.
