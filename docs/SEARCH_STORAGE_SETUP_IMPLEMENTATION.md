# Operation-bound search storage setup (P68)

Both search start endpoints created their result directory after accepting a
running owner and before entering the worker failure boundary. A directory
creation error therefore returned a request error while leaving that owner
running. It blocked retries and consumed logical capacity without executing a
search.

Directory creation now runs through an optional preparation callback inside the
existing search-worker wrapper, after thread-owned connection setup and before
scientific execution. Failures produce redacted `worker_storage_setup`
diagnostics, identify the accepted operation and transition only its current
running owner to error. Scientific work never starts. The wrapper still closes
worker-owned connections; a separate cleanup failure cannot replace the original
preparation diagnostic. Inline factories preserve caller connections as before.

A successful worker launch still acknowledges `started`. That acknowledgement
does not assert that storage preparation or scientific execution succeeded; live
status is authoritative. If preparation fails immediately, the next status read
shows the operation-bound error. The preceding result bytes remain inspectable
and are not replaced with a setup-failure artifact. Once storage recovers, an
explicit retry receives a new operation UUID and uses the unchanged two-owner
admission limit. There is no automatic retry or filesystem repair.

Seventeen new cases cover both APIs, three injected directory errors, actual
blocking files, preserved evidence, redaction, fresh retries with another active
search, stale/removed/replaced identities, preparation order in inline and real
threads, and independent cleanup diagnostics. Eight API cases fail against
byte-identical predecessor view/worker implementations. Existing connection,
launch, cancellation, admission and scientific regressions remain required.

This remains process-local execution. It does not journal setup failures across
process loss, guarantee successful storage access after directory creation,
introduce distributed search ownership, repair installations or complete D07.
Full installation/upgrade/rollback/restore, durable search, expert isolation and
release/customer gates remain open. Operational resources, timeouts, scientific
assertions, coverage/skip gates and browser retry budgets are unchanged.
