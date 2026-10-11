# Packaged private native jobs — P33

P33 runs the fixed private image's worker and dispatcher as separate disposable containers, through their unchanged manifest-verified entrypoint. The existing private PostgreSQL fixture now performs this check whenever `--private-api-image` is selected. The fixture uses its TLS-verified PostgreSQL and authenticated TLS job broker; it never adopts or modifies an installed service.

## Execution and evidence

The containers use an exact local image ID with `--pull never`, UID/GID 10001, a read-only root, no capabilities, no new privileges, two CPUs, 2 GiB memory and 256 PIDs. They receive only the fixture's read-only installation volume and writable synthetic artifact volume. They have no public port, source bind, Docker socket, API socket or observer-state volume. Qualification checks the daemon-reported configuration as well as task results.

An ephemeral observer runs trusted repository test code through stdin in the same fixed native runtime. Its state, expected scores and login cookies stay in a separate private volume that is destroyed with the fixture. This observer is a test harness, not an expert-code execution service. It creates actual native classification/regression models, assessment and bundles through the authenticated/CSRF-protected Django workflow. Fitting remains synchronous in the observer; P33 does not migrate training or search to queued execution.

The fixed dispatcher discovers durable requests and the fixed prefork worker processes ten synthetic jobs: native integrity checking, classification/regression CSV scoring, queued cancellations, changed/missing input rejection and current actor-authority rejection. Classification is calibrated; each scoring input has 650 rows with a different feature order. Full authorized HTTP receipts must match direct evaluated scoring within the existing `1e-12` absolute/relative tolerance. Replayed submissions keep their durable ID, authority, specification and history.

After initial completion, the controller stops its dispatcher, publishes twenty distinct duplicate deliveries, and waits for broker drain. It then requires a successful warm worker shutdown and checks the dedicated broker's queues and unacked records again with no consumer running. This final check closes the queue-pop-to-unacked visibility gap; a timed sleep or an empty queue alone does not establish acknowledgement. Terminal history, full results and artifact hashes must remain unchanged. This additional check does not replace the existing source-runner recovery scenarios or their actual completion-log checks.

## Dispatcher shutdown correction

A Python dispatcher running as container PID 1 previously had no explicit SIGTERM handler. The first packaged qualification reached task completion but rejected its forced shutdown. The command now handles SIGTERM/SIGINT, finishes its current bounded dispatch transaction, checks a lock-free stop flag during its five-second wait, and returns without starting another dispatch. It restores prior signal handlers on exit. `--once` retains its existing behavior and does not change signal ownership. The worker's existing Celery warm-shutdown behavior remains in use.

## Running the check

Use the existing owned-fixture command in [the image-set runbook](PRIVATE_IMAGE_SET_IMPLEMENTATION.md), supplying the newly built exact API image. A complete invocation retains the compiled ingress/browser and all earlier TLS, restore, natural-lease, scoring and PostgreSQL regression checks. Reports under ignored `test-reports` include `fixed-jobs.json`; installation secrets, observer state and cookies are never release evidence.

The checked-in source qualification record is [P33 evidence](evidence/p33-qualification-2026-10-11.json). Hosted CI builds and imports the API from the current source before running the same fixed service check on native Linux AMD64. Local qualification uses native Linux ARM64. Architecture-specific image IDs are separate; this is not cross-architecture model portability certification.

Complete restricted-network installation, operator secrets/storage initialization, authenticated supply, upgrade/rollback, live/machine-loss recovery, training/search migration, comprehensive egress/retention, gVisor expert isolation, independent refit reproduction, accessibility and all release/value/customer gates remain open. P33 qualifies bounded native packaged task execution, not a production deployment or completed D07.
