# Reliable native metadata validation (P79)

Native metadata could escape the invalid-input boundary in two ways. The JSON
decoder raises `RecursionError` for unsupported nesting, which was not handled
as a known input failure. JSON the decoder accepts could then exceed the Python
call-stack limit in evidence-scope traversal. Admission could return an internal
error; a worker could retain a lease until recovery instead of recording a known
terminal refusal.

Native admission, evidence parsing and bounded bundle verification now share a
decoder wrapper that converts only a decoder nesting failure to `ValueError`.
Existing API and worker handlers retain their static invalid-input responses.
The evidence-scope walk uses iterators in the same depth-first order, checks all
relations and preserves cross-project denials without depending on Python call
depth. Auxiliary traversal storage follows nesting depth rather than copying
wide containers. Shared acyclic values remain unchanged; internally constructed
cycles still raise an unexpected recursion error. Capture/execution failures
outside JSON decoding keep their original uncertainty/recovery boundary.

Thirty-seven new cases cover actual decoder overflow, decoder-supported deep
evidence, authorized and foreign references, real HTTP admission, durable
terminal receipts, duplicate execution, fresh-request recovery, normal values,
syntax-error compatibility, cycles and unexpected-error propagation. The
predecessor fails twenty-four cases and passes thirteen references. A draft
fixture that did not exceed this image's C decoder limit is retained separately;
the corrected fixture checks the actual decoder behavior. No runtime recursion
limit, byte limit, workload, timeout, retry, coverage or skip budget is changed.

This is native metadata validation, not a sandbox or a complete hostile-input
resource guarantee. Default non-job/offline JSON reading retains its existing
behavior. Existing filesystem custody, bounded reads, manifest-change checks,
authority checks and external resource limits remain necessary. D07 remains in
progress; durable search, lifecycle/upgrade/restore, expert and release/customer
qualification remain open.
