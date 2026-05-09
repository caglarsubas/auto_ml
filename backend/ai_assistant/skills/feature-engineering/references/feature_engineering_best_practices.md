# Feature Engineering Best Practices

## Overview

This guide covers proven techniques for feature engineering across multiple domains and use cases. Feature engineering is often the most impactful step in the machine learning pipeline, frequently outperforming model tuning and hyperparameter optimization.

## Core Principles

### 1. Domain Knowledge First
- Leverage domain expertise to create meaningful features
- Understand the business problem and data context
- Validate features with domain experts

### 2. Simplicity Over Complexity
- Start with simple, interpretable features
- Add complexity only when justified by performance gains
- Avoid over-engineering features

### 3. Data Quality Foundation
- Clean data before feature engineering
- Handle missing values appropriately
- Remove or flag outliers based on domain context

## Encoding Methods

### Categorical Encoding

#### One-Hot Encoding
- **Use case**: Low cardinality features (<20 categories)
- **Pros**: Works well with linear models, interpretable
- **Cons**: Creates many columns for high cardinality
- **Implementation**: `pd.get_dummies()`, `sklearn.preprocessing.OneHotEncoder`

#### Label Encoding
- **Use case**: Tree-based models, ordinal categories
- **Pros**: Maintains order information
- **Cons**: Implies false ordering for nominal categories
- **Implementation**: `sklearn.preprocessing.LabelEncoder`

#### Target Encoding
- **Use case**: High cardinality features
- **Pros**: Captures relationship with target, reduces dimensionality
- **Cons**: Risk of leakage if not done carefully
- **Implementation**: Out-of-fold encoding, smoothing with global mean
- **Formula**: `enc(c) = (n_c · mean_c + m · global_mean) / (n_c + m)`

#### Weight of Evidence (WOE)
- **Use case**: Credit risk, regulated domains
- **Pros**: Monotonic relationship to log-odds, handles missing as separate bin
- **Cons**: Requires binning, more complex
- **Formula**: `WOE_i = ln(% non-events_i / % events_i)`

### Numerical Scaling

#### Standardization (Z-score)
- **Formula**: `(x - mean) / std`
- **Use case**: Linear models, distance-based algorithms
- **Implementation**: `sklearn.preprocessing.StandardScaler`

#### Min-Max Scaling
- **Formula**: `(x - min) / (max - min)`
- **Use case**: Bounded features, neural networks
- **Implementation**: `sklearn.preprocessing.MinMaxScaler`

#### Log Transformation
- **Use case**: Skewed distributions, monetary values
- **Formula**: `log(x + 1)` (add 1 to handle zeros)
- **Implementation**: `np.log1p()`

#### Box-Cox Transformation
- **Use case**: Normalizing distributions
- **Pros**: Automatically finds optimal transformation
- **Implementation**: `scipy.stats.boxcox`

## Feature Selection Algorithms

### Filter Methods
- **Variance Threshold**: Remove low-variance features
- **Correlation Analysis**: Remove highly correlated features
- **Statistical Tests**: Chi-square, ANOVA, mutual information
- **Pros**: Fast, independent of model
- **Cons**: Doesn't consider feature interactions

### Wrapper Methods
- **Forward Selection**: Add features one by one
- **Backward Elimination**: Remove features one by one
- **Recursive Feature Elimination (RFE)**: Recursive removal based on importance
- **Pros**: Considers feature interactions
- **Cons**: Computationally expensive

### Embedded Methods
- **Tree-Based Importance**: Random Forest, XGBoost feature importance
- **Regularization**: L1 (Lasso), L2 (Ridge) penalties
- **Pros**: Fast, considers model performance
- **Cons**: Model-specific

## Feature Creation Techniques

### Temporal Features
- **Time-Since**: Days since last event, account opening
- **Lag Features**: Previous values at different time steps
- **Rolling Statistics**: Mean, std, min, max over windows
- **Seasonal Features**: Day of week, month, quarter, holiday flags

### Interaction Features
- **Multiplication**: `feature_1 * feature_2`
- **Division**: `feature_1 / feature_2` (with safe handling)
- **Addition/Subtraction**: `feature_1 + feature_2`, `feature_1 - feature_2`
- **Polynomial**: `feature_1^2`, `feature_1^3`

### Aggregation Features
- **Group-By Aggregations**: Count, sum, mean, std by category
- **Entity-Level Aggregates**: Customer-level, merchant-level statistics
- **Time-Window Aggregates**: Last 7 days, 30 days, 90 days

### Domain-Specific Features
- **Financial Ratios**: DTI, LTV, utilization
- **Behavioral Scores**: RFM (Recency, Frequency, Monetary)
- **Network Features**: Degree, centrality, community ID
- **Text Features**: TF-IDF, topic modeling, embeddings

## Data Leakage Prevention

### Common Leakage Scenarios

1. **Time Leakage**
   - Using future information to predict the past
   - Solution: Strict time-ordered splits, as-of joins

2. **Target Leakage**
   - Using post-decision variables
   - Solution: Only use information available at prediction time

3. **Encoding Leakage**
   - Computing statistics on entire dataset
   - Solution: Out-of-fold encoding, fit on training data only

4. **Shared Entity Leakage**
   - Same entity appearing in train and test
   - Solution: Group-aware cross-validation

### Prevention Checklist

- [ ] Ensure training data precedes test data chronologically
- [ ] Use as-of joins for temporal data
- [ ] Compute statistics on training data only
- [ ] Use out-of-fold encoding for categorical variables
- [ ] Validate with domain experts
- [ ] Monitor for train-serve skew in production

## Feature Monitoring

### Key Metrics

- **Feature Drift**: Distribution changes over time
- **Missing Rate**: Percentage of missing values
- **Cardinality**: Number of unique values
- **Correlation Changes**: Relationships with target changing

### Production Considerations

- **Feature Versioning**: Track feature definitions over time
- **Feature Documentation**: Document creation logic and ownership
- **Automated Retraining**: Trigger retraining on significant drift
- **A/B Testing**: Validate feature impact in production

## Tools and Libraries

### Python Libraries
- **scikit-learn**: Preprocessing, feature selection
- **pandas**: Data manipulation, aggregations
- **featuretools**: Automated feature engineering
- **tsfresh**: Time-series feature extraction
- **category_encoders**: Advanced categorical encoding

### Feature Stores
- **Feast**: Open-source feature store
- **Tecton**: Enterprise feature platform
- **Hopsworks**: Feature store with ML capabilities

## References

- Kaggle Competitions: Winning solutions often detail feature engineering approaches
- Feature Engineering for Machine Learning (O'Reilly)
- Domain-specific papers and industry guidelines
