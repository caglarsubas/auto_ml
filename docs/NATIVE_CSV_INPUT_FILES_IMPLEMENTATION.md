# Native CSV regular-file capture (P77)

Native CSV input capture used a blocking path open. An owned FIFO with no writer
blocked both preparation and worker capture, including replacement after the
existing path checks. Preparation also runs during admission under the queue
serialization boundary, so this could occupy the API and delay unrelated jobs.

Capture now opens with nonblocking/no-follow flags and checks the opened
descriptor for a regular file before reading. FIFOs, directories, sockets and a
late final-component symlink fail with `job_input_unavailable`. The descriptor
has one explicit owner and closes after success, size rejection, stream failures
or a cancellation checkpoint. I/O diagnostics stay static; missing paths retain
the existing API failure boundary and durable worker reason. Existing authority,
byte limits, input digests, CSV parsing and scoring remain unchanged.

Twenty-two new capture cases and one durable-receipt regression cover actual FIFO blocking in exclusively owned forked processes,
late replacement, special files, exact regular CSV bytes and receipts, and cleanup
on failures. Forked probes inherit controlled metadata/authority seams and perform
no database work. A three-second fixture join detects the old blocking behavior;
only its own child is terminated on failure. This does not change existing application,
worker or test budgets. Initial CI caught a missing-input reason-code regression; the original private
assertion is preserved and the handler now preserves that existing diagnostic.
Existing full private qualification remains required for
actual PostgreSQL, scoring parity, recovery, TLS, installation and cleanup.

This closes special-file/final-component capture failures. It does not make all
ancestor resolution atomic, guarantee a stable filesystem snapshot, bound kernel
I/O on regular files, or qualify hostile filesystem mutation. Existing protected
root custody, expected input digest checks and external runtime limits remain
necessary. No existing dataset or installation is rewritten. D07 remains in
progress; durable search, lifecycle/upgrade/restore, expert and release/customer
gates remain open.
