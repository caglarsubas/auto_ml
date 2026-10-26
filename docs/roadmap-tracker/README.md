# Local roadmap tracker sources

`build.py` and `template.html` are the versioned sources for the existing local tracker. Copy them to the tracker document root, retain its editorial `notes.json`, and run `python3 build.py --repo <checkout>`. `metrics.py` computes snapshot data from that checkout and is covered by backend unit CI. Browsing the exported HTML remains offline: CSP denies network connections. The reload button reloads the current snapshot; generation remains an explicit builder step.

Status percentages are record distributions. With 15 planned and 11 in-progress outcomes, they are 57.7% and 42.3% regardless of how many partial D07 deliveries merge. If every recorded packet is tested, adding another leaves its tested share at 100%. The delivery-activity panel therefore shows counts, change from the preceding ledger record and the last 12 cumulative counts. It does not invent a remaining-scope denominator, time series, effort estimate or release readiness score.

The trend uses current recorded statuses in ledger order, counting tested/released/customer-accepted packets as test-qualified. D07 implementation counts exclude documentation-reconciliation packets. Outcomes and packets have separate denominators; list filters do not alter either population. Empty datasets show zero rather than dividing by zero.

The always-visible progress summary shows **done / open / blocked** for both populations, including counts, shares, signed count changes and percentage-point changes against a named, commit-pinned comparison snapshot. Done groups tested, released and customer-accepted records; open groups unfinished records. An open record is blocked only when it has an explicit nonempty `blocked_reason`. Unmet dependencies alone do not invent a blocker. Invalid or contradictory comparisons fail validation. Without a prior snapshot the summary says so instead of inventing a delta. New delivery packets stay open until independent merged-main qualification; source, local tests, PR checks, release and customer acceptance remain separate evidence states.

Run `node docs/roadmap-tracker/check_interactions.cjs <snapshot.json>` and `node docs/roadmap-tracker/check_progress.cjs <snapshot.json>` for isolated JavaScript checks. These do not establish rendered appearance or accessibility.

The local browser policy has prevented fresh rendering checks. Isolated JavaScript logic and generated-source checks are recorded separately from rendered, layout, console or browser-interaction evidence.
