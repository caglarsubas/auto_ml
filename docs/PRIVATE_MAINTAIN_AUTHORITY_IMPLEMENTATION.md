# PostgreSQL maintenance-role authority — P110

P110 excludes `pg_maintain` from the existing private application-role profile.
The built-in-qualified, six-column query checks both `current_user` and
`session_user` using the existing conservative `MEMBER` policy. It rejects
inherited, indirect, switch-only and disabled-option membership, while an
unrelated role's membership does not disqualify the application. No schema,
settings, grants, startup SQL or service ordering changes are introduced.

Status: local final-source qualification passed. Exact-head CI, PR merge
and independent main qualification remain pending. D07, full lifecycle,
release and customer acceptance remain open.

## Retained predecessor reproduction

P109 / [PR #200](https://github.com/caglarsubas/auto_ml/pull/200) merged as
`ccf670d27351efdcdc36c199197cba952c9a1bc8`. Exact-head
[CI 39218919217](https://github.com/caglarsubas/auto_ml/actions/runs/39218919217)
and independent main
[CI 39222299623](https://github.com/caglarsubas/auto_ml/actions/runs/39222299623)
passed all six on attempt 1 with complete native/private receipts. Main native:
4,439 passed, six unchanged skips, 479.842s; physical matrix 560; frontend 651;
browser 37 first-attempt passes. The merged tree matches the qualified PR.

## Observed bounded gap

An owned PostgreSQL 17 development fixture gives the application schema usage
on one administrator-owned test table, without SELECT, UPDATE or direct table
grants. Ordinary `ACCESS EXCLUSIVE LOCK` initially fails with SQLSTATE 42501.
An explicit fixture-administrator connection then grants `pg_maintain`.

The five elevated role attributes, login defaults, replication-parameter
privileges, table ownership and table ACLs stay unchanged. Existing role
admission and the flagged management command accept the granted authority.
Actual ordinary-role `LOCK TABLE` succeeds; an independent administrator
session observes the granted lock and receives 55P03 when trying a conflicting
`ACCESS SHARE NOWAIT` lock. Ending the application transaction releases it.
Revocation restores actual 42501 denial and the original membership.

The temporary schema is removed. Target rows/ACLs, all original trigger and
constraint/column metadata, model rows and 31 migration records are preserved.
Normal deferred foreign-key and duplicate rejection controls still pass.
Owned Docker resources are removed; no public port or customer installation
is used.

This is an explicitly delegated unsupported role profile, not a no-grant
exploit. The development harness has an explicit administrator control
connection inside the harness; it is not the separately administered physical
qualifier. Initial TLS/broker responses are fixtures over plaintext, not
transport, controller/endpoint or complete threat-model qualification.

## Admission and physical qualification

Elevated membership fails with `job_application_role_elevated`; unavailable
built-in authority evidence fails with `job_application_role_unavailable`.
These static errors do not expose database details. The flagged management
command still checks runtime/schema/broker before checking role authority.
Unflagged runtime and schema checks remain separate observations. Admission
observes authority; it does not revoke grants, perform maintenance or fence
subsequent administrator changes.

The separately administered physical qualifier appends 50 startup cases to
all 560 original cases, preserving their expectations. It covers direct,
inherited, switch-only, transitive, session-only, active-only, disabled-option
and unrelated membership; healthy origin/local modes; public-first forged
role catalogs, membership functions and name equality; denied genuine lookup;
and restoration. Effective `USAGE` and conservative `MEMBER` remain distinct.

An administrator-owned table outside the application's metadata schema has no
table ACL or application SELECT/UPDATE grant. The application has schema
USAGE only, including explicit schema USAGE for switched fixture principals.
Actual application `ACCESS EXCLUSIVE LOCK` succeeds only with effective
maintenance authority. The host controller independently observes its granted
lock and receives 55P03 on a conflicting `ACCESS SHARE NOWAIT`; ending the
application transaction releases it. Missing effective authority receives
42501. Deliberately forced SQL after admission rejection is a fixture
capability control, not service execution after rejection.

The host controller alone has administrator access. The application runner
has only its restricted login and deliberately delegated test memberships,
without an administrator password or Docker socket. Metadata, ACLs, memberships,
parameter/function grants, role defaults, rows, trigger/constraint metadata and
migration history are restored; temporary fixtures and owned resources are
removed. These controls are over plaintext with explicit initial TLS/broker
fixtures; complete private transport/install/worker/recovery/browser receipts
are separate qualification evidence.

The frozen P109 source passes the original 560 cases and fails 30 new admission
expectations in the 610-case matrix. Candidate source passes all 610. Native regression: 4,439 passed with six
unchanged skips in 223.580s; focused PostgreSQL/reference: 869/969; frontend
651. Full unchanged lint and original case/skip/isolation audits pass. See the
[source qualification receipt](evidence/p110-qualification-2026-10-19.json).

Original scientific cases, skip identities, assertions, workloads, resource
and pool budgets, coverage/retry settings, the 900-second full-suite limit and
120-second per-test limit remain unchanged. Only two existing qualification
files gain additive coverage; removing P110's additions restores their exact
predecessor bytes. The sole product change adds `pg_maintain` to the existing
role predicate.

This is bounded named-role admission, not certification of all predefined or
object-level authority, historical integrity, continuous fencing, a no-grant
exploit or release/customer readiness.

References: [PostgreSQL 17 predefined roles](https://www.postgresql.org/docs/17/predefined-roles.html),
[LOCK privileges](https://www.postgresql.org/docs/17/sql-lock.html).
