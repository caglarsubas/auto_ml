# Technical Disclosure

## Scope

This document explains what data-science decisions DeclarAI makes, what it
calculates, and why those calculations exist. It is written for platform users,
model validators, and technical reviewers who need to understand the assumptions
behind the pipeline.

## General Modeling Assumptions

DeclarAI focuses on tabular supervised learning. Binary classification is the
primary product path; continuous targets train a boosting regressor through the
same adapter interface (XGBoost / LightGBM / CatBoost) with the leakage-safe
split and train-only impute contract. In
credit-risk style projects, the target is usually an event indicator such as
default, fraud, churn, or another adverse outcome. The platform assumes the user
can identify the target variable and can separate legitimate predictors from
identifiers, timestamps, leakage fields, and administrative fields.

The platform favors transparent, reviewable transformations over opaque
automation. Automatic inference is used to accelerate work, but user-declared
settings remain the governing source of truth.

## Data Type and Measurement-Level Decisions

At declaration time, DeclarAI infers data type from the uploaded file and assigns
a Level of Measurement where possible. These inferred labels are starting
points. The user can correct them because measurement level is a modeling
decision.

Common assumptions:

- Numeric columns may be continuous, ordinal, binary, identifiers, or encoded
  categories.
- Object/string columns are usually categorical, but they may encode dates,
  identifiers, or ordered categories.
- Binary columns can be true predictive flags, target variables, or leakage
  flags depending on business meaning.
- Ordinal categories require a meaningful user-approved order.

## Data Purifier Decisions

The purifier applies user-selected rules from a canonical catalog. It does not
search for all possible preprocessing strategies automatically. Each selected
option exists to remove a specific data-quality risk.

Standalone options:

- Column-wise duplicate drop removes redundant columns with identical values.
- Row-wise duplicate drop removes duplicate records.
- Zero-variance drop removes features that carry no signal.
- Perfect-correlation drop removes one feature from a perfectly correlated pair.

Threshold families:

- Correlation-drop removes one of two highly correlated features at or above the
  selected threshold. Lower thresholds are more aggressive.
- Sparsity-drop removes features dominated by zero-like values at or above the
  selected threshold.
- Missing-drop removes features whose missing ratio meets or exceeds the
  selected threshold.
- Combined sparsity/missingness drop uses max(zero_ratio, missing_ratio) and
  removes columns at or above the selected threshold.
- Numeric outlier quantile clipping caps numeric values to selected lower and
  upper quantiles.
- Categorical rare-level merge groups rare categories below the selected
  frequency threshold.

The reason for these rules is practical: remove or cap data defects that can
destabilize model training, reduce generalization, or make review artifacts
harder to interpret.

## Train/Test Split Decisions

The split creates an out-of-sample evaluation set. DeclarAI supports random and
out-of-time split strategies.

Random split assumes the sample is exchangeable enough that random partitioning
approximates future data. Out-of-time split assumes time ordering matters and
that later observations better represent deployment behavior.

The platform calculates row counts and target rates for the full, train, and
test samples. Large target-rate differences can indicate sampling risk,
temporal drift, or insufficient event volume.

Preprocessing persists the outer train/test indices as a canonical split
artifact. Modeling reuses that outer split: validation is carved from the
outer-train portion for early stopping and hyperparameter search, while the
outer test remains locked until Evaluation. Numeric imputation and supervised
encodings are fit on train rows only.

## Data Quality Calculations

Data Quality Summary calculations help determine whether a feature is stable and
usable.

Population Stability Index (PSI) compares feature distributions between train
and test or across time windows. A common rule of thumb is:

- PSI < 0.10: stable.
- PSI 0.10 to 0.25: moderate shift.
- PSI > 0.25: significant shift.

Characteristic Stability Index (CSI) applies a similar distribution-shift idea
to categorical feature characteristics. Jensen-Shannon Divergence compares
probability distributions in a bounded, symmetric way.

Missing percentage, unique counts, distribution summaries, and data-type labels
are calculated so analysts can spot variables that may need exclusion, special
handling, or business review.

## Encoding Decisions

DeclarAI prefers native categorical support for boosting models when available
because it avoids unnecessary information loss from manual encoding. The
encoding plan still records fallback strategies because not all categorical
variables are equally safe to pass natively.

Fallback assumptions:

- Nominal features have no natural order. Label encoding can be used as a
  fallback, but the user should be cautious because integer labels can imply an
  artificial order to some models.
- Ordinal features have a meaningful rank order. DeclarAI expects explicit
  rankings for ordinal categories so the ordering is reviewable.
- Very low-cardinality categoricals may be one-hot encoded in fallback paths.
- High-cardinality categorical features may need target encoding. When modeling
  supplies train indices, target encoding uses out-of-fold means on train and
  applies the train mapping to valid/test (with smoothing toward the train
  prior). Standalone encoding apply without a split still uses in-sample means.
  Target encoding should still be reviewed for leakage and overfitting risk.

## Modeling Calculations

Modeling trains XGBoost, LightGBM, or CatBoost through a shared booster adapter.
Binary / low-cardinality targets are handled as classification outcomes.
High-cardinality continuous targets (more than 50 unique values) train a
boosting regressor and report R² / RMSE / MAE on the locked outer test.
Class imbalance is addressed with `scale_pos_weight = neg/pos` on the train fold.
Numeric imputation means are fit on the train fold only and applied to valid/test.
Data Purifier learned decisions (variance/correlation/missingness/sparsity drops,
numeric clip bounds, rare-category merges) are fit on the outer-train partition
only and then applied to the full frame; structural deduplication runs before the
split is frozen.
The platform uses cross-validation on train+valid (excluding the locked outer
test) to estimate model performance more robustly than a single split. When the
preprocessing split strategy is out-of-time (OOT), CV uses time-ordered folds
instead of shuffled stratified folds. When an entity/ID column is available
(typically a Model_Usage=No identifier still present on the frame), CV uses
group-aware folds so the same entity does not appear in both train and
validation within a fold.
Probability calibration (isotonic when validation is large enough, otherwise
Platt) is fit on validation scores and applied in Evaluation and Deployment.
Automated leakage heuristics flag high-IV, near-perfect target correlation,
identifier-like names, and near-unique columns as review warnings.

Common metrics:

- ROC-AUC measures ranking ability across classification thresholds.
- PR-AUC focuses on precision and recall and is often more informative for rare
  positive classes.
- Precision is the share of predicted positives that are true positives.
- Recall is the share of actual positives that the model captures.
- F1 balances precision and recall.
- Log-loss penalizes overconfident wrong probabilities.

The platform does not treat one metric as universally best. The right metric
depends on the business objective and class balance.

## Explainability Calculations

SHAP values estimate how much each feature contributes to individual model
predictions. Mean absolute SHAP impact summarizes global importance. Signed
impact indicates whether high feature values generally push predictions upward
or downward, subject to the model and data distribution.

Gain importance comes from the tree model and measures how much splits on a
feature improved the objective during training. SHAP and gain can disagree
because they measure different things.

DeclarAI combines SHAP percentile and gain percentile using a geometric mean.
The calculation is:

1. Convert absolute SHAP impact to an ECDF percentile.
2. Convert gain importance to an ECDF percentile.
3. Compute sqrt(SHAP_percentile * Gain_percentile).

This rewards features that rank well on both explainability and model-split
importance while reducing scale mismatch between SHAP and gain.

## VIF and Multicollinearity

Variance Inflation Factor (VIF) estimates how predictable one feature is from
the other features. High VIF indicates multicollinearity risk. Common review
thresholds are:

- VIF <= 5: usually acceptable.
- VIF 5 to 10: elevated.
- VIF > 10: severe.

High VIF does not always mean a feature must be dropped. The user should compare
VIF with SHAP, gain, business meaning, and SFS behavior.

## Sequential Feature Selection Decisions

SFS evaluates feature subsets through repeated model fits. Backward selection
starts from all candidate features and removes weak contributors. Forward
selection starts from none and adds strong contributors. Forward-from-backward
uses a backward survivor set as the candidate pool for forward selection.

SFS stops according to configured criteria, not necessarily after exhausting all
possible subsets. Stopping criteria include monitored metrics, percentage-change
thresholds, minimum features, and maximum features.

Top-K candidate screening is a performance optimization. It does not mean the
platform is proving that all non-top-K candidates are useless.

## Hyperparameter Tuning Decisions

Hyperparameter tuning searches model settings after a feature set is chosen.
Grid search is exhaustive over a configured grid but can be expensive. Random
search samples configurations and is useful for larger spaces. Bayesian search
uses prior results to choose promising next configurations. The automatic mode
uses estimated fit count per worker to choose a practical strategy.

The platform records the requested method, resolved method, number of trials,
primary metric, and validation-curve outputs so reviewers can understand the
search.

## Assistant Retrieval and Tool Decisions

The assistant uses three context sources:

- Knowledge-bank retrieval for stable platform documentation, terminology, and
  technical disclosure.
- Live pipeline tools for current user data, settings, metrics, and artifacts.
- Executable action proposals for user-approved pipeline changes.

Knowledge-bank retrieval should answer "how does this work?" and "what does
this term mean?" Live tools should answer "what is happening in my current
pipeline?" Action blocks should only appear when the user asks to change or run
something, or when the assistant offers a concrete applyable recommendation.
