# D07-T03 — Staged upgrade and compatible rollback

P165 is in progress. D07-T03 acceptance is unchanged. The target is a real sealed
release/schema transition, interrupted execution without partial adoption, and
rollback that rejects incompatible state while preserving current data/evidence.
The inventory stays 66 tasks: 4 done/55 open/7 blocked until qualification.

The initial supported transition is an API-image upgrade with identical dependency
images, interpreter/dependency versions, application/data layout and scientific
execution code. Only explicitly reviewed, reversible physical index migrations
are supported. Other application/schema changes require their own compatibility
recipe; they cannot silently enter this path.

The destination is a separately initialized root. An exact plan binds source
backup, source/target images and migration graphs, the trusted migration runner,
code and resource limits. Source history is preserved. The source schema/data is
restored from trusted sealed code and encrypted binary data, then the reviewed
migration runs transactionally. A verified copy checkpoint prevents recopy after
a failed migration advances PostgreSQL's nontransactional migration-recorder
sequence; every application sequence must still match exactly. Pending transition
intent blocks adoption. A lost
commit/completion acknowledgement resumes only the same operation, verifies data
and artifact evidence, and never silently executes a changed plan.

Rollback uses a fresh quiescent backup of the currently upgraded installation and
reverses the compatible migration in another fresh root. It preserves post-upgrade
work and authority. Unknown graphs, changed code/data layout, irreversible or
non-index operations, occupied targets and divergent pending state are refused.
No arbitrary saved SQL schema or fitted Python is imported by a controller.

Acceptance requires native classification/regression export/scoring, account and
project authority, both transition directions, interrupted migration/publication,
stale plans, incompatible rollback, and idempotent adoption. Qualification release
reconstruction is disclosed. Customer upgrades, key custody, recovery objectives,
capacity, full D07 and release/customer acceptance remain separate gates.

## Operator workflow

1. Select exact native source/target image IDs and retain both independently
   verified offline image sets. Load them through the existing verifier. This
   recipe requires identical PostgreSQL, Redis and ingress images and locked
   Python dependencies. Do not substitute a tag or a newer dependency image.
2. Stop intake and gracefully stop/remove only the source installation's owned
   application services. Keep its dependency services available for the existing
   coordinated backup command. Retain the source root and externally held backup
   key. Keep the source quiescent through validation/cutover: the backup is the
   explicitly chosen authority point, not a live replication stream.
3. Render, initialize and start dependencies for a separate target installation
   using the target image set and new installation ID/root. Keep its artifact
   directory empty; do **not** run the fresh-schema initialization command and do
   not adopt application services. TLS credentials and database credentials belong
   to this destination. Source application rows are restored under that identity.
4. Render a transition plan using `private_installation_upgrade.py plan`. Supply
   `--archive`, `--expected-backup-sha256`, `--key-file`, `--source-plan`,
   `--expected-source-sha256`, `--target-plan`, `--expected-target-sha256` and a
   new private `--transition-plan` file. Review its exact image IDs, source/target
   graphs, index operations, current backup authority point and limits. Retain the
   returned plan digest separately. Inspecting image metadata has no database
   access; execution uses the non-elevated TLS database role.
5. Execute `private_installation_upgrade.py apply` with the same archive, key,
   target plan/digest, transition-plan file and
   `--expected-transition-sha256`. A pending intent blocks normal adoption. After
   interruption, repeat these exact inputs; changed inputs require review and a
   fresh destination. The controller publishes completion only after catalog,
   application-row, sequence and artifact verification. Its helpers are bounded
   to one CPU, 1 GiB RAM, 64 PIDs and 120 seconds per call; existing SQL timeouts
   remain 45 seconds with a 5-second lock timeout.
6. Adopt through the existing application-adoption controller, then verify TLS,
   project roles, retained evidence and export/scoring parity. Route customer
   traffic only after the responsible operator accepts the installation. Technical
   completion does not grant model-use approval. Retain the untouched source and
   backup until the organization's retention/rollback policy permits disposal.
7. For compatible rollback after new work, quiesce the **currently upgraded**
   installation and take a fresh coordinated backup. Prepare another empty root
   pinned to the previous image; render/apply the reverse transition from this
   current backup. The newer image remains the trusted migration runner. Reverse
   only the admitted index operations and preserve current application data,
   authority and evidence. Never restore an older pre-upgrade snapshot over new
   work. Incompatible code, row layout, migration history or dependency changes
   require a separate qualified recipe; they fail this controller's admission.

The first production migration adds `native_job_project_history_idx` for scoped
native job-history ordering. It changes physical indexing without changing model
state or scientific-runtime fingerprints. Django's
[SeparateDatabaseAndState](https://docs.djangoproject.com/en/5.2/ref/migration-operations/#separatedatabaseandstate)
is used deliberately; migration state remains synchronized with unchanged models.
The transition adds no general saved-SQL or expert-code execution interface.

## Qualification boundary

CI reconstructs the previous release's **exact allowlisted source bytes**, pinned
in `evidence/p165-reference-source.json`, on the current locked dependency image.
It reseals, exports and verifies a genuine offline source image set. The target
contains the real new migration. Both image IDs and schema digests differ; the
three dependency images remain identical. This repeatable synthetic release
fixture is disclosed and does not certify an arbitrary historical customer image.

The installed drill retains all original source-installation assertions, trains
and exports classification/regression candidates, migrates copied state, injects
an exception inside the migration transaction, loses commit/publication
acknowledgements and verifies adoption refusal until completion. It then creates
real scoring work after upgrade, backs up current data, rolls back to a third root
and checks original plus new history, role enforcement and prediction parity.
The new additional drill has a 600-second parent cap; the original installation,
recovery, native-suite and workflow limits are unchanged.

The qualification fixture removes only its temporary image references with parent
pruning disabled, then reimports and verifies the original API image from its
trusted tag-free offline bundle. This preserves the exact inputs required by
downstream tests on the supported Linux Docker profile. Keep the exact controller
revision with the reviewed plan for later replay and adoption.
