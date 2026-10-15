# Session and active database authority (P74)

The existing application-role preflight inspected `current_user` and its role
memberships. An owned PostgreSQL probe demonstrated that `SET ROLE
pg_database_owner` could select an ordinary active role while the session
principal retained elevated authority; the original preflight accepted it.

The privileged-role membership predicate now checks both `current_user` and
`session_user`. Membership includes the principal itself, so elevated session
flags and membership in the existing privileged-role policy are covered even
when the active role differs. Direct active-role flag checks, the six-boolean
result contract, strict false validation and static errors remain unchanged.
No roles, grants, schema, credentials or execution budgets are modified.

PostgreSQL distinguishes the permission-checking active user from the session
user, which normally initiated the connection. `SET ROLE` changes the former;
`MEMBER` tests direct or indirect membership regardless of immediate inherited
privileges. See the primary [identity and privilege function documentation](https://www.postgresql.org/docs/17/functions-info.html)
and [SET ROLE documentation](https://www.postgresql.org/docs/17/sql-set-role.html).

Eleven new cases cover the ordinary query result, both principal predicates,
actual PostgreSQL role switching through the direct helper, required management
preflight and all four fixed launcher roles; unswitched elevated references;
and redacted cursor/query failures. Every role-changing test resets its own
session in a finally block, including setup/assertion failures. SQLite uses
explicit decision seams rather than claiming PostgreSQL session behavior.
Existing private qualification supplies real ordinary-login positives for the
newly sealed services, alongside TLS, recovery, adoption and image checks.

The owned before/after probe only changes its own session role, resets it and
closes the connection; its temporary database/network are removed. It uses an
internal development fixture, not private TLS or customer installation proof.
The initial probe import-path error and first passing focused run before the
finally-boundary refinement are retained separately; final qualification uses
the same product query as that first passing run and the corrected harness.

The scope is current/session principals and `SET ROLE`. It does not bind an
original authenticated identity after superuser-controlled session authorization,
provide continuous privilege monitoring or resist privileged database tampering.
Durable search, lifecycle/upgrade/rollback/restore, expert isolation, release and
customer acceptance remain open. All-six exact-head checks, complete private
receipts and independent main qualification remain required.
