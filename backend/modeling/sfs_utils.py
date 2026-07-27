"""
Sequential Feature Selection (SFS) utilities for model optimization.

This module provides forward and backward sequential feature selection
with comprehensive metrics tracking, stability analysis (PSI/CSI), and
SHAP impact monitoring.
"""

import warnings
import os
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.metrics import (
    roc_auc_score, average_precision_score, r2_score, mean_squared_error,
)
from mlxtend.feature_selection import SequentialFeatureSelector as SFS
import xgboost as xgb  # legacy run_forward_sfs / run_backward_sfs paths
import shap

from modeling.booster_adapters import fit_booster

# Suppress NumPy warnings for invalid values during PSI/CSI/SHAP calculations
warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered')
from typing import Dict, List, Tuple, Any, Optional


def _normalize_sfs_task(task: Optional[str]) -> str:
    t = (task or 'classification').strip().lower()
    return 'regression' if t in ('regression', 'regressor', 'reg') else 'classification'


def _sfs_booster_params(task: str, nthread: int) -> Dict[str, Any]:
    """Shared SFS knobs (adapter maps aliases per algorithm)."""
    base = {
        'n_estimators': 100,
        'max_depth': 6,
        'learning_rate': 0.1,
        'eta': 0.1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'seed': 42,
        'nthread': nthread,
    }
    if task == 'regression':
        base.update({'objective': 'reg:squarederror', 'eval_metric': 'rmse', 'task': 'regression'})
    else:
        base.update({'objective': 'binary:logistic', 'eval_metric': 'auc', 'task': 'classification'})
    return base


# Backward-compatible alias
def _sfs_xgb_params(task: str, nthread: int) -> Dict[str, Any]:
    return _sfs_booster_params(task, nthread)


def _sfs_fit(
    algorithm: str,
    X_tr, y_tr, X_va, y_va,
    params: Dict[str, Any],
    *,
    task: str = 'classification',
    num_boost_round: int = 100,
    early_stopping_rounds: int = 10,
):
    return fit_booster(
        algorithm, X_tr, y_tr, X_va, y_va, params,
        task=task,
        nthread=int(params.get('nthread', 0) or 0),
        num_boost_round=num_boost_round,
        early_stopping_rounds=early_stopping_rounds,
    )


def _sfs_cv_splitter(task: str, cv_folds: int):
    if task == 'regression':
        return KFold(n_splits=cv_folds, shuffle=True, random_state=42)
    return StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)


def _sfs_score_pair(y_true, y_pred, task: str) -> Tuple[float, float]:
    """Return (primary, secondary) scores — both higher-is-better for ranking.

    Classification: ROC-AUC, PR-AUC.
    Regression: R², −RMSE (so max() ranking still works).
    """
    if task == 'regression':
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        primary = float(r2_score(y_true, y_pred)) if len(y_true) >= 2 else float('-inf')
        rmse = float(np.sqrt(mean_squared_error(y_true, y_pred))) if len(y_true) else float('inf')
        return primary, -rmse
    return (
        float(roc_auc_score(y_true, y_pred)),
        float(average_precision_score(y_true, y_pred)),
    )


def _sfs_metric_fields(y_true, y_pred, task: str, prefix: str) -> Dict[str, float]:
    """Build train_/test_/cv_ metric fields with classification aliases."""
    primary, secondary = _sfs_score_pair(y_true, y_pred, task)
    out = {
        f'{prefix}roc_auc': primary,
        f'{prefix}pr_auc': secondary,
    }
    if task == 'regression':
        out[f'{prefix}r2'] = primary
        out[f'{prefix}rmse'] = -secondary
    return out


def _normalize_sfs_metric_criteria(metric_criteria: List[Dict[str, Any]], task: str) -> List[Dict[str, Any]]:
    """Map classification metric names to regression equivalents when needed."""
    if task != 'regression':
        return metric_criteria or [{'metric': 'roc_auc', 'pct_change': 0.0}]
    if not metric_criteria:
        return [{'metric': 'r2', 'pct_change': 0.0}]
    out = []
    for mc in metric_criteria:
        name = (mc.get('metric') or 'r2').strip().lower()
        if name in ('roc_auc', 'pr_auc', 'auc'):
            name = 'r2'
        if name == 'rmse':
            # Stopping logic assumes higher-is-better; steer users to r2.
            name = 'r2'
        out.append({**mc, 'metric': name})
    return out or [{'metric': 'r2', 'pct_change': 0.0}]


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
    cv_folds: int = 5,
    n_jobs: int = 1
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
    
    # Detect categorical columns for enable_categorical support
    _has_cat = any(
        hasattr(X_train[c], 'cat') or X_train[c].dtype.name == 'category' or X_train[c].dtype == 'object' or pd.api.types.is_string_dtype(X_train[c])
        for c in X_train.columns
    )
    
    if max_features is None:
        max_features = len(feature_names)
    
    print(f"[SFS-Forward] Starting with {len(feature_names)} features, max_features={max_features}, n_jobs={n_jobs}, enable_categorical={_has_cat}")
    
    try:
        previous_shap_importance = {}
        selected_features = []
        remaining_features = feature_names.copy()
        
        ranking_params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 6,
            'eta': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'seed': 42,
            'nthread': 1 if n_jobs > 1 else 0
        }
        
        for step in range(min(max_features, len(feature_names))):
            print(f"[SFS-Forward] Step {step + 1}/{max_features}")
            
            def evaluate_candidate(feature):
                candidate_features = selected_features + [feature]
                dtrain = xgb.DMatrix(X_train[candidate_features], label=y_train, enable_categorical=_has_cat)
                dtest = xgb.DMatrix(X_test[candidate_features], label=y_test, enable_categorical=_has_cat)
                booster = xgb.train(
                    ranking_params, dtrain, num_boost_round=100,
                    evals=[(dtrain, 'train')], early_stopping_rounds=10,
                    verbose_eval=False
                )
                y_tr = booster.predict(dtrain)
                y_te = booster.predict(dtest)
                return feature, {
                    'train_roc_auc': float(roc_auc_score(y_train, y_tr)),
                    'train_pr_auc': float(average_precision_score(y_train, y_tr)),
                    'test_roc_auc': float(roc_auc_score(y_test, y_te)),
                    'test_pr_auc': float(average_precision_score(y_test, y_te)),
                }
            
            # Phase 1: Rank candidates in parallel (train+test only)
            effective_jobs = min(n_jobs, len(remaining_features))
            candidate_results = {}
            if effective_jobs > 1:
                with ThreadPoolExecutor(max_workers=effective_jobs) as pool:
                    futures = {pool.submit(evaluate_candidate, f): f for f in remaining_features}
                    for future in as_completed(futures):
                        feat, metrics = future.result()
                        candidate_results[feat] = metrics
            else:
                for feat in remaining_features:
                    _, metrics = evaluate_candidate(feat)
                    candidate_results[feat] = metrics
            
            best_feature = max(candidate_results, key=lambda f: candidate_results[f]['test_roc_auc'])
            
            # Phase 2: Retrain winner with all threads + full CV
            selected_features.append(best_feature)
            remaining_features.remove(best_feature)
            
            winner_params = {**ranking_params, 'nthread': 0}
            X_train_sub = X_train[selected_features]
            X_test_sub = X_test[selected_features]
            dtrain_w = xgb.DMatrix(X_train_sub, label=y_train, enable_categorical=_has_cat)
            dtest_w = xgb.DMatrix(X_test_sub, label=y_test, enable_categorical=_has_cat)
            
            winner_booster = xgb.train(
                winner_params, dtrain_w, num_boost_round=100,
                evals=[(dtrain_w, 'train')], early_stopping_rounds=10,
                verbose_eval=False
            )
            
            y_tr_pred = winner_booster.predict(dtrain_w)
            y_te_pred = winner_booster.predict(dtest_w)
            train_roc_auc = float(roc_auc_score(y_train, y_tr_pred))
            train_pr_auc = float(average_precision_score(y_train, y_tr_pred))
            test_roc_auc = float(roc_auc_score(y_test, y_te_pred))
            test_pr_auc = float(average_precision_score(y_test, y_te_pred))
            
            skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
            cv_roc_scores, cv_pr_scores = [], []
            for train_idx, val_idx in skf.split(X_train_sub, y_train):
                dcv_train = xgb.DMatrix(X_train_sub.iloc[train_idx], label=y_train.iloc[train_idx], enable_categorical=_has_cat)
                dcv_val = xgb.DMatrix(X_train_sub.iloc[val_idx], label=y_train.iloc[val_idx], enable_categorical=_has_cat)
                cv_booster = xgb.train(
                    winner_params, dcv_train, num_boost_round=100,
                    evals=[(dcv_train, 'train')], early_stopping_rounds=10,
                    verbose_eval=False
                )
                y_cv_pred = cv_booster.predict(dcv_val)
                cv_roc_scores.append(roc_auc_score(y_train.iloc[val_idx], y_cv_pred))
                cv_pr_scores.append(average_precision_score(y_train.iloc[val_idx], y_cv_pred))
            
            cv_roc_auc = float(np.mean(cv_roc_scores))
            cv_pr_auc = float(np.mean(cv_pr_scores))
            
            # Phase 3: Model PSI & SHAP
            try:
                dtrain_sel = xgb.DMatrix(X_train[selected_features], enable_categorical=_has_cat)
                dtest_sel = xgb.DMatrix(X_test[selected_features], enable_categorical=_has_cat)
                stability_metric = calculate_psi(
                    winner_booster.predict(dtrain_sel, output_margin=True),
                    winner_booster.predict(dtest_sel, output_margin=True)
                )
                stability_type = 'PSI'
            except Exception:
                stability_metric = None
                stability_type = 'PSI'
            
            current_shap_importance = compute_shap_importance(winner_booster, X_train[selected_features], selected_features)
            
            shap_changes = {}
            for feat in selected_features[:-1]:
                shap_changes[feat] = current_shap_importance.get(feat, 0.0) - previous_shap_importance.get(feat, 0.0)
            
            step_result = {
                'step': step + 1,
                'direction': 'forward',
                'action': 'added',
                'feature_name': best_feature,
                'selected_features': selected_features.copy(),
                'train_roc_auc': train_roc_auc,
                'train_pr_auc': train_pr_auc,
                'cv_roc_auc': cv_roc_auc,
                'cv_pr_auc': cv_pr_auc,
                'test_roc_auc': test_roc_auc,
                'test_pr_auc': test_pr_auc,
                'stability_type': stability_type,
                'stability_value': stability_metric,
                'shap_importance': current_shap_importance.get(best_feature, 0.0),
                'shap_changes': shap_changes,
                'feature_importance': dict(winner_booster.get_score(importance_type='gain')),
                'shap_importance_by_feature': dict(current_shap_importance)
            }
            
            results.append(step_result)
            previous_shap_importance = current_shap_importance
            
            print(f"[SFS-Forward] Step {step + 1}: Added '{best_feature}', CV ROC-AUC={cv_roc_auc:.4f}")
        
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
    cv_folds: int = 5,
    n_jobs: int = 1
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
    
    # Detect categorical columns for enable_categorical support
    _has_cat = any(
        hasattr(X_train[c], 'cat') or X_train[c].dtype.name == 'category' or X_train[c].dtype == 'object' or pd.api.types.is_string_dtype(X_train[c])
        for c in X_train.columns
    )
    
    print(f"[SFS-Backward] Starting with {len(feature_names)} features, min_features={min_features}, n_jobs={n_jobs}, enable_categorical={_has_cat}")
    
    try:
        selected_features = feature_names.copy()
        
        ranking_params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 6,
            'eta': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'seed': 42,
            'nthread': 1 if n_jobs > 1 else 0
        }
        winner_params = {**ranking_params, 'nthread': 0}
        
        # Compute initial SHAP importance with all features
        dtrain_full = xgb.DMatrix(X_train, label=y_train, enable_categorical=_has_cat)
        initial_booster = xgb.train(
            winner_params, dtrain_full, num_boost_round=100,
            evals=[(dtrain_full, 'train')], early_stopping_rounds=10,
            verbose_eval=False
        )
        previous_shap_importance = compute_shap_importance(initial_booster, X_train, feature_names)
        
        step = 0
        while len(selected_features) > min_features:
            step += 1
            print(f"[SFS-Backward] Step {step}, {len(selected_features)} features remaining")
            
            def evaluate_candidate(feature):
                candidate_features = [f for f in selected_features if f != feature]
                if len(candidate_features) == 0:
                    return feature, {'test_roc_auc': -np.inf}
                dtrain = xgb.DMatrix(X_train[candidate_features], label=y_train, enable_categorical=_has_cat)
                dtest = xgb.DMatrix(X_test[candidate_features], label=y_test, enable_categorical=_has_cat)
                booster = xgb.train(
                    ranking_params, dtrain, num_boost_round=100,
                    evals=[(dtrain, 'train')], early_stopping_rounds=10,
                    verbose_eval=False
                )
                y_tr = booster.predict(dtrain)
                y_te = booster.predict(dtest)
                return feature, {
                    'train_roc_auc': float(roc_auc_score(y_train, y_tr)),
                    'train_pr_auc': float(average_precision_score(y_train, y_tr)),
                    'test_roc_auc': float(roc_auc_score(y_test, y_te)),
                    'test_pr_auc': float(average_precision_score(y_test, y_te)),
                }
            
            # Phase 1: Rank candidates in parallel
            effective_jobs = min(n_jobs, len(selected_features))
            candidate_results = {}
            if effective_jobs > 1:
                with ThreadPoolExecutor(max_workers=effective_jobs) as pool:
                    futures = {pool.submit(evaluate_candidate, f): f for f in selected_features}
                    for future in as_completed(futures):
                        feat, metrics = future.result()
                        candidate_results[feat] = metrics
            else:
                for feat in selected_features:
                    _, metrics = evaluate_candidate(feat)
                    candidate_results[feat] = metrics
            
            best_feature_to_drop = max(candidate_results, key=lambda f: candidate_results[f]['test_roc_auc'])
            
            # Phase 2: Retrain winner with all threads + full CV
            selected_features.remove(best_feature_to_drop)
            remaining = selected_features.copy()
            
            X_train_sub = X_train[remaining]
            X_test_sub = X_test[remaining]
            dtrain_w = xgb.DMatrix(X_train_sub, label=y_train, enable_categorical=_has_cat)
            dtest_w = xgb.DMatrix(X_test_sub, label=y_test, enable_categorical=_has_cat)
            
            winner_booster = xgb.train(
                winner_params, dtrain_w, num_boost_round=100,
                evals=[(dtrain_w, 'train')], early_stopping_rounds=10,
                verbose_eval=False
            )
            
            y_tr_pred = winner_booster.predict(dtrain_w)
            y_te_pred = winner_booster.predict(dtest_w)
            train_roc_auc = float(roc_auc_score(y_train, y_tr_pred))
            train_pr_auc = float(average_precision_score(y_train, y_tr_pred))
            test_roc_auc = float(roc_auc_score(y_test, y_te_pred))
            test_pr_auc = float(average_precision_score(y_test, y_te_pred))
            
            skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
            cv_roc_scores, cv_pr_scores = [], []
            for train_idx, val_idx in skf.split(X_train_sub, y_train):
                dcv_train = xgb.DMatrix(X_train_sub.iloc[train_idx], label=y_train.iloc[train_idx], enable_categorical=_has_cat)
                dcv_val = xgb.DMatrix(X_train_sub.iloc[val_idx], label=y_train.iloc[val_idx], enable_categorical=_has_cat)
                cv_booster = xgb.train(
                    winner_params, dcv_train, num_boost_round=100,
                    evals=[(dcv_train, 'train')], early_stopping_rounds=10,
                    verbose_eval=False
                )
                y_cv_pred = cv_booster.predict(dcv_val)
                cv_roc_scores.append(roc_auc_score(y_train.iloc[val_idx], y_cv_pred))
                cv_pr_scores.append(average_precision_score(y_train.iloc[val_idx], y_cv_pred))
            
            cv_roc_auc = float(np.mean(cv_roc_scores))
            cv_pr_auc = float(np.mean(cv_pr_scores))
            
            # Phase 3: Model PSI & SHAP
            try:
                dtrain_sel = xgb.DMatrix(X_train[remaining], enable_categorical=_has_cat)
                dtest_sel = xgb.DMatrix(X_test[remaining], enable_categorical=_has_cat)
                stability_metric = calculate_psi(
                    winner_booster.predict(dtrain_sel, output_margin=True),
                    winner_booster.predict(dtest_sel, output_margin=True)
                )
                stability_type = 'PSI'
            except Exception:
                stability_metric = None
                stability_type = 'PSI'
            
            current_shap_importance = compute_shap_importance(winner_booster, X_train[remaining], remaining)
            
            shap_changes = {}
            for feat in remaining:
                shap_changes[feat] = current_shap_importance.get(feat, 0.0) - previous_shap_importance.get(feat, 0.0)
            
            step_result = {
                'step': step,
                'direction': 'backward',
                'action': 'dropped',
                'feature_name': best_feature_to_drop,
                'selected_features': remaining,
                'train_roc_auc': train_roc_auc,
                'train_pr_auc': train_pr_auc,
                'cv_roc_auc': cv_roc_auc,
                'cv_pr_auc': cv_pr_auc,
                'test_roc_auc': test_roc_auc,
                'test_pr_auc': test_pr_auc,
                'stability_type': stability_type,
                'stability_value': stability_metric,
                'shap_importance': previous_shap_importance.get(best_feature_to_drop, 0.0),
                'shap_changes': shap_changes,
                'feature_importance': dict(winner_booster.get_score(importance_type='gain')),
                'shap_importance_by_feature': dict(current_shap_importance)
            }
            
            results.append(step_result)
            previous_shap_importance = current_shap_importance
            
            print(f"[SFS-Backward] Step {step}: Dropped '{best_feature_to_drop}', CV ROC-AUC={cv_roc_auc:.4f}")
        
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
    initial_features: Optional[List[str]] = None,  # Optional: Start with specific features
    n_jobs: int = 1,  # Number of parallel workers for candidate evaluation
    top_k: int = 3,  # Number of top candidates to CV-evaluate per step
    stop_flag: Optional[Dict] = None,  # Dict with 'stop_requested' key checked each step
    resume_state: Optional[Dict] = None,  # State to resume from (forward/backward completed steps)
    task: str = 'classification',
    algorithm: str = 'xgboost',
) -> Dict[str, Any]:
    """
    Run SFS with user-specified methods, stopping criteria, and progress tracking.
    
    Args:
        X_train, y_train: Training data
        X_test, y_test: Test data
        X_train_raw, X_test_raw: Raw data for stability calculations
        methods: List of methods to run ('forward', 'backward', or both)
        stopping_criteria: Dict with keys:
            - metrics: List of {metric: 'roc_auc'|'pr_auc'|'r2', pct_change: float}
            - min_features: Minimum features to keep (for backward)
            - max_features: Maximum features to add (for forward)
        status_callback: Function to call with progress updates
        cv_folds: Number of CV folds
        task: 'classification' or 'regression'
    
    Returns:
        Dict with forward/backward results and final metrics
    """
    task = _normalize_sfs_task(task)
    algorithm = (algorithm or 'xgboost').strip().lower()
    results = {'forward': [], 'backward': [], 'status': 'running', 'task': task, 'algorithm': algorithm}
    completed_steps = []  # Track completed steps for real-time viewing

    def is_stop_requested():
        """Check if stop has been requested via the shared progress dict."""
        if stop_flag and stop_flag.get('stop_requested'):
            return True
        return False

    # Filter by initial_features if provided
    if initial_features:
        valid_features = [f for f in initial_features if f in X_train.columns]
        if valid_features:
            X_train = X_train[valid_features]
            X_test = X_test[valid_features]
            if X_train_raw is not None and hasattr(X_train_raw, 'columns'):
                X_train_raw = X_train_raw[[c for c in valid_features if c in X_train_raw.columns]]
            if X_test_raw is not None and hasattr(X_test_raw, 'columns'):
                X_test_raw = X_test_raw[[c for c in valid_features if c in X_test_raw.columns]]
            print(f"[SFS] Starting with {len(valid_features)} initial features: {valid_features}")
    
    print(f"[SFS] Parallelism: n_jobs={n_jobs}, available CPUs={os.cpu_count()}, task={task}")
    
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
        default_metric = 'r2' if task == 'regression' else 'roc_auc'
        metric_criteria = stopping_criteria.get('metrics', [{'metric': default_metric, 'pct_change': 0.0}])
        if not metric_criteria:  # Fallback for backward compatibility
            metric_criteria = [{'metric': default_metric, 'pct_change': 0.0}]
        metric_criteria = _normalize_sfs_metric_criteria(metric_criteria, task)
        
        min_features = stopping_criteria.get('min_features', 3)
        max_features = stopping_criteria.get('max_features', min(10, X_train.shape[1]))
        
        # Run Forward Selection
        if 'forward' in methods:
            forward_results = []
            selected_features = []
            previous_metrics = {mc['metric']: 0.0 for mc in metric_criteria}
            forward_start_step = 1

            # Resume from previous state if available
            if resume_state and resume_state.get('forward_results'):
                forward_results = resume_state['forward_results']
                selected_features = resume_state.get('forward_selected_features', [])
                previous_metrics = resume_state.get('forward_previous_metrics', previous_metrics)
                forward_start_step = resume_state.get('forward_start_step', len(forward_results) + 1)
                completed_steps = resume_state.get('completed_steps', [])
                print(f"[SFS] Resuming forward from step {forward_start_step}, {len(selected_features)} features selected")

            update_status(f'Starting forward selection (max {max_features} features)...', 0.0)
            
            for step in range(forward_start_step, max_features + 1):
                if is_stop_requested():
                    print(f"[SFS] Stop requested at forward step {step}")
                    results['forward'] = forward_results
                    results['status'] = 'stopped'
                    results['stopped_at'] = {'direction': 'forward', 'step': step}
                    results['resume_state'] = {
                        'forward_results': forward_results,
                        'forward_selected_features': selected_features,
                        'forward_previous_metrics': previous_metrics,
                        'forward_start_step': step,
                        'completed_steps': completed_steps.copy()
                    }
                    update_status(f'SFS stopped by user at forward step {step}', step / max_features)
                    return results
                step_progress = (step / max_features) * method_progress_weight
                update_status(f'Forward selection: Step {step}/{max_features}', step_progress)
                
                # Run one step of forward selection
                step_result = _run_forward_step(
                    X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
                    selected_features, step, cv_folds, n_jobs=n_jobs, top_k=top_k, task=task,
                    algorithm=algorithm,
                )
                
                if step_result:
                    # Get current metric values (r2 aliases onto cv_roc_auc for regressors)
                    current_metrics = {}
                    for mc in metric_criteria:
                        metric_name = mc['metric']
                        key = f'cv_{metric_name}'
                        if key in step_result:
                            current_metrics[metric_name] = step_result[key]
                        elif metric_name == 'r2':
                            current_metrics[metric_name] = step_result.get('cv_roc_auc', 0.0)
                        else:
                            current_metrics[metric_name] = 0.0
                    
                    # Calculate percentage changes for display (abs denom supports negative R²)
                    pct_changes = {}
                    if step > 1:
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            current_val = current_metrics[metric_name]
                            prev_val = previous_metrics[metric_name]
                            if abs(prev_val) > 1e-12:
                                pct_changes[metric_name] = ((current_val - prev_val) / abs(prev_val)) * 100
                            else:
                                pct_changes[metric_name] = 0.0
                    
                    # Forward stopping: stop when signed pct_change is NOT > threshold
                    # (i.e. improvement is too small or metric decreased)
                    should_stop = False
                    if step > 1:
                        stop_reasons = []
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            pct_threshold = mc.get('pct_change', 0.0)
                            if pct_threshold > 0:
                                current_val = current_metrics[metric_name]
                                prev_val = previous_metrics[metric_name]
                                if abs(prev_val) > 1e-12:
                                    signed_change = ((current_val - prev_val) / abs(prev_val)) * 100
                                    if not (signed_change > pct_threshold):
                                        stop_reasons.append(f'{metric_name} change ({signed_change:+.2f}%) not > {pct_threshold}%')
                        if stop_reasons:
                            update_status(
                                f'Forward selection stopped: Feature rejected ({step_result["feature_name"]}), {"; ".join(stop_reasons)}',
                                step_progress, previous_metrics
                            )
                            should_stop = True
                    
                    if should_stop:
                        break
                    
                    # Accept the feature
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
                        'cv_r2': step_result.get('cv_r2'),
                        'cv_rmse': step_result.get('cv_rmse'),
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
            
            backward_results = []
            current_features = list(X_train.columns)
            max_drops = len(current_features) - min_features
            previous_metrics = None
            backward_start_step = 1

            # Resume from previous state if available
            if resume_state and resume_state.get('backward_results'):
                backward_results = resume_state['backward_results']
                current_features = resume_state.get('backward_current_features', current_features)
                previous_metrics = resume_state.get('backward_previous_metrics', None)
                backward_start_step = resume_state.get('backward_start_step', len(backward_results) + 1)
                if not completed_steps and resume_state.get('completed_steps'):
                    completed_steps = resume_state['completed_steps']
                max_drops = len(list(X_train.columns)) - min_features  # recalculate from full columns
                print(f"[SFS] Resuming backward from step {backward_start_step}, {len(current_features)} features remaining")

            update_status(f'Starting backward elimination (min {min_features} features)...', base_progress)
            
            for step in range(backward_start_step, max_drops + 1):
                if is_stop_requested():
                    print(f"[SFS] Stop requested at backward step {step}")
                    results['backward'] = backward_results
                    if backward_results:
                        results['backward_remaining_features'] = current_features
                    else:
                        results['backward_remaining_features'] = list(X_train.columns)
                    results['status'] = 'stopped'
                    results['stopped_at'] = {'direction': 'backward', 'step': step}
                    results['resume_state'] = {
                        'backward_results': backward_results,
                        'backward_current_features': current_features,
                        'backward_previous_metrics': previous_metrics,
                        'backward_start_step': step,
                        'completed_steps': completed_steps.copy()
                    }
                    # Also include any forward results completed earlier
                    if results.get('forward'):
                        results['resume_state']['forward_results'] = results['forward']
                    update_status(f'SFS stopped by user at backward step {step}', base_progress + (step / max_drops) * method_progress_weight)
                    return results
                step_progress = base_progress + (step / max_drops) * method_progress_weight
                update_status(f'Backward elimination: Step {step}/{max_drops}', step_progress)
                
                # Run one step of backward elimination
                step_result = _run_backward_step(
                    X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
                    current_features, step, cv_folds, n_jobs=n_jobs, top_k=top_k, task=task,
                    algorithm=algorithm,
                )
                
                if step_result:
                    # Get current metric values (r2 aliases onto cv_roc_auc for regressors)
                    current_metrics = {}
                    for mc in metric_criteria:
                        metric_name = mc['metric']
                        key = f'cv_{metric_name}'
                        if key in step_result:
                            current_metrics[metric_name] = step_result[key]
                        elif metric_name == 'r2':
                            current_metrics[metric_name] = step_result.get('cv_roc_auc', 0.0)
                        else:
                            current_metrics[metric_name] = 0.0
                    
                    # Calculate percentage changes for display (abs denom supports negative R²)
                    pct_changes = {}
                    if previous_metrics is not None:
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            current_val = current_metrics[metric_name]
                            prev_val = previous_metrics[metric_name]
                            if abs(prev_val) > 1e-12:
                                pct_changes[metric_name] = ((current_val - prev_val) / abs(prev_val)) * 100
                            else:
                                pct_changes[metric_name] = 0.0
                    
                    # Backward stopping: stop when |pct_change| > threshold
                    # (dropping this feature degrades metric too much)
                    should_stop = False
                    if previous_metrics is not None:
                        stop_reasons = []
                        for mc in metric_criteria:
                            metric_name = mc['metric']
                            pct_threshold = mc.get('pct_change', 0.0)
                            if pct_threshold > 0:
                                current_val = current_metrics[metric_name]
                                prev_val = previous_metrics[metric_name]
                                if abs(prev_val) > 1e-12:
                                    signed_change = ((current_val - prev_val) / abs(prev_val)) * 100
                                    if abs(signed_change) > pct_threshold:
                                        stop_reasons.append(f'{metric_name} |change| ({abs(signed_change):.2f}%) > {pct_threshold}%')
                        if stop_reasons:
                            update_status(
                                f'Backward elimination stopped: Feature drop rejected ({step_result["feature_name"]}), {"; ".join(stop_reasons)}',
                                step_progress, previous_metrics
                            )
                            should_stop = True
                    
                    if should_stop:
                        break
                    
                    # Accept the drop
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
                        'cv_r2': step_result.get('cv_r2'),
                        'cv_rmse': step_result.get('cv_rmse'),
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
                      current_features: List[str], step: int, cv_folds: int,
                      n_jobs: int = 1, top_k: int = 3, task: str = 'classification',
                      algorithm: str = 'xgboost') -> Optional[Dict]:
    """Run a single forward selection step with parallel candidate evaluation.
    
    Optimizations applied:
    - Parallel evaluation of candidates via ThreadPoolExecutor (n_jobs)
    - CV only for the winning candidate (train+test score used for ranking)
    - Early stopping in booster training (early_stopping_rounds=10)
    """
    try:
        task = _normalize_sfs_task(task)
        algorithm = (algorithm or 'xgboost').strip().lower()
        
        remaining_features = [f for f in X_train.columns if f not in current_features]
        if not remaining_features:
            return None
        
        # When parallelizing, restrict booster to 1 thread per worker to avoid oversubscription
        ranking_params = _sfs_booster_params(task, nthread=1 if n_jobs > 1 else 0)
        
        def evaluate_candidate(feature):
            """Evaluate adding one feature using train+test only (no CV for ranking)."""
            candidate_features = current_features + [feature]
            adapter = _sfs_fit(
                algorithm,
                X_train[candidate_features], y_train,
                X_test[candidate_features], y_test,
                ranking_params, task=task, num_boost_round=100, early_stopping_rounds=10,
            )
            y_tr = adapter.predict_proba(X_train[candidate_features])
            y_te = adapter.predict_proba(X_test[candidate_features])
            fields = _sfs_metric_fields(y_train, y_tr, task, 'train_')
            fields.update(_sfs_metric_fields(y_test, y_te, task, 'test_'))
            return feature, fields
        
        # --- Phase 1: Rank candidates in parallel (train+test only, no CV) ---
        effective_jobs = min(n_jobs, len(remaining_features))
        candidate_results = {}
        
        if effective_jobs > 1:
            with ThreadPoolExecutor(max_workers=effective_jobs) as pool:
                futures = {pool.submit(evaluate_candidate, f): f for f in remaining_features}
                for future in as_completed(futures):
                    feat, metrics = future.result()
                    candidate_results[feat] = metrics
        else:
            for feat in remaining_features:
                _, metrics = evaluate_candidate(feat)
                candidate_results[feat] = metrics
        
        # Pick top-K candidates by primary test score for full CV evaluation
        TOP_K = min(top_k, len(candidate_results))
        sorted_candidates = sorted(candidate_results, key=lambda f: candidate_results[f]['test_roc_auc'], reverse=True)
        top_candidates = sorted_candidates[:TOP_K]
        
        # --- Phase 2: Run CV for top-K candidates, pick best by CV primary score ---
        winner_params = {**ranking_params, 'nthread': 0}  # Use all cores for final model
        skf = _sfs_cv_splitter(task, cv_folds)
        
        best_feature = None
        best_cv_roc = float('-inf')
        best_cv_result = {}
        
        for candidate_feat in top_candidates:
            cand_features = current_features + [candidate_feat]
            X_train_cand = X_train[cand_features]
            
            cv_roc_scores = []
            cv_pr_scores = []
            for train_idx, val_idx in skf.split(X_train_cand, y_train):
                X_cv_train = X_train_cand.iloc[train_idx]
                X_cv_val = X_train_cand.iloc[val_idx]
                y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                cv_adapter = _sfs_fit(
                    algorithm, X_cv_train, y_cv_train, X_cv_val, y_cv_val,
                    winner_params, task=task, num_boost_round=100, early_stopping_rounds=10,
                )
                y_cv_pred = cv_adapter.predict_proba(X_cv_val)
                p, s = _sfs_score_pair(y_cv_val, y_cv_pred, task)
                cv_roc_scores.append(p)
                cv_pr_scores.append(s)
            
            cand_cv_roc = float(np.mean(cv_roc_scores))
            cand_cv_pr = float(np.mean(cv_pr_scores))
            print(f"[SFS-Forward-Step] Top-K CV: {candidate_feat} cv_primary={cand_cv_roc:.4f}")
            
            if cand_cv_roc > best_cv_roc:
                best_cv_roc = cand_cv_roc
                best_feature = candidate_feat
                best_cv_result = {'cv_roc_auc': cand_cv_roc, 'cv_pr_auc': cand_cv_pr}
        
        cv_roc_auc = best_cv_result['cv_roc_auc']
        cv_pr_auc = best_cv_result['cv_pr_auc']
        
        # Retrain final winner model for metrics
        new_features = current_features + [best_feature]
        X_train_subset = X_train[new_features]
        X_test_subset = X_test[new_features]
        
        winner_adapter = _sfs_fit(
            algorithm, X_train_subset, y_train, X_test_subset, y_test,
            winner_params, task=task, num_boost_round=100, early_stopping_rounds=10,
        )
        winner_booster = winner_adapter.shap_model()
        
        y_tr_pred = winner_adapter.predict_proba(X_train_subset)
        y_te_pred = winner_adapter.predict_proba(X_test_subset)
        train_fields = _sfs_metric_fields(y_train, y_tr_pred, task, 'train_')
        test_fields = _sfs_metric_fields(y_test, y_te_pred, task, 'test_')
        
        # --- Phase 3: Model PSI & SHAP for the winner ---
        try:
            train_scores = winner_adapter.predict_proba(X_train[new_features])
            test_scores = winner_adapter.predict_proba(X_test[new_features])
            stability_value = calculate_psi(train_scores, test_scores)
            stability_type = 'PSI'
        except Exception as e:
            print(f"[SFS-Forward-Step] Model PSI error: {e}")
            stability_value = None
            stability_type = 'PSI'
        
        shap_importance_by_feature = compute_shap_importance(winner_booster, X_train[new_features], new_features)
        shap_importance = float(shap_importance_by_feature.get(best_feature, 0.0))
        
        try:
            feature_importance = {d['feature']: float(d['score']) for d in winner_adapter.gain_importance()}
        except Exception:
            feature_importance = {}
        
        result = {
            'step': step,
            'direction': 'forward',
            'action': 'added',
            'feature_name': best_feature,
            'selected_features': new_features,
            'task': task,
            'train_roc_auc': train_fields['train_roc_auc'],
            'cv_roc_auc': cv_roc_auc,
            'test_roc_auc': test_fields['test_roc_auc'],
            'train_pr_auc': train_fields['train_pr_auc'],
            'cv_pr_auc': cv_pr_auc,
            'test_pr_auc': test_fields['test_pr_auc'],
            'stability_type': stability_type,
            'stability_value': stability_value,
            'shap_importance': shap_importance,
            'shap_changes': {},
            'feature_importance': feature_importance,
            'shap_importance_by_feature': shap_importance_by_feature
        }
        if task == 'regression':
            result.update({
                'train_r2': train_fields.get('train_r2'),
                'test_r2': test_fields.get('test_r2'),
                'cv_r2': cv_roc_auc,
                'train_rmse': train_fields.get('train_rmse'),
                'test_rmse': test_fields.get('test_rmse'),
                'cv_rmse': -cv_pr_auc if cv_pr_auc is not None else None,
            })
        return result
    except Exception as e:
        print(f"[SFS-Forward-Step] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _run_backward_step(X_train, y_train, X_test, y_test, X_train_raw, X_test_raw,
                       current_features: List[str], step: int, cv_folds: int,
                       n_jobs: int = 1, top_k: int = 3, task: str = 'classification',
                       algorithm: str = 'xgboost') -> Optional[Dict]:
    """Run a single backward elimination step with parallel candidate evaluation.
    
    Optimizations applied:
    - Parallel evaluation of candidates via ThreadPoolExecutor (n_jobs)
    - CV only for the winning candidate (train+test score used for ranking)
    - Early stopping in booster training (early_stopping_rounds=10)
    """
    try:
        task = _normalize_sfs_task(task)
        algorithm = (algorithm or 'xgboost').strip().lower()
        
        if len(current_features) <= 1:
            return None
        
        ranking_params = _sfs_booster_params(task, nthread=1 if n_jobs > 1 else 0)
        
        def evaluate_candidate(feature):
            """Evaluate dropping one feature using train+test only (no CV for ranking)."""
            candidate_features = [f for f in current_features if f != feature]
            adapter = _sfs_fit(
                algorithm,
                X_train[candidate_features], y_train,
                X_test[candidate_features], y_test,
                ranking_params, task=task, num_boost_round=100, early_stopping_rounds=10,
            )
            y_tr = adapter.predict_proba(X_train[candidate_features])
            y_te = adapter.predict_proba(X_test[candidate_features])
            fields = _sfs_metric_fields(y_train, y_tr, task, 'train_')
            fields.update(_sfs_metric_fields(y_test, y_te, task, 'test_'))
            return feature, fields
        
        # --- Phase 1: Rank candidates in parallel (train+test only, no CV) ---
        effective_jobs = min(n_jobs, len(current_features))
        candidate_results = {}
        
        if effective_jobs > 1:
            with ThreadPoolExecutor(max_workers=effective_jobs) as pool:
                futures = {pool.submit(evaluate_candidate, f): f for f in current_features}
                for future in as_completed(futures):
                    feat, metrics = future.result()
                    candidate_results[feat] = metrics
        else:
            for feat in current_features:
                _, metrics = evaluate_candidate(feat)
                candidate_results[feat] = metrics
        
        # Pick top-K candidates whose removal maintains best primary test score
        TOP_K = min(top_k, len(candidate_results))
        sorted_candidates = sorted(candidate_results, key=lambda f: candidate_results[f]['test_roc_auc'], reverse=True)
        top_candidates = sorted_candidates[:TOP_K]
        
        # --- Phase 2: Run CV for top-K candidates, pick best by CV primary score ---
        winner_params = {**ranking_params, 'nthread': 0}
        skf = _sfs_cv_splitter(task, cv_folds)
        
        best_feature_to_drop = None
        best_cv_roc = float('-inf')
        best_cv_result = {}
        
        for candidate_feat in top_candidates:
            cand_remaining = [f for f in current_features if f != candidate_feat]
            X_train_cand = X_train[cand_remaining]
            
            cv_roc_scores = []
            cv_pr_scores = []
            for train_idx, val_idx in skf.split(X_train_cand, y_train):
                X_cv_train = X_train_cand.iloc[train_idx]
                X_cv_val = X_train_cand.iloc[val_idx]
                y_cv_train, y_cv_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                cv_adapter = _sfs_fit(
                    algorithm, X_cv_train, y_cv_train, X_cv_val, y_cv_val,
                    winner_params, task=task, num_boost_round=100, early_stopping_rounds=10,
                )
                y_cv_pred = cv_adapter.predict_proba(X_cv_val)
                p, s = _sfs_score_pair(y_cv_val, y_cv_pred, task)
                cv_roc_scores.append(p)
                cv_pr_scores.append(s)
            
            cand_cv_roc = float(np.mean(cv_roc_scores))
            cand_cv_pr = float(np.mean(cv_pr_scores))
            print(f"[SFS-Backward-Step] Top-K CV: drop {candidate_feat} cv_primary={cand_cv_roc:.4f}")
            
            if cand_cv_roc > best_cv_roc:
                best_cv_roc = cand_cv_roc
                best_feature_to_drop = candidate_feat
                best_cv_result = {'cv_roc_auc': cand_cv_roc, 'cv_pr_auc': cand_cv_pr}
        
        cv_roc_auc = best_cv_result['cv_roc_auc']
        cv_pr_auc = best_cv_result['cv_pr_auc']
        
        # Retrain final winner model for metrics
        remaining_features = [f for f in current_features if f != best_feature_to_drop]
        X_train_subset = X_train[remaining_features]
        X_test_subset = X_test[remaining_features]
        
        winner_adapter = _sfs_fit(
            algorithm, X_train_subset, y_train, X_test_subset, y_test,
            winner_params, task=task, num_boost_round=100, early_stopping_rounds=10,
        )
        winner_booster = winner_adapter.shap_model()
        
        y_tr_pred = winner_adapter.predict_proba(X_train_subset)
        y_te_pred = winner_adapter.predict_proba(X_test_subset)
        train_fields = _sfs_metric_fields(y_train, y_tr_pred, task, 'train_')
        test_fields = _sfs_metric_fields(y_test, y_te_pred, task, 'test_')
        
        # --- Phase 3: Model PSI & SHAP ---
        try:
            train_scores = winner_adapter.predict_proba(X_train[remaining_features])
            test_scores = winner_adapter.predict_proba(X_test[remaining_features])
            stability_value = calculate_psi(train_scores, test_scores)
            stability_type = 'PSI'
        except Exception as e:
            print(f"[SFS-Backward-Step] Model PSI error: {e}")
            stability_value = None
            stability_type = 'PSI'
        
        shap_importance_by_feature = compute_shap_importance(winner_booster, X_train[remaining_features], remaining_features)
        shap_importance = 0.0
        
        try:
            feature_importance = {d['feature']: float(d['score']) for d in winner_adapter.gain_importance()}
        except Exception:
            feature_importance = {}
        
        result = {
            'step': step,
            'direction': 'backward',
            'action': 'dropped',
            'feature_name': best_feature_to_drop,
            'selected_features': remaining_features,
            'task': task,
            'train_roc_auc': train_fields['train_roc_auc'],
            'cv_roc_auc': cv_roc_auc,
            'test_roc_auc': test_fields['test_roc_auc'],
            'train_pr_auc': train_fields['train_pr_auc'],
            'cv_pr_auc': cv_pr_auc,
            'test_pr_auc': test_fields['test_pr_auc'],
            'stability_type': stability_type,
            'stability_value': stability_value,
            'shap_importance': shap_importance,
            'shap_changes': {},
            'feature_importance': feature_importance,
            'shap_importance_by_feature': shap_importance_by_feature
        }
        if task == 'regression':
            result.update({
                'train_r2': train_fields.get('train_r2'),
                'test_r2': test_fields.get('test_r2'),
                'cv_r2': cv_roc_auc,
                'train_rmse': train_fields.get('train_rmse'),
                'test_rmse': test_fields.get('test_rmse'),
                'cv_rmse': -cv_pr_auc if cv_pr_auc is not None else None,
            })
        return result
    except Exception as e:
        print(f"[SFS-Backward-Step] Error: {e}")
        import traceback
        traceback.print_exc()
        return None
