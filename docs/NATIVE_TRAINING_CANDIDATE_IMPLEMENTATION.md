# Native training candidate export and scoring (P120)

D07 supports deterministic export and durable batch scoring of successful **P118 bounded native development training/search** results. The launch/history UI exposes these actions. This adds a separate candidate handoff; it does not adopt a champion, grant review/production approval, perform a final assessment, or migrate legacy training/SFS/broad HPO.

## Export and portable scoring

An authorized reader downloads `GET /api/jobs/{training_job_id}/candidate/?project_id={project}&sha256={result_sha256}`. The server rechecks current dataset/project authority, terminal success, supported native kind and the canonical result digest. The deterministic JSON envelope includes the exact model JSON, contract and positive-class meaning, ordered predictors, fitted numeric means, development evidence, training/result identity, fitting environment and scoring reader environment/source digest. The response is `no-store`; `X-DeclarAI-Export-SHA256` is the external export pin shown beside the UI download. Retain it independently from the file. Hashes detect changes against that receipt; they do not prove independent authenticity.

The standalone runner requires the recorded Python, NumPy, pandas and XGBoost versions, the matching reader source, and an externally retained export digest:

```sh
python scripts/score_native_candidate.py candidate.json features.csv \
  --export-sha256 EXTERNALLY_RETAINED_DIGEST --output scores.json
```

The runner imports the repository's `backend/deployment/native_candidate.py`, requires no database, broker or Django setup, and refuses to overwrite an existing output. Run it in the recorded environment. Candidate exports are data files, not executable Python packages. Only the explicit offline runner or queued worker loads native XGBoost JSON; the API/controller never loads fitted models. Pickle, joblib, expert objects and custom transformations/scorers are unsupported. Customer-platform adapters, signed distribution and a standalone dependency-image distribution remain separate work.

## Reviewed durable scoring

Developers prepare `POST /api/jobs/{training_job_id}/scoring-input/` with exactly `input_file_id` and `training_result_sha256`. Both datasets must be currently authorized in the same project. The feature input must be a governed header CSV: UTF-8, 1–10,000 data rows, at most 5 MiB, and exactly the frozen 1–32 numeric predictor names. Source column order may differ; the reader restores model order. Missing values use the **training refit's** finite means, including all-missing scoring columns. Non-numeric categories, infinities, duplicate/missing/extra columns, malformed widths and empty inputs stop. Labels, identifiers and validation controls must be omitted. Known split/modeling/fitted-state inputs and any exact-byte known holdout population are blocked without opening their state. Unknown, reordered or modified upstream histories remain unverified; export/scoring never creates confirmatory evidence.

The preview binds training job/result/export, exact source bytes/parser, authority revisions, runtime/source versions, chunk size and all execution limits into `scoring_sha256`. It displays the contract, source/model digests and budget before separate confirmation. Edits/context changes invalidate approval; uncertain admission retains the exact UUID/body for explicit retry. Pending state is in memory; leaving requires checking durable history before replacement.

Submit `POST /api/jobs/datasets/{training_dataset_id}/` with exactly:

- `kind: native_training_scoring_v1` and fresh `request_id` UUID;
- `training_job_id`, `training_result_sha256`;
- `input_file_id`, `input_sha256`, `scoring_sha256` from the preview.

The existing queue retains its two-active/100-pending bounds, 120-second work deadline, three attempts and 180-second lease. Native scoring uses one thread and fixed 500-row chunks. Retries recompute from pinned immutable model state and exact input. Current authority, training-result integrity, runtime, budget, cancellation, expiration and lease fencing govern claim, execution and publication. Only a fenced DB result publishes; no files/shared model projections are adopted. Missing/changed inputs or dependencies block. Exact UUID/body retries return the same job and cannot double-publish.

Authorized readers inspect history or download `GET /api/jobs/{scoring_job_id}/scores/?sha256={result_sha256}`. Large job details show only 500 preview scores; the full no-store receipt retains every row, exact input/model/export identities, ordered features, positive-class probability or regression semantics, uncalibrated status, and false adoption/review/production flags. Row alignment is zero-based parsed CSV data-row order, ignoring blank records. No outcomes, thresholds, calibration or decision policy are fitted here. Candidate receipts cannot be selected as package review evidence.

## Acceptance evidence

Additive backend tests exercise actual classification (both positive-label mappings) and low-cardinality regression, exported/refit/offline/queued parity, reordered columns, frozen missing-value handling and chunk invariance, full receipts beyond 500 rows, stale/altered artifacts and approvals, role/project changes, protected-population copies, cancellation, lease loss and late dependency tampering. Existing inventories and budgets remain intact. New frontend tests cover explicit confirmation, context/edit invalidation, authority-bound downloads and exact uncertain retries. Two real browser workflows score binary/regression candidates through workers and download complete receipts. An additive private TLS/PostgreSQL/prefork/dispatcher proof verifies both tasks, real CSRF, external export pins, batch parity and single publication; existing recovery/physical tests remain unchanged. Qualification states and run links are retained in the roadmap; source evidence is not a release or customer acceptance claim.
