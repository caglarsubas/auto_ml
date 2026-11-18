# Paired development diagnostics

Open a successful native training job and expand **Paired development comparison**.
The job receipt records the comparison and its limitations. Independent reproduction
checks the comparison against a fresh refit with the exact approved plan and runtime.

The current scope is the native numeric classification and regression search. It
compares depth 2 with depth 1 under one accepted plan, source snapshot, and declared
metric. The candidates must have identical ordered training and validation memberships
for every fold. Validation rows must be unique across folds. This applies to the
supported random, grouped, and out-of-time plans. The job records an unavailable
status with a reason when fold evidence or a finite metric is missing.

- The effect is the equal-weight mean of the within-fold differences, in the
  declared metric's units. Equal fold weighting matches native candidate selection.
  Positive improvement favors depth 2 for either metric direction.
- The sensitivity range is the minimum and maximum improvement after omitting
  each validation fold in turn, with the original fits held fixed. The receipt
  retains each omission and the per-fold scores and validation counts.
- Sampling uncertainty is unavailable. Overlapping training sets and dependent
  observations limit inference from a single cross-validation run. Grouped and
  out-of-time folds retain their declared entity and time boundaries. Comparisons
  are exploratory and use development outcomes only. [Bengio and Grandvalet, 2004](https://jmlr.csail.mit.edu/papers/v5/grandvalet04a.html)

The diagnostic adds no fits, automatic decisions or numerical acceptance gates.
Plan version 2 binds the result shape for new submissions. Historical receipts
remain inspectable, and exact historical reproduction uses the recorded runtime.
The saved-model comparison endpoint reports that matching evidence is unavailable
and returns no outer-test scores. Broader feature and model comparisons are
tracked in D10.
