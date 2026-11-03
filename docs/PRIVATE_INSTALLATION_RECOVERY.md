# D07-T04 — Coordinated installed recovery

P164 is in progress. The acceptance target is recovery of the supported synthetic
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

The fixed inventory remains 66 tasks. D07-T04 stays open until implementation,
regressions, the complete installed recovery scenario, all six exact-head PR
checks and independent automatic push-main qualification pass. The target is
4 done (6.1%); the current 3 done (4.5%) is unchanged during implementation.
