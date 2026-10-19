# PostgreSQL subscription-role authority — P111

Status: frozen P110 main reproduced the admission gap: all 610 original
physical cases pass and 30 new admission checks fail. The sole product
change adds `pg_create_subscription` to the existing role predicate. Fixed
physical and local regression qualification pass. Exact-head CI, merge and
independent main qualification remain pending.

## Boundary

The initial application-role profile is for DeclarAI's application and job
services. Logical-replication provisioning is outside that profile. Exclude
`pg_create_subscription` using the existing built-in-qualified, six-column
current/session membership query, conservative `MEMBER` policy, static errors
and runtime-before-role command order. Startup must only observe authority;
it must not alter grants, remove subscriptions or initiate replication.

PostgreSQL 17 permits non-superusers with effective `pg_create_subscription`
authority and database CREATE permission to create subscriptions. The bounded
fixture uses `connect=false`, `enabled=false`, `create_slot=false`,
`copy_data=false` and `slot_name=NONE`, with an absent fixture-only Unix socket
in its connection string. This tests actual catalog creation without a
publisher connection, replication slot, active worker or data copy.

The host controller alone has administrator access. The application process
has only its restricted login and explicitly delegated test memberships.
Direct, inherited, switch-only, transitive, session-only, active-only,
disabled-option and unrelated membership, database-CREATE dependency,
public-first forged lookups, unavailable evidence and restoration must be
qualified through the separately administered matrix. An independent administrator observes any
created definition and its owner/disabled settings before the application
removes it. Scoped catalog rows, ACLs, metadata and model rows restore. Five actual
definitions are independently observed and dropped; missing database CREATE
receives 42501 despite effective role authority. None of these definitions has
a slot or active worker.

This is an explicitly delegated unsupported role profile, not a no-grant
exploit, replication/egress demonstration, historical subscription scan or
continuous fencing. Initial TLS/broker responses in the physical qualifier are
fixtures; complete private deployment qualification remains separate.

Preserve all 610 original physical cases, original scientific case/skip
identities, assertions, workloads, resource/pool/coverage/retry budgets,
900-second full-native limit and 120-second per-test limit. Require local
qualification, exact-head all-six/native/private receipts, guarded merge and
independent main CI. D07, lifecycle, release and customer gates remain open.

References: [PostgreSQL 17 predefined roles](https://www.postgresql.org/docs/17/predefined-roles.html),
[CREATE SUBSCRIPTION privileges and disconnected mode](https://www.postgresql.org/docs/17/sql-createsubscription.html).

## Local qualification

All 660 physical cases pass; the frozen predecessor passes all 610 original
cases and fails 30 new admission checks. Native: 4,439 passed with six
unchanged skips in 236.406s. Focused PostgreSQL/reference: 869/969;
frontend: 651 plus production build. Complete unchanged lint, original
case/skip/isolation audit and roadmap validation pass. See the
[source receipt](evidence/p111-qualification-2026-10-19.json).

Direct SQL in the fixture is a deliberately forced capability control. It
does not represent service execution after denied admission. The guard
observes membership; it neither revokes authority nor audits prior definitions.
