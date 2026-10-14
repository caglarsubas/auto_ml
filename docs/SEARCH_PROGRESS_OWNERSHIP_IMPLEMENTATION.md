# Search progress ownership (P63)

SFS and tuning previously updated the entry currently stored under a dataset ID.
A late callback could revive a terminal run, change its operation identity or
modify a later run. SFS also exposed error status before constructing its failure
diagnostic, allowing a new request to claim the dataset during that transition.

## Bound progress and cancellation

Both workers now retain their accepted progress object and operation UUID. A
shared updater checks object identity and UUID under the existing short admission
lock before publishing. Updates pin the accepted UUID. Callbacks can update only
a matching running owner, and keep it running until final publication finishes.
Terminal and stale callbacks are ignored; rejected SFS callbacks cannot write an
intermediate checkpoint.

Search and tuning cancellation read the bound owner's stop flag. A deferred old
worker cannot borrow a later operation's cancellation flag. Final progress and
failure transitions publish their fields together under the admission lock. SFS
constructs its failure diagnostic before exposing error status, so a new claim
cannot interleave with diagnostic publication. Tuning archive and secondary
storage-failure progress fields use the same owner check.

## Validation and limits

Twenty-eight new API regressions cover both handlers, terminal states, legitimate
subsequent claims, replaced/retokened/missing owners, callback UUID/state changes,
bound stop flags and diagnostic publication. All 155 focused checks pass. Twenty-one
selected cases fail against the preceding handlers; one selected reference case
already passed there.

Full SQLite and exact-head/private Linux qualification are recorded in the
associated source evidence. Independent main qualification is required after
merge. Scientific inputs, assertions, metrics, folds and timeout/coverage/skip/
browser-retry budgets remain unchanged. The admission implementation contributes
to the existing SFS basis fingerprint; implementation-mismatched resumes remain
inspectable and blocked.

This is process-local progress ownership. It does not provide distributed
leases, durable worker recovery or complete artifact/adoption fencing if a live
registry is forcibly replaced during execution. Publication remains subject to
the existing evidence contracts. D07 lifecycle/upgrade/restore, expert isolation
and release/value/customer gates remain open.
