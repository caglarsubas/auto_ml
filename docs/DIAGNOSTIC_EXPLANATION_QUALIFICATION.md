# Diagnostic and explanation qualification

## Collinearity

The authenticated inspection workflow compares exact, retained development
executions. Permuting nominal category labels preserves centered numeric VIF
and grouped GVIF within the qualification tolerance. Numeric VIF excludes
outputs derived from categories. Grouped GVIF requires exact category-group
provenance and reports explicit unavailability when a lossy encoding collapses
levels. Both archive readers check the member format, dimensions and payload
length before allocating the retained matrix.

## Importance and prediction explanations

The selected-feature table shows combined importance as a ranking heuristic
over SHAP and gain percentiles. An unavailable score remains distinct from a
measured zero. Statistical tests, effect estimates and validation decisions
require separate evidence.

The interactive explanation route uses a verified binary or regression
XGBoost execution and development predictors. It reports SHAP and partial
dependence in raw model output units. Partial dependence varies one predictor
over a grid and averages the resulting model outputs. Correlated predictors
can produce grid combinations that are rare in the development sample.
Multiclass, alternate-model, category-grid and unverified evidence states
are reported explicitly. [Partial dependence and ICE](https://scikit-learn.org/stable/modules/partial_dependence.html)

## Sequential patterns

The scan uses the training predictors from the exact recorded execution. It
reports the ordering column or input order, training and scanned row counts,
sampling stride and whether the candidate limit stopped the scan. The scan
assesses adjacent scanned rows and caps the work at 800 rows and 25 candidates.
Flags identify associations for review. Causal conclusions require separate
evidence. Historical results without verified provenance are unavailable.

D05-T01 records paired development-fold sensitivity. Broader paired feature
and model branch experiments remain in D10.
