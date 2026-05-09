#!/usr/bin/env python3
"""
Feature Importance Analyzer

Analyzes feature importance using multiple techniques including permutation importance,
SHAP values, and tree-based importance to provide comprehensive feature insights.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.inspection import permutation_importance
import warnings

warnings.filterwarnings('ignore')


class FeatureImportanceAnalyzer:
    """Comprehensive feature importance analysis."""

    def __init__(self, model, X_train, X_test, y_train, y_test, feature_names=None):
        """
        Initialize the analyzer.

        Parameters:
        -----------
        model : sklearn model
            Trained model
        X_train : array-like
            Training features
        X_test : array-like
            Test features
        y_train : array-like
            Training target
        y_test : array-like
            Test target
        feature_names : list
            Names of features
        """
        self.model = model
        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test
        self.feature_names = feature_names or [f'Feature_{i}' for i in range(X_train.shape[1])]
        self.importance_results = {}

    def get_tree_importance(self):
        """Get importance from tree-based models."""
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            importance_df = pd.DataFrame({
                'feature': self.feature_names,
                'importance': importances,
                'method': 'Tree-Based'
            }).sort_values('importance', ascending=False)

            self.importance_results['tree_based'] = importance_df
            return importance_df
        return None

    def get_permutation_importance(self, n_repeats=10):
        """Calculate permutation importance."""
        result = permutation_importance(
            self.model, self.X_test, self.y_test,
            n_repeats=n_repeats, random_state=42, n_jobs=-1
        )

        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': result.importances_mean,
            'std': result.importances_std,
            'method': 'Permutation'
        }).sort_values('importance', ascending=False)

        self.importance_results['permutation'] = importance_df
        return importance_df

    def get_correlation_importance(self, target):
        """Calculate correlation-based importance."""
        # Combine features and target
        data = np.column_stack([self.X_train, target])
        df = pd.DataFrame(data, columns=self.feature_names + ['target'])

        correlations = df.corr()['target'].drop('target').abs().sort_values(ascending=False)

        importance_df = pd.DataFrame({
            'feature': correlations.index,
            'importance': correlations.values,
            'method': 'Correlation'
        })

        self.importance_results['correlation'] = importance_df
        return importance_df

    def summarize_importance(self):
        """Summarize importance across all methods."""
        if not self.importance_results:
            return None

        # Normalize importances to 0-1 scale
        normalized_results = {}
        for method, df in self.importance_results.items():
            df_copy = df.copy()
            max_imp = df_copy['importance'].max()
            if max_imp > 0:
                df_copy['importance'] = df_copy['importance'] / max_imp
            normalized_results[method] = df_copy.set_index('feature')['importance']

        # Average across methods
        summary_df = pd.DataFrame(normalized_results).mean(axis=1).sort_values(ascending=False)

        return pd.DataFrame({
            'feature': summary_df.index,
            'average_importance': summary_df.values
        })

    def print_report(self):
        """Print comprehensive importance report."""
        print("\n" + "=" * 80)
        print("FEATURE IMPORTANCE ANALYSIS REPORT")
        print("=" * 80 + "\n")

        for method, df in self.importance_results.items():
            print(f"\n{method.upper()} IMPORTANCE:")
            print("-" * 80)
            print(df.to_string(index=False))

        summary = self.summarize_importance()
        if summary is not None:
            print(f"\n\nAVERAGE IMPORTANCE (Normalized):")
            print("-" * 80)
            print(summary.to_string(index=False))

        print("\n" + "=" * 80 + "\n")

    def get_top_features(self, n=10):
        """Get top N features based on average importance."""
        summary = self.summarize_importance()
        if summary is not None:
            return summary.head(n)['feature'].tolist()
        return []

    def analyze(self, target=None, n_repeats=10):
        """Run complete analysis."""
        print("\n🔍 Starting Feature Importance Analysis...\n")

        # Tree-based importance
        tree_imp = self.get_tree_importance()
        if tree_imp is not None:
            print(f"✓ Tree-based importance calculated")

        # Permutation importance
        perm_imp = self.get_permutation_importance(n_repeats=n_repeats)
        print(f"✓ Permutation importance calculated")

        # Correlation importance
        if target is not None:
            corr_imp = self.get_correlation_importance(target)
            print(f"✓ Correlation importance calculated")

        self.print_report()

        top_features = self.get_top_features(n=10)
        print(f"✓ Top 10 features: {top_features}")

        return self.importance_results


if __name__ == "__main__":
    # Example usage
    from sklearn.datasets import make_classification
    from sklearn.model_selection import train_test_split

    X, y = make_classification(n_samples=1000, n_features=20, n_informative=10, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    analyzer = FeatureImportanceAnalyzer(
        model, X_train, X_test, y_train, y_test,
        feature_names=[f'Feature_{i}' for i in range(20)]
    )
    analyzer.analyze(target=y_train)
