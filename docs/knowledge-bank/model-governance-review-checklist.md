# Model Governance and Review Checklist

## Purpose

This checklist helps analysts and validators review a DeclarAI pipeline before
relying on the model, exporting artifacts, or moving toward deployment.

## Data Declaration Review

- Target variable is explicitly selected.
- Target definition is documented in business terms.
- ID, timestamp, operational-only, and leakage-prone fields are excluded from
  modeling.
- Feature descriptions are complete enough for review.
- Level of Measurement values are checked for categorical and ordinal features.
- Binary flags are verified as predictors, targets, or exclusions.

## Data Purifier Review

- Selected purifier options match the intended data-cleaning policy.
- Threshold options are not more aggressive than the project can justify.
- Dropped columns and removed rows are reviewed.
- Outlier clipping is appropriate for the business and does not hide meaningful
  rare events.
- Rare-category merging is reviewed for minority-class or protected-group risk.
- The processed file exists before downstream modeling steps are run.

## Split and Stability Review

- Split strategy matches the deployment scenario.
- Out-of-time split is used when time ordering is material.
- Train and test target rates are reasonable.
- PSI, CSI, missingness, and distribution-shift flags are reviewed.
- High-drift features are either justified, transformed, excluded, or monitored.

## Encoding Review

- Native categorical handling is appropriate for the selected algorithm.
- Fallback strategies are documented.
- Ordinal features have complete rankings.
- High-cardinality categoricals are checked for leakage and overfitting risk.
- Encoding decisions align with Level of Measurement.

## Modeling Review

- Algorithm choice is documented.
- Cross-validation metrics are reviewed with class balance in mind.
- ROC-AUC and PR-AUC are interpreted together for imbalanced targets.
- SHAP and gain are compared instead of relying on one importance signal.
- Combined Score is used as a ranking aid, not as a substitute for business
  review.
- VIF and correlated features are reviewed for redundancy.

## SFS Review

- SFS method is appropriate for the modeling goal.
- Stopping criteria are documented.
- Minimum and maximum feature counts are justified.
- Top-K and worker settings are recorded.
- Backward and forward results are interpreted according to their direction.
- The chosen feature subset balances performance, stability, simplicity, and
  business meaning.

## Hyperparameter Review

- Tuning is run after a reasonably stable feature set is chosen.
- Search method and trial count are documented.
- Primary metric aligns with the business objective.
- Validation curves are reviewed for overfitting or unstable settings.
- Tuning gains are compared against baseline model performance.

## Assistant and Action Review

- Assistant recommendations are grounded in live tool results or knowledge-bank
  citations.
- Applied actions are reversible where possible.
- Feature exclusions use feature usage rather than permanent column deletion
  unless destructive mutation was explicitly intended.
- Notes capture why important changes were made.
- No assistant response is treated as approval without human review.

## Deployment Readiness

- Data, preprocessing, encoding, feature-selection, and tuning decisions are
  traceable. *(enforced: score-bundle freeze requires lineage + outer-test evaluation)*
- High-severity automated leakage findings are cleared or features excluded.
  *(enforced: `n_high > 0` blocks score-bundle creation)*
- Performance and stability metrics are acceptable for the intended use case.
  *(human residual — no numeric AUC/PSI floors in product defaults)*
- Feature explanations are understandable to non-developer stakeholders.
  *(human residual; SHAP/gain artifacts are available for review)*
- Known limitations, data gaps, and assumptions are documented.
  *(surfaced on the model card `known_limitations` + residual human checks)*
- Monitoring requirements are defined for future data drift and performance
  decay. *(human residual; bundle manifest recommends PSI / score-distribution checks)*
