# Search worker launch failures (P62)

SFS and tuning previously registered running owners before constructing and
starting their background threads. A launch exception returned an uncorrelated
500, printed exception values and left the owner running indefinitely.

## Launch and ownership behavior

Both handlers now share a launch boundary. Construction, daemon-configuration
and start failures produce a bounded `worker_start` diagnostic carrying the
accepted operation, dataset and source execution identifiers. Service logs and
the public launch response omit exception values. Known startup failures return
503 with `search_worker_start_failed`; the matching current owner becomes error
and can be replaced by a fresh, explicitly requested operation.

The failure transition uses the same short lock as admission, checking both the
owner object and operation UUID. A failed old launch cannot modify a replacement
owner or a retokened entry. Thread creation/execution and diagnostics remain
outside the admission lock.

If a thread reports an identity, identity inspection fails, or the matching owner
has already reached a terminal state, launch is uncertain. The response is 503
with `search_worker_start_uncertain`. Its matching owner retains its state and
receives a separate `launch_failure` diagnostic. A possibly active running owner
continues blocking duplicate claims; completed/error evidence is not overwritten
by the launch exception. Stale ownership also returns uncertainty without
modifying the current entry.

Normal successful launches preserve the existing response, daemon-thread behavior
and scientific execution. A known failed launch executes no search/refit and
does not replace current files or earlier archives.

## Validation and limits

Twenty new regressions cover both handlers, startup stages, canonical IDs,
retry/correlation, redaction, replaced/retokened owners, uncertain identities,
terminal preservation and missing/stale claims. A real thread started before an
acknowledgement exception remains active and blocks a second claim until it
finishes. All 127 focused launch/admission/failure/history checks pass. Fourteen
selected API cases fail against the preceding handlers.

Full controlled SQLite passed 3,371 cases with six existing skips, zero failures,
75.22% line/65.33% branch coverage in 280.331 seconds.
Exact-head private Linux and independent main qualification remain required. Scientific data/assertions and time/skip/coverage/retry limits are
unchanged. The changed admission implementation is included in the existing SFS
basis fingerprint; implementation-mismatched saved resumes remain inspectable
and are blocked rather than silently replayed.

This guards process-local startup. It is not distributed ownership, a durable
launch journal, automatic recovery or cross-store publication atomicity. Uncertain
launches must not be treated as permission to retry active work. Process loss can
still remove live startup evidence; existing saved files retain their own
operation identifiers. D07 lifecycle/upgrade/restore, expert isolation and
release/value/customer gates remain open.
