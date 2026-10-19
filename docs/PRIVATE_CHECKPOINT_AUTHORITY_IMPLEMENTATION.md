# PostgreSQL checkpoint-role authority

P109 excludes `pg_checkpoint` membership from the existing private
application-role admission profile. This predefined role grants server-wide
`CHECKPOINT` execution without changing the five elevated role attributes or
replication-parameter privileges checked previously.

The existing built-in-qualified, six-column query checks both `current_user`
and `session_user` through the conservative `MEMBER` policy. Direct, inherited,
switch-only and indirect membership cannot become an approved profile through
`SET ROLE` or restricted membership options. An unrelated role's membership
does not disqualify the application. Query shape, static errors, existing
command order and service-launch admission remain unchanged. Startup observes
authority; it does not repair grants or issue a checkpoint.

## Bounded proof and qualification

The retained predecessor proof uses an owned PostgreSQL 17 fixture. A separate
fixture administrator deliberately grants `pg_checkpoint` to an otherwise
restricted application login. Existing admission and the flagged management
command accept it; actual application `CHECKPOINT` succeeds, and independent
administrator control-file evidence confirms checkpoint LSN advancement.
Revocation restores SQLSTATE 42501, original membership, schema, rows and
migration history. This is an unsupported explicitly delegated authority
profile, not an exploit by a role without that grant.

The fix rejects admission with `job_application_role_elevated`. An unavailable
membership lookup retains `job_application_role_unavailable`, without leaking
database details. The flagged command still checks runtime/schema/broker before
role authority; rejection does not imply that the preceding broker probe was
avoided. Unflagged runtime checks remain separate current-state observations.

The physical qualifier appends 50 cases to the original 510, covering direct,
inherited, switch-only, transitive, session-only, active-only, disabled-option
and unrelated membership profiles; healthy origin/local controls; public-first
forged catalogs, membership functions and name equality; genuine membership
lookup denial; and restoration. Actual application checkpoint success/denial
controls distinguish effective use from the conservative membership policy.
Deliberately forced SQL after denied admission is a fixture control, not a
claim of service execution after rejection.

The host controller alone owns administrator access. The application process
receives only its restricted login and deliberately delegated test authority;
it has no administrator password or Docker socket. No public port or customer
installation is used. Initial TLS and broker responses are explicit fixtures;
actual private transport, installation, workers, recovery and browser behavior
require independent receipts.

The frozen predecessor passes 530 of 560 cases and misses 30 added admission expectations. The fixed matrix passes all 560. Focused native 869 and reference/adoption 969 pass; full native 4,439 passed with six unchanged skips in 252.386s. Original inventories and worker isolation verify. Exact-head CI, guarded merge and independent main remain required. See [P109 qualification](evidence/p109-qualification-2026-10-19.json). Preserve all original cases and scientific
assertions, workloads, skip/coverage/retry policies, resource/pool limits, the
900-second native-suite deadline and 120-second per-test deadline. Only
additive physical qualification changes are permitted. This bounded startup
profile does not certify all predefined roles, historical data integrity,
later-state fencing, complete recovery or release/customer acceptance. D07
remains in progress.

## Roadmap maintenance

Update the canonical `product-roadmap.json` and regenerate
`PRODUCT_DEVELOPMENT_ROADMAP.md` at each packet transition. Refresh the local
HTML tracker from the same source and verification receipts after local
qualification, publication/merge and independent main verification. Keep
in-progress packets separate from tested deliveries and preserve explicit
release/customer gates. The tracker must disclose a working-tree snapshot or
unavailable remote verification rather than displaying old green status as
current evidence.

Reference: [PostgreSQL 17 predefined roles](https://www.postgresql.org/docs/17/predefined-roles.html).
