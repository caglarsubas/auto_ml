# PostgreSQL replication-parameter authority

P108 extends the existing private application-role admission query to exclude
`SET` and `ALTER SYSTEM` authority for `session_replication_role`. A connection
in healthy `origin` mode can still possess authority to change enforcement
later. P107 checks actual mode; P108 checks the declared role profile.

The same six-column query now includes built-in
`pg_catalog.has_parameter_privilege` evidence in its elevated-role predicate.
Existing membership checks cover both `current_user` and `session_user`,
including indirect membership. Effective/PUBLIC privileges and parameter grants
held by reachable membership roles cannot disappear behind `SET ROLE` or
`NOINHERIT`. The existing conservative `MEMBER` policy is preserved, rather
than interpreting membership-option restrictions as profile approval. An
unrelated role's parameter privileges do not disqualify the application.
Catalogs, functions, operators and text types remain bound to PostgreSQL.

Unsupported authority emits `job_application_role_elevated`. Unavailable lookup
evidence retains `job_application_role_unavailable` without database details.
Startup never grants, revokes or repairs authority. The flagged management
command and fixed service launchers retain their existing runtime-before-role
order: role rejection blocks service execution, but does not promise that the
earlier runtime/broker check was avoided. Unflagged runtime remains a separate
current-state check.

## Reproduction and qualification

The frozen P107 predecessor starts with a restricted role, healthy deferred
foreign keys and denied ordinary parameter SET (SQLSTATE 42501). A separate
administrator of the owned fixture deliberately grants replication-parameter
SET authority. Real role admission and the flagged command accept it while
mode is still `origin`. The role then changes mode, commits an orphan visible
to an independent `origin` connection, and returns to `origin`. Role flags,
defaults, memberships, all 152 trigger OIDs/attributes, 38 declared foreign keys,
other constraints/columns and 31 migration records remain unchanged.

The fixed role query rejects that capability while mode is still healthy. Any
subsequent deliberately forced direct SQL in the proof is an integrity control
after admission denial, not a service bypass. P107 continues to reject actual
`replica`. The proof removes its orphan, revokes the temporary grant, restores
the exact fresh parameter ACL catalog and verifies normal deferred-FK and
compound-uniqueness enforcement with original rows/history intact.

Append 70 physical cases to the existing separately administered qualifier:

- Healthy `origin`/`local`, direct/PUBLIC grants, inherited and switch-only
  membership, transitive membership, session-only and active-only authority,
  and unrelated-role controls for both parameter privilege types.
- Direct role admission and the actual flagged management command, with real
  metadata checks and an explicit initial TLS/broker response fixture.
- Public-first forged parameter/membership functions and name equality, alone
  and combined, with zero forged-function side effects.
- Genuine revoked lookup execution permission, static redaction and restoration.

The predecessor passes all original 440 physical cases and 20 new controls,
but misses 50 new expectations. Roles, memberships, parameter/function/table
ACLs and original schema state are restored. The host controller alone holds
administrator access; the application gets only its own password and the
deliberately delegated capability under test. No Docker socket, public port or
customer installation is used.

The original scientific suite and workflow stay byte identical. Only the two
physical qualification helpers receive additive cases; removing P108 additions
restores their P107 bytes. Original case/skip identities, workloads, assertions,
resources, pools, coverage/retry budgets, the 900-second full native deadline and
120-second per-test limit are preserved. Source hashes and qualification states
are recorded in [P108 qualification](evidence/p108-qualification-2026-10-19.json).

This is bounded role-profile admission for one parameter. It does not attest
all parameter/predefined-role authority, repair historical rows, fence later
changes or certify controller/endpoint/transport behavior from response
fixtures. The physical ALTER SYSTEM cases attest privileges without writing
server configuration. Actual private TLS, installation, recovery, workers and
browser workflows require their independent receipts. D07 and broader
lifecycle/release/customer gates remain open.

References: [PostgreSQL privilege inquiry functions](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE),
[parameter grants](https://www.postgresql.org/docs/17/sql-grant.html).
