# PostgreSQL settings-role authority — P113

Frozen P112 passes all 714 original physical cases and misses 30 new admission
rejections after a fixture administrator deliberately delegates
`pg_read_all_settings`. The otherwise restricted application can then inspect
the disposable server's protected `data_directory`, `config_file` and `hba_file`
values through `pg_settings`, and read `data_directory` through `current_setting`.
Revocation hides the view rows and restores direct-read SQLSTATE 42501.

The sole product change adds `pg_read_all_settings` to the existing built-in-qualified,
six-column current/session application-role predicate. Preserve conservative
`MEMBER` checks, strict boolean evidence, static errors and runtime-before-role
command order. Startup observes authority without changing grants or settings.
P112 already excludes `pg_monitor` through its statistics-role membership; this
change covers settings authority without requiring statistics authority.

## Qualification boundary

Append 50 physical cases to the unchanged 714-case matrix: direct, inherited,
switch-only, transitive, session-only, active-only, disabled-option and unrelated
roles; public-first forged catalog/function/operator evidence; genuine unavailable
membership lookup; and exact scoped restoration. Exercise both the real role
helper and flagged management command. The command's prior runtime/broker check
retains its existing order and is not claimed to have been avoided.

The host controller alone owns administrator access. It independently observes
three paths belonging only to the disposable PostgreSQL server. The application
runner has no administrator credential or Docker socket. Direct capability reads
under delegated authority, including forced reads after denied admission, do not
represent service execution after rejection. Revocation restores hidden settings
and denied direct reads. Roles, memberships, scoped catalog/function/table ACLs
and metadata rows restore, and owned containers/networks are removed.

The P113 controls change no server configuration, read no files and exercise no
customer installation, host paths or external connection. Initial TLS/broker
responses remain explicit response fixtures; private-runtime qualification is
separate. Protected fixture paths establish the named-role capability, not
disclosure of customer secrets, complete configuration confidentiality, custom
grant certification, historical access auditing, grant repair or continuous
fencing. Other authority and full D07/lifecycle/release/customer gates remain open.

Preserve original scientific case/skip identities, assertions, workloads,
resource/pool/coverage/retry budgets, the 900-second native suite limit and the
120-second per-test limit. Require local qualification, all-six exact-head CI
and complete native/private reports, guarded merge and independent automatic
push-main qualification. Delivery states remain explicit in the canonical roadmap.

References: [PostgreSQL 17 predefined roles](https://www.postgresql.org/docs/17/predefined-roles.html),
[`pg_settings`](https://www.postgresql.org/docs/17/view-pg-settings.html).

## Local qualification

All 764 physical cases pass. Frozen P112 passes the 714 originals and misses
30 new admission rejections. Native: 4,439 passed/six unchanged skips in 237.003s;
focused PostgreSQL/reference: 869/969; frontend: 651 and production build.
Original inventories, isolation, unchanged lint and roadmap checks pass. See
the [source receipt](evidence/p113-qualification-2026-10-20.json). Exact-head CI,
merge and independent main remain pending.
