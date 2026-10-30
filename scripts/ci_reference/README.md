# Bounded P162 Mac-hosted reference pilot

This is the owner-approved experimental profile for PR #261 and its marked
automatic push-main qualification. Only the native PostgreSQL job is routed to
a fresh, disposable Ubuntu 24.04 amd64 VM on an ARM64 Mac. Four emulated vCPUs,
16 GiB RAM and at least 100 GB free disk are recorded; this is not native-amd64
hardware or customer capacity qualification. Existing tests, fixtures, skips,
coverage, retries, two workers, thread controls and the 900-second native child
cap remain unchanged. All original native steps and the other five jobs remain.

The host controller validates repository, source/base revision, workflow, actor,
automatic event, run and attempt against GitHub before arming root-owned guest
policy. `worker_guard.py` replaces the pinned runner's worker entry point and
validates the first job packet before starting the vendor worker. A single-use
lease prevents a second accepted job. Runner labels and workflow conditions are
not the admission boundary. Policy failure denies execution before checkout or
action preparation. Original job bytes are forwarded unchanged after admission.

The host signs a revision/run-bound execution profile; `verify_profile.py`
verifies its Ed25519 signature, scope, finite lifetime, controls and platform.
The private signing key and runner-administration credential remain outside the
guest and repository. Only a short-lived registration token enters the guest.
Registration is ephemeral and automatic updates are disabled for the pinned
runner. The PR and main use separate fresh disk overlays and registrations.

`proxy_server.py` enforces approved public package/GitHub endpoints outside the
guest. QEMU has no routed network, workspace shares or host Docker socket.
The proxy uses a fixed HTTPS DNS resolver, refuses non-public addresses, connects
the checked numeric address, and bounds concurrent connections, headers, bytes
and lifetimes. Bodyless HTTP Debian package GET/HEAD requests are restricted to
approved Debian hosts and forwarded to a verified TLS origin. Docker's original
build arguments are unchanged; only build commands receive client proxy config.
Runtime containers receive no injected proxy environment. The daemon is guest
owned; existing Mac services are preserved.

The controller tests exercise forged/missing/duplicate claims, pre-worker
refusal, wire-byte parity, lease exclusivity, signature tampering, expiry,
private-address rebinding, header smuggling and bounded proxy refusals. They
supplement the original application tests. Qualification still requires all six
exact-head checks, raw inventories and successful native exit, guarded merge,
then independent automatic main evidence. A timeout or missing receipt fails.
There is no automatic retry or broader self-hosted runner rollout.

Protocol reference: [pinned GitHub runner ProcessChannel](https://github.com/actions/runner/blob/v2.338.2/src/Runner.Common/ProcessChannel.cs).
Trust guidance: [GitHub self-hosted runner security](https://docs.github.com/en/actions/reference/security/secure-use).


The first Mac PR workflow (40992060920) refused admission before vendor startup
or checkout. The owner approved one additional diagnostic PR workflow on
30 October 2026. The guard now emits fixed stages/error classifications and
match/mismatch/absent/invalid-type results for eight fixed public claim names.
It never logs job values, payloads, exception messages, tracebacks or credentials.
Admission predicates and original controller tests remain; three tests cover
safe refusal diagnostics. The diagnostic guest/registration and evidence use a
separate ordinal. Another failure stops this additional allowance; no admission
relaxation, workflow rerun or further source head is authorized by it.


The corrective checkpoint replaces the unsupported internal `JobName`/YAML-key
assumption with explicit workflow/API-backed unique display identity. The host
verifier is published verbatim as `verify_job_identity.py` for independent review.
Before listener startup it checks the exact approved CI bytes and all six API
jobs against literal unique workflow names, the exact source/run, target queued
state/API ID and runner labels. The worker requires the resulting root-owned
identity proof and exact display, alongside all eight original scope claims,
expiry, vendor hash and single-use lease. Numeric API IDs are not equated to the
runner's internal UUID. Opaque internal names are no longer identity claims.

The owner continued from the concrete reviewed correction on 30 October 2026,
authorizing one corrective automatic PR run and conditional independent main.
Fourteen guard and eight host-verifier tests cover this mapping. Nine of the
previous twelve controller methods remain identical; three transparently revise
the incorrect internal-name expectation/identity fixtures. Application tests and
all existing qualification controls remain. Pre-listener proof receipts preserve
exact workflow/API/policy bytes for post-run independent verification. Failure
stops this corrective allowance without another head or rerun.
