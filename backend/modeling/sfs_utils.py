"""
Sequential Feature Selection (SFS) utilities for model optimization.

This module provides forward and backward sequential feature selection
with comprehensive metrics tracking, stability analysis (PSI/CSI), and
SHAP impact monitoring.
"""

import warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score
from mlxtend.feature_selection import SequentialFeatureSelector as SFS
import xgboost as xgb
import shap

# Suppress NumPy warnings for invalid values during PSI/CSI/SHAP calculations
warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
from typing import Dict, List, Tuple, Any, Optional


def calculate_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Calculate Population Stability Index (PSI) for numerical features.
    
    Args:
        expected: Reference distribution (e.g., training data)
        actual: Current distribution (e.g., validation/test data)
        bins: Number of bins for discretization
    
    Returns:
        PSI value (higher values indicate more distribution shift)
    """
    try:
        import warnings
        with warnings.catch_warnings():
            # Suppress numpy warnings for invalid values
            warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
            
            # Remove NaN values
            expected_clean = expected[np.isfinite(expected)]
            actual_clean = actual[np.isfinite(actual)]
            
            if len(expected_clean) == 0 or len(actual_clean) == 0:
                return None
            
            # Create bins based on expected distribution
            breakpoints = np.percentile(expected_clean, np.linspace(0, 100, bins + 1))
            breakpoints = np.unique(breakpoints)  # Remove duplicates
            
            if len(breakpoints) < 2:
                return None
            
            # Calculate distributions
            expected_percents = np.histogram(expected_clean, bins=breakpoints)[0] / len(expected_clean)
            actual_percents = np.histogram(actual_clean, bins=breakpoints)[0] / len(actual_clean)
            
            # Add small constant to avoid division by zero
            expected_percents = np.where(expected_percents == 0, 0.0001, expected_percents)
            actual_percents = np.where(actual_percents == 0, 0.0001, actual_percents)
            
            # Calculate PSI
            psi_value = np.sum((actual_percents - expected_percents) * np.log(actual_percents / expected_percents))
            
            return float(psi_value) if np.isfinite(psi_value) else None
        
    except Exception as e:
        print(f"PSI calculation error: {e}")
        return None


def calculate_csi(expected: np.ndarray, actual: np.ndarray) -> float:
    """
    Calculate Characteristic Stability Index (CSI) for categorical features.
    
    Args:
        expected: Reference distribution (e.g., training data)
        actual: Current distribution (e.g., validation/test data)
    
    Returns:
        CSI value (higher values indicate more distribution shift)
    """
    try:
        import warnings
        with warnings.catch_warnings():
            # Suppress numpy warnings for invalid values
            warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
            
            # Get unique categories from both distributions
            all_categories = np.unique(np.concatenate([expected, actual]))
            
            csi_value = 0.0
            for category in all_categories:
                expected_pct = np.sum(expected == category) / len(expected) if len(expected) > 0 else 0.0001
                actual_pct = np.sum(actual == category) / len(actual) if len(actual) > 0 else 0.0001
                
                # Add small constant to avoid division by zero
                expected_pct = max(expected_pct, 0.0001)
                actual_pct = max(actual_pct, 0.0001)
                
                csi_value += (actual_pct - expected_pct) * np.log(actual_pct / expected_pct)
            
            return float(csi_value) if np.isfinite(csi_value) else None
        
    except Exception as e:
        print(f"CSI calculation error: {e}")
        return None


def compute_shap_importance(booster, X: pd.DataFrame, feature_names: List[str]) -> Dict[str, float]:
    """
    Compute SHAP importance scores for all features.
    
    Args:
        booster: Trained XGBoost model
        X: Feature matrix
        feature_names: List of feature names
    
    Returns:
        Dictionary mapping feature names to SHAP importance scores
    """
    try:
        # Suppress SHAP FutureWarning about feature_perturbation
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=FutureWarning, module='shap')
            explainer = shap.TreeExplainer(booster, feature_perturbation='interventional')
        
        # Limit samples for performance
        X_sample = X.sample(min(1000, len(X)), random_state=42) if len(X) > 1000 else X
        
        shap_values = explainer.shap_values(X_sample)
        
        # Handle multi-class output
        if isinstance(shap_values, list):
            shap_matrix = np.mean(np.stack(shap_values, axis=0), axis=0)
        else:
            shap_matrix = shap_values
        
        # Calculate mean absolute SHAP values
        mean_abs_shap = np.mean(np.abs(shap_matrix), axis=0)
        
        return {feature_names[i]: float(mean_abs_shap[i]) for i in range(len(feature_names))}
        
    except Exception as e:
        print(f"SHAP computation error: {e}")
        return {fn: 0.0 for fn in feature_names}


def run_forward_sfs(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    X_train_raw: pd.DataFrame,
    X_test_raw: pd.DataFrame,
    max_features: Optional[int] = None,
    cv_folds: int = 5
) -> List[Dict[str, Any]]:
    """
    Run forward sequential feature selection with comprehensive tracking.
    
    Args:
        X_train: Training features
        y_train: Training target
        X_test: Test features  
        y_test: Test target
        X_train_raw: Raw training features (for PSI/CSI)
        X_test_raw: Raw test features (for PSI/CSI)
        max_features: Maximum number of features to select (None = all)
        cv_folds: Number of cross-validation folds
    
    Returns:
        List of dictionaries containing step-by-step results
    """
    results = []
    feature_names = list(X_train.columns)
    
    if max_features is None:
        max_features = len(feature_names)
    
    print(f"[SFS-Forward] Starting with {len(feature_names)} features, max_features={max_features}")
    
    try:
        # Initial baseline SHAP importance (empty model baseline)
        previous_shap_importance = {}
        
        # Incrementally add features
        selected_features = []
        remaining_features = feature_names.copy()
        
        for step in range(min(max_features, len(feature_names))):
            best_feature = None
            best_score = -np.inf
            best_metrics = None
            
            print(f"[SFS-Forward] Step {step + 1}/{max_features}")
            
            # Try adding each remaining feature
            for feature in remaining_features:
                current_features = selected_features + [feature]
                
                # Train model with current feature set
                X_train_subset = X_train[current_features]
                X_test_subset = X_test[current_features]
                
                # Train XGBoost model
                dtrain = xgb.DMatrix(X_train_subset, label=y_train)
                dtest = xgb.DMatrix(X_test_subset, label=y_test)
                
                params = {
                    'objective': 'binary:logistic',
                    'eval_metric': 'auc',
                    'max_depth': 6,
                    'eta': 0.1,
                    'subsample': 0.8,
                    'colsample_bytree': 0.8,
                    'seed': 42
                }
                
                booster = xgb.train(params, dtrain, num_boost_round=100, verbose_eval=False)
                
                # Evaluate on train
                y_train_pred = booster.predict(dtrain)
                train_roc_auc = roc_auc_score(y_train, y_train_pred)
                train_pr_auc = average_precision_score(y_train, y_train_pred)
                
                # Evaluate on test
                y_test_pred = booster.predict(dtest)
                test_roc_auc = roc_auc_score(y_test, y_test_pred)
                test_pr_auc = average_precision_score(y_test, y_test_pred)
                
                # Cross-validation
                skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
                cv_roc_scores = []
                cv_pr_scores = []
                
                for train_idx, val_idx in skf.split(X_train_subset, y_train):
                    X_cv_train, X_cv_val = X_train_subset.iloc[train_idx], X_train_subset.iloc[val_idx]
                    y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                    
                    dcv_train = xgb.DMatrix(X_cv_train, label=y_cv_train)
                    dcv_val = xgb.DMatrix(X_cv_val, label=y_cv_val)
                    
                    cv_booster = xgb.train(params, dcv_train, num_boost_round=100, verbose_eval=False)
                    y_cv_pred = cv_booster.predict(dcv_val)
                    
                    cv_roc_scores.append(roc_auc_score(y_cv_val, y_cv_pred))
                    cv_pr_scores.append(average_precision_score(y_cv_val, y_cv_pred))
                
                cv_roc_auc = np.mean(cv_roc_scores)
                cv_pr_auc = np.mean(cv_pr_scores)
                
                # Use CV ROC-AUC as selection criterion
                if cv_roc_auc > best_score:
                    best_score = cv_roc_auc
                    best_feature = feature
                    best_metrics = {
                        'train_roc_auc': train_roc_auc,
                        'train_pr_auc': train_pr_auc,
                        'cv_roc_auc': cv_roc_auc,
                        'cv_pr_auc': cv_pr_auc,
                        'test_roc_auc': test_roc_auc,
                        'test_pr_auc': test_pr_auc,
                        'booster': booster
                    }
            
            if best_feature is None:
                print(f"[SFS-Forward] No improvement found, stopping at step {step}")
                break
            
            # Add best feature to selected set
            selected_features.append(best_feature)
            remaining_features.remove(best_feature)
            
            # Calculate PSI/CSI for the added feature
            feature_idx = feature_names.index(best_feature)
            train_feature_values = X_train_raw.iloc[:, feature_idx].values
            test_feature_values = X_test_raw.iloc[:, feature_idx].values
            
            # Determine if numeric or categorical
            is_numeric = pd.api.types.is_numeric_dtype(X_train_raw.iloc[:, feature_idx])
            
            if is_numeric:
                stability_metric = calculate_psi(train_feature_values, test_feature_values)
                stability_type = 'PSI'
            else:
                stability_metric = calculate_csi(train_feature_values, test_feature_values)
                stability_type = 'CSI'
            
            # Compute SHAP importance for current model
            current_shap_importance = compute_shap_importance(
                best_metrics['booster'],
                X_train[selected_features],
                selected_features
            )
            
            # Calculate SHAP impact changes for existing features
            shap_changes = {}
            for feat in selected_features[:-1]:  # Exclude the just-added feature
                prev_impact = previous_shap_importance.get(feat, 0.0)
                curr_impact = current_shap_importance.get(feat, 0.0)
                shap_changes[feat] = curr_impact - prev_impact
            
            # Store result for this step
            step_result = {
                'step': step + 1,
                'direction': 'forward',
                'action': 'added',
                'feature_name': best_feature,
                'selected_features': selected_features.copy(),
                'train_roc_auc': best_metrics['train_roc_auc'],
                'train_pr_auc': best_metrics['train_pr_auc'],
                'cv_roc_auc': best_metrics['cv_roc_auc'],
                'cv_pr_auc': best_metrics['cv_pr_auc'],
                'test_roc_auc': best_metrics['test_roc_auc'],
                'test_pr_auc': best_metrics['test_pr_auc'],
                'stability_type': stability_type,
                'stability_value': stability_metric,
                'shap_importance': current_shap_importance.get(best_feature, 0.0),
                'shap_changes': shap_changes,
                'feature_importance': dict(best_metrics['booster'].get_score(importance_type='gain'))
            }
            
            results.append(step_result)
            previous_shap_importance = current_shap_importance
            
            print(f"[SFS-Forward] Step {step + 1}: Added '{best_feature}', CV ROC-AUC={best_metrics['cv_roc_auc']:.4f}")
        
        return results
        
    except Exception as e:
        print(f"[SFS-Forward] Error: {e}")
        import traceback
        traceback.print_exc()
        return results


def run_backward_sfs(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    X_train_raw: pd.DataFrame,
    X_test_raw: pd.DataFrame,
    min_features: int = 1,
    cv_folds: int = 5
) -> List[Dict[str, Any]]:
    """
    Run backward sequential feature elimination with comprehensive tracking.
    
    Args:
        X_train: Training features
        y_train: Training target
        X_test: Test features
        y_test: Test target
        X_train_raw: Raw training features (for PSI/CSI)
        X_test_raw: Raw test features (for PSI/CSI)
        min_features: Minimum number of features to retain
        cv_folds: Number of cross-validation folds
    
    Returns:
        List of dictionaries containing step-by-step results
    """
    results = []
    feature_names = list(X_train.columns)
    
    print(f"[SFS-Backward] Starting with {len(feature_names)} features, min_features={min_features}")
    
    try:
        # Start with all features
        selected_features = feature_names.copy()
        
        # Compute initial SHAP importance with all features
        dtrain_full = xgb.DMatrix(X_train, label=y_train)
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 6,
            'eta': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'seed': 42
        }
        initial_booster = xgb.train(params, dtrain_full, num_boost_round=100, verbose_eval=False)
        previous_shap_importance = compute_shap_importance(initial_booster, X_train, feature_names)
        
        step = 0
        while len(selected_features) > min_features:
            best_feature_to_drop = None
            best_score = -np.inf
            best_metrics = None
            
            step += 1
            print(f"[SFS-Backward] Step {step}, {len(selected_features)} features remaining")
            
            # Try dropping each feature
            for feature in selected_features:
                current_features = [f for f in selected_features if f != feature]
                
                if len(current_features) == 0:
                    continue
                
                # Train model without this feature
                X_train_subset = X_train[current_features]
                X_test_subset = X_test[current_features]
                
                dtrain = xgb.DMatrix(X_train_subset, label=y_train)
                dtest = xgb.DMatrix(X_test_subset, label=y_test)
                
                booster = xgb.train(params, dtrain, num_boost_round=100, verbose_eval=False)
                
                # Evaluate on train
                y_train_pred = booster.predict(dtrain)
                train_roc_auc = roc_auc_score(y_train, y_train_pred)
                train_pr_auc = average_precision_score(y_train, y_train_pred)
                
                # Evaluate on test
                y_test_pred = booster.predict(dtest)
                test_roc_auc = roc_auc_score(y_test, y_test_pred)
                test_pr_auc = average_precision_score(y_test, y_test_pred)
                
                # Cross-validation
                skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
                cv_roc_scores = []
                cv_pr_scores = []
                
                for train_idx, val_idx in skf.split(X_train_subset, y_train):
                    X_cv_train, X_cv_val = X_train_subset.iloc[train_idx], X_train_subset.iloc[val_idx]
                    y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                    
                    dcv_train = xgb.DMatrix(X_cv_train, label=y_cv_train)
                    dcv_val = xgb.DMatrix(X_cv_val, label=y_cv_val)
                    
                    cv_booster = xgb.train(params, dcv_train, num_boost_round=100, verbose_eval=False)
                    y_cv_pred = cv_booster.predict(dcv_val)
                    
                    cv_roc_scores.append(roc_auc_score(y_cv_val, y_cv_pred))
                    cv_pr_scores.append(average_precision_score(y_cv_val, y_cv_pred))
                
                cv_roc_auc = np.mean(cv_roc_scores)
                cv_pr_auc = np.mean(cv_pr_scores)
                
                # Select feature to drop that maintains or improves performance
                if cv_roc_auc > best_score:
                    best_score = cv_roc_auc
                    best_feature_to_drop = feature
                    best_metrics = {
                        'train_roc_auc': train_roc_auc,
                        'train_pr_auc': train_pr_auc,
                        'cv_roc_auc': cv_roc_auc,
                        'cv_pr_auc': cv_pr_auc,
                        'test_roc_auc': test_roc_auc,
                        'test_pr_auc': test_pr_auc,
                        'booster': booster,
                        'remaining_features': current_features
                    }
            
            if best_feature_to_drop is None:
                print(f"[SFS-Backward] No feature to drop found, stopping at step {step}")
                break
            
            # Remove the feature
            selected_features.remove(best_feature_to_drop)
            
            # Calculate PSI/CSI for the dropped feature
            feature_idx = feature_names.index(best_feature_to_drop)
            train_feature_values = X_train_raw.iloc[:, feature_idx].values
            test_feature_values = X_test_raw.iloc[:, feature_idx].values
            
            # Determine if numeric or categorical
            is_numeric = pd.api.types.is_numeric_dtype(X_train_raw.iloc[:, feature_idx])
            
            if is_numeric:
                stability_metric = calculate_psi(train_feature_values, test_feature_values)
                stability_type = 'PSI'
            else:
                stability_metric = calculate_csi(train_feature_values, test_feature_values)
                stability_type = 'CSI'
            
            # Compute SHAP importance for model after removal
            current_shap_importance = compute_shap_importance(
                best_metrics['booster'],
                X_train[best_metrics['remaining_features']],
                best_metrics['remaining_features']
            )
            
            # Calculate SHAP impact changes
            shap_changes = {}
            for feat in best_metrics['remaining_features']:
                prev_impact = previous_shap_importance.get(feat, 0.0)
                curr_impact = current_shap_importance.get(feat, 0.0)
                shap_changes[feat] = curr_impact - prev_impact
            
            # Store result for this step
            step_result = {
                'step': step,
                'direction': 'backward',
                'action': 'dropped',
                'feature_name': best_feature_to_drop,
                'selected_features': best_metrics['remaining_features'].copy(),
                'train_roc_auc': best_metrics['train_roc_auc'],
                'train_pr_auc': best_metrics['train_pr_auc'],
                'cv_roc_auc': best_metrics['cv_roc_auc'],
                'cv_pr_auc': best_metrics['cv_pr_auc'],
                'test_roc_auc': best_metrics['test_roc_auc'],
                'test_pr_auc': best_metrics['test_pr_auc'],
                'stability_type': stability_type,
                'stability_value': stability_metric,
                'shap_importance': previous_shap_importance.get(best_feature_to_drop, 0.0),
                'shap_changes': shap_changes,
                'feature_importance': dict(best_metrics['booster'].get_score(importance_type='gain'))
            }
            
            results.append(step_result)
            previous_shap_importance = current_shap_importance
            
            print(f"[SFS-Backward] Step {step}: Dropped '{best_feature_to_drop}', CV ROC-AUC={best_metrics['cv_roc_auc']:.4f}")
        
        return results
        
    except Exception as e:
        print(f"[SFS-Backward] Error: {e}")
        import traceback
        traceback.print_exc()
        return results


def run_sfs_with_progress(
    X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
    methods: List[str],  # ['forward', 'backward', 'both']
    stopping_criteria: Dict[str, Any],  # {metrics: [{metric, pct_change}], min_features, max_features}
    status_callback: Optional[callable] = None,
    cv_folds: int = 3,
    initial_features: Optional[List[str]] = None  # Optional: Start with specific features
) -> Dict[str, Any]:
    """
    Run SFS with user-specified methods, stopping criteria, and progress tracking.
    
    Args:
        X_train, y_train: Training data
        X_test, y_test: Test data
        X_train_raw, X_test_raw: Raw data for stability calculations
        methods: List of methods to run ('forward', 'backward', or both)
        stopping_criteria: Dict with keys:
            - metrics: List of {metric: 'roc_auc'|'pr_auc', pct_change: float}
            - min_features: Minimum features to keep (for backward)
            - max_features: Maximum features to add (for forward)
        status_callback: Function to call with progress updates
        cv_folds: Number of CV folds
    
    Returns:
        Dict with forward/backward results and final metrics
    """
    results = {'forward': [], 'backward': [], 'status': 'running'}
    completed_steps = []  # Track completed steps for real-time viewing
    
    # Filter by initial_features if provided
    if initial_features:
        valid_features = [f for f in initial_features if f in X_train.columns]
        if valid_features:
            X_train = X_train[valid_features]
            X_test = X_test[valid_features]
            X_train_raw = X_train_raw[valid_features]
            X_test_raw = X_test_raw[valid_features]
            print(f"[SFS] Starting with {len(valid_features)} initial features: {valid_features}")
    
    def update_status(message: str, progress: float, current_metrics: Dict[str, float] = None, step_result: Dict = None):
        """Update status via callback"""
        if status_callback:
            callback_data = {
                'message': message,
                'progress': progress,
                'current_metrics': current_metrics or {},
                'status': 'running',
                'completed_steps': completed_steps.copy()  # Send current completed steps
            }
            status_callback(callback_data)
    
    try:
        total_methods = len(methods)
        method_progress_weight = 1.0 / total_methods if total_methods > 0 else 1.0
        
        # Extract stopping criteria - support multiple metrics
        metric_criteria = stopping_criteria.get('metrics', [{'metric': 'roc_auc', 'pct_change': 0.0}])
        if not metric_criteria:  # Fallback for backward compatibility
            metric_criteria = [{'metric': 'roc_auc', 'pct_change': 0.0}]
        
        min_features = stopping_criteria.get('min_features', 3)
        max_features = stopping_criteria.get('max_features', min(10, X_train.shape[1]))
        
        # Run Forward Selection
        if 'forward' in methods:
            update_status(f'Starting forward selection (max {max_features} features)...', 0.0)
            
            forward_results = []
            selected_features = []
            previous_metrics = {mc['metric']: 0.0 for mc in metric_criteria}
            
            for step in range(1, max_features + 1):
                step_progress = (step / max_features) * method_progress_weight
                update_status(f'Forward selection: Step {step}/{max_features}', step_progress)
                
                # Run one step of forward selection
                step_result = _run_forward_step(
                    X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
                    selected_features, step, cv_folds
                )
                
                if step_result:
                    # Get current metric values
                    current_metrics = {}
                    for mc in metric_criteria:
                        metric_name = mc['metric']
                        current_metrics[metric_name] = step_result.get(f'cv_{metric_name}', 0.0)
                    
                    # Calculate percentage changes for display
                    pct_changes = {}
                    if step > 1:
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            current_val = current_metrics[metric_name]
                            prev_val = previous_metrics[metric_name]
                            if prev_val > 0:
                                pct_changes[metric_name] = ((current_val - prev_val) / prev_val) * 100
                            else:
                                pct_changes[metric_name] = 0.0
                    
                    # Check stopping criteria BEFORE accepting the feature
                    should_stop = False
                    if step > 1:
                        stop_reasons = []
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            pct_threshold = mc.get('pct_change', 0.0)
                            
                            if pct_threshold > 0:
                                current_val = current_metrics[metric_name]
                                prev_val = previous_metrics[metric_name]
                                
                                if prev_val > 0:
                                    pct_change = abs((current_val - prev_val) / prev_val) * 100
                                    if pct_change < pct_threshold:
                                        stop_reasons.append(f'{metric_name} change ({pct_change:.2f}%) < {pct_threshold}%')
                        
                        # Stop if any metric violates its threshold
                        if stop_reasons:
                            update_status(
                                f'Forward selection stopped: Feature rejected ({step_result["feature_name"]}), {"; ".join(stop_reasons)}',
                                step_progress, previous_metrics
                            )
                            should_stop = True
                    
                    # Only add to results if threshold is satisfied (or first step)
                    if should_stop:
                        break
                    
                    # Accept the feature - add to results
                    forward_results.append(step_result)
                    selected_features = step_result['selected_features']
                    
                    # Add to completed steps for real-time viewing
                    completed_step_info = {
                        'step': step,
                        'direction': 'forward',
                        'action': 'added',
                        'feature_name': step_result['feature_name'],
                        'cv_roc_auc': step_result.get('cv_roc_auc', 0.0),
                        'cv_pr_auc': step_result.get('cv_pr_auc', 0.0),
                        'test_roc_auc': step_result.get('test_roc_auc', 0.0),
                        'test_pr_auc': step_result.get('test_pr_auc', 0.0),
                        'pct_changes': pct_changes
                    }
                    completed_steps.append(completed_step_info)
                    
                    previous_metrics = current_metrics.copy()
                    metric_str = ', '.join([f'{k}={v:.4f}' for k, v in current_metrics.items()])
                    update_status(f'Forward step {step} complete: {metric_str}', step_progress, current_metrics)
                else:
                    break
            
            results['forward'] = forward_results
        
        # Run Backward Elimination
        if 'backward' in methods:
            base_progress = method_progress_weight if 'forward' in methods else 0.0
            update_status(f'Starting backward elimination (min {min_features} features)...', base_progress)
            
            backward_results = []
            current_features = list(X_train.columns)
            max_drops = len(current_features) - min_features
            previous_metrics = None
            
            for step in range(1, max_drops + 1):
                step_progress = base_progress + (step / max_drops) * method_progress_weight
                update_status(f'Backward elimination: Step {step}/{max_drops}', step_progress)
                
                # Run one step of backward elimination
                step_result = _run_backward_step(
                    X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
                    current_features, step, cv_folds
                )
                
                if step_result:
                    # Get current metric values
                    current_metrics = {}
                    for mc in metric_criteria:
                        metric_name = mc['metric']
                        current_metrics[metric_name] = step_result.get(f'cv_{metric_name}', 0.0)
                    
                    # Calculate percentage changes for display
                    pct_changes = {}
                    if previous_metrics is not None:
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            current_val = current_metrics[metric_name]
                            prev_val = previous_metrics[metric_name]
                            if prev_val > 0:
                                pct_changes[metric_name] = ((current_val - prev_val) / prev_val) * 100
                            else:
                                pct_changes[metric_name] = 0.0
                    
                    # Check stopping criteria BEFORE accepting the drop
                    should_stop = False
                    if previous_metrics is not None:
                        stop_reasons = []
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            pct_threshold = mc.get('pct_change', 0.0)
                            
                            if pct_threshold > 0:
                                current_val = current_metrics[metric_name]
                                prev_val = previous_metrics[metric_name]
                                
                                if prev_val > 0:
                                    pct_change = abs((current_val - prev_val) / prev_val) * 100
                                    # For backward, we stop if metric DECREASES (degrades) too much
                                    if pct_change > pct_threshold:
                                        stop_reasons.append(f'{metric_name} degraded ({pct_change:.2f}%) > {pct_threshold}%')
                        
                        if stop_reasons:
                            update_status(
                                f'Backward elimination stopped: Feature drop rejected ({step_result["feature_name"]}), {"; ".join(stop_reasons)}',
                                step_progress, previous_metrics
                            )
                            should_stop = True
                    
                    # Only drop feature if threshold is satisfied (or first step)
                    if should_stop:
                        break
                    
                    # Accept the drop - add to results
                    backward_results.append(step_result)
                    current_features = step_result['selected_features']
                    
                    # Add to completed steps for real-time viewing
                    completed_step_info = {
                        'step': step,
                        'direction': 'backward',
                        'action': 'dropped',
                        'feature_name': step_result['feature_name'],
                        'cv_roc_auc': step_result.get('cv_roc_auc', 0.0),
                        'cv_pr_auc': step_result.get('cv_pr_auc', 0.0),
                        'test_roc_auc': step_result.get('test_roc_auc', 0.0),
                        'test_pr_auc': step_result.get('test_pr_auc', 0.0),
                        'pct_changes': pct_changes
                    }
                    completed_steps.append(completed_step_info)
                    
                    previous_metrics = current_metrics.copy()
                    metric_str = ', '.join([f'{k}={v:.4f}' for k, v in current_metrics.items()])
                    update_status(f'Backward step {step} complete: {metric_str}', step_progress, current_metrics)
                else:
                    break
            
            results['backward'] = backward_results
            # Add remaining features after backward elimination
            if backward_results:
                results['backward_remaining_features'] = current_features
                print(f"[SFS-Backward] Completed with {len(current_features)} remaining features: {current_features}")
            else:
                results['backward_remaining_features'] = list(X_train.columns)
        
        results['status'] = 'completed'
        update_status('SFS completed successfully', 1.0)
        
    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        if status_callback:
            status_callback({
                'message': f'SFS failed: {str(e)}',
                'progress': 0.0,
                'status': 'error',
                'error': str(e)
            })
        print(f"[SFS] Error: {e}")
        import traceback
        traceback.print_exc()

    return results


def _run_forward_step(X_train, y_train, X_test, y_test, X_train_raw, X_test_raw, 
                      current_features: List[str], step: int, cv_folds: int) -> Optional[Dict]:
    """Run a single forward selection step - evaluates all remaining features"""
    try:
        remaining_features = [f for f in X_train.columns if f not in current_features]
        if not remaining_features:
            return None
        
        best_feature = None
        best_score = -np.inf
        best_metrics = None
        
        # Try adding each remaining feature and pick the best
        for feature in remaining_features:
            candidate_features = current_features + [feature]
            
            # Train model with candidate feature set
            X_train_subset = X_train[candidate_features]
            X_test_subset = X_test[candidate_features]
            
            # Train XGBoost model
            dtrain = xgb.DMatrix(X_train_subset, label=y_train)
            dtest = xgb.DMatrix(X_test_subset, label=y_test)
            
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'eta': 0.1,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'seed': 42
            }
            
            booster = xgb.train(params, dtrain, num_boost_round=100, verbose_eval=False)
            
            # Evaluate on train
            y_train_pred = booster.predict(dtrain)
            train_roc_auc = float(roc_auc_score(y_train, y_train_pred))
            train_pr_auc = float(average_precision_score(y_train, y_train_pred))
            
            # Evaluate on test
            y_test_pred = booster.predict(dtest)
            test_roc_auc = float(roc_auc_score(y_test, y_test_pred))
            test_pr_auc = float(average_precision_score(y_test, y_test_pred))
            
            # Cross-validation
            skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
            cv_roc_scores = []
            cv_pr_scores = []
            
            for train_idx, val_idx in skf.split(X_train_subset, y_train):
                X_cv_train, X_cv_val = X_train_subset.iloc[train_idx], X_train_subset.iloc[val_idx]
                y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                dcv_train = xgb.DMatrix(X_cv_train, label=y_cv_train)
                dcv_val = xgb.DMatrix(X_cv_val, label=y_cv_val)
                
                cv_booster = xgb.train(params, dcv_train, num_boost_round=100, verbose_eval=False)
                y_cv_pred = cv_booster.predict(dcv_val)
                
                cv_roc_scores.append(roc_auc_score(y_cv_val, y_cv_pred))
                cv_pr_scores.append(average_precision_score(y_cv_val, y_cv_pred))
            
            cv_roc_auc = float(np.mean(cv_roc_scores))
            cv_pr_auc = float(np.mean(cv_pr_scores))
            
            # Use CV ROC-AUC as primary selection criterion
            if cv_roc_auc > best_score:
                best_score = cv_roc_auc
                best_feature = feature
                best_metrics = {
                    'train_roc_auc': train_roc_auc,
                    'train_pr_auc': train_pr_auc,
                    'cv_roc_auc': cv_roc_auc,
                    'cv_pr_auc': cv_pr_auc,
                    'test_roc_auc': test_roc_auc,
                    'test_pr_auc': test_pr_auc,
                    'booster': booster
                }
        
        if best_feature is None:
            return None
        
        # Build final feature set
        new_features = current_features + [best_feature]
        
        # Calculate stability for the added feature
        try:
            if pd.api.types.is_numeric_dtype(X_train_raw[best_feature]):
                stability_value = calculate_psi(
                    X_train_raw[best_feature].values,
                    X_test_raw[best_feature].values
                )
                stability_type = 'PSI'
            else:
                stability_value = calculate_csi(
                    X_train_raw[best_feature].values,
                    X_test_raw[best_feature].values
                )
                stability_type = 'CSI'
        except Exception:
            stability_value = None
            stability_type = 'N/A'
        
        shap_importance_by_feature = compute_shap_importance(
            best_metrics['booster'],
            X_train[new_features],
            new_features
        )
        shap_importance = float(shap_importance_by_feature.get(best_feature, 0.0))
        
        # Get feature importances from model
        try:
            gain_importance = best_metrics['booster'].get_score(importance_type='gain')
            feature_importance = {k: float(v) for k, v in gain_importance.items()}
        except Exception:
            feature_importance = {}
        
        return {
            'step': step,
            'direction': 'forward',
            'action': 'added',
            'feature_name': best_feature,
            'selected_features': new_features,
            'train_roc_auc': best_metrics['train_roc_auc'],
            'cv_roc_auc': best_metrics['cv_roc_auc'],
            'test_roc_auc': best_metrics['test_roc_auc'],
            'train_pr_auc': best_metrics['train_pr_auc'],
            'cv_pr_auc': best_metrics['cv_pr_auc'],
            'test_pr_auc': best_metrics['test_pr_auc'],
            'stability_type': stability_type,
            'stability_value': stability_value,
            'shap_importance': shap_importance,
            'shap_changes': {},  # Could track changes if needed
            'feature_importance': feature_importance,
            'shap_importance_by_feature': shap_importance_by_feature
        }
    except Exception as e:
        print(f"[SFS-Forward-Step] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _run_backward_step(X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
                       current_features: List[str], step: int, cv_folds: int) -> Optional[Dict]:
    """Run a single backward elimination step - evaluates dropping each feature"""
    try:
        if len(current_features) <= 1:
            return None
        
        best_feature_to_drop = None
        best_score = -np.inf
        best_metrics = None
        
        # Try dropping each feature and pick the one that maintains best performance
        for feature in current_features:
            candidate_features = [f for f in current_features if f != feature]
            
            # Train model without this feature
            X_train_subset = X_train[candidate_features]
            X_test_subset = X_test[candidate_features]
            
            # Train XGBoost model
            dtrain = xgb.DMatrix(X_train_subset, label=y_train)
            dtest = xgb.DMatrix(X_test_subset, label=y_test)
            
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'eta': 0.1,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'seed': 42
            }
            
            booster = xgb.train(params, dtrain, num_boost_round=100, verbose_eval=False)
            
            # Evaluate on train
            y_train_pred = booster.predict(dtrain)
            train_roc_auc = float(roc_auc_score(y_train, y_train_pred))
            train_pr_auc = float(average_precision_score(y_train, y_train_pred))
            
            # Evaluate on test
            y_test_pred = booster.predict(dtest)
            test_roc_auc = float(roc_auc_score(y_test, y_test_pred))
            test_pr_auc = float(average_precision_score(y_test, y_test_pred))
            
            # Cross-validation
            skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
            cv_roc_scores = []
            cv_pr_scores = []
            
            for train_idx, val_idx in skf.split(X_train_subset, y_train):
                X_cv_train, X_cv_val = X_train_subset.iloc[train_idx], X_train_subset.iloc[val_idx]
                y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                dcv_train = xgb.DMatrix(X_cv_train, label=y_cv_train)
                dcv_val = xgb.DMatrix(X_cv_val, label=y_cv_val)
                
                cv_booster = xgb.train(params, dcv_train, num_boost_round=100, verbose_eval=False)
                y_cv_pred = cv_booster.predict(dcv_val)
                
                cv_roc_scores.append(roc_auc_score(y_cv_val, y_cv_pred))
                cv_pr_scores.append(average_precision_score(y_cv_val, y_cv_pred))
            
            cv_roc_auc = float(np.mean(cv_roc_scores))
            cv_pr_auc = float(np.mean(cv_pr_scores))
            
            # Use CV ROC-AUC as criterion - drop feature that maintains best score
            if cv_roc_auc > best_score:
                best_score = cv_roc_auc
                best_feature_to_drop = feature
                best_metrics = {
                    'train_roc_auc': train_roc_auc,
                    'train_pr_auc': train_pr_auc,
                    'cv_roc_auc': cv_roc_auc,
                    'cv_pr_auc': cv_pr_auc,
                    'test_roc_auc': test_roc_auc,
                    'test_pr_auc': test_pr_auc,
                    'booster': booster
                }
        
        if best_feature_to_drop is None:
            return None
        
        # Build final feature set
        remaining_features = [f for f in current_features if f != best_feature_to_drop]
        
        # Calculate stability for the dropped feature
        try:
            if pd.api.types.is_numeric_dtype(X_train_raw[best_feature_to_drop]):
                stability_value = calculate_psi(
                    X_train_raw[best_feature_to_drop].values,
                    X_test_raw[best_feature_to_drop].values
                )
                stability_type = 'PSI'
            else:
                stability_value = calculate_csi(
                    X_train_raw[best_feature_to_drop].values,
                    X_test_raw[best_feature_to_drop].values
                )
                stability_type = 'CSI'
        except Exception:
            stability_value = None
            stability_type = 'N/A'
        
        shap_importance_by_feature = compute_shap_importance(
            best_metrics['booster'],
            X_train[remaining_features],
            remaining_features
        )
        shap_importance = 0.0
        
        # Get feature importances from model
        try:
            gain_importance = best_metrics['booster'].get_score(importance_type='gain')
            feature_importance = {k: float(v) for k, v in gain_importance.items()}
        except Exception:
            feature_importance = {}
        
        return {
            'step': step,
            'direction': 'backward',
            'action': 'dropped',
            'feature_name': best_feature_to_drop,
            'selected_features': remaining_features,
            'train_roc_auc': best_metrics['train_roc_auc'],
            'cv_roc_auc': best_metrics['cv_roc_auc'],
            'test_roc_auc': best_metrics['test_roc_auc'],
            'train_pr_auc': best_metrics['train_pr_auc'],
            'cv_pr_auc': best_metrics['cv_pr_auc'],
            'test_pr_auc': best_metrics['test_pr_auc'],
            'stability_type': stability_type,
            'stability_value': stability_value,
            'shap_importance': shap_importance,
            'shap_changes': {},
            'feature_importance': feature_importance,
            'shap_importance_by_feature': shap_importance_by_feature
        }
    except Exception as e:
        print(f"[SFS-Backward-Step] Error: {e}")
        import traceback
        traceback.print_exc()
        return None
