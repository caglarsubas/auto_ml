# Private PostgreSQL TLS evidence trust (P90)

The private startup TLS query previously resolved its statistics view, backend
PID function and equality operator through the connection namespace. An owned
ordinary PostgreSQL application role reproduces plaintext metadata connections
receiving `private_metadata_tls: verified` through public or temporary
`pg_stat_ssl` views, including a combined public PID function substitution.
PostgreSQL TLS state, migration history, schema, permissions and connection modes
are actual in this proof; only broker transport is stubbed. It requires control
of database objects/search paths and does not establish an HTTP privilege exploit.

The query now explicitly uses `pg_catalog.pg_stat_ssl`,
`pg_catalog.pg_backend_pid()` and `OPERATOR(pg_catalog.=)`. Its evidence must refer
to the actual metadata backend. Plaintext still returns the existing static
`job_metadata_tls_required` before mode, migration, schema, broker or cache work.
Driver errors remain redacted as `job_storage_unavailable`. Existing role checks,
successful receipts, ordering and launcher behavior are unchanged.

Eight new direct/management cases cover public and temporary views, combined
view/PID-function substitution, and an untrusted comparison-operator trap. Six
view cases demonstrate false TLS evidence; the two operator cases demonstrate
untrusted SQL execution and the wrong diagnostic rather than claiming another
local plaintext-to-TLS bypass. All eight fail against the predecessor. The
isolated prototype passes 296 native PostgreSQL cases before adoption. Final
source passes 296 focused PostgreSQL cases, 396 SQLite/reference and adoption
cases, and the full local suite: 4,004 passed, six existing skips, no failures or
errors.

Native tests open a separate plaintext connection to pytest's owned database,
including when its default fixture uses TLS. Transactional shadow objects roll
back, the copy closes, and the original connection's settings, backend PID and
TLS state are preserved. This changes no product connection configuration or
private TLS requirement. SQLite cases are explicit TLS denial references, not
PostgreSQL namespace/TLS semantics or a product fallback. Existing healthy TLS,
redaction, role and schema assertions remain unchanged.

See [P90 source evidence](evidence/p90-qualification-2026-10-17.json). Exact-commit
all-six checks, complete retained private/native reports and independent main
verification remain required. Scientific workloads, fixtures and existing
timeout, coverage, skip, retry and resource budgets are preserved.

This is startup evidence for the current metadata connection. It is not
continuous connection monitoring, every-query namespace hardening, failover or
full lifecycle/recovery qualification. D07 remains in progress, including durable
training/search, supported dependency findings, upgrade/rollback/coordinated
restore and release/customer gates. No customer installation is modified.
