# Bounded native package reads (P78)

Native package admission checked metadata paths before opening them. Workers
also checked evidence size before an unbounded text read and opened artifacts
directly for hashing. A final-component replacement could therefore follow a
symlink or wait indefinitely for a FIFO writer. Metadata growth after the size
check could allocate beyond the intended limit; grown evidence could be accepted.

Package reads now use a nonblocking, no-follow descriptor and verify its regular
file type before reading. Metadata reads check the opened file size and consume
at most the existing limit plus one byte, rejecting overflow before parsing.
The manifest/publication limits remain 1 MiB/64 KiB and evidence remains 8 MiB.
Hashing retains its 1 MiB chunks, aggregate byte limit and authority, cancellation
and deadline checkpoints. Descriptors have one explicit owner and close on
success, failure or cancellation. Missing-file and existing budget reason codes
are preserved. CSV capture and scoring semantics are unchanged.

The helpers live in the existing runtime-fingerprinted service module. New
regressions cover late FIFOs, symlinks and directories, growth during metadata
reads, missing/oversized inputs, normal metadata/hash receipts, and descriptor
cleanup after failure or cancellation. FIFO probes use exclusively owned forked
children with controlled metadata/worker seams and no database work; their
three-second join only detects blocking and does not change worker/test budgets.
Only an owned child is terminated if the predecessor blocks. Full private
qualification remains required for PostgreSQL, immutable images, TLS, scoring,
installation, recovery and cleanup.

This does not provide atomic ancestor resolution, a stable filesystem snapshot
or a deadline on kernel I/O for regular files. Protected artifact roots, expected
digests and external resource limits remain required. No customer installation
or stored dataset is changed. D07 remains in progress; durable search,
lifecycle/upgrade/restore, expert and release/customer qualification remain open.
