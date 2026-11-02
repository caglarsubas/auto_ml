# P163 — Native preparation and diagnostics runtime

The first retained PR #262 run reached the unchanged 900-second PostgreSQL suite cap
with 6,912 cases finished out of the original 7,401. That partial run is not
qualification. CPU observations identify native fitting/input preparation and
complete development diagnostics among the repeated work.

The repair makes two bounded changes:

- XGBoost 2.1.4 with pandas 3.0.6 and NumPy 2.5.3 can prepare small mixed numeric
  and categorical frames directly in their native float32 representation.
  Cells, missing values, feature types/names, model bytes, predictions and fit
  receipts remain equal. Unsupported storage, overflow, replaced constructors,
  other versions and larger inputs retain native pandas dispatch.
- For scikit-learn 1.9.1 with NumPy 2.5.3, complete binary diagnostics can build
  ROC and precision/recall curves from one bounded stable threshold grouping.
  Threshold counts follow the unweighted
  [public reference](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.confusion_matrix_at_thresholds.html).
  ROC corner filtering and PR endpoints match both reference APIs.
  The independent public ROC-AUC and confusion-matrix checks still execute.
  Larger inputs, replaced curve callables and other versions retain the
  original route. No caller arrays or results are cached.

Existing tests and fixtures are preserved. New cases cover native representation,
exact fitted outputs, unsupported-profile fallback, curve arrays/endpoints,
caller mutation and continued independent assessment checks. The model round,
dataset, worker, coverage, skip, scheduling and retry budgets are unchanged.

The second run completed all 7,459 cases and both worker sessions exited with
status zero, but the parent hit 900 seconds during finalization. No native XML
or successful parent exit was retained, so that run is also unqualified. The
next source removes the remaining threshold-validation duplication only after
the caller has validated every input, and keeps all independent full checks.

Local tests under the pinned numeric libraries pass 307 related cases, plus
211 curve/declared-metric regression cases including existing full-check spies.
These suites overlap and must not be added together as unique-case coverage.
Controlled ARM64 Mac microbenchmarks observed about 2.6× faster mixed-matrix
construction and 1.2× faster complete binary summaries. These are local
measurements, not Linux qualification or capacity promises. Exact-head CI and
independent main qualification must still pass all original gates, including
two workers and the 900-second cap.

This PR also extends the existing installer with a coherent two-root
classification/regression, export/scoring and baseline-backup acceptance route.
It preserves existing installation/fault assertions rather than substituting
component receipts. The next acceptance closure remains
[D07-T02 clean installation](PRIVATE_INSTALLATION_ACCEPTANCE.md). P162 snapshot
reads remain an independent P1 optimization. This performance repair does not
close installation, upgrade, recovery, release or customer acceptance.
