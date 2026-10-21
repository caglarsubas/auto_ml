# Native cancellation, recovery and operational handoff (P122)

The existing durable queue retains the same request identity through worker interruptions. Cancellation is attributable and idempotent. A running cancellation waits for acknowledgement or lease expiry; it dominates result publication. The dispatcher retries an expired lease within the original three-attempt, one-hour request and 120-second work budgets. Recovery recomputes partial training work; it has no trial checkpoint or authority to change inputs, runtime, approval or outcome-access history.

## Read-only review handoff

`GET /api/jobs/{id}/operational-handoff/?revision={observed_revision}` requires current project access. The response pins request/result hashes, state, revision, actor, event chronology, attempt limits, lease/expiry, source identifiers and protected-access counters. It contains no predictions, model, sealed bytes, row membership or arbitrary access parameters. A download additionally supplies the displayed `sha256`; changed revision, access accounting or authority blocks it. Responses use `Cache-Control: no-store`. SHA-256 detects changes; it is not a signature.

The job history panel exposes inspection and keyboard-accessible download. Refresh/reopen retrieves current state. Uncertain cancellation retains the same pending request; a handoff cannot start during that mutation. Inspection and download never dispatch, cancel, recover or approve anything. A failed read clears the displayed snapshot.

Started, failed and completed reservations all count as possible protected-outcome access. A process killed after reservation leaves an unresolved `started` receipt. A retry creates another receipt and discloses prior related access. Completed access does not guarantee that a result was published. Cancellation cannot erase inspection or establish an unused holdout. Every protected assessment remains exploratory.

## Operator and reviewer procedure

1. Reopen the exact job; do not create a replacement while submission or cancellation is uncertain. Retry the same pending request when access or service recovers.
2. For running/cancel-requested jobs, wait for worker acknowledgement or the retained lease deadline. The dispatcher handles bounded same-request recovery. Never edit lease, state, attempts or access records to force progress.
3. For failed/blocked jobs, retain the handoff and reason. An installation operator checks worker, dispatcher, broker, PostgreSQL, artifact availability and pinned runtime health using installation runbooks. This observation itself does not test service health.
4. Resolve the cause. Any new execution needs an explicit request within current project and independent-review authority. The handoff grants no recovery authority.
5. An independent reviewer traces exact result, request and access evidence. Success is technical completion; it does not imply scientific validity, confirmatory evidence, release, deployment or production-use approval.

## Qualification and remaining boundaries

Additive backend cases cover all states, role isolation, stale/tampered snapshots, read-only/no-model/no-payload reads, conservative access accounting and cancellation/publication fences. Additive frontend cases cover revision/digest pinning, denied downloads, context invalidation and pending mutations. A dedicated real browser workflow preserves existing populations and tests the keyboard handoff/download against actual workers.

The disposable private TLS fixture uses actual prefork workers and the dispatcher. A fixture-only checkpoint pauses each binary/regression assessment after its committed access reservation. Killing that owned worker process group, without editing a lease or clock, proves natural 180-second lease recovery, one publication and stale-token/duplicate fencing. Additional running assessments cancel through real session/CSRF APIs and acknowledge without publication; retries preserve their identity. Coordinated PostgreSQL/media restore verifies original outcomes, exact result/handoff hashes, cancellation and access records. Existing private and physical scenarios remain mandatory.

This proves the bounded numeric native profile on a synthetic installation. It does not migrate legacy training/SFS/broad HPO, qualify arbitrary customer recovery, trial checkpoints, confirmatory protocols, expert code, production promotion, upgrade/rollback, release or customer acceptance. D07 remains open.
