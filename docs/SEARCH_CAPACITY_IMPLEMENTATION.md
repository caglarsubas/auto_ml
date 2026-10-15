# Bounded active search admission (P67)

SFS and hyperparameter tuning previously admitted one active operation per
dataset and search kind, with no bound across datasets. The API now admits at
most **two active search owners per process**, counting both registries together.
The existing admission lock covers duplicate detection, capacity counting and
owner publication; simultaneous requests cannot reserve the same remaining slot.
The same registry supplied more than once is counted once.

An existing operation on the requested dataset/kind retains its 409 conflict.
Otherwise exhausted capacity returns HTTP 503 with
`error_code: search_capacity_exhausted`, `status: busy`, the requested dataset and
the limit. It exposes no other project, dataset or operation identities. It does
not claim an owner, create a worker, replace current evidence or enqueue work.
The existing browser start-error handling displays the explanation. Retry is an
explicit user action after capacity becomes available.

Running owners remain counted after a cooperative stop and after an uncertain
worker launch. Successful terminal publication or a known failed launch frees
logical capacity under the same lock. Completed, stopped and failed history
remains inspectable without consuming a slot. All start/resume paths use the
same final admission check after their existing validation.

This bounds accepted active searches, **not physical thread lifetime or memory**.
Input loading and validation precede admission; terminal workers can still be
closing their connections. Candidate parallelism and existing container limits
are unchanged. This process-local limit is separate from the durable native job
lease limit. The supported private API profile still uses one API worker; this
does not enable multiple API processes, distributed leases, durable search
recovery, fairness between projects, forced cancellation or a queue. Uncertain
owners are deliberately retained rather than inventing released capacity.

The admission module remains part of SFS implementation provenance. Existing
results remain inspectable; checkpoints with a different implementation basis
cannot silently resume under the new code.

Seventeen new cases cover both endpoints, same/mixed/other search kinds,
non-disclosure, preserved evidence, cooperative stop/terminal transitions,
duplicate precedence, launch uncertainty, retained terminal history, repeated
registry arguments and twelve simultaneous real admission threads. Six endpoint
cases fail against byte-identical predecessor admission/view implementations.
Existing scientific assertions, timeouts, workload sizes, resource budgets,
coverage gates, skip limits and browser retry budgets are unchanged.

Exact-head CI/private runtime receipts and independent merged-main qualification
remain required. Full D07 installation/upgrade/rollback/restore, durable search,
expert isolation, release and customer acceptance gates remain open.
