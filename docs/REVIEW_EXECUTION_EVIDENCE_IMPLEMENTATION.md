# Exact execution receipts in package review — P26

Review findings, developer responses and reviewer dispositions can now cite a successful native package-integrity or CSV-scoring job for the discussion's exact dataset, bundle, execution, assessment and manifest. A reviewer can trace the written action to what ran, who submitted it, its input version and its retained result. Prose-only actions remain supported.

## Adoption and evidence

The existing `POST /api/reviews/{review_id}/` action accepts one optional `evidence` object containing exactly `job_id` and `result_sha256`. The server checks current model/input access, successful completion, supported native kind, package identities and the full result digest. Queued, running, failed, blocked or cancelled jobs cannot be cited as successful checks. Different packages, altered references and changed results block adoption without appending an event.

The event retains a protected job foreign key and a compact server-derived snapshot: result/specification digests, terminal revision and completion time, submitter, package identity, source dataset/input digest and supported result facts. Review text and the review actor remain separate from the execution submitter. Repeated citations validate a given job once per discussion read. No scores are duplicated into discussion events, and no fitted state is loaded during review or download.

Exact request retries retain the original action/reference and publish no second event. A receipt UUID reused with changed evidence conflicts. Evidence is verified again before transaction completion. Existing publication locks and project authority rules continue to apply; review code does not acquire the native queue lock, avoiding inversion of queue/project locks.

Discussion reads and receipt downloads revalidate retained snapshots and current access to every cited scoring input. Input authority also joins the HTTP response's final rechecks. A source reassigned outside the recorded project withholds the linked discussion and its receipt even when the actor has membership in both projects. Original database events remain intact. A membership revocation similarly withholds evidence. A recorded reference grants no new access.

`GET /api/reviews/{review_id}/events/{event_id}/receipt/` downloads a freshly authorized JSON document containing the exact reference and retained native job, including **all scoring rows**, its specification and event history. The event must belong to that review. The response uses `Cache-Control: no-store`. Historical discussions can still download their cited receipts under current authority; a new package cannot inherit the old discussion or accept its check as current evidence.

The additive deployment migration leaves historical events with null references. A database constraint pairs the optional snapshot with its retained job. The foreign key prevents incidental deletion of cited jobs. Comprehensive retention/deletion and privileged-administrator tamper protection remain separate work; hashes are not signatures.

## User workflow

Open a current package review, open a successful job, and choose **Use receipt for review action**. Selection refreshes authority and shows the job kind, identifier and result digest. Record a finding, response or disposition with that optional reference. The finding and attributable history show the link; **Download linked receipt** fetches it again from the server. Remove selection explicitly to submit prose alone.

Project/dataset/review changes clear selected evidence. An ambiguous write retains its original payload for an exact retry. Denied selection/downloads produce no browser download; superseded responses cannot attach evidence to a different context. Native buttons support keyboard selection and downloading. Full screen-reader/accessibility qualification remains open.

## Scope and qualification

An integrity receipt attests to the bounded recorded integrity check. A scoring receipt records the native model's outputs for the declared input/runtime. Neither constitutes independent refit/assessment reproduction, organizational independence, review approval, an accepted exception or production-use approval. The snapshot explicitly records `independent_reproduction_verified: false`, and all existing approval flags remain false.

Regression coverage uses real native executions/packages and HTTP roles, 650-row scoring receipts, exact retries, unsuccessful jobs, malformed references, package mismatch, digest/snapshot/specification tampering, publication rollback, historical/actor preservation, input reassignment and final response checks. The real browser workflow exercises keyboard attachment and downloaded integrity/scoring references. The [qualification record](evidence/p26-qualification-2026-10-10.json) reports the full SQLite/private PostgreSQL matrices, frontend/browser checks and retained operational drills.

D04/D06/D09/D12 advance partially. Full refit/assessment reproduction, expert Python isolation, organizational approval/independence, comprehensive accessibility, durable training/search, complete private/offline installation, authenticity/retention/egress and production recovery remain open. No milestone, release, pilot, value or customer-acceptance gate closes.
