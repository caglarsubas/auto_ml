# Native publication work deadline (P81)

Native integrity and CSV-scoring workers checked their 120-second cooperative
work budget during execution, but successful terminal publication only fenced
the database lease and request expiry. Waiting for publication locks, checking
authority or preparing the result digest could cross the work deadline and
still adopt a successful result. The predecessor PostgreSQL reproduction
records 22 late-success failures and 19 passing references.

Both worker success paths now pass their original monotonic deadline into
publication. Under the existing queue lock, publication checks that deadline
before authority work and again after authority checks and result preparation,
immediately before adopting a result. Equality counts as expired. A current
attempt that exceeds its work budget receives the existing terminal blocked
`job_time_budget_exceeded` receipt, clears its lease and adopts no result or
digest. It cannot automatically consume another attempt. Results that reach
the boundary before the deadline retain their existing bytes and digest rules.

Existing lease ownership, cancellation and request-expiry fences take
precedence. An expired lease remains untouched for reconciliation; cancellation
and request expiry retain their existing outcomes. Unexpected publication
failures still leave uncertain work leased rather than inventing completion.
Internal callers that exercise lease fencing without an execution deadline
retain the existing call contract; every native worker success path supplies
its own attempt deadline. No monotonic timestamp is persisted across processes.

Forty-one new cases execute the real integrity/scoring paths and move only the
work clock at publication entry, queue-lock acquisition, model/source authority,
authority recheck or result hashing. They cover exact/late deadline refusal,
publication just before the deadline, cancellation/expiry precedence and
unexpected-failure recovery. An existing package-reader probe now accepts and
asserts the success deadline while retaining its original assertions. Local
draft fixture failures are retained separately from the final qualifications.

This is a transition-time fence, not a promise that a database commit completes
by the deadline, forced interruption of blocked I/O, or a new retry policy.
The 120-second work budget, 180-second lease, Celery limits, admission/attempt
limits, scientific workloads, timeout/coverage/skip gates and browser retries
remain unchanged. Existing runtime fingerprints bind the changed worker source;
historical receipts remain inspectable, and queued requests from an older
runtime retain the existing fail-closed runtime-change behavior.

Source qualification is recorded in [P81 evidence](evidence/p81-qualification-2026-10-16.json).
All-six exact-head/private receipts and independent main qualification remain
required. D07 lifecycle/upgrade/rollback/restore, durable search, expert execution,
release and customer-acceptance gates remain open.
