# Prediction contract across supported entrypoints

P184 covers D01-T01. A saved pipeline binds the task, target column and binary
positive label at training admission. A contradictory request is rejected before
starting a fit. A new pipeline version can adopt an updated declaration through
the existing save workflow. Historical runs without a saved task and target can
take an explicit declaration when training a new execution.

The Business Understanding form uses the explicit task when validating the
selected metric. Wording and metric suggestions guide the form before a task is
declared. The assistant sees the same task, target and declared positive label,
including the numeric label zero. The durable numeric training form displays the
server-resolved contract and surfaces actionable declaration errors.
Assistant split summaries identify raw label coding and flag a cached report for
a different target. Feature Card reads available importance results; users start
governed training from Modeling with its accepted declaration.

## Supported paths

| Entry point | Qualified task and model combinations |
| --- | --- |
| Legacy training, exact evaluation and versioned batch scoring | XGBoost, LightGBM and CatBoost for binary or multiclass classification and regression. Logistic regression and scorecards for binary classification. Isolation forest for labeled anomaly ranking. |
| Durable numeric training, protected assessment and portable scoring | XGBoost binary classification and regression using numeric predictors. |
| Legacy feature selection and hyperparameter tuning | Supported boosters for binary classification and regression. Multiclass and anomaly requests stop with an explanation. |
| Legacy candidate refit | Binary classification, regression and the existing alternate-model refit paths. Initial multiclass models can be assessed and scored directly. |

The assessment dispatcher uses the frozen task for contract-bearing executions.
Recorded model, fit, evaluation and scoring metadata must agree with the
contract. Classification columns follow the encoded class order, with binary
positive labels at index 1. Regression retains numeric outcomes even with few
distinct values. Isolation forest emits a ranking. Native protected assessment
uses the fitted label values, accepts equivalent integer and decimal CSV
representations and rejects unseen or incompatible labels. An explicitly
excluded feature named `Target` remains excluded when a different column holds
the declared outcome.

## Evidence and scope

- The existing 12-case scoring matrix compares exact evaluated scores with
  versioned exports across row order and batch sizes. It now includes a distinct
  excluded `Target` column and a misleading historical model type name.
- Regression coverage exercises saved-declaration conflicts at both legacy
  training entrypoints, binary zero and numeric CSV labels in assessment, and
  contradictory positive-label metadata in portable scoring. Existing tests cover
  low-cardinality regression, 65-class classification, missing labels, unsupported
  task/model combinations and anomaly-ranking semantics.
- The release workflow uses all seven PR checks and independently verifies the
  automatic push to `main` on the merged tree. The exact CI runs and their
  retained receipt are available through the development tracker.

Historical immutable evidence keeps its recorded hashes. Replaying an older
portable package requires the matching scoring reader and runtime recorded in
that package. D01-T02 handles broader population, availability, prediction
horizon and label maturity qualification.
