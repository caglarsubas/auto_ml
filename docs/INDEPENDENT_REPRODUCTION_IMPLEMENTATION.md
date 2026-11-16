# Independent native refit and assessment reproduction

A project reviewer independent of the original fit and adoption proposal can export a manifest for a completed, currently applicable protected assessment. The first supported profile is the durable numeric XGBoost worker for binary classification and regression on Linux. The manifest records the fit and assessment previously performed by the worker.

## Reviewer workflow

1. Open the assessed job under **Package jobs** and download the reproduction manifest. Retain the displayed export SHA-256 in the review record through an authenticated channel. The download requires the exact assessment result SHA-256 and the reviewer's current project role. The project, adoption approval, outcome seal and completed outcome-access receipt must still agree.
2. Obtain the exact original development CSV and protected outcome CSV through their approved custody channels. Preserve the bytes, including row and column order. The manifest contains declarations, hashes, fold membership, fit and transformation receipts, aggregate metrics and review metadata. It carries neither CSV, row-level scores, labels nor fitted executable state. Limit access to the manifest and report to the approved review scope.
3. Start a fresh, matching Linux runtime from the recorded release. Use a non-root identity, a read-only runtime and input mount, a separate writable evidence directory and disabled network access. Use the original CPU architecture and recorded Python and package versions. Run the command from the runtime's backend source directory or include that directory on `PYTHONPATH`.

```sh
python -m deployment.offline_reproduce \
  --manifest /approved/reproduction.json \
  --manifest-sha256 "$RETAINED_EXPORT_SHA256" \
  --development /approved/development.csv \
  --outcomes /approved/outcomes.csv \
  --output /evidence/reproduction-report.json
```

The CLI verifies the manifest against the separately retained digest and checks runtime versions, replay source hashes and the links among the fit, candidate, approval, outcome seal and assessment. It verifies development bytes, regenerates ordered folds, refits fold-local preprocessing and model candidates, and compares the exact completed fit and serialized candidate digests. Only a matching refit permits it to open the supplied outcomes. It recomputes population checks, the declared objective, aggregate metrics and the digest of the ordered score vector using the fresh candidate. There is no Django initialization, database access, installation media access, historical fitted-state loading, or holdout reservation.

Exit status zero requires both comparisons to pass. A blocked or failed report exits nonzero. Use a fresh report path for each attempt. Review an exact-runtime mismatch by retrieving the recorded release and environment. Historical jobs without replay runtime provenance and model types outside the supported profile remain available through their existing evidence paths.

## Qualification and governance

Frontend E2E exports one synthetic reviewer assessment for each supported task and hands exact input bytes to `scripts/qualify_offline_reproduction.py`. The script starts a fresh container from the backend image used by the fixture, with networking disabled, the runtime mounted read-only, and empty installation media mounted read-only. CI publishes the resulting digest and comparison reports.

A passing report records successful technical reproduction. It confers no new first-use confirmation, adoption, review decision or production approval. The original assessment may be exploratory or confirmatory according to its recorded first-use and reuse evidence. A named independent reviewer exercise and organizational sign-off are tracked in D09-T03.
