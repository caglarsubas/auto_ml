# D07-T04 — Coordinated installed recovery

P164 is test-qualified. D07-T04 is accepted for recovery of the supported synthetic
Ubuntu 24.04 ARM64 installation after removal of its application/dependency
services and installation storage. A second, independently initialized root
must recover its database and artifact files from one encrypted backup, using
the same exact sealed images. Source storage must be unavailable to the restored
services. This is separate from a restart, a backup catalog check or component
restore fixtures.

The controller will accept only a separately trusted backup digest and an exact
approved restore plan for an empty target. Backups contain binary table data and
artifact bytes, never saved Python modules or executable SQL schemas. A fresh
schema comes from the sealed target runtime; schema/image mismatch stops before
data replacement. Restore uses the existing application database authority.
An empty target permits the sealed migration's exact QueueLock(id=1) singleton
and Django migration/content-type/permission seeds. Additional or altered lock
rows, accounts, projects, jobs, sessions and customer rows are refused.

A protected intent fences application adoption throughout recovery. Interrupted
database/artifact publication must resume only the same approved operation,
refuse divergent state and preserve completed evidence. A completed operation
must be idempotent. Credentials are supplied separately; rotating the Django
signing key invalidates pre-recovery sessions.

The initial recovery profile uses an empty artifact directory on the same
filesystem as its installation metadata, allowing atomic directory publication.
Separate mounted artifact filesystems require another qualification profile.
The database data is restored through the
[PostgreSQL binary COPY protocol](https://www.postgresql.org/docs/17/sql-copy.html)
using [Psycopg's transactional COPY interface](https://www.psycopg.org/psycopg3/docs/basic/copy.html).
It is restricted to identical sealed runtime/database images and the verified
column, constraint, index and sequence definitions.

Required installed scenarios include classification/regression export/scoring
parity, original account/project authority, immutable completed job results,
pending work with a naturally expired original lease, cancellation, empty
broker/cache reconstruction and duplicate-delivery refusal. Tampered input,
wrong keys/plans, mismatched schema/images, occupied targets and incomplete
recovery must stop before adoption. Raw data, secrets and backup keys never
enter public qualification reports.

The scope is a quiescent backup point with coordinated participating controllers;
privileged concurrent host changes are outside that boundary. Initial declared
byte/resource limits are technical acceptance limits, not customer capacity or
RPO/RTO promises. Operator key custody, external identity/revocation reconciliation,
actual customer recovery objectives, upgrade/rollback, full D07 and release
acceptance retain their separate gates.

The fixed inventory remains 66 tasks. Implementation, regressions, the complete
installed recovery scenario, all six exact-head PR checks and independent
automatic push-main qualification have passed. D07-T04 adds one accepted task;
operator/customer and broader release acceptance remain separate.

## Operator handoff

Use the exact image set and verified source plan from the accepted installation.
Record the chosen quiescent authority point and maintenance window. Remove all
application service containers through the owned installation's normal service
procedure; keep its managed database, broker and cache available. The controller
refuses a source or incomplete target with application containers present.

Provision an external, root-owned private directory and a random 32-byte backup
key in a root-owned regular file with mode 0400. Keep that key separately from
the encrypted archive and preserve the returned archive digest in independent
trusted storage. The backup and key must be outside the source installation.
The controller does not print either content.

The root controller's sequence is:

1. `private_installation_recovery.py backup` with the source `--plan`, its
   `--expected-plan-sha256`, `--key-file` and an absent external `--archive`.
2. Independently initialize the destination with exactly the same four images,
   new deployment credentials and signing key, fresh schema, no application
   accounts, an empty artifact directory, and no application containers.
3. `private_installation_recovery.py plan` with the destination plan/digest,
   archive/key, independently trusted `--expected-backup-sha256` and an absent
   `--restore-plan` output. Review that output's source/target, images, schema
   and chosen authority point; retain its exact returned digest.
4. `private_installation_recovery.py restore` with the same destination,
   archive/key, `--restore-plan` and `--expected-restore-plan-sha256`. An
   interrupted attempt may repeat only those exact inputs. Divergent state is
   refused, and an incomplete journal blocks application adoption.
5. After completion, adopt the installation through the usual pinned-plan and
   selected-CA procedure. Verify restored access, immutable exports and pending
   work. The technical completion receipt grants no production-use approval.

A completed restore replay returns its recorded completion without reverting
subsequent legitimate work. It is not a new health check. New signing keys
invalidate old sessions; password/project authority is restored as of the
chosen backup point. Review revocations and external identity changes since
that point before customer use.

Initial bounds: 64 MiB combined table/artifact bytes, 96 MiB encrypted envelope,
1024 artifact files, 2048 directory entries, 32 directory levels, and an empty
artifact root on the installation metadata filesystem. The data helper uses
one CPU, 1 GiB RAM, 64 PIDs, a read-only exact runtime and a 120-second invocation
cap. PostgreSQL statement/lock limits remain 45/5 seconds. No saved SQL schema,
expert module or fitted pickle is imported by the controller.

## Qualification evidence

PR #264 and independent automatic push-main passed all six checks. The exact
commits, artifact hashes, original case/skip identities, native durations,
installed recovery receipts and retained failed cleanup/bootstrap attempts are recorded in
[P164 qualification](evidence/p164-qualification-2026-11-03.json).

The fixed inventory now has 4 done/55 open/7 blocked tasks: 6.1% done, up from 4.5%.
The full D07 outcome, upgrade/rollback, customer recovery objectives and release
acceptance remain open.
