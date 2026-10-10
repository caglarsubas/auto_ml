# Durable native CSV scoring (P24)

This is partial **D04/D07/D09/D12**. `native_csv_scoring_v1` extends the recorded P22/P23 job service to score a bounded, registered CSV using an exact frozen native package. It preserves fitted preprocessing, encoding, calibration and score semantics. It does not fit a model, inspect final labels for selection, approve independent review or authorize production use. Training/search and the existing synchronous scoring routes remain available; their migration is still open. Expert execution requires the separate D08 isolation service.

## Developer and reviewer workflow

Upload a CSV through the existing governed dataset workflow and note its dataset ID. In the selected project's package-review workspace, a developer selects that input ID, chooses **Prepare scoring input**, inspects the source name/byte count/SHA-256 and the exact package/budget, then chooses **Queue CSV scoring**. The input defaults to the current model dataset, but a separate scoring upload in the same project is supported. Preparation reads bounded bytes without running a model or validating the entire CSV. It is not execution approval.

The database records the request before independent dispatcher/broker delivery. Leaving the browser does not cancel it. Refresh/open the recorded job to inspect state, attempts, attributable events and explicit reason codes; submitters can cancel. An uncertain response retains the exact request UUID and payload for retry. Project/dataset changes clear browser evidence and pending actions. Current reviewer/admin members can inspect authorized receipts; only developers submit scoring. Integrity checks retain their existing developer/reviewer submission rule.

Completed scoring offers a freshly authorized **Download full scoring receipt** action. For more than 500 rows the job detail includes a 500-row preview; its `result_sha256` always identifies the full canonical scoring JSON, not the preview or outer job receipt. The separately downloaded job receipt retains request specification/history. Keyboard preparation, submission, refresh and download are covered by the browser fixture; full screen-reader/accessibility qualification remains open.

## Exact request and authority

`GET /api/jobs/datasets/{input_id}/input/?project_id={project_uuid}` returns current input identity, raw SHA-256/bytes, default Pandas parser/version and fixed bounds. It requires current dataset read authority and active governance. Only registered `.csv` files under managed media with declared headers are supported. Traversing, absolute or symlink paths fail closed, including symlink ancestors.

Submit `POST /api/jobs/datasets/{model_file_id}/` with exactly:

```json
{
  "request_id": "<fresh UUID retained for identical retry>",
  "kind": "native_csv_scoring_v1",
  "bundle_id": "<frozen package UUID>",
  "manifest_sha256": "<exact lowercase SHA-256>",
  "input_file_id": 27,
  "input_sha256": "<prepared raw CSV SHA-256>"
}
```

Real session/CSRF, selected project and server-side dataset authorization apply. Model and input datasets must share a project; cross-project admission fails even if the actor belongs to both. Caller-supplied code, actor, budgets, paths and additional fields are rejected. Admission pins package/execution/assessment identities, actor and both authority revisions, input relative reference/bytes/parser, native job/scoring module and package versions, limits and one-hour expiry. The additional nullable `NativeJob.source_dataset` protected reference is an additive migration; historical requests are preserved.

An exact retry replays the retained request only after current model and input authority and result integrity checks. Altered UUID reuse conflicts. During execution both authority snapshots are rechecked. Final publication locks both dataset bindings/memberships and uses the existing database lease fence. Current authority to both datasets is required for completed-result reads/downloads; moving the input to another project withholds the historical result from its old project. This does not erase recorded history or grant access through the submitting actor.

## Execution, budgets and atomic publication

The allowlist is the existing native verifier's `xgboost`, `lightgbm`, `catboost`, `logistic_regression`, `scorecard`, and `isolation_forest`. Native serialized state is trusted installation infrastructure. No expert package is admitted; this worker is not a hostile-code sandbox. Artifact hashes are checked before native state is loaded, with bounded byte hashing and the existing cancellation/authority/lease checkpoints. Neither a filename nor a changed current model selects another package.

Source bytes are bounded using the opened descriptor, checked against the pinned hash/parser/reference, then parsed/scored from those exact in-memory bytes. The worker does not reopen a mutable input path after parsing. Changing a registered source's bytes or path after queueing blocks the job instead of substituting another input. Raw source files are not duplicated into a new snapshot store; offline replay requires the independently retained, exact input bytes. Storage authenticity and hostile concurrent filesystem mutation are outside this trusted native profile.

Fixed limits:

| Boundary | Limit |
|---|---|
| Raw input | 5 MiB, UTF-8 CSV, header required |
| Parsed rows / columns | 10,000 / 256 |
| CSV precheck | Standard dialect, strict quoting, unique header, default Python field-size limit; no record wider than header |
| Canonical full result | 16 MiB |
| Package | Existing 256 artifacts / 1 GiB |
| Installation queue / active leases | Existing 100 / 2, shared across both job kinds |
| Work / attempts / metadata lease / expiry | Existing 120 cooperative seconds / 3 / 180 seconds / 1 hour |

Row/width/quoting checks run before Pandas frame allocation. The production constants are not relaxed by tests. Resource enforcement, blocked native calls and process/clock behavior still require supported Linux/private deployment qualification; the existing prefork soft/hard timeouts and operator CPU/memory/PID limits remain necessary.

CSV validation polls authority/time/cancellation at completed records after 65,536 decoded characters and at parsing/scoring/serialization boundaries. Raw input and artifact reads retain their byte checkpoints; final publication retains both authority locks and the lease fence. This avoids multiple database round trips for every tiny CSV record while still checking every record's schema and count. Query-count regressions cover the unchanged 650-row parity and 10,001-row rejection fixtures, including revocation during parsing before native state is loaded.

The full JSON result and its digest are committed atomically with the terminal event in `NativeJob`. There is no separately staged score file or unguarded adoption step. Cancellation, revocation, expiry and stale lease tokens withhold publication. A recomputed attempt may perform scoring again, but terminal publication is fenced and duplicate delivery cannot overwrite it. Broker failure retains the committed request for the existing dispatcher/reconciliation service.

`GET /api/jobs/{uuid}/scores/?sha256={full_result_sha256}&project_id={project_uuid}` returns the exact canonical JSON only for a succeeded scoring job with matching digest and current authority. The response is `no-store` with a digest header. The receipt contains all ordered scores, input bytes/parser/runtime anchors, execution/assessment identities, calibration/semantics and explicit false review/production-use approvals. It remains compatible with the existing P21 offline native score verifier, including different chunk sizes. It proves bounded score parity relative to supplied hashes, not full training reproduction, authenticity or statistical validity.

## Migration and qualification boundary

Apply normal additive migrations before starting API/worker/dispatcher. They must run the same installed native/scoring source and dependencies. This packet changes runtime hashes; queued jobs admitted by earlier code block as `job_runtime_changed` instead of silently running new code. Submit a fresh, explicitly approved request after inspecting its scope. Historical terminal receipts remain inspectable; reproducing old scores still requires their recorded scoring runtime.

The [P24 evidence record](evidence/p24-qualification-2026-10-10.json) binds qualification to the exact application/test source. Coverage includes registered-input changes/limits, role/project/CSRF boundaries, late publication/cancellation, recovered attempts/duplicate delivery, full receipt integrity, native logistic scoring and isolated offline replay. Real prefork worker/dispatcher browser fixtures cover native XGBoost classification/regression and keyboard receipt download. Existing private TLS/quiescent restore and killed-worker integrity fixtures are preserved; they do not claim a new production scoring recovery drill.

Remaining: migration of training/search and other scoring profiles; durable assistant/mission grants; complete private/offline installation and dependency locking; production supervisor/resource/hard-timeout/clock, live backup and machine-loss recovery; signed/authentic artifacts and data retention/egress; full refit/assessment reproduction; expert gVisor/runsc isolation; complete accessibility; and every milestone/release/value/design-partner/customer acceptance gate.

The first exact-head CI run passed five jobs but its full PostgreSQL suite reached the existing 900-second fixture deadline. Profiling identified repeated CSV authority queries and redundant password hashing in test setup. The bounded polling above corrects the product overhead. The shared test fixture caches only a real Django-encoded synthetic credential; every case still creates fresh users, sessions, permissions, native models and evidence, and correct/incorrect password checks remain exercised. Dataset sizes, rounds, assertions, test/fixture deadlines, skips and coverage gates are preserved. Final-source requalification is recorded separately from the initial run.
