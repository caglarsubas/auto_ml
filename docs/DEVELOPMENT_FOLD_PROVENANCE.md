# Export development fold provenance

Open a completed modeling or search job in the project job history and choose
**Download fold provenance**. Retain the SHA-256 shown after download in the
review record. Automation can use the same authenticated read.

```text
GET /api/jobs/<job_id>/fold-provenance/?sha256=<result_sha256>&project_id=<project_uuid>
```

The request pins the job result digest. The response returns the export digest
in `X-DeclarAI-Export-SHA256`. Current project read authority applies to the job
and every bound source job. Successful responses and errors use `no-store`.
The exporter reads frozen JSON metadata and the referenced selection-fit
artifact. It excludes model bytes, protected row memberships, predictions,
outcome values and descriptive encoding statistics.

Verify the saved file with the digest retained in the review record.

```sh
python backend/modeling/verify_fold_provenance.py development-folds-<id>.json \
  --sha256 <export_sha256>
```

The versioned JSON links each development fit to its ordered input rows,
training and validation roles, native fit receipt and fitted state. It records
purifier steps, encoding, imputation, alternate design matrices or scorecard
WOE, anomaly score reference and fit weights where applicable. Binary
calibration records its development-validation rows, input digest and fitted
mapping. For supported random-split target encoding, each inner mapping
identifies its ordered fit and application rows. The legacy route pins the immutable input snapshot and original raw
input when the fitted purifier has a replay recipe. The numeric route pins its
development CSV and accepted validation declaration.

Search exports cover screened SFS alternatives, top-K CV fits and the
post-selection candidate refit and CV. Tuning exports include recorded trial
attempts, fold provenance, validation-curve points and the published candidate.
The selection worker puts additional fits in a bounded, digest-bound JSONL
artifact so that wide searches retain small result and checkpoint references.
Resumes carry that artifact with the checkpoint. Missing historical evidence,
unavailable fits and the selection evidence budget are reported in
`unverified`. An export beyond the 8 MiB download limit returns
`job_fold_provenance_budget_exceeded`.

The offline tool checks integrity and consistency against the retained digest.
Independent refitting, protected assessment and production approval have their
own workflows.
