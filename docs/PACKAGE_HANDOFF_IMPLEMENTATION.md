# Exact package and scoring handoff

P11, 9 October 2026. Base: PR #100 merge
`4762cc0015ec415682776687ee5762695954a243`; its main CI passed all five jobs.
This is partial delivery against D04/D09/D12. Release and customer gates remain open.

## Behavior

Readiness and native packaging resolve one exact execution and assessment. Mutable
per-file artifacts select compatibility defaults; their metrics, cards, lineage,
feature subsets and pipeline business state cannot substitute for frozen evidence.
An explicit historical selection works even when compatibility projections are
corrupt. Incomplete or mismatched selections stop with an actionable error.

Packages retain original model-status, lineage, evaluation and model-card bytes,
source execution/environment and assessment manifests, fitted native model,
calibration, raw purifier, encoding/schema, declared objective and monitoring
sidecars. The source model and its required input paths must belong to the verified
execution manifest before native state is loaded. New packages bind the complete
scoring manifest to a publication receipt containing dataset, bundle, execution,
assessment and manifest SHA-256.

Staging directories are private candidates until integrity/source checks finish;
ordinary failures clean them up without creating a version or changing the current
pointer. Publication renames a complete UUID version, then atomically adopts its
pointer under the same per-file lock used by native modeling and assessment
projections. A changed model or assessment leaves the package as a historical
version. Repackaging an earlier assessment cannot replace a newer current bundle.
Interrupted publication, cross-service durability and abandoned staging cleanup
remain D07 work; this is not a distributed job or recovery guarantee.

Scoring, status and downloads verify selected identities, manifest receipts,
required model/calibrator/purifier/evidence membership, recorded hashes and sizes,
and flat non-symlink artifact paths. Scoring does not substitute another model file
for a missing governed artifact. Downloads export recorded files only, excluding
unrecorded extras; pack creation passes its returned bundle ID directly to export.
Evaluation and scoring-pack exports use unique names and exclusive writes. Batch
receipts retain bundle, execution, assessment and manifest digest alongside scores.

The package panel remains available after modeling, including blocked assessment
states and older bundles. Creation uses the model/assessment pair checked by the
server. CSV scoring and download use the displayed bundle ID. File changes clear
prior state and ignore late responses. Version/evidence and scoring receipts are
expandable and keyboard accessible. A new model does not silently replace a
previously displayed scoring package.

## Interfaces and migration

- `GET /api/deployment/bundle/?file_id=<id>` returns readiness and exact version IDs.
  Optional `execution_id` and `assessment_id` must be provided together.
- `POST /api/deployment/bundle/` accepts the same pair with `file_id`. It returns a
  bundle ID, manifest digest and `adoption_status`. Historical publication reports
  `version_only_current_changed` rather than changing the compatibility pointer.
- `GET /api/deployment/status/<file_id>/?bundle_id=<uuid>` verifies that bundle.
  Omitting the ID resolves the current pointer once; a mutable summary is not used
  as authority. Absence returns `unknown`; integrity conflicts return HTTP 409.
- `POST /api/deployment/pack/` accepts `file_id` and `bundle_id` for an existing
  exact package, or an execution/assessment pair to build and export one. Mixing
  the selectors is rejected. Response headers expose `X-DeclarAI-Bundle-Id` and
  `X-DeclarAI-Manifest-SHA256`.
- `POST /api/deployment/score/` accepts `bundle_id` with multipart input or JSON
  rows. Omitting it retains the compatibility-current scoring path. Saved batch
  results include the exact version receipt; UI calls always provide the ID.

No database migration or dependency change is required. Existing governed bundle
schemas keep their original bytes and integrity maps; they do not acquire a new
historical publication receipt. Earlier unversioned bundles remain inspectable
and export their known sidecars with explicit unverified provenance. Legacy
scoring inputs remain governed by their original schema; missing evidence is not
reconstructed as certainty.

## Qualification and limits

See [source qualification](evidence/p11-qualification-2026-10-09.json). Regression
scenarios cover frozen-vs-mutable evidence, historical assessment selection,
changed-current publication, cleanup after failure, metadata/artifact tampering,
required artifact omissions, original export bytes, unique archive names,
unrecorded-file exclusion, versioned batch receipts, real classification/regression
raw replay and chunk parity. The authenticated browser workflow resumes a saved
model, observes blocked new packaging, expands the older bundle's evidence by
keyboard and downloads that exact bundle.

Hashes detect corruption relative to recorded local manifests and receipts. They
are not signatures, independent authenticity or protection against an actor who
can rewrite all package storage. Protect database and artifact storage together.
Native fitted-state deserialization remains trusted platform code; expert Python
is blocked until the separate isolation service is qualified. These exports do
not include a complete independent reproduction runner or confer reviewer,
policy, deployment or production-use approval. All new assessment evidence stays
exploratory. PostgreSQL/jobs, project authorization, distributed publication and
restore, expert isolation, clean independent reproduction, full accessibility,
release and customer/value acceptance remain open.
