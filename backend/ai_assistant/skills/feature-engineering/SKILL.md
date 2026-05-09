---
name: feature-engineering
description: "Comprehensive best practices, formulas, and strategies for generating new features from existing data. Use for: tabular data modeling, automated feature generation, domain-specific feature design (banking, fraud, telecom, insurance, healthcare, trading), and avoiding data leakage."
license: Complete terms in LICENSE.txt
---

# Feature Engineering Guide

This skill provides a structured, point-in-time-safe catalogue of reusable feature patterns. It is designed to guide automated feature generation by providing domain-specific transformations, cross-cutting universal patterns, and strict leakage-prevention rules.

## Core Principles

1. **Domain-Aware First**: Domain-aware feature generation outperforms model tuning for tabular problems. Apply domain-specific ratios, aggregations, and interactions before resorting to complex model architectures.
2. **Leakage is the Silent Killer**: Features must be defined with explicit event time, retrieval time, and as-of join semantics.
3. **Cardinality Dictates Encoding**: Low cardinality (<20) uses one-hot; medium uses target/frequency; high uses embeddings or Weight of Evidence (WOE).

## Cross-Cutting Universal Feature Patterns

These patterns apply across nearly all tabular machine learning tasks.

### 1. Temporal and Aggregate Features
- **RFM (Recency, Frequency, Monetary)**:
  - Recency: Days since last event.
  - Frequency: Count of events in a window (e.g., 7d, 30d, 90d).
  - Monetary: Sum, mean, max, or median of transaction amounts.
- **Lags and Rolling Windows**:
  - `lag_k(x)`: Value at time $t-k$. Shift by $\ge$ forecast horizon to avoid leakage.
  - Rolling mean/std/sum over windows (7, 14, 30, 60, 90 days).
  - EWMA (Exponentially Weighted Moving Average): $\text{EWMA}_{\lambda}(x_t)=\sum_{k=0}^{K}\lambda^k x_{t-k}$.

### 2. Ratio and Interaction Features
- Ratios linearize monotone-but-nonlinear relationships and are scale-invariant.
- **Velocity Ratios**: Compare short-term activity to long-term baseline (e.g., last 1h count vs. last 30d average).
- **Utilization**: $\frac{\text{balance}}{\max(\text{credit\_limit},\epsilon)}$.
- **Interactions**: Products of informative features (e.g., age $\times$ tenure).

### 3. Categorical Encoding and Binning
- **Weight of Evidence (WOE) & Information Value (IV)** (Standard in credit risk):
  - $\text{WOE}_i = \ln\left(\frac{\% \text{non-events}_i}{\% \text{events}_i}\right)$
  - $IV = \sum_i (\% \text{non-events}_i - \% \text{events}_i) \cdot \text{WOE}_i$
  - IV interpretation: <0.02 (useless), 0.02–0.1 (weak), 0.1–0.3 (medium), 0.3–0.5 (strong), >0.5 (suspicious, check for leakage).
- **Target Encoding**: Must use out-of-fold or smoothing to avoid leakage.

### 4. Network and Graph Features
- Degree (in/out), weighted degree (sum amounts).
- PageRank, centrality, community ID.
- Shared-attribute features: Number of accounts sharing a device, IP, or email.

## Industry-Specific Patterns

### Banking & Credit Scoring
- **Goal**: Predict default risk.
- **Core Features**:
  - Credit-to-Income: `AMT_CREDIT / AMT_INCOME_TOTAL`
  - Annuity-to-Income: `AMT_ANNUITY / AMT_INCOME_TOTAL`
  - Years Employed: `DAYS_EMPLOYED / 365`
  - Income per Family Member: `AMT_INCOME_TOTAL / (CNT_FAM_MEMBERS + 1)`
- **Techniques**: Heavy use of WOE/IV binning to ensure monotonicity and interpretability.

### Fraud Detection (Payments & E-commerce)
- **Goal**: Detect anomalous transactions.
- **Core Features**:
  - Velocity: $\frac{\text{Count(Tx}_{1h}\text{)}}{\text{Avg(Tx}_{1h\_over\_30d}\text{)}}$
  - Aggregations: Count/amount in rolling windows by card, account, device, or IP.
  - Behavioral: Device/IP changes, email domain score, essential vs. non-essential spend patterns.
  - Graph: Shared devices or payment methods between accounts.

### Telecom Churn & Propensity
- **Goal**: Predict churn or offer acceptance.
- **Core Features**:
  - Average Monthly Charges: `TotalCharges / tenure`
  - Service Aggregates: Count of additional services (e.g., DeviceProtection + TechSupport).
  - Monthly Charges Ratio: `MonthlyCharges / TotalCharges`
  - Behavioral: Number of services (high = sticky, low = churn risk).

### Insurance (Claims & Pricing)
- **Goal**: Assess claim severity, frequency, and price elasticity.
- **Core Features**:
  - Claim frequency: `count_ClaimID_perProvider`
  - Mean hospital days per provider, third parties involved per claim.
  - Temporal: Days since policy start, days between loss date and policy alteration.
  - Price Elasticity: $\text{PED} = \frac{\Delta Q / Q}{\Delta P / P}$

### Trading & Price Sensitivity
- **Goal**: Predict price direction or volatility.
- **Core Features**:
  - Returns: $r_t = \frac{P_t - P_{t-1}}{P_{t-1}}$
  - Trend: SMA, EMA, MACD, RSI.
  - Volatility: Standard deviation, Average True Range (ATR), Realized Volatility (RV).

### Healthcare Risk Modeling
- **Goal**: Predict disease risk, readmission, or adherence.
- **Core Features**:
  - Clinical Aggregates: Age, obesity (BMI>30), cardiovascular risk flags.
  - Temporal Trends: Vitals deltas, medication possession ratios, lab-value trends.
  - Behavioral: Visit frequency, appointment no-show history.

## Using Bundled Resources

This skill includes comprehensive scripts and references to accelerate feature engineering workflows.

### Scripts

**feature_engineering_pipeline.py** automates the complete feature engineering workflow. Initialize with your target column and task type (classification or regression), then call the `run()` method to execute data loading, cleaning, categorical encoding, feature creation, feature selection, and model training in sequence.

**feature_importance_analyzer.py** analyzes feature importance using multiple techniques including tree-based importance, permutation importance, and correlation analysis. It provides normalized importance scores across methods and identifies your top features for the model.

**data_visualizer.py** generates comprehensive visualizations including feature distributions, correlation heatmaps, target relationships, missing value patterns, box plots, and summary statistics. All plots are automatically saved to your specified output directory.

**feature_store_integration.py** manages the complete feature lifecycle with support for local or cloud-based feature stores. Register features, publish feature groups, and retrieve features for specific entities with point-in-time correctness guarantees.

### References

**feature_engineering_best_practices.md** provides detailed guidance on encoding methods (one-hot, label, target, WOE), scaling techniques (standardization, min-max, log, Box-Cox), feature selection algorithms (filter, wrapper, embedded), and feature creation techniques (temporal, interaction, aggregation, domain-specific).

**error_handling_guide.md** offers practical solutions for common feature engineering errors including data type mismatches, missing values, outliers, division by zero, categorical encoding errors, scaling issues, memory problems, and temporal leakage prevention.

## Leakage Prevention Checklist

1. **Time-Ordered Splits**: Ensure training data strictly precedes test data chronologically.
2. **Point-in-Time Correctness**: Use as-of joins; never aggregate future events relative to the prediction time.
3. **Fold-Aware Encoding**: When target encoding, compute means out-of-fold.
4. **Domain Traps**:
   - Fraud: Label delay (chargebacks take weeks to arrive).
   - Credit: Post-decision variables or future bureau updates.
   - Graph: Edges from the future relative to prediction time.
