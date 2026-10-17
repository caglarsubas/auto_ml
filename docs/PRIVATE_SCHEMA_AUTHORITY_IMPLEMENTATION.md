# Trusted initializer authority evidence (P96)

The schema initializer's role/TLS and database owner/encoding queries previously
resolved catalogs, functions and equality operators through caller-controlled
namespaces. Owned native probes execute the actual authority cursor block:
forged public TLS/role/membership views falsely attest an ordinary plaintext
session, an elevated CREATEDB fixture and an explicit-membership fixture as
acceptable. A separate actual owner statement/assertion accepts a genuinely
foreign database owner through a substituted owner function. The original row
and empty migration history are preserved. Administrative setup affects only the
disposable fixture cluster; these are isolated authority SQL/assertion proofs,
not full controller/bootstrap or verified-transport bypasses. Runtime/manifest,
graph/state/migration and controller publication are outside their scope.

Both initializer queries now bind catalog relations, database/PID/owner/encoding
functions, equality operators and the UTF8 name literal to PostgreSQL built-ins.
The declared database/user, TLS/login, elevated-role, strict no-explicit-membership,
owner and UTF8 policy is unchanged. Search path, query order, phase diagnostics,
timeouts, trusted advisory lock, helper/image binding, migrations and resource
budgets are unchanged. No grants, role attributes or database ownership are
changed by the product.

Fourteen new cases compile actual production SQL, fetches and policy assertions.
Eight exercise genuine role/TLS evidence and substitutes for roles, role-name
operators, membership, OID operators, public/temporary TLS statistics and a
combined PID/TLS source. Six exercise genuine owned/UTF8 evidence despite public
or temporary database catalogs, owner/encoding functions and name operators
reporting foreign state. Twelve regressions fail against the predecessor while
two genuine-state controls pass; all fourteen pass after the fix. The native
pytest fixture is CREATEDB, otherwise ordinary with no explicit membership; a
separate copied plaintext connection preserves the original connection's PID,
TLS and options. SQLite uses explicit unsafe or genuine response references,
without emulating PostgreSQL role, namespace or transport semantics.

Focused native tests pass 491 cases; reference/adoption tests pass 591. The
standalone probe additionally checks reported TLS/CREATEDB/membership fields
against genuine catalogs independently of overall rejection, and checks foreign
ownership independently of TLS. Before/fixed acceptance-only preliminary receipts
remain retained separately. Native DDL rolls back, preserving the owned seed row
and migration history. See
[P96 source qualification](evidence/p96-qualification-2026-10-18.json).

All six exact-commit checks, complete private/native reports and independent
merged-main qualification remain required. Existing real-TLS installation,
rollback, adoption and recovery receipts remain mandatory. Scientific workloads,
fixtures and timeout/coverage/skip/retry/resource limits are unchanged. No customer
installation is modified. These are selected-controller observations, without
continuous fencing or complete physical-schema/data equivalence. Other helper
boundaries, durable training/search, supported dependency findings, full
upgrade/rollback/coordinated restore and release/customer gates remain open;
D07 remains in progress.
