# Independent review of a reproduced assessment

A technical review decision applies to one exact completed protected assessment and its independently reproduced fit. The supported profile is the durable numeric XGBoost binary classifier or regressor described in [Independent refit and assessment reproduction](INDEPENDENT_REPRODUCTION_IMPLEMENTATION.md).

## Developer and reviewer workflow

1. The reviewer opens the assessed job under **Package jobs**, downloads its reproduction manifest, then opens its review from the same workspace. The opening records the assessment job ID, result digest and manifest digest. It records an attributable discussion with no approval.
2. Reviewers record findings and developers respond. An independent reviewer can resolve, reopen, or record a written exception for one open finding. An exception requires a timezone-aware expiration. While the exception and its reviewer's authority remain current, the finding is shown as excepted. Expiry or lost authority returns it to open. The exception leaves the original finding and rationale in the history.
3. Using the approved custody channels, the independent reviewer runs the [offline reproduction command](INDEPENDENT_REPRODUCTION_IMPLEMENTATION.md). Submit its successful JSON report with an explicit **Approve technical review** decision and rationale. All findings must be resolved or covered by an active exception.
4. Refresh or download the review snapshot to inspect the current status and historical receipts. A reviewer can explicitly revoke the approval. A new assessment starts its own review.

Technical approval checks that the report matches the complete expected identity and results for this refit and protected assessment. It is an attributable reviewer submission. The installation verifies the report bindings without repeating the refit, opening the sealed outcomes, or establishing who ran the offline command. The separate named reviewer exercise remains D09-T03.

## Authority and applicability

The original trainer and adoption proposer cannot act as native reviewers. A developer who responded in the case cannot act as its reviewer after a membership change. Current administrators can inspect authorized history. A current reviewer action binds the observed revision, request UUID and actual project authority.

An approval pins the assessment and manifest digests, the reproduction report, the versioned decision and installation data policy, and the exact discussion preceding the decision. New findings or dispositions, changed evidence, an unavailable exception, a changed policy or loss of the original approver's authority invalidate current applicability. The original decision, actor, rationale, applied exception, report and receipt digest stay visible in authorized history. Resolve or reopen actions affect only the named finding. Packaging, finding closure and technical approval confer no authorization for production use.

Frozen legacy package discussions remain available through their existing review workflow. The first technical-decision profile uses recorded native training/adoption actors and reproducible protected assessment evidence.

## API and retention

- Open via `POST /api/reviews/datasets/{file_id}/` with `request_id`, `assessment_job_id`, `assessment_result_sha256` and `manifest_sha256`.
- Read and append via `/api/reviews/{review_id}/`. Actions include `request_id`, `expected_revision`, `event_type` and `text`. Send the target `finding_id` and `expires_at` for `exception`, or the parsed CLI `report` for `approve`. The explicit `revoke` action requires a rationale.
- The authorized JSON snapshot carries the review status, decision digest, append-only events, report and provenance. Responses use `Cache-Control: no-store`. An exact retry returns the current snapshot without appending a second action.
- Preserve review metadata and cited artifacts in coordinated restore. The additive migration protects the linked assessment job and preserves existing review history. Used evidence remains under the installation retention policy. The review API exposes no mutation or deletion of historical events. Follow the private upgrade procedure's coordinated restore when rolling back an installation that has recorded native reviews.

CI exercises the reviewer path in the native assessment browser workflow. Its metadata receipt binds the submitted report digest to the separate clean Linux reproduction.
