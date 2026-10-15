# Atomic search cancellation (P65)

SFS and tuning stop handlers previously checked a live status and then looked up
the dataset again to set cancellation. Completion and a fresh claim between those
steps could redirect the stop to a different operation. They also ignored an
explicit operation ID, allowing a stale caller to stop the current run.

## Cancellation contract

Both handlers now use the same short lock as admission and terminal publication
to select, check and signal one owner. A running owner remains running until the
worker finishes its cooperative stop; requesting cancellation does not release
admission. Repeating a matching stop is idempotent. The response carries the
operation ID captured in that transition.

The request body is an object. An optional `operation_id` must be a canonical UUID;
explicit null, invalid types and malformed/noncanonical IDs return 400 with
`invalid_stop_operation`. A supplied UUID that is no longer current, including a
missing live owner, returns 409 with `search_operation_changed`. Neither rejection
changes progress or signals a stop. Matching terminal owners are not modified.
No evidence files or models are written by cancellation.

Requests that omit `operation_id` retain the existing current-run semantics,
including SFS's missing-run 404 and tuning's `not_running` response. They gain an
atomic transition but cannot express which operation the caller intended. The
browser successor must bind requests to the displayed/accepted operation; this
packet does not claim stale-intent protection for legacy unbound callers.

## Qualification and limits

Fifty API regressions cover matching and legacy requests, duplicates,
admission preservation, stale and absent owners, invalid values/bodies, terminal
states, malformed JSON/media errors and other-dataset isolation. A real-thread
proof pauses cancellation while a terminal transition and fresh claim attempt to
proceed: they remain serialized,
the original owner receives the stop, and the new owner stays unchanged.

All 222 focused checks pass. Negative-before, full SQLite and exact-head private
qualification are recorded in associated evidence; independent main verification
remains required. Scientific assertions/data, resource and timeout/coverage/skip/
browser-retry budgets are unchanged. Admission implementation changes participate
in the existing SFS basis fingerprint: mismatched historical resumes remain
inspectable and blocked rather than silently replayed.

This is process-local cooperative cancellation, not distributed leases, forced
termination or durable worker migration. Process-loss recovery, complete
artifact/adoption fencing, D07 lifecycle/upgrade/restore, expert isolation and
release/value/customer gates remain open.
