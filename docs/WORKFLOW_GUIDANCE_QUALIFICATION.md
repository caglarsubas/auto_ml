# Developer and reviewer workflow guidance

P189 completes D12-T02 over the supported project, durable training, scoring
and independent assessment review interfaces. It retains the existing Angular
workbench, design tokens, server authority and exact evidence contracts.

## Entry and navigation

The home screen directs developers to the selected project's development
workspace. Reviewers and administrators enter project records and evidence.
Project selection, missing membership, empty datasets and empty pipeline records
explain the next available action. The training and review panels use
`/home?project_id=…&dataset_id=…&view=training|review`. Reload and browser history
restore a panel only after current project access and dataset membership have
been checked. Project changes, malformed links, revoked access and foreign
datasets withhold stale panels and explain how to select accessible work.

## Recorded progress and recovery

Job lists and history filters show readable operation and state names while
preserving their exact API values. Selected receipts expose the recorded actor,
attempts, timestamps and request expiry. Queued, running, cancellation-requested,
cancelled, blocked, failed and completed states each explain the next step.
Cancellation acknowledgement remains distinct from its request. Recovery guidance
points to the operator handoff and retains any protected-outcome access history.
Ambiguous writes retain their exact request receipt for retry. Authority failures
withdraw stale actionable evidence. Technical codes, limits and execution
references remain available in expandable detail. No elapsed-time percentage or
estimated completion time is invented.

## Review handoff

The review panel explains the next step for developers, reviewers and inspecting
administrators. It exposes the latest attributable change, open findings,
independent reproduction requirements and technical decision status. Invalidation
and revocation reasons include an actionable explanation and the recorded code.
Exact assessment/package identity and event history remain expandable. Download
access revocation withdraws stale review controls. Approval still requires the
server's current role, independence, findings, exceptions and exact reproduction
report checks. Technical approval and production-use approval remain separate.

## Qualification and limits

The complete Angular suite covers 767 cases, including URL restoration, context
changes, blocked/cancellation guidance, denied downloads and decision explanation.
Existing browser cases additionally exercise training panel reload, keyboard
expansion of exact identity, and reviewer finding/exception/approval/invalidation
handoff. The isolated browser profile includes project roles, binary/regression
training, protected assessment and operator navigation. The original CI suite,
case identities, coverage controls, worker limits and 900-second PostgreSQL cap
remain unchanged. Exact PR and independent push-main receipts are publication
gates and remain separate from local checks.

D12-T03 retains complete keyboard/screen-reader journey qualification. This
packet does not establish assistive-technology acceptance, customer usability
acceptance or production-use approval. The roadmap's 66-task denominator is
unchanged. Qualified D12-T02 moves done/open/blocked from 27/32/7 to 28/31/7:
40.9% to 42.4% done, a 1.5 percentage-point increase. D12 remains in progress.
