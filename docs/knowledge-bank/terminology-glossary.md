# Terminology Glossary

## Action Block

A structured assistant response section that the chat panel turns into an
Apply button. Action blocks can update metadata, update configuration, execute
code, start pipeline runs, apply encoding, start modeling, start SFS, start
hyperparameter tuning, or update notes.

## AI Assistant

The embedded DeclarAI copilot. It can explain concepts, retrieve platform
documentation, inspect current pipeline artifacts through tools, and prepare
actions for the user to apply.

## AUC

Area Under the Curve. In DeclarAI, AUC usually refers to ROC-AUC unless stated
otherwise.

## Backward Selection

An SFS method that starts with all candidate features and removes one feature at
each step. Early removed features are usually weaker contributors under the
configured evaluation setup.

## CatBoost

A gradient-boosting algorithm with strong native support for categorical
features. It is one of the intended boosting-family algorithms for DeclarAI.

## CSI

Characteristic Stability Index. A categorical stability metric used to detect
distribution shift in categorical features or feature characteristics.

## CV

Cross-validation. A model-evaluation method that trains and evaluates across
multiple folds to estimate performance more robustly than one train/test split.

## Data Declaration

The stage where users upload data, confirm parsing, declare a target, and review
the data dictionary.

## Data Dictionary

The table of feature metadata: feature name, description, data type, Level of
Measurement, model-usage flag, and related fields.

## Data Purifier

The preprocessing stage where selected rules remove duplicates, constant
features, highly correlated features, sparse or missing-heavy features, and
outlier issues.

## ECDF

Empirical Cumulative Distribution Function. DeclarAI uses ECDF percentiles to
place SHAP impact and gain importance on comparable rank scales before
computing the Combined Score.

## Encoding Plan

The per-feature plan for categorical handling. It records measurement level,
unique values, native strategy, fallback strategy, and ordinal-ranking needs.

## Feature Usage

The keep/drop decision in the selected-features table. Dropping via feature
usage excludes a feature from SFS/modeling workflows without permanently
deleting the column from the dataset.

## Forward Selection

An SFS method that starts with no features and adds one feature at each step.
Early added features are usually the strongest individual contributors under
the configured evaluation setup.

## Forward-from-Backward

An SFS workflow where the user chooses a backward-selection cut step and then
runs forward selection using the remaining features at that step as the
candidate pool.

## Gain

Tree split gain importance. It measures how much a feature's splits improved
the tree objective during model training.

## Hyperparameter

A model setting chosen before or during training, such as max depth, learning
rate, number of estimators, regularization strength, or sampling fraction.

## IV

Information Value. A credit-risk metric often used with Weight of Evidence
binning to evaluate predictive strength. It may appear in domain discussions
even when the current boosting pipeline does not require scorecard binning.

## JSD

Jensen-Shannon Divergence. A bounded, symmetric distribution-distance metric
used to compare probability distributions.

## Leakage

Information that would not be available at prediction time or that directly
reveals the target. Leakage can make validation metrics look unrealistically
strong and must be excluded.

## Level of Measurement

The semantic measurement type of a feature. Common values include nominal,
ordinal, continuous, binary, interval, ratio, or unknown. It affects encoding
and interpretation.

## LightGBM

A gradient-boosting algorithm with efficient training and native categorical
handling.

## Model_Usage_YN

The data dictionary flag that controls whether a column is included for
modeling. Use `No` for IDs, timestamps, leakage fields, and operational-only
columns.

## Native Categorical Handling

Passing categorical features to a boosting algorithm in a way the algorithm can
handle directly, instead of forcing manual one-hot, ordinal, or label encoding.

## OOT Split

Out-of-time split. A validation split where later observations are held out to
simulate future deployment behavior.

## PR-AUC

Area under the Precision-Recall curve. It is especially useful for imbalanced
binary classification where the positive class is rare.

## Precision

The share of predicted positives that are true positives.

## PSI

Population Stability Index. A distribution-shift metric often reviewed with
rules of thumb: below 0.10 is stable, 0.10 to 0.25 is moderate shift, and above
0.25 is significant shift.

## Recall

The share of actual positives that the model correctly captures. Also called
sensitivity or true positive rate.

## ROC-AUC

Area under the Receiver Operating Characteristic curve. It measures ranking
quality across thresholds.

## SFS

Sequential Feature Selection. A stepwise feature-subset search that can run
forward, backward, or forward-from-backward.

## SHAP

SHapley Additive exPlanations. SHAP values estimate feature contribution to
individual predictions. Mean absolute SHAP summarizes global feature impact.

## Split Validation

The review of full/train/test row counts and target rates after a split is
created.

## Target Definition

The business meaning of the target variable. The assistant should tie modeling
advice back to the target definition when it is available.

## Top-K Candidates

An SFS performance optimization that fully evaluates only the best quick-screened
candidates at each step.

## VIF

Variance Inflation Factor. A multicollinearity metric. Values above 5 deserve
review; values above 10 are usually severe.

## WOE

Weight of Evidence. A credit-risk transformation that maps bins or categories to
log odds. It is common in scorecards and may be discussed as a domain concept.

## XGBoost

A gradient-boosting algorithm commonly used for tabular classification. DeclarAI
supports it as a primary boosting model and can use native categorical handling.
