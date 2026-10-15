# Refreshed native job expiry checks (P70)

Claim and terminal publication previously checked expiry before authority/runtime
validation. Publication could then wait for authority locks or prepare a result
digest and use its earlier eligibility decision after the lease or request had
expired. Reconciliation also captured its time before acquiring the queue lock.

Claim now checks request expiry again after successful authority and runtime
validation, immediately before assigning a lease. Expired requests receive the
existing failed `job_expired` receipt without consuming an attempt or starting
scientific execution. The new lease uses that fresh time.

Publication prepares its result and digest without changing durable job fields,
then samples time again. It rechecks the matching active lease and request expiry
before applying the result and terminal receipt. An expired lease leaves the
request and events unchanged for reconciliation; it cannot publish success or a
late authority-denial receipt. A still-current lease whose request has expired
records the existing failed `job_expired` outcome without adopting the result.
Current authority denials retain their existing blocked outcome. Cancellation,
fencing tokens, attempt/lease/work budgets and result digest semantics remain.

Reconciliation now samples its batch time after acquiring serialization, so a
wait for that lock does not exclude work already expired when its batch begins.
This remains a batch snapshot, not continuous observation of every later instant.

Twenty-five new cases cover native integrity and CSV-scoring jobs at the first
and source authority locks, authority recheck and result digest; exact deadline
equality; valid pre-deadline publication; authority denial after lease expiry;
claim expiry during authority/runtime validation; and delayed reconciliation of
running, cancelled and queued requests. Controlled clocks isolate the boundary
conditions without altering scientific workloads or timing/retry budgets. P69's
real PostgreSQL contention cases remain in the focused and full qualification.

These are refreshed transition checks under the existing metadata lock, not a
claim that a database commit completes by a wall-clock deadline or that external
scoring effects can be undone. No extra retry, promotion, lease renewal, schema
change or production use is authorized. Runtime fingerprints continue to bind
exact source; historical requests and results remain inspectable.

Exact-head/private and independent main receipts remain required. Full D07
lifecycle/upgrade/rollback/restore, durable search, expert isolation and release/
customer gates remain open.
