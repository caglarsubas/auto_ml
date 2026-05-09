#!/usr/bin/env python3
"""
Feature Store Integration

Integrates with feature stores (e.g., Feast, Tecton) to manage and serve features
for online and offline model deployment.
"""

import pandas as pd
import json
from datetime import datetime
from typing import Dict, List, Optional
import warnings

warnings.filterwarnings('ignore')


class FeatureStoreConnector:
    """Base connector for feature store integration."""

    def __init__(self, store_type='local', config=None):
        """
        Initialize feature store connector.

        Parameters:
        -----------
        store_type : str
            Type of feature store ('local', 'feast', 'tecton')
        config : dict
            Configuration for the feature store
        """
        self.store_type = store_type
        self.config = config or {}
        self.features = {}
        self.metadata = {}

    def register_feature(self, feature_name: str, feature_type: str, description: str = ""):
        """Register a feature in the store."""
        self.features[feature_name] = {
            'type': feature_type,
            'description': description,
            'registered_at': datetime.now().isoformat()
        }
        print(f"✓ Feature registered: {feature_name}")

    def register_feature_group(self, group_name: str, features: List[Dict]):
        """Register a group of related features."""
        self.metadata[group_name] = {
            'features': features,
            'created_at': datetime.now().isoformat()
        }
        print(f"✓ Feature group registered: {group_name}")

    def store_features(self, df: pd.DataFrame, entity_id_col: str, feature_group: str):
        """Store features for entities."""
        if feature_group not in self.metadata:
            self.metadata[feature_group] = {
                'features': [],
                'created_at': datetime.now().isoformat()
            }

        self.metadata[feature_group]['data'] = df.to_dict('records')
        self.metadata[feature_group]['entity_id_col'] = entity_id_col
        print(f"✓ Features stored for group: {feature_group}")

    def retrieve_features(self, entity_ids: List, feature_group: str) -> Optional[pd.DataFrame]:
        """Retrieve features for specific entities."""
        if feature_group not in self.metadata or 'data' not in self.metadata[feature_group]:
            print(f"✗ Feature group not found: {feature_group}")
            return None

        data = self.metadata[feature_group]['data']
        entity_id_col = self.metadata[feature_group].get('entity_id_col', 'entity_id')

        # Filter data for requested entities
        filtered_data = [record for record in data if record.get(entity_id_col) in entity_ids]

        if filtered_data:
            df = pd.DataFrame(filtered_data)
            print(f"✓ Retrieved {len(df)} records from {feature_group}")
            return df
        else:
            print(f"✗ No records found for entities in {feature_group}")
            return None

    def list_features(self) -> pd.DataFrame:
        """List all registered features."""
        features_list = []
        for name, info in self.features.items():
            features_list.append({
                'feature_name': name,
                'type': info['type'],
                'description': info['description'],
                'registered_at': info['registered_at']
            })

        return pd.DataFrame(features_list)

    def export_metadata(self, filepath: str):
        """Export feature metadata to JSON."""
        metadata = {
            'store_type': self.store_type,
            'features': self.features,
            'feature_groups': self.metadata,
            'exported_at': datetime.now().isoformat()
        }

        with open(filepath, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"✓ Metadata exported to: {filepath}")

    def import_metadata(self, filepath: str):
        """Import feature metadata from JSON."""
        with open(filepath, 'r') as f:
            metadata = json.load(f)

        self.features = metadata.get('features', {})
        self.metadata = metadata.get('feature_groups', {})

        print(f"✓ Metadata imported from: {filepath}")


class LocalFeatureStore(FeatureStoreConnector):
    """Local file-based feature store implementation."""

    def __init__(self, base_path='./feature_store'):
        """Initialize local feature store."""
        super().__init__(store_type='local', config={'base_path': base_path})
        self.base_path = base_path
        import os
        os.makedirs(base_path, exist_ok=True)

    def store_features(self, df: pd.DataFrame, entity_id_col: str, feature_group: str):
        """Store features to CSV file."""
        super().store_features(df, entity_id_col, feature_group)

        filepath = f"{self.base_path}/{feature_group}.csv"
        df.to_csv(filepath, index=False)
        print(f"✓ Features saved to: {filepath}")

    def retrieve_features(self, entity_ids: List, feature_group: str) -> Optional[pd.DataFrame]:
        """Retrieve features from CSV file."""
        filepath = f"{self.base_path}/{feature_group}.csv"

        try:
            df = pd.read_csv(filepath)
            entity_id_col = self.metadata.get(feature_group, {}).get('entity_id_col', 'entity_id')

            if entity_id_col in df.columns:
                filtered_df = df[df[entity_id_col].isin(entity_ids)]
                print(f"✓ Retrieved {len(filtered_df)} records from {feature_group}")
                return filtered_df
            else:
                print(f"✗ Entity ID column '{entity_id_col}' not found in {feature_group}")
                return None
        except FileNotFoundError:
            print(f"✗ Feature group file not found: {filepath}")
            return None


class FeatureStoreManager:
    """Manager for feature store operations."""

    def __init__(self, store: FeatureStoreConnector):
        """Initialize manager."""
        self.store = store

    def create_feature_catalog(self, features_dict: Dict[str, Dict]):
        """Create a catalog of features."""
        print("\n📚 Creating Feature Catalog...\n")

        for feature_name, feature_info in features_dict.items():
            self.store.register_feature(
                feature_name=feature_name,
                feature_type=feature_info.get('type', 'numeric'),
                description=feature_info.get('description', '')
            )

        print(f"\n✓ Catalog created with {len(features_dict)} features\n")

    def publish_features(self, df: pd.DataFrame, entity_id_col: str, feature_group: str):
        """Publish features to the store."""
        print(f"\n📤 Publishing features for group: {feature_group}...\n")
        self.store.store_features(df, entity_id_col, feature_group)
        print(f"\n✓ Features published\n")

    def get_features(self, entity_ids: List, feature_group: str) -> Optional[pd.DataFrame]:
        """Get features for entities."""
        print(f"\n📥 Retrieving features for {len(entity_ids)} entities from {feature_group}...\n")
        return self.store.retrieve_features(entity_ids, feature_group)

    def print_catalog(self):
        """Print feature catalog."""
        catalog = self.store.list_features()
        print("\n" + "=" * 80)
        print("FEATURE CATALOG")
        print("=" * 80 + "\n")
        print(catalog.to_string(index=False))
        print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    # Example usage
    from sklearn.datasets import make_classification

    # Create sample data
    X, y = make_classification(n_samples=100, n_features=5, random_state=42)
    df = pd.DataFrame(X, columns=[f'feature_{i}' for i in range(5)])
    df['entity_id'] = range(100)
    df['target'] = y

    # Initialize local feature store
    store = LocalFeatureStore(base_path='./feature_store')
    manager = FeatureStoreManager(store)

    # Create feature catalog
    features_dict = {
        f'feature_{i}': {'type': 'numeric', 'description': f'Feature {i}'}
        for i in range(5)
    }
    manager.create_feature_catalog(features_dict)

    # Publish features
    manager.publish_features(df, 'entity_id', 'sample_features')

    # Print catalog
    manager.print_catalog()

    # Retrieve features
    retrieved_df = manager.get_features([0, 1, 2, 3, 4], 'sample_features')
    if retrieved_df is not None:
        print(retrieved_df.head())
