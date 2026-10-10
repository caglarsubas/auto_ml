# Offline native CSV score verification — P21

P21 adds a partial D09/D12 reproduction workflow: a reviewer checks that a frozen native scoring package reproduces the full scores from a recorded batch on the exact CSV, including different batch sizes. It does not refit a model, reproduce final assessment metrics, establish reviewer independence, approve use, or qualify the first governed release.

## Obtain the evidence

Score an approved CSV against an explicit frozen bundle. The response includes its batch UUID, exact bundle/execution/assessment and manifest digest, CSV byte hash, parser/version, scoring runtime and full receipt digest. Large inline previews remain limited to 500 scores; the stored receipt contains every score. Excel and JSON-row scoring still work, but are explicitly unsupported by this first offline verifier. Historical receipts are preserved; missing input/runtime evidence is never synthesized.

The developer page provides **Download full scoring receipt** next to the score result and retains the input/manifest/receipt digests in expandable detail. Keep the original CSV and download that exact selected bundle. Obtain the package SHA-256 from your trusted download, and retain all digests through an independent trusted channel before transferring files. Hashes detect changes relative to those anchors; a hash obtained only from an untrusted package does not establish authenticity.

`GET /api/deployment/receipts/{file_id}/{batch_id}/?sha256={receipt_sha256}` downloads the original full JSON under current dataset/project read authority. Developers, reviewers and administrators may read; outsiders and revoked members cannot. The exact digest and dataset/batch identity must match. Native response checks revalidate authority and evidence scope before delivery. Downloads are not cached. No new generic media access, assistant/MCP authority, data retention exception or approval is granted.

## Run independently

Use the matching fixed DeclarAI Python runtime, supplied without customer media/database or credentials, on a dedicated Linux worker with no network. Mount only approved package/CSV/receipt inputs read-only and a separate evidence output directory. Bound CPU, memory, process count and temporary storage externally. Dependency acquisition happens when building the fixed runtime, not during verification. `scripts/qualify_offline_scoring.py` demonstrates these controls for two explicit synthetic browser fixtures; it is not a customer-data runner or a sandbox for hostile code.

The runner comes from the installed DeclarAI distribution. It never imports a script from the ZIP. From the directory containing the installed backend packages:

```sh
python -m deployment.offline_verify \
  --package /approved/package.zip --csv /approved/input.csv \
  --receipt /approved/scoring.json \
  --package-sha256 "$PACKAGE_SHA256" --receipt-sha256 "$RECEIPT_SHA256" \
  --manifest-sha256 "$MANIFEST_SHA256" \
  --trust-native-state --atol 1e-12 --rtol 1e-12 \
  --chunk-sizes 1 17 64 --output /evidence/verification.json
```

The tolerance values above belong to the qualified synthetic profile, not a universal statistical gate. A reviewer must select and record tolerances for the declared model/hardware. At least two distinct positive chunk sizes are required. The CSV is parsed once with the recorded pandas defaults, then partitioned without changing row order or inferred types. This checks scorer batch invariance rather than independent CSV chunk-parser inference. Monitoring summaries naturally differ with batch size and are excluded from prediction parity.

Before native state loading, the verifier copies approved inputs into a private temporary directory, checks independent ZIP/receipt/manifest hashes and exact CSV bytes/parser metadata, rejects traversal, links, duplicate/encrypted or unrecorded ZIP members, verifies package publication/artifact integrity and exact version identities, and compares runtime Python/dependency versions and recorded core scoring-source hashes. The original model environment must also match. Dependency/source drift blocks qualification instead of issuing a qualified-looking pass. These source hashes cover the listed scoring modules, not a cryptographic attestation of the whole runtime image or every transitive dependency.

Only versioned registered native XGBoost, LightGBM, CatBoost, logistic, scorecard and isolation-forest packages with execution/assessment evidence are admitted structurally. Original provenance disclosures remain in the output. Native pickle/joblib models and calibrators are executable state: **explicit trust in their source is required**, even when hashes agree. The flags and container restrictions do not make malicious serialization safe or implement D08 expert isolation. Customer expert artifacts remain blocked pending the required gVisor execution boundary; they cannot acquire authority by appearing in a ZIP. A hostile artifact masquerading as native state is outside this trusted-state verifier's safety claim.

## Results and limits

The immutable-by-creation JSON output records exact evidence identities/digests, environment, row/score shape, declared tolerances, whole-batch and chunk checks, maximum absolute differences and pass/fail status. Numerical disagreement produces `failed`; missing/changed/unsupported input or runtime produces `blocked`. Both return a nonzero process exit. Existing output paths are never overwritten. A blocked check defined by this runner includes an actionable explanation; unexpected runtime errors retain a generic error without source data or deserializer details.

Full refit and assessment reproduction need additional versioned, approved datasets, execution recipes and environment packaging. P21 exports no additional training/holdout rows and makes no new data-egress policy claim. Organizational approval/exception protocols, comprehensive accessibility, D07 offline installation/durable jobs/recovery, D08 expert isolation, the agentic pilot and release/value/customer gates remain open.

Qualification: `docs/evidence/p21-qualification-2026-10-10.json`.
