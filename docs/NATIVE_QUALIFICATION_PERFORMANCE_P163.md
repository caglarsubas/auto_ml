# P163 — Native preparation and diagnostics runtime

The retained PR #262 run reached the unchanged 900-second PostgreSQL suite cap
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
  ROC and precision/recall curves from one public
  [confusion_matrix_at_thresholds](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.confusion_matrix_at_thresholds.html)
  calculation. ROC corner filtering and PR endpoints match both reference APIs.
  The independent public ROC-AUC and confusion-matrix checks still execute.
  Larger inputs, replaced curve callables and other versions retain the
  original route. No caller arrays or results are cached.

Existing tests and fixtures are preserved. New cases cover native representation,
exact fitted outputs, unsupported-profile fallback, curve arrays/endpoints,
caller mutation and continued independent assessment checks. The model round,
dataset, worker, coverage, skip, scheduling and retry budgets are unchanged.

Local tests under the pinned numeric libraries pass 295 related cases.
Controlled ARM64 Mac microbenchmarks observed about 2.6× faster mixed-matrix
construction and 1.2× faster complete binary summaries. These are local
measurements, not Linux qualification or capacity promises. Exact-head CI and
independent main qualification must still pass all original gates, including
two workers and the 900-second cap.

The next acceptance closure remains
[D07-T02 clean installation](PRIVATE_INSTALLATION_ACCEPTANCE.md). P162 snapshot
reads remain an independent P1 optimization. This performance repair does not
close installation, upgrade, recovery, release or customer acceptance.
