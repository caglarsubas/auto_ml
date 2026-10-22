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
success, failure or cancellation. Native integrity and CSV-scoring verification
receive the same bounded metadata reader; the manifest digest uses the captured
bytes, with bounded rechecks that retain the final manifest-change fence.
Each native metadata read checks the accepted manifest digest. Missing-file and existing budget reason
codes are preserved. CSV capture and scoring semantics are unchanged; default
non-job/offline verification retains its existing reader.

The helpers live in the existing runtime-fingerprinted service module. New
regressions cover late FIFOs, symlinks and directories, growth during metadata
reads, missing/oversized inputs, normal metadata/hash receipts, and descriptor
cleanup after failure or cancellation. FIFO probes use exclusively owned forked
children with controlled metadata/worker seams and no database work; their
three-second join only detects blocking and does not change worker/test budgets.
Four additional regressions reproduce the downstream verifier's reopen gap in
the first PR head. A further regression preserves rejection when a manifest
changes during artifact verification; the final change includes thirty-four new cases.
Only an owned child is terminated if the predecessor blocks. Full private
qualification remains required for PostgreSQL, immutable images, TLS, scoring,
installation, recovery and cleanup.

This does not provide atomic ancestor resolution, a stable filesystem snapshot
or a deadline on kernel I/O for regular files. Native model/purifier/calibrator
loading and non-job readers still require protected filesystem custody; this is
not a sandbox or a complete hostile-filesystem qualification. Protected artifact roots, expected
digests and external resource limits remain required. No customer installation
or stored dataset is changed. D07 remains in progress; durable search,
lifecycle/upgrade/restore, expert and release/customer qualification remain open.

## Pinned package parents (P132)

Native package metadata, evidence and worker artifact hashing now open files through P131's no-follow directory descriptors. Capture pins the configured storage root and every relative parent, then opens the final file relative to its pinned parent. Lexical root normalization prevents trailing separator/dot forms bypassing root no-follow. Outside-root and traversal paths fail before any open. A late parent/root symlink is rejected; renaming an already-opened parent cannot redirect its subsequent file open.

The existing manifest/publication/evidence limits, regular-file checks, metadata/change digests, aggregate hash budget, authority/cancellation/deadline checkpoints and failure receipts remain. Every acquired descriptor has explicit cleanup. The helper already belongs to the runtime-fingerprinted CSV module; no new runtime dependency or untracked execution module is introduced.

103 additive cases exercise real owned parent/root races, original pinned bytes, root suffixes, special/missing parents, descriptor cleanup, invalid paths, header admission and worker publication/hash behavior. Two existing package-test fault-injection adapters resolve relative opens through their real directory descriptors; all original assertions, fixtures, workloads, limits and test identities are preserved. The exact adapter patch is audited against the retained original file.

Configured-root and ancestor custody remain trusted. This is not an atomic content snapshot, a bound on kernel I/O, hostile root-ancestor/mount-namespace qualification or model-deserialization isolation. Model/purifier/calibrator loading and non-job/offline readers retain their existing custody requirements. No stored dataset or customer installation is changed. D07, release and customer acceptance remain open.
