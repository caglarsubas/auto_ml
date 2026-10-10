# Exact-package review discussion — P20

P20 adds a partial D09/D12 workflow to the existing project directory and frozen handoff packages. Reviewers open a discussion of an exact dataset, bundle, execution, assessment and manifest digest. They record findings with explicit severity and resolve or reopen them with a written disposition. Developers respond to open findings. Administrators can read discussions; administration does not confer development or reviewer authority.

The home project workspace provides a **Review package** action for each dataset. It shows the current verified package, current and historical discussions, findings and attributable event history. Users can download the exact original package and a freshly fetched JSON discussion snapshot. Labels, forms, statuses and native controls support keyboard operation. Existing scientific evidence remains exploratory.

## Interfaces and authority

- `GET /api/reviews/datasets/{file_id}/?project_id={uuid}&offset=0`: authorized current package identity and a paginated discussion directory (50 per page, explicit total/next offset).
- `POST` to the same route: reviewer-only opening with exactly `request_id`, `bundle_id`, `manifest_sha256`. Unverified legacy packages and packages without a recorded execution/assessment cannot start a discussion.
- `GET /api/reviews/{review_id}/?project_id={uuid}`: a coherent discussion snapshot with package identity, context digest, revision, freshness, findings, events and explicit false model/production approval flags.
- `POST` to the same route: append a typed `finding`, `response`, `resolve` or `reopen` event with an exact request UUID, last observed revision and written text. Findings require a supported severity; the other actions reference a finding in this discussion. Text is limited to 10,000 characters and rendered as text.

Every operation requires a real authenticated actor and current dataset/project membership. Both routes use the native endpoint registry and response rechecks; an optional project selector must agree with the recorded dataset assignment. Opening/findings/dispositions require reviewer membership; responses require developer membership. The actor and role/revision are server-derived and retained as snapshots. A reviewer cannot resolve their own earlier developer response after a role change. This restriction does not prove organizational independence from all prior model-development work.

There are no event editing/deletion endpoints, assistant/MCP review mutation tools, model approval, waiver/exception acceptance, deployment authorization or production-use authority. Resolving every finding does not advance any of those states. This packet does not qualify a complete independent-review workflow or customer acceptance.

## Evidence and publication

`PackageReview` retains exact package identities and a context digest. `PackageReviewEvent` contains the receipt UUID, actor/authority snapshots, request digest, monotonic discussion revision and timestamp. The opening is itself an event. Dataset/project foreign keys protect retained discussion history from incidental deletion; the dataset API returns an actionable 409. A comprehensive authorized retention/deletion procedure remains D06 work.

The native package verifier checks publication and artifact integrity before any discussion mutation; review reads never deserialize fitted model state. Existing cross-project outcome evidence is withheld. New model/assessment selection, replacement of the current bundle, changes to source bytes/header semantics, modeling/evaluation projections or dataset-linked pipeline state invalidate further edits. Artifact corruption or absence is reported separately as `integrity_unavailable`. Original discussion events and package bytes stay inspectable where current access and integrity permit. A new package starts a new discussion; it cannot inherit the previous discussion's findings/dispositions.

Writes serialize with the existing dataset projection lock plus database transactions and row locks. A last-observed revision rejects conflicting edits. Exact request retries return the recorded discussion without appending another event; reusing a UUID with altered action/actor/context fails. Authority and evidence are checked again before transaction commit. The browser preserves an ambiguous request's exact receipt and payload for an explicit retry, including a response withheld by a final authority check; a 403 clears displayed evidence without discarding that receipt and clears mounted context on access refresh, project/dataset change and sign-out. Reads of event history share the publication lock so revision and events agree.

Hashes detect changes relative to recorded data; they are not signatures. API append-only behavior does not protect against a database/storage administrator. The lock follows the existing single-installation filesystem design; distributed storage/worker durability, signed external attestations and production recovery remain open. The context digest pins the specified mutable inputs, not a universal dependency graph. Complete approval invalidation must extend these foundations rather than infer approval from finding closure.

## Migration and remaining work

The additive deployment migration creates only review tables and constraints. It does not change or synthesize historical model/package provenance. Restore must retain the metadata and artifacts together under the existing private deployment procedure.

D09 still needs clean-environment reproduction, findings linked to reproducible checks, attributable organizational exceptions and approval protocols, comprehensive development-author/reviewer independence rules, and downstream evidence/approval invalidation. D12 still needs full screen-reader qualification and the complete reviewer workflow. D07 durable queued jobs/recovery and D08 required Linux gVisor expert isolation remain release foundations. No milestone or release/value gate closes in P20.

Qualification evidence: `docs/evidence/p20-qualification-2026-10-10.json`.
