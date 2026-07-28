# Platform Guideline and User Manual

## Purpose

DeclarAI is a guided model-development platform for tabular supervised machine
learning, with the current product centered on binary classification and
credit-risk style modeling. The core workflow is declarative: the analyst
declares data roles, pipeline settings, feature usage, encoding choices, and
run steps; the platform executes those choices and preserves the resulting
artifacts for review.

## Main Capabilities

DeclarAI supports these primary capabilities:

- File upload and data declaration for CSV and Excel inputs.
- Data dictionary generation with editable descriptions, measurement levels,
  and model-usage flags.
- Data purifier configuration and execution.
- Train/test split setup, including random and out-of-time strategies.
- Data quality review with stability and distribution metrics.
- Categorical encoding analysis with native categorical handling as the
  preferred path for boosting models.
- Model training, cross-validation, explainability, and feature ranking.
- Sequential Feature Selection (SFS), including forward, backward, and
  forward-from-backward workflows.
- Hyperparameter tuning after a selected feature set is available.
- Pipeline notes that preserve analyst rationale at key review points.
- AI assistant support for explanation, inspection, configuration proposals,
  and executable pipeline actions.

## Pipeline Stages

### Modeling pipeline variants (v3.0)

- **Boosting** — XGBoost / LightGBM / CatBoost with SFS and hyperparameter tuning.
- **Logit** — sklearn LogisticRegression; skip SFS/HP and continue to Evaluation.
- **Credit scoring** — WOE/IV binning + logistic coefficients mapped to PDO score points.
- **Anomaly detection** — IsolationForest MVP; outer-test ranking metrics when a binary Target exists.

DeclarAI follows the **CRISP-DM operating model**: each iteration cycles through
business understanding, data understanding, preparation, modeling, evaluation,
deployment, and monitoring. The left navigation mirrors these phases; checkpoint
state preserves Business Understanding fields and `crisp_dm` metadata across saves
and iteration clones.

1. **Business Understanding** — problem framing, target contract, forbidden
   features, and success criteria (primary metric, direction, floor, cost matrix).
   Optional hard-block prevents modeling until a floor is set.
2. **Data Understanding** — pipeline type, upload, dictionary review (formerly
   “Declaration”).
3. **Data Purifier** — preprocessing and train/test split.
4. **Data Quality Summary** — stability, PSI, and model-usage review. Export
   CRISP pack available from the DQ toolbar.
5. **Categorical Feature Encoding** — handled automatically for native boosting.
6. **Modeling** — algorithm training, CV metrics, explainability.
7. **Sequential Feature Selection** — backward/forward SFS with run history and CSV export.
8. **Hyperparameter Tuning** — grid/random/Bayesian search; champion promotion to Evaluation.
9. **Evaluation** — locked outer-test scoring, business floor pass/fail, cost-aware
   threshold table, governance checkboxes, evaluation pack download, model card.
10. **Deployment** — gated score bundle and deployment pack when readiness checks pass.
11. **Monitoring** — offline drift on uploaded scored batches; **Start iteration N+1**
    clones the pipeline run while preserving Business Understanding.

The user should not treat these stages as isolated screens. For example, model
performance depends on business success criteria, data declaration, purifier
selections, split strategy, encoding readiness, and the chosen feature set.

## Data Declaration

The analyst uploads data, confirms the parser settings, reviews a preview, and
declares the target variable. DeclarAI generates a data dictionary with feature
names, inferred data types, Level of Measurement, descriptions, and model-usage
flags.

Important user actions:

- Mark the target variable explicitly.
- Exclude IDs, timestamps, leakage columns, and operational-only columns from
  modeling by setting Model_Usage_YN to `No`.
- Add or improve feature descriptions so modeling and assistant guidance can
  use business context.
- Correct Level of Measurement where automatic inference is ambiguous.

## Data Purifier

The Data Purifier applies selected preprocessing options and creates the
processed file consumed downstream. Options are selected from the canonical
catalog of 34 choices. Standalone options can be combined freely. Threshold
families are mutually exclusive within their group, so the user should choose
one correlation threshold, one sparsity threshold, one missingness threshold,
one combined sparsity/missingness threshold, one numeric outlier clipping band,
and one categorical rare-level merge threshold when those families are used.

The purifier is not a hidden AutoML step. The user chooses the options, and the
summary reports what changed.

## Split Configuration

DeclarAI supports random split and out-of-time split. A random split is useful
for ordinary development when the sample is not time ordered. An out-of-time
split is preferred when the deployment setting depends on future data behaving
like a later time window.

The user should review target rates and row counts across full, train, and test
sets. A split that creates severe target imbalance or unrealistic time leakage
should be corrected before modeling.

## Data Quality Summary

The Data Quality Summary helps the user identify stability, missingness,
distribution drift, and variable-health issues before training. It should be
used to confirm that data is plausible and that risky variables are flagged
early.

Common review questions:

- Which variables have high missingness?
- Which variables drift between train and test?
- Are any variables dominated by one value?
- Are any features excluded from modeling and why?

## Categorical Feature Encoding

DeclarAI prefers native categorical handling for supported boosting models. The
encoding plan still matters: it identifies categorical features, measurement
levels, unique values, fallback strategies, and ordinal ranking needs.

When a feature is ordinal, the user should provide a ranking of category values.
Ranking is a modeling decision, not a formatting detail. If the ranking is wrong,
the model can learn the wrong monotonic order.

## Modeling

Modeling trains the selected boosting algorithm, computes cross-validation
results, records model performance, calculates explainability artifacts, and
builds the selected-features table. The selected-features table combines SHAP,
gain, and VIF-style multicollinearity signals so the analyst can distinguish
predictive value from redundancy.

Before starting modeling, confirm:

- Data purifier has run and produced a processed file.
- Encoding plan is ready.
- Ordinal features have rankings where required.
- Model_Usage_YN has excluded identifiers, timestamps, and leakage columns.
- Algorithm selection is intentional.

## Sequential Feature Selection

Sequential Feature Selection is used after modeling to test smaller feature
subsets under cross-validation. Backward selection starts with all candidate
features and removes weak contributors. Forward selection starts with no
features and adds strong contributors. Forward-from-backward starts from a
survivor set at a chosen backward step and then performs forward selection
inside that pool.

SFS is controlled by stopping criteria:

- Monitored metrics, such as ROC-AUC or PR-AUC.
- Percentage-change thresholds.
- Minimum and maximum feature counts.
- Parallel jobs and top-K candidate settings.

The last SFS row is the point where stopping criteria fired. It is not
automatically proof that every possible feature was tested.

## Hyperparameter Tuning

Hyperparameter tuning runs after SFS has produced a candidate feature set. It
can use grid, random, Bayesian, or automatic search-method selection. The
automatic method estimates grid cost using candidate count, CV folds, and
worker count, then chooses a practical search strategy.

Users should tune only after feature selection is reasonably stable. Tuning a
large, unstable, or leakage-prone feature set can make the model look better
without improving deployment readiness.

## Assistant Usage

The assistant can answer conceptual questions, explain platform workflow, fetch
live pipeline artifacts, inspect current results, and propose executable
actions. It should be treated as an analyst copilot: it can help reason and
prepare changes, but the user remains responsible for accepting applied actions
and validating business assumptions.

Use the assistant for:

- Explaining a pipeline stage or metric.
- Asking what a current result means.
- Reviewing selected features, SHAP, VIF, SFS, or data quality.
- Asking which purifier or encoding settings are appropriate.
- Preparing one-click actions such as updating model usage, setting ordinal
  rankings, starting preprocessing, applying encoding, starting modeling,
  starting SFS, or starting hyperparameter tuning.

## Settings and Configuration Summary

Key settings include:

- Target variable and target definition.
- Feature descriptions and Level of Measurement.
- Model_Usage_YN for inclusion or exclusion from modeling.
- Purifier option IDs and thresholds.
- Split strategy, date column, cutoff, and random percentage.
- Algorithm selection.
- Encoding native/fallback behavior and ordinal rankings.
- SFS methods, stopping criteria, `n_jobs`, and `top_k`.
- Hyperparameter search method, iterations, CV folds, workers, metric, and
  enabled parameter ranges.

## Practical Operating Pattern

For a high-quality modeling run:

1. Upload data and confirm the parser settings.
2. Declare target and document features.
3. Exclude IDs, timestamps, and obvious leakage.
4. Choose purifier options and split strategy.
5. Run preprocessing and review the purifier summary.
6. Review data quality and split validation.
7. Resolve encoding and ordinal ranking decisions.
8. Train the model and inspect CV, SHAP, gain, and VIF.
9. Use SFS to evaluate smaller feature sets (ROC-AUC / PR-AUC for classifiers; R² for regressors).
10. Tune hyperparameters on the selected feature set.
11. Run Evaluation on the locked outer test and review the model card (deploy readiness).
12. Resolve any blocking items (missing lineage, high leakage) before Deployment.
13. Create the score bundle only when the model-card gate is ready; batch-score CSVs against the frozen schema.
14. Document decisions with notes and export artifacts for review.
