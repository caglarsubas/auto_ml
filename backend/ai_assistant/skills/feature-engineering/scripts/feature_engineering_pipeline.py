#!/usr/bin/env python3
"""
Feature Engineering Pipeline

Automates the entire feature engineering process including data loading, cleaning,
transformation, selection, and model evaluation.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score, accuracy_score, f1_score
import warnings

warnings.filterwarnings('ignore')


class FeatureEngineeringPipeline:
    """Comprehensive feature engineering pipeline for ML models."""

    def __init__(self, target_col, task_type='classification', test_size=0.2, random_state=42):
        """
        Initialize the pipeline.

        Parameters:
        -----------
        target_col : str
            Name of the target column
        task_type : str
            'classification' or 'regression'
        test_size : float
            Proportion of data for testing
        random_state : int
            Random seed for reproducibility
        """
        self.target_col = target_col
        self.task_type = task_type
        self.test_size = test_size
        self.random_state = random_state
        self.df = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoders = {}

    def load_data(self, filepath):
        """Load data from CSV file."""
        self.df = pd.read_csv(filepath)
        print(f"✓ Data loaded: {self.df.shape[0]} rows, {self.df.shape[1]} columns")
        return self

    def clean_data(self):
        """Handle missing values and basic data cleaning."""
        # Handle missing values
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        categorical_cols = self.df.select_dtypes(include=['object']).columns

        for col in numeric_cols:
            self.df[col].fillna(self.df[col].median(), inplace=True)

        for col in categorical_cols:
            self.df[col].fillna(self.df[col].mode()[0] if len(self.df[col].mode()) > 0 else 'Unknown', inplace=True)

        print(f"✓ Data cleaned: Missing values handled")
        return self

    def encode_categorical(self):
        """Encode categorical variables."""
        categorical_cols = self.df.select_dtypes(include=['object']).columns

        for col in categorical_cols:
            if col != self.target_col:
                le = LabelEncoder()
                self.df[col] = le.fit_transform(self.df[col].astype(str))
                self.label_encoders[col] = le

        # Encode target if classification
        if self.task_type == 'classification' and self.df[self.target_col].dtype == 'object':
            le = LabelEncoder()
            self.df[self.target_col] = le.fit_transform(self.df[self.target_col].astype(str))
            self.label_encoders[self.target_col] = le

        print(f"✓ Categorical encoding: {len(self.label_encoders)} columns encoded")
        return self

    def create_features(self):
        """Create interaction and polynomial features."""
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()

        # Remove target from feature list
        if self.target_col in numeric_cols:
            numeric_cols.remove(self.target_col)

        # Create ratio features for pairs of numeric columns
        if len(numeric_cols) >= 2:
            for i in range(len(numeric_cols)):
                for j in range(i + 1, min(i + 3, len(numeric_cols))):
                    col1, col2 = numeric_cols[i], numeric_cols[j]
                    # Avoid division by zero
                    if (self.df[col2] != 0).all():
                        self.df[f'{col1}_div_{col2}'] = self.df[col1] / (self.df[col2] + 1e-8)
                    self.df[f'{col1}_mul_{col2}'] = self.df[col1] * self.df[col2]

        print(f"✓ Feature creation: Interaction features created")
        return self

    def select_features(self, n_features=None):
        """Select top features using Random Forest importance."""
        X = self.df.drop(columns=[self.target_col])
        y = self.df[self.target_col]

        if self.task_type == 'classification':
            model = RandomForestClassifier(n_estimators=100, random_state=self.random_state, n_jobs=-1)
        else:
            model = RandomForestRegressor(n_estimators=100, random_state=self.random_state, n_jobs=-1)

        model.fit(X, y)

        # Get feature importance
        importance_df = pd.DataFrame({
            'feature': X.columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)

        if n_features is None:
            n_features = max(1, len(X.columns) // 2)

        top_features = importance_df.head(n_features)['feature'].tolist()
        self.df = self.df[[self.target_col] + top_features]

        print(f"✓ Feature selection: Top {n_features} features selected")
        return self

    def split_data(self):
        """Split data into train and test sets."""
        X = self.df.drop(columns=[self.target_col])
        y = self.df[self.target_col]

        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state
        )

        # Scale features
        self.X_train = self.scaler.fit_transform(self.X_train)
        self.X_test = self.scaler.transform(self.X_test)

        print(f"✓ Data split: Train {self.X_train.shape[0]}, Test {self.X_test.shape[0]}")
        return self

    def train_model(self):
        """Train the model."""
        if self.task_type == 'classification':
            self.model = RandomForestClassifier(n_estimators=100, random_state=self.random_state, n_jobs=-1)
        else:
            self.model = RandomForestRegressor(n_estimators=100, random_state=self.random_state, n_jobs=-1)

        self.model.fit(self.X_train, self.y_train)
        print(f"✓ Model trained: {self.model.__class__.__name__}")
        return self

    def evaluate_model(self):
        """Evaluate model performance."""
        y_pred = self.model.predict(self.X_test)

        if self.task_type == 'classification':
            accuracy = accuracy_score(self.y_test, y_pred)
            f1 = f1_score(self.y_test, y_pred, average='weighted', zero_division=0)
            print(f"✓ Model evaluation:")
            print(f"  - Accuracy: {accuracy:.4f}")
            print(f"  - F1-Score: {f1:.4f}")
            return {'accuracy': accuracy, 'f1_score': f1}
        else:
            mse = mean_squared_error(self.y_test, y_pred)
            r2 = r2_score(self.y_test, y_pred)
            print(f"✓ Model evaluation:")
            print(f"  - MSE: {mse:.4f}")
            print(f"  - R² Score: {r2:.4f}")
            return {'mse': mse, 'r2_score': r2}

    def run(self, filepath, n_features=None):
        """Run the complete pipeline."""
        print("\n🚀 Starting Feature Engineering Pipeline...\n")
        self.load_data(filepath)
        self.clean_data()
        self.encode_categorical()
        self.create_features()
        self.select_features(n_features)
        self.split_data()
        self.train_model()
        metrics = self.evaluate_model()
        print("\n✅ Pipeline completed!\n")
        return metrics


if __name__ == "__main__":
    # Example usage
    pipeline = FeatureEngineeringPipeline(
        target_col='target',
        task_type='classification',
        test_size=0.2,
        random_state=42
    )
    # pipeline.run('data.csv', n_features=10)
