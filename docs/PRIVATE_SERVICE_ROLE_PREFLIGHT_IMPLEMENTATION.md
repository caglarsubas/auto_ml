# Database authority checks on every private launch (P73)

The fixed private launcher required a non-elevated application database role
only for its `preflight` adoption action. Later API, worker and dispatcher starts
still checked TLS, schema and broker connectivity, but omitted the role check.
The direct private worker/dispatcher shell entrypoint also omitted it.

Every fixed role now invokes `check_job_runtime --require-application-role`
after verifying the sealed runtime inventory and before service execution. The
direct native shell entrypoint requires the same flag. An elevated or unavailable
role check stops startup; the fixed wrapper retains its static preflight failure,
and the shell retains the management command's existing redacted diagnostic.
No service starts, migrations run or privileges change on rejection.

Sixteen new cases cover accepted/rejected launches of API, worker, dispatcher
and adoption preflight, actual shell entrypoint ordering, unchanged native worker
arguments, and actual PostgreSQL elevated-role rejection through the management
command. Transport/schema/broker calls and final process execution use explicit
test seams; existing private qualification separately exercises real ordinary
application roles and all services from the newly sealed image. SQLite retains
compatibility cases without claiming PostgreSQL authority qualification.

Initial fixture failures are retained: shell argv[0] is `sh` while its executable
is `/bin/sh`, and the isolated runner intentionally mounts `/tmp` non-executable.
A committed test-only shell seam invokes the controlled probe with its real
interpreter, so that filesystem restriction stays in place. The initial full
run was retired after the fixture defects were identified; no complete receipt
is claimed for that interrupted run. Final qualification uses the corrected
fixtures with the original resource, timeout, coverage, skip and retry budgets.

The existing current-role query is unchanged. These startup observations are
not continuous authority monitoring or resistance to privileged database changes
after a check. Credentials, installed services and customer data are untouched.
Durable search, full lifecycle/upgrade/rollback/restore, expert isolation, release
and customer acceptance remain open. All-six exact-head checks, complete private
receipts and independent merged-main qualification remain required.
