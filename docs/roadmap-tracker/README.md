# Local roadmap tracker sources

`build.py` and `template.html` are the versioned sources for the existing local tracker. Copy them to the tracker document root, retain its editorial `notes.json`, and run `python3 build.py --repo <checkout>`. `metrics.py` computes snapshot data from that checkout and is covered by backend unit CI. Browsing the exported HTML remains offline: CSP denies network connections. The reload button reloads the current snapshot; generation remains an explicit builder step.

Status percentages are record distributions. With 15 planned and 11 in-progress outcomes, they are 57.7% and 42.3% regardless of how many partial D07 deliveries merge. If every recorded packet is tested, adding another leaves its tested share at 100%. The delivery-activity panel therefore shows counts, change from the preceding ledger record and the last 12 cumulative counts. It does not invent a remaining-scope denominator, time series, effort estimate or release readiness score.

The trend uses current recorded statuses in ledger order, counting tested/released/customer-accepted packets as test-qualified. D07 implementation counts exclude documentation-reconciliation packets. Outcomes and packets have separate denominators; list filters do not alter either population. Empty datasets show zero rather than dividing by zero.

The local browser policy has prevented fresh rendering checks. Isolated JavaScript logic and generated-source checks are recorded separately from rendered, layout, console or browser-interaction evidence.
