#!/usr/bin/env python3
"""
Data Visualizer

Generates visualizations of features and their relationships to the target variable,
aiding in understanding data patterns and feature distributions.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
import warnings

warnings.filterwarnings('ignore')

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 10)


class DataVisualizer:
    """Comprehensive data visualization for feature analysis."""

    def __init__(self, df, target_col, output_dir='./visualizations'):
        """
        Initialize the visualizer.

        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
        target_col : str
            Name of target column
        output_dir : str
            Directory to save visualizations
        """
        self.df = df
        self.target_col = target_col
        self.output_dir = output_dir
        self.numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if self.target_col in self.numeric_cols:
            self.numeric_cols.remove(self.target_col)

    def plot_feature_distributions(self, n_cols=4):
        """Plot distributions of numeric features."""
        n_features = len(self.numeric_cols)
        n_rows = (n_features + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
        axes = axes.flatten()

        for idx, col in enumerate(self.numeric_cols):
            axes[idx].hist(self.df[col], bins=30, edgecolor='black', alpha=0.7)
            axes[idx].set_title(f'Distribution of {col}')
            axes[idx].set_xlabel(col)
            axes[idx].set_ylabel('Frequency')

        # Hide unused subplots
        for idx in range(n_features, len(axes)):
            axes[idx].set_visible(False)

        plt.tight_layout()
        filepath = f'{self.output_dir}/feature_distributions.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def plot_correlation_heatmap(self):
        """Plot correlation heatmap of numeric features."""
        numeric_data = self.df[self.numeric_cols + [self.target_col]].select_dtypes(include=[np.number])

        fig, ax = plt.subplots(figsize=(12, 10))
        correlation_matrix = numeric_data.corr()

        sns.heatmap(correlation_matrix, annot=True, fmt='.2f', cmap='coolwarm',
                    center=0, square=True, ax=ax, cbar_kws={'label': 'Correlation'})
        ax.set_title('Feature Correlation Heatmap')

        plt.tight_layout()
        filepath = f'{self.output_dir}/correlation_heatmap.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def plot_feature_target_relationship(self, n_cols=3):
        """Plot relationship between features and target."""
        n_features = len(self.numeric_cols)
        n_rows = (n_features + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 5 * n_rows))
        axes = axes.flatten()

        for idx, col in enumerate(self.numeric_cols):
            # Scatter plot with target
            scatter = axes[idx].scatter(self.df[col], self.df[self.target_col],
                                       alpha=0.5, c=self.df[self.target_col], cmap='viridis')
            axes[idx].set_xlabel(col)
            axes[idx].set_ylabel(self.target_col)
            axes[idx].set_title(f'{col} vs {self.target_col}')
            plt.colorbar(scatter, ax=axes[idx])

        # Hide unused subplots
        for idx in range(n_features, len(axes)):
            axes[idx].set_visible(False)

        plt.tight_layout()
        filepath = f'{self.output_dir}/feature_target_relationships.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def plot_missing_values(self):
        """Plot missing values heatmap."""
        missing_data = self.df.isnull()

        fig, ax = plt.subplots(figsize=(12, 6))
        sns.heatmap(missing_data, yticklabels=False, cbar=True, cmap='viridis', ax=ax)
        ax.set_title('Missing Values Heatmap')

        plt.tight_layout()
        filepath = f'{self.output_dir}/missing_values.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def plot_feature_statistics(self):
        """Plot box plots for feature statistics."""
        n_features = len(self.numeric_cols)
        n_cols = 4
        n_rows = (n_features + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
        axes = axes.flatten()

        for idx, col in enumerate(self.numeric_cols):
            axes[idx].boxplot(self.df[col].dropna())
            axes[idx].set_title(f'Box Plot of {col}')
            axes[idx].set_ylabel(col)

        # Hide unused subplots
        for idx in range(n_features, len(axes)):
            axes[idx].set_visible(False)

        plt.tight_layout()
        filepath = f'{self.output_dir}/feature_statistics.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def plot_target_distribution(self):
        """Plot target variable distribution."""
        fig, ax = plt.subplots(figsize=(10, 6))

        if self.df[self.target_col].dtype == 'object' or self.df[self.target_col].nunique() < 20:
            # Categorical target
            self.df[self.target_col].value_counts().plot(kind='bar', ax=ax, color='steelblue')
            ax.set_title(f'Distribution of {self.target_col}')
            ax.set_xlabel(self.target_col)
            ax.set_ylabel('Count')
        else:
            # Continuous target
            ax.hist(self.df[self.target_col], bins=30, edgecolor='black', alpha=0.7, color='steelblue')
            ax.set_title(f'Distribution of {self.target_col}')
            ax.set_xlabel(self.target_col)
            ax.set_ylabel('Frequency')

        plt.tight_layout()
        filepath = f'{self.output_dir}/target_distribution.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def generate_summary_report(self):
        """Generate summary statistics report."""
        summary = self.df.describe().T

        fig, ax = plt.subplots(figsize=(12, 8))
        ax.axis('tight')
        ax.axis('off')

        table = ax.table(cellText=summary.round(3).values,
                        colLabels=summary.columns,
                        rowLabels=summary.index,
                        cellLoc='center',
                        loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.5)

        ax.set_title('Data Summary Statistics', fontsize=14, fontweight='bold', pad=20)

        plt.tight_layout()
        filepath = f'{self.output_dir}/summary_statistics.png'
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        print(f"✓ Saved: {filepath}")
        plt.close()

    def visualize_all(self):
        """Generate all visualizations."""
        import os
        os.makedirs(self.output_dir, exist_ok=True)

        print(f"\n📊 Generating visualizations in {self.output_dir}...\n")

        self.plot_target_distribution()
        self.plot_feature_distributions()
        self.plot_feature_target_relationship()
        self.plot_correlation_heatmap()
        self.plot_feature_statistics()
        self.plot_missing_values()
        self.generate_summary_report()

        print(f"\n✅ All visualizations generated!\n")


if __name__ == "__main__":
    # Example usage
    from sklearn.datasets import make_classification

    X, y = make_classification(n_samples=500, n_features=10, n_informative=5, random_state=42)
    df = pd.DataFrame(X, columns=[f'Feature_{i}' for i in range(10)])
    df['target'] = y

    visualizer = DataVisualizer(df, 'target', output_dir='./visualizations')
    visualizer.visualize_all()
