# Managed adoption operation serialization — P116

Managed application adoption now joins `dependencies/start.lock`, the existing
nonblocking advisory lock used by dependency startup and schema initialization.
It acquires the lock before any Docker operation and retains it through actual
runtime preflight, service startup, HTTPS readiness, final profile/dependency
checks and result construction. Success adds `managed_operation_serialized` to
the adoption receipt. All exits close the guard, including exceptions.

The guard pins the trusted installation and managed dependency directories. It
rejects changed ownership/modes, ACLs, nonregular/linked lock files and replacement
of the lock pathname after acquisition. Nonblocking no-follow opens prevent FIFO
or symlink lock inputs from blocking or selecting another object. It never
repairs an existing object or steals a held lock. Contention retains the existing
`dependency_operation_in_progress` error.

The preceding controller could proceed while startup/schema work held this
lock. Two before/fixed regression cases demonstrate that bypass and the missing
guard at first Docker access. Fourteen new cases cover the complete guard
interval, exception cleanup, private lock creation and unsafe inputs. Existing
adoption tests retain their assertions; only their simulated external host
boundary is extended for the new guard.

The actual owned Linux-root installation qualifier additionally holds the real
lock while all three public controllers attempt entry. Each must refuse before
startup. Repeated adoption verifies that the guard remains held during the real
CA/hostname-verified HTTPS check and is released after return. Container IDs,
process state, restart counts and startup/schema history must remain unchanged.
This adds a bounded check to the existing fixture; its 300-second controller
limit, full native suite's 900-second limit, per-test timeouts, six CI jobs,
workloads, original skip identities and physical matrix remain unchanged.

Historical operator-managed dependencies without a managed directory retain
their existing protocol and report `managed_operation_serialized: false`. No
new concurrency qualification is attributed to that scope. The advisory lock
serializes cooperating controllers; it does not fence administrators, direct
Docker commands or arbitrary database clients. It is not a maintenance,
backup/restore, upgrade/rollback or customer-deployment approval.

The next step is a read-only lifecycle readiness report for operator review.
Actual deployment targets, acceptable downtime, recovery objectives and external
storage/network controls require operator-specific acceptance. D07, release and
customer gates remain open. See the [source receipt](evidence/p116-qualification-2026-10-20.json)
and [roadmap ledger](product-roadmap.json).
