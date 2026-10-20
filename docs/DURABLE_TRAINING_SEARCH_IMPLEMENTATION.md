# Durable native development training and search — P118

This is the first bounded training/search profile in the existing database-backed job service. A developer previews an explicit development-only declaration, then submits the exact input and plan digests. A private Celery worker performs matched-fold search and an all-development refit. The native JSON model and evidence become visible together through the existing lease-fenced terminal database transaction.

## Supported workflow

1. Sign in as a current project developer and bind a headered CSV to the project.
2. POST `/api/jobs/datasets/{file_id}/training-input/` with `data_role: "development_only"`, `business_understanding`, an ordered `features` list, and `validation`.
3. Review the resolved prediction contract, exact fold membership, budget, evidence scope, `input_sha256` and `training_sha256` returned by the preview.
4. POST those same four options to `/api/jobs/datasets/{file_id}/`, adding `kind: "native_numeric_training_search_v1"`, a fresh UUID `request_id`, and the two reviewed digests. Normal session, CSRF and project authorization apply to both endpoints. The service must be enabled to queue work.
5. Use the existing job detail/list/cancel API. Repeating the identical request UUID returns the existing job; changed request fields conflict. Developers can cancel; authorized independent readers can inspect the resulting evidence.

The declaration must explicitly identify binary classification or regression, target and positive label when applicable, objective, population, prediction horizon, label maturity and feature availability. Cardinality does not choose the task. These are recorded customer declarations, not independent verification of their truth.

The profile requires a fresh development input: existing split/model/train-data paths or recorded assessments for the dataset or exact source hash block preview and execution. It does not automatically link edited or reordered copies, unknown historical partitions, or external data use. A developer declaration alone cannot establish independent confirmation.

The profile accepts UTF-8 CSVs up to 5 MiB, 30–1,000 development rows, 40 columns and 1–32 numeric predictors. Missing predictors receive means fitted inside each training fold. The target, declared forbidden features and split control columns cannot be predictors. Numeric infinities, missing labels, unsupported tasks and malformed configurations fail closed. Raw-input upstream provenance remains unverified; no prior preprocessing lineage is invented.

`validation` requires an explicit `strategy` (`random`, `group` or `oot`) and integer `n_splits` (2 or 3). Group validation requires `group_column`; temporal validation requires `date_column` and supports `label_end_column` and `group_column`. Existing shared fold construction preserves entity separation, temporal ordering and outcome-window purging without shuffled fallback.

## Search, evidence and durability

Two fixed native XGBoost candidates use maximum depth 1 and 2, learning rate 0.1, 16 boosting rounds, one training thread and seed 42. They use the same declared development folds and objective. Selection uses the unweighted mean fold score in the metric's declared direction; ties retain the first candidate. Reference scores use each fold's training-label mean/prevalence. Threshold metrics retain their trusted fixed 0.5 semantics. There is no tuning of preprocessing, thresholds, calibration, stopping rounds, class weights or hidden model families.

The selected configuration is refitted on all declared development rows, with fold-local preprocessing and native fit receipts. Validation data never selects early stopping in this profile. Output contains the contract, feature order, input/plan/runtime pins, fold membership and preprocessing, candidate/reference scores, selection rule, final fit receipt and `xgboost_json` model text. The output is bounded to 8 MiB. Fold variation is exploratory evidence, not an independent confidence interval or final assessment.

Requests persist in PostgreSQL; Redis/Celery remains transport. The existing queue bounds, three-attempt limit, 120-second execution budget, 180-second leases, cancellation, authority rechecks, revocation and runtime checks apply. A worker reconstructs from the persisted request and current source only if byte/parser and plan pins still match. Changed or unavailable sources block execution: this packet does not introduce a permanent copy of uploaded bytes.

Each fit checks the live lease/authority and budget before and after native work. Late, expired, cancelled or superseded attempts cannot publish a result. Only the existing transactional completion path publishes the JSON model and evidence; retry recomputes interrupted work and cannot double-publish. Source artifacts and legacy model/search projections are not rewritten. The API/controller and worker never import user code or deserialize a user-supplied fitted model for this profile.

## Qualification and remaining scope

The new behavioral tests exercise real fitting for binary classification (both positive-label meanings), low-cardinality regression, grouped and temporal folds, imputation, authorization, CSRF, contradictory profiles, input/runtime/authority changes, cancellation, retry and stale publication. Original regression files, physical cases, workloads, resources, skips, coverage, browser retries and the 900-second PostgreSQL suite limit are preserved.

The additive private fixture signs in through real CSRF/session handling, uses the TLS PostgreSQL/broker and prefork worker/dispatcher, interrupts an observed running job by killing only its owned process group, injects an expired lease, and verifies recomputation, stale-token fencing, duplicate publication protection, queued cancellation and changed-input rejection. The injected expiry is explicitly distinguished from the existing generic job fixture's natural 180-second recovery proof. This is synthetic qualification, not a customer recovery drill.

Legacy synchronous training, SFS, broad HPO and their launch UI are not migrated. This packet supplies an observable API workflow; the existing job viewer can display and download training evidence, but dedicated launch controls, broader algorithms/data sizes, immutable trial checkpoints, resume within a search, a reproducible model export/scoring interface, final assessment integration and reviewed candidate adoption remain future work. No champion, package, approval or production decision is created. D07, coordinated customer recovery, upgrade/rollback, release and customer acceptance remain open.
