# Fold-local preparation for alternate models and search

D02-T01 makes the stored split declaration authoritative during model fitting
and feature or hyperparameter search. The inner splitter preserves the
declared temporal order, entity separation and outcome-window purge. A
constrained source with missing or contradictory search inputs requires a
refit before search can proceed. Historical records retain their provenance.

Training and development folds now fit category levels for predictors omitted
from a partial encoding plan. Each fold learns those levels from its own
training rows. A category seen only in validation becomes missing for native
categorical prediction. Explicit encoders and numeric imputation use the same
fit partition. Constrained target encoding remains unavailable pending D02-T03.

New scorecards fit quantile cuts on the raw values in the fit partition.
Training and scoring share the same bin assignment, including ties and values
outside the fitted range. Existing scorecard packages retain their recorded
mapping format.

Qualification uses synthetic examples with repeated entities, overlapping label
windows, held-out categories and missing numeric values. It exercises actual
logit, scorecard, feature selection and tuning fits. An authenticated durable
training and search test verifies the frozen source recipe through both worker
operations. The checks establish development preparation. Complete exported
provenance, protected-assessment invalidation and independent refit and review
are subsequent roadmap gates.
