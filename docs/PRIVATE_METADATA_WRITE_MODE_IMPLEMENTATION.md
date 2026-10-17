# Private metadata write-mode guard (P88)

A read-only PostgreSQL connection can expose current history, schema, permissions
and RLS flags while refusing metadata writes. An owned ordinary application owner
reproduces writes failing with SQLSTATE `25006` while the preceding full startup
preflight accepts the connection. TLS/broker transport is stubbed in this local
proof; PostgreSQL settings, catalogs and write behavior are actual.

The shared private API/worker/dispatcher preflight now requires both
`transaction_read_only` and `default_transaction_read_only` to report `off` on
Django's metadata connection. It queries actual session settings after verified
metadata TLS and before history/schema checks or broker/cache contact. A mismatch
at this phase returns `job_metadata_read_only`; driver failures retain the
redacted `job_storage_unavailable` diagnostic. TLS errors retain precedence.
Positive receipt fields and the fixed service launcher's generic error wrapper
remain unchanged. Use `check_job_runtime` for the detailed static diagnostic.

The query explicitly names `pg_catalog.current_setting`. An actual PostgreSQL
fixture shows a public function falsifying the unqualified lookup when `public`
precedes the catalog; the qualified guard still rejects the read-only default.
This follows [PostgreSQL's schema search-path rules](https://www.postgresql.org/docs/17/ddl-schemas.html#DDL-SCHEMAS-CATALOG).

Both settings matter: an active transaction can remain writable after its session
default changes. A separate owned commit-transition proof shows the next
transaction becoming read-only and refusing a write. Default-only states do not
all imply a failing write in the already-active transaction. The supported
metadata profile requires both modes off. This does not apply a write requirement
to separate dataset-source connections.

The product only reads settings. It never changes transaction modes, reconnects,
probes writes, grants privileges, repairs schema or edits history. Earlier
LOCAL-setting reference evidence is retained separately and does not establish
persistence; the final session SET/commit proof establishes that claim.

Twelve new direct/command cases cover current-only, default-only and combined modes,
healthy settings, redacted query failures and two built-in shadowing cases. Actual PostgreSQL tests check
reported states and refused writes, or the still-permitted current write in the
default-only case. They restore owned session settings or roll back transactions
and verify no fixture row survives. They also prove blocked modes stop before
migration loading and broker contact. SQLite's explicit response references do
not provide PostgreSQL setting or function-namespace semantics or a product fallback. Existing
history/presence/permission/RLS fixtures isolate this independent new phase while
preserving all prior assertions.

See [P88 source evidence](evidence/p88-qualification-2026-10-17.json).
Exact-commit all-six checks, complete retained private/native reports and separate
merged-main qualification remain required. Existing scientific, timeout,
coverage, skip, retry and resource budgets are unchanged.

This startup observation does not fence subsequent settings changes, prove every
write will succeed, qualify storage capacity/availability, or establish failover,
primary fencing, sequence access, full schema/data or lifecycle equivalence.
D07 remains in progress, including supported dependency findings, durable
training/search, complete upgrade/rollback and recovery. Expert isolation and
release/value/customer gates remain separate.
