# PostgreSQL statistics-role authority — P112

Frozen P111 passes all 660 original physical cases and fails 34 new admission
expectations. A separate fixture administrator deliberately delegates
`pg_read_all_stats` or `pg_monitor`; the otherwise restricted application can
then read a synthetic administrator session's query where PostgreSQL previously
returned `<insufficient privilege>`. Revoking authority restores redaction.

The sole product change adds `pg_read_all_stats` to the existing built-in-qualified,
six-column current/session application-role predicate. Conservative `MEMBER`
checks also exclude indirect membership through `pg_monitor`, switched roles
and authority retained by the session principal. Startup emits existing static
errors and never changes grants or session activity. The flagged command keeps
its runtime-before-role order; rejection does not promise that its prior
runtime/broker check was avoided.

## Qualification boundary

Append 54 physical cases to the unchanged 660-case matrix: direct, inherited,
switch-only, transitive, session-only, active-only, disabled-option and unrelated
roles; direct and session-only `pg_monitor`; public-first forged catalog/function/
operator evidence; genuine unavailable membership lookup; and restoration.
Admission is exercised through both the real role helper and the flagged command.

The host controller alone owns administrator access and the synthetic observer.
It independently observes the canary query; the application process has neither
administrator credentials nor a Docker socket. Direct activity reads under
deliberately delegated authority demonstrate capability, including forced reads
after rejected admission. They do not represent service execution after denial.
Roles, memberships, scoped catalog/function/table ACLs and metadata rows restore;
the observer and all owned containers/networks are removed. No customer data,
public port or installation is used. Initial TLS and broker responses in this
physical fixture are explicit response fixtures, separate from private-runtime
qualification.

This is named-role profile admission, not proof of privilege escalation without
an administrator grant, complete statistics-view confidentiality, custom view/
function grants, historical access auditing, grant repair or continuous fencing.
Other predefined/parameter authority and full D07/lifecycle/release/customer gates
remain open.

Preserve all original scientific case/skip identities, assertions, workloads,
resource/pool/coverage/retry budgets, the 900-second native suite limit and the
120-second per-test limit. Require local qualification, all-six exact-head CI
with complete native/private reports, guarded merge and independent automatic
push-main qualification. Current delivery states are recorded in the canonical
roadmap and retained receipts.

References: [PostgreSQL 17 predefined roles](https://www.postgresql.org/docs/17/predefined-roles.html),
[statistics visibility](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-STATS-VIEWS).

## Local qualification

All 714 physical cases pass. Frozen P111 passes the 660 originals and misses
34 new admission expectations. Native: 4,439 passed/six unchanged skips in 300.541s;
focused PostgreSQL/reference: 869/969; frontend: 651 and production build.
Original inventories, worker isolation, unchanged lint and roadmap checks pass.
See the [source receipt](evidence/p112-qualification-2026-10-19.json). Exact-head
CI, merge and independent main qualification remain pending.
