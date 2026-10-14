# Operation-bound tuning history (P61)

Tuning previously replaced one current result file. P61 retains terminal
completed, stopped and error evidence under a canonical operation UUID before
publishing the current result or live terminal state. Later iterations retain
the preceding archives and legacy files.

## Publication and recovery

The existing synchronized JSON writer now shares its no-overwrite archive
publication with tuning. A temporary file is serialized without nonfinite JSON
constants, synchronized and linked exclusively to its operation path; the
containing directory is synchronized. Identical retries validate the existing
record and reconcile directory synchronization without changing bytes or inode.
Conflicting or malformed evidence is refused and retained for inspection.

New tuning archives use the same strict state/shape contract as recorded results.
Nonterminal or contradictory evidence cannot be archived as terminal. The exact
archive reference is included in the archived/current record and status response.
Project artifact registration follows successful file publication and must
succeed before the current pointer or terminal completion advances. Protected
media downloads retain the existing project roles and dataset ownership checks.

An archive or ownership-registration failure leaves the preceding current result
intact and exposes an operation-correlated `history_evidence_write` failure.
An original search exception is preserved if saving its failure history also
fails; that secondary failure is recorded separately as `failure_history_write`.
Existing current-file saving failures retain their `final_evidence_write` or
`failure_evidence_write` stages and cannot overwrite another operation's archive.

## Evidence and limits

Thirty-six new regressions cover terminal states, identity/shape validation,
concurrent publication, conflicting retries, file/directory faults, current-save
ordering, failure diagnostics, legacy/later-iteration preservation, registration
failure/reconciliation and actual project-scoped media downloads. All 146
focused checks pass; eight selected cases fail against the preceding tuning
handler. Existing handler fixtures reaching the new registration boundary use
an actual test database. Their assertions and scientific data are unchanged.

The full controlled SQLite suite passed 3,351 cases with six existing skips,
zero failures, 75.18% line and 65.27% branch coverage
in 195.639 seconds. Exact-head private Linux and independent main
qualification remain required. Coverage, skip, timeout and retry limits remain unchanged.

The archive records computation/refit evidence. Model candidate publication
still precedes the terminal archive; this change does not make candidate
adoption, database registration, file history and current-pointer saving one
transaction. A current-save failure can leave a completed computation archive
alongside a live publication error. The saved archive does not prove current
adoption or successful publication of the current pointer. Failed registration
can leave durable bytes without a downloadable artifact registration; a later
exact retry can reconcile it.

This is not a complete crash-safe operation journal or distributed search owner.
Missing historical evidence is not reconstructed. D07 installation lifecycle,
full upgrade/rollback and coordinated recovery, expert isolation, release/value
and customer acceptance gates remain open.
