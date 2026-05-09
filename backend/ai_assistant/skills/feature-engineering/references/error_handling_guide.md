# Feature Engineering Error Handling Guide

## Overview

This guide covers common errors encountered during feature engineering and provides practical solutions for handling them effectively.

## Data Type Mismatches

### Problem: Incompatible Data Types
When features have unexpected data types (e.g., numeric column stored as string), operations fail.

**Common Causes:**
- Data imported with incorrect dtypes
- Mixed types in a single column
- String representations of numbers

**Solutions:**

```python
# Convert column to numeric, coercing errors
df['feature'] = pd.to_numeric(df['feature'], errors='coerce')

# Handle mixed types
df['feature'] = df['feature'].astype(str).str.replace(',', '').astype(float)

# Check dtypes before operations
assert df['feature'].dtype in [np.float64, np.int64], "Expected numeric type"
```

### Prevention:
- Validate data types after loading
- Use `df.info()` and `df.dtypes` to inspect
- Document expected types in data schema

## Missing Values

### Problem: NaN and Null Values
Missing values cause operations to fail or produce incorrect results.

**Common Causes:**
- Data collection gaps
- Data entry errors
- Intentional missing indicators

**Solutions:**

```python
# Check missing values
print(df.isnull().sum())
print(df.isnull().sum() / len(df) * 100)  # Percentage

# Handle missing values by strategy
# 1. Deletion (if < 5% missing)
df = df.dropna(subset=['feature'])

# 2. Mean/Median imputation (numeric)
df['feature'].fillna(df['feature'].median(), inplace=True)

# 3. Mode imputation (categorical)
df['feature'].fillna(df['feature'].mode()[0], inplace=True)

# 4. Forward/Backward fill (time-series)
df['feature'].fillna(method='ffill', inplace=True)

# 5. Create missing indicator
df['feature_missing'] = df['feature'].isnull().astype(int)
df['feature'].fillna(df['feature'].median(), inplace=True)

# 6. KNN imputation
from sklearn.impute import KNNImputer
imputer = KNNImputer(n_neighbors=5)
df[['feature1', 'feature2']] = imputer.fit_transform(df[['feature1', 'feature2']])
```

### Prevention:
- Understand missing data patterns
- Document missing data handling strategy
- Create missing indicators for important features
- Validate imputation doesn't introduce bias

## Outliers

### Problem: Extreme Values
Outliers can distort statistics and model performance.

**Detection Methods:**

```python
# Z-score method
from scipy import stats
z_scores = np.abs(stats.zscore(df['feature']))
outliers = df[z_scores > 3]

# IQR method
Q1 = df['feature'].quantile(0.25)
Q3 = df['feature'].quantile(0.75)
IQR = Q3 - Q1
outliers = df[(df['feature'] < Q1 - 1.5*IQR) | (df['feature'] > Q3 + 1.5*IQR)]

# Isolation Forest
from sklearn.ensemble import IsolationForest
iso_forest = IsolationForest(contamination=0.05)
outlier_labels = iso_forest.fit_predict(df[['feature']])
```

**Handling Strategies:**

```python
# 1. Remove outliers
df = df[~((df['feature'] < lower_bound) | (df['feature'] > upper_bound))]

# 2. Cap/Winsorize
df['feature'] = df['feature'].clip(lower=lower_bound, upper=upper_bound)

# 3. Transform
df['feature'] = np.log1p(df['feature'])

# 4. Create outlier flag
df['feature_outlier'] = ((df['feature'] < lower_bound) | (df['feature'] > upper_bound)).astype(int)
```

### Prevention:
- Understand domain-specific acceptable ranges
- Document outlier handling decisions
- Validate outlier removal doesn't remove important information

## Division by Zero

### Problem: Invalid Operations
Division by zero or invalid mathematical operations cause errors.

**Solutions:**

```python
# Safe division
df['ratio'] = df['numerator'] / (df['denominator'] + 1e-8)

# Conditional division
df['ratio'] = np.where(df['denominator'] != 0, 
                       df['numerator'] / df['denominator'], 
                       0)

# Replace infinite values
df['ratio'] = df['ratio'].replace([np.inf, -np.inf], 0)
```

## Categorical Encoding Errors

### Problem: Unseen Categories
During prediction, new categories not seen in training appear.

**Solutions:**

```python
# 1. One-hot encoding with handle_unknown
from sklearn.preprocessing import OneHotEncoder
encoder = OneHotEncoder(handle_unknown='ignore', sparse=False)

# 2. Target encoding with smoothing
def target_encode(train_df, test_df, col, target):
    global_mean = train_df[target].mean()
    stats = train_df.groupby(col)[target].agg(['sum', 'count'])
    
    # Smoothing
    m = 1  # Smoothing parameter
    stats['encoded'] = (stats['sum'] + m * global_mean) / (stats['count'] + m)
    
    # Map to test data
    test_df[f'{col}_encoded'] = test_df[col].map(stats['encoded']).fillna(global_mean)
    return test_df

# 3. Frequency encoding
freq_map = train_df[col].value_counts().to_dict()
test_df[f'{col}_freq'] = test_df[col].map(freq_map).fillna(0)
```

## Feature Scaling Issues

### Problem: Inconsistent Scaling
Training and test data scaled differently causes model performance degradation.

**Solutions:**

```python
# Fit scaler on training data only
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)  # Use fit parameters

# Save scaler for production
import joblib
joblib.dump(scaler, 'scaler.pkl')
scaler = joblib.load('scaler.pkl')
```

### Prevention:
- Always fit scalers on training data only
- Save and version scalers with models
- Document scaling parameters

## Memory Issues

### Problem: Large Datasets
Feature engineering on large datasets can cause memory errors.

**Solutions:**

```python
# Process in chunks
chunk_size = 10000
for chunk in pd.read_csv('large_file.csv', chunksize=chunk_size):
    # Process chunk
    processed_chunk = feature_engineering_function(chunk)
    # Save or aggregate

# Use efficient dtypes
df['int_col'] = df['int_col'].astype('int32')  # Instead of int64
df['float_col'] = df['float_col'].astype('float32')  # Instead of float64

# Drop unnecessary columns
df = df.drop(columns=['unused_col1', 'unused_col2'])

# Use sparse matrices for categorical features
from scipy.sparse import csr_matrix
sparse_matrix = csr_matrix(encoded_features)
```

## Time Series Feature Errors

### Problem: Temporal Leakage
Using future information to predict the past.

**Solutions:**

```python
# Ensure proper time ordering
df = df.sort_values('date')

# Use expanding windows (not rolling into future)
df['rolling_mean'] = df['value'].rolling(window=7, min_periods=1).mean()

# Shift features to avoid leakage
df['lagged_feature'] = df['feature'].shift(1)  # Previous day's value

# Validate no future data in features
assert df['date'].max() <= prediction_date, "Future data detected"
```

## Validation Checklist

- [ ] All data types are correct
- [ ] Missing values handled appropriately
- [ ] Outliers identified and addressed
- [ ] No division by zero errors
- [ ] Categorical encoding handles unseen categories
- [ ] Scaling fitted on training data only
- [ ] No temporal leakage in time-series features
- [ ] Memory usage is acceptable
- [ ] Features are documented
- [ ] Error handling is tested

## Debugging Tips

1. **Use assertions**: Validate assumptions at each step
   ```python
   assert df.shape[0] > 0, "Empty dataframe"
   assert df[col].dtype == 'float64', "Wrong dtype"
   ```

2. **Log intermediate results**: Track data shape and statistics
   ```python
   print(f"Shape: {df.shape}, Missing: {df.isnull().sum().sum()}")
   ```

3. **Validate with domain experts**: Ensure features make sense
   ```python
   # Review top/bottom values
   print(df['feature'].describe())
   print(df['feature'].nlargest(5))
   ```

4. **Test on small samples**: Debug faster on subsets
   ```python
   df_sample = df.sample(n=1000, random_state=42)
   ```

5. **Use try-except blocks**: Graceful error handling
   ```python
   try:
       result = operation(data)
   except ValueError as e:
       print(f"Error: {e}")
       result = fallback_value
   ```
