# Protected holdout reuse and assessment evidence

P10, 9 October 2026. Base: PR #99 merge
`459fc5601613ac3fba1ebebe27f19d00b74b919f`; its main CI passed all five jobs.
This is partial delivery against D03/D04/D09/D12. Scientific, security,
reproduction, release and customer gates remain open.

## Behavior

- New native executions record the frozen source digest, target column and exact
  final-row membership. Raw purifier snapshots take precedence over processed
  snapshots. Identity excludes fitted models, selected features, objectives,
  thresholds and positive-class encoding. Candidate publication preserves it
  without deserializing protected outcomes; publication/loading verify it against
  the frozen source, accepted target and split.
- Assessment commits an attributable access reservation before deserializing
  development or final data. Its audit record retains execution, source, contract,
  requested threshold/features and an actor snapshot that survives account deletion.
  Completed, failed and interrupted/started attempts all count as possible access.
  A failed reservation blocks assessment before loading input. Final rows and
  labels must align with the recorded identity before metrics are produced.
- History distinguishes the same final rows, overlapping final rows for the same
  source/target, and historical receipts with unknown identity. Changed candidates,
  objective/threshold changes or reversed class meanings cannot erase recorded
  reuse. A different final split exposes overlapping accesses instead of calling
  them independent confirmation. Disjoint rows and different targets are separate.
- The authenticated history endpoint reads receipts and verifies the frozen
  execution; it does not deserialize inputs or outcomes or add access receipts.
  It reports complete related-access counts with paginated records. The evaluation
  page shows concise counts, expandable records/limitations, keyboard-operable
  details and explicit unavailable-history messages. It pins evaluation to the
  selected execution and discards results/responses belonging to an older selection.
  Saved model restoration preserves the checkpoint used by the parent evaluation
  gate, so the review panel remains reachable after resuming a completed workflow.
- Evaluations and model cards retain the history at access reservation. Later
  accesses do not rewrite their immutable evidence. Evaluation packs accept an
  exact execution/assessment pair, verify both packages and export original
  assessment/model-status bytes. A separate export-time history records later
  access. Compatibility downloads resolve their recorded exact assessment;
  mutable model/SHAP projections cannot replace the assessed version's evidence.
  A feature override requires a new fitted candidate rather than silently changing
  the assessed inputs. All current evidence remains **exploratory**.

## Interfaces and migration

`GET /api/evaluation/holdout-history/<execution_id>/?file_id=<id>&limit=50&offset=0`
requires authentication and matching execution/dataset identity. `limit` is 1–100;
`next_offset` identifies the next page. Reading history never inspects final labels.
`POST /api/evaluation/pack/` accepts `file_id`, `execution_id` and `assessment_id`;
both version IDs must be supplied together. Omitting them resolves the compatibility
evaluation's recorded assessment. Missing/tampered exact evidence blocks export.

Apply additive migration `modeling/0003_holdout_identity.py` after backing up the
database and artifact tree together. Existing receipts default to unknown identity,
unknown attempt state and no reconstructed actor snapshot. Existing execution
packages remain inspectable and assessed as historical/unverified. New candidates
from old executions retain that uncertainty; a new training execution is needed
for a recorded source/row identity. No historical access is inferred as certainty.

## Qualification and limits

Qualification results and source/report digests are recorded in the packet's
qualification receipt after checks finish. Tests cover concurrent reservations,
changed candidates, positive-label reversal with fixed final rows, overlapping
cohorts, stale binding, failed reads/retries, audit storage failure, actor deletion,
unaligned outcomes, exact export bytes, tampered assessment rejection, legacy
uncertainty and real authentication. Browser/API qualification extends the existing
raw-input classification/regression journeys and exercises rendered history details
with a keyboard.

The current single-installation profile serializes access reservations with a
source/target filesystem lock and database transaction. This does not qualify
distributed/multi-host durability, protected roles, audit retention, database plus
artifact recovery or project authorization. Authenticated users still share the
installation under the existing policy. Input storage remains a trusted native
boundary; hashing is integrity evidence relative to a manifest, not a signature or
an authorization control. Expert-code execution remains blocked pending isolation.

Source edits, reordered/reformatted imports and copied outcomes in another source
are not linked automatically. Historical unknown receipts are conservatively
disclosed for the file; missing earlier logs cannot prove an unused holdout.
Counts reflect recorded reservations, not proof that a human viewed every outcome.
Access history is observational; it does not qualify prevention of upstream raw-data
inspection, a confirmatory assessment protocol or independent review. No automatic
approval, production use, complete reproduction package, capacity or accessibility
acceptance is claimed. D18–D26 remain planned and the shared-foundation queue is unchanged.
