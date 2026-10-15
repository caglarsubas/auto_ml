# Browser operation-bound cancellation (P66)

The browser previously posted an empty stop body and identified work only by its
dataset. P65 added an optional operation check at the server. This packet makes
the browser use it and prevents a missing JavaScript argument from silently
falling back to the legacy unbound request.

## Displayed operation and requests

SFS and tuning retain a dataset/operation pair from start/resume acknowledgements,
fresh running status, polling and active-process reattachment. Server metadata
must contain the exact requested numeric dataset ID and a canonical operation
UUID. Saved checkpoints and result history cannot provide stop authority.
Identities are cleared across dataset changes, new starts, restart, failure and
terminal transitions. Responses for a different current dataset are ignored.

Both HTTP service methods require an operation ID and also validate it at runtime:
an undefined argument would otherwise disappear during JSON serialization and
invoke the server's legacy path. Invalid identity sends no HTTP request. The
component blocks missing identity with a refresh explanation and suppresses
duplicate stop clicks while waiting.

Stop responses apply only while their dataset/operation pair is still displayed.
Acknowledgements must match that pair. A terminal response or an unverifiable
acknowledgement clears the waiting state and requires fresh status. A 409 exposes
the server explanation, clears stale authority and never triggers an unbound
fallback, refresh-and-stop or automatic retry. Tuning's HTTP service preserves
the original structured error instead of reducing it to a generic Error.

Polling that observes another operation clears the preceding stop wait. Delayed
responses from an earlier dataset cannot bind the current one. An older response
for the same dataset may require a subsequent status refresh; the server's exact
UUID check remains the final guard against signalling a newer operation.

## Qualification and limits

Fifty-two new service/component cases cover request identity, invalid runtime
arguments, conflicts, missing/foreign metadata, cached history, start/resume/
reattachment, polling, duplicate clicks, mismatched acknowledgements and delayed
responses during operation/dataset changes. All 651 frontend tests pass with the
existing global coverage gates. TypeScript, ESLint (zero errors) and the private
Angular build pass.

An isolated predecessor export fails 51 of the 52 new cases; one reference case
already passes. Only erased TypeScript overload declarations were added to that
comparison tree so the new tests compile against the preceding service signatures.
Implementation parameters and request/control bodies are unchanged. The focused
subset does not qualify global coverage; the full-suite result is the coverage
gate.

Backend/scientific code and assertions, operational budgets and existing browser
workloads are unchanged. Exact-head CI/private runtime and independent main
receipts remain required. Legacy non-browser callers may still use P65's unbound
API contract. Durable/distributed search recovery, full D07 lifecycle/upgrade/
restore, expert isolation, complete accessibility and release/customer gates
remain open.
