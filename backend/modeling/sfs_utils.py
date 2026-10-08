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
from modeling.development_validation import iter_validation_folds
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
    if task == 'classification' and early_stopping_rounds and (
        set(np.unique(y_tr)) != {0, 1} or set(np.unique(y_va)) != {0, 1}
    ):
        raise ValueError('Native selection uses AUC early stopping, which requires both encoded classes in training and validation. Revise the population or validation split; objective-aligned fitting remains open.')
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


def _selection_cv(X, y, task, algorithm, context, cv_folds, objective):
    from modeling.development_assessment import development_metrics, metric_coverage

    rows, provenance = [], []
    for fold, (X_tr, y_tr, X_va, y_va, receipt) in enumerate(iter_validation_folds(context, X, y, cv_folds, task), 1):
        if task == "classification" and set(y_tr.unique()) != {0, 1}:
            raise ValueError(f"Feature-selection fold {fold} lacks a training class; revise the population or split.")
        adapter = _sfs_fit(algorithm, X_tr, y_tr, X_va, y_va, _sfs_booster_params(task, 0), task=task)
        predictions = adapter.predict(X_va) if task == "regression" else adapter.predict_proba(X_va)
        rows.append(development_metrics(y_va, predictions, task, 2, objective["cost_matrix"]))
        provenance.append({**receipt, "native_fit": adapter.fit_receipt})
    if len(rows) != cv_folds:
        raise ValueError("Feature-selection CV did not produce every requested fold.")
    coverage = {key: metric_coverage([row[key] for row in rows]) for key in rows[0]}
    primary = objective["primary_metric"]
    if coverage[primary]["status"] != "complete":
        raise ValueError(
            f"Feature-selection objective {primary} is unavailable in one or more folds; revise the metric or validation population."
        )
    return {
        "schema_version": 2,
        "status": "completed",
        "metrics": {key: value["mean"] for key, value in coverage.items()},
        "metric_coverage": coverage,
        "fold_metrics": rows,
        "fold_provenance": provenance,
        "qualification": objective["qualification"],
        "uncertainty": "Unweighted fold means; fold spread is descriptive, not a confidence interval.",
        "selection_method": "Development-validation screening then top-K CV; reused selection data, not nested validation.",
    }


def _run_selection_step(
    X_train,
    y_train,
    X_valid,
    y_valid,
    current_features,
    step,
    cv_folds,
    n_jobs,
    top_k,
    task,
    algorithm,
    context,
    mode,
    objective,
):
    from modeling.development_assessment import development_metrics

    primary = objective["primary_metric"]
    sign = -1 if objective["direction"] == "minimize" else 1
    candidates = (
        [name for name in X_train if name not in current_features] if mode == "forward" else list(current_features)
    )
    if not candidates or (mode == "backward" and len(current_features) <= 1):
        return None
    subset = lambda name: current_features + [name] if mode == "forward" else [f for f in current_features if f != name]
    params = _sfs_booster_params(task, 1 if n_jobs > 1 else 0)

    def screen(name):
        features = subset(name)
        adapter = _sfs_fit(algorithm, X_train[features], y_train, X_valid[features], y_valid, params, task=task)
        predictions = (
            adapter.predict(X_valid[features]) if task == "regression" else adapter.predict_proba(X_valid[features])
        )
        value = development_metrics(y_valid, predictions, task, 2, objective["cost_matrix"])[primary]
        if value is None or not np.isfinite(value):
            raise ValueError(
                f"Development-validation screening metric {primary} is unavailable; revise the split or objective."
            )
        return name, float(value)

    if n_jobs > 1:
        with ThreadPoolExecutor(max_workers=min(n_jobs, len(candidates))) as pool:
            screened = dict(pool.map(screen, candidates))
    else:
        screened = dict(screen(name) for name in candidates)
    # Stable ties preserve the declared feature order, even with parallel workers.
    ranked = sorted(candidates, key=lambda name: (-sign * screened[name], candidates.index(name)))
    evidence = {
        name: _selection_cv(X_train[subset(name)], y_train, task, algorithm, context, cv_folds, objective)
        for name in ranked[: min(top_k, len(ranked))]
    }
    winner = max(evidence, key=lambda name: sign * evidence[name]["metrics"][primary])
    features, cv = subset(winner), evidence[winner]
    adapter = _sfs_fit(
        algorithm, X_train[features], y_train, X_valid[features], y_valid, _sfs_booster_params(task, 0), task=task
    )
    train_p = adapter.predict(X_train[features]) if task == "regression" else adapter.predict_proba(X_train[features])
    valid_p = adapter.predict(X_valid[features]) if task == "regression" else adapter.predict_proba(X_valid[features])
    metrics = {
        "train": development_metrics(y_train, train_p, task, 2, objective["cost_matrix"]),
        "test": development_metrics(y_valid, valid_p, task, 2, objective["cost_matrix"]),
        "cv": cv["metrics"],
    }
    shap_values = compute_shap_importance(adapter.shap_model(), X_train[features], features)
    result = {
        "schema_version": 2,
        "step": step,
        "direction": mode,
        "action": "added" if mode == "forward" else "dropped",
        "feature_name": winner,
        "selected_features": features,
        "task": task,
        "selection_objective": objective,
        "cv_evidence": cv,
        "validation_provenance": cv["fold_provenance"],
        "fit_receipt": adapter.fit_receipt,
        "screening_scores": screened,
        "cv_candidate_scores": {name: value["metrics"][primary] for name, value in evidence.items()},
        "top_k_evaluated": list(evidence),
        "test_partition": "development_validation",
        "stability_type": "PSI",
        "stability_value": calculate_psi(train_p, valid_p),
        "shap_importance": float(shap_values.get(winner, 0.0)),
        "shap_changes": {},
        "feature_importance": {row["feature"]: float(row["score"]) for row in adapter.gain_importance()},
        "shap_importance_by_feature": shap_values,
    }
    for split, values in metrics.items():
        result.update({split + "_" + name: value for name, value in values.items()})
    return result


def _run_forward_step(
    X_train,
    y_train,
    X_test,
    y_test,
    X_train_raw,
    X_test_raw,
    current_features,
    step,
    cv_folds,
    n_jobs=1,
    top_k=3,
    task="classification",
    algorithm="xgboost",
    validation_context=None,
    selection_objective=None,
):
    from modeling.sfs_objective import resolve_objective

    objective = selection_objective or resolve_objective(task, validation_context, {})[0]
    return _run_selection_step(
        X_train,
        y_train,
        X_test,
        y_test,
        current_features,
        step,
        cv_folds,
        n_jobs,
        top_k,
        task,
        algorithm,
        validation_context,
        "forward",
        objective,
    )


def _run_backward_step(
    X_train,
    y_train,
    X_test,
    y_test,
    X_train_raw,
    X_test_raw,
    current_features,
    step,
    cv_folds,
    n_jobs=1,
    top_k=3,
    task="classification",
    algorithm="xgboost",
    validation_context=None,
    selection_objective=None,
):
    from modeling.sfs_objective import resolve_objective

    objective = selection_objective or resolve_objective(task, validation_context, {})[0]
    return _run_selection_step(
        X_train,
        y_train,
        X_test,
        y_test,
        current_features,
        step,
        cv_folds,
        n_jobs,
        top_k,
        task,
        algorithm,
        validation_context,
        "backward",
        objective,
    )


def run_sfs_with_progress(
    X_train,
    y_train,
    X_test,
    y_test,
    X_train_raw,
    X_test_raw,
    methods,
    stopping_criteria,
    status_callback=None,
    cv_folds=3,
    initial_features=None,
    n_jobs=1,
    top_k=3,
    stop_flag=None,
    resume_state=None,
    task="classification",
    algorithm="xgboost",
    validation_context=None,
    execution_id=None,
    prediction_contract=None,
):
    """Native exploratory selection; unavailable evidence never means zero/success."""
    from modeling.sfs_objective import prepare_search, validate_resume, current_metrics, stopping_decision

    results = {"forward": [], "backward": [], "status": "running", "task": task, "algorithm": algorithm}
    completed = []
    try:
        X_train, X_test, objective, config, basis = prepare_search(
            X_train,
            y_train,
            X_test,
            y_test,
            task,
            algorithm,
            validation_context or {"task": task, "prediction_contract": prediction_contract or {}},
            stopping_criteria,
            cv_folds,
            top_k,
            methods,
            initial_features,
            execution_id,
            n_jobs,
        )
        criteria = config["metrics"]
        min_features, max_features = config["min_features"], config["max_features"]
        validate_resume(resume_state, basis)
        results.update(
            selection_objective=objective,
            stopping_criteria=config,
            resume_basis=basis,
            change_semantics="Positive percentage means improvement in the metric direction; zero baseline percentages are unavailable. Zero threshold disables its percentage gate.",
            baselines=(resume_state or {}).get("baselines", {}),
        )
        completed = (resume_state or {}).get("completed_steps", []).copy()

        def update(message, progress, state="running", metrics=None):
            if status_callback:
                status_callback(
                    {
                        "message": message,
                        "progress": progress,
                        "status": state,
                        "current_metrics": metrics or {},
                        "completed_steps": completed.copy(),
                        "selection_objective": objective,
                        "resume_basis": basis,
                    }
                )

        for method_index, mode in enumerate(methods):
            steps = (resume_state or {}).get(mode + "_results", []).copy()
            features = (
                (resume_state or {}).get("forward_selected_features", [])
                if mode == "forward"
                else (resume_state or {}).get("backward_current_features", list(X_train))
            )
            previous = (resume_state or {}).get(mode + "_previous_metrics")
            if steps:
                previous = current_metrics(steps[-1], criteria)
            count = max_features if mode == "forward" else max(0, len(X_train.columns) - min_features)
            start = len(steps) + 1
            update(
                f"Starting {mode} selection: {objective['primary_metric']} ({objective['direction']})",
                method_index / len(methods),
            )
            for step in range(start, count + 1):
                if stop_flag and stop_flag.get("stop_requested"):
                    results[mode] = steps
                    if mode == "backward":
                        results["backward_remaining_features"] = features
                    state = {
                        "completed_steps": completed.copy(),
                        "resume_basis": basis,
                        "baselines": results["baselines"],
                    }
                    for name in methods:
                        if results.get(name):
                            state[name + "_results"] = results[name]
                    state.update(
                        {
                            mode + "_results": steps,
                            mode + "_previous_metrics": previous,
                            "forward_selected_features" if mode == "forward" else "backward_current_features": features,
                        }
                    )
                    results.update(status="stopped", stopped_at={"direction": mode, "step": step}, resume_state=state)
                    update(
                        f"Selection stopped at {mode} step {step}",
                        (method_index + (step - 1) / count) / len(methods),
                        "stopped",
                    )
                    return results
                if mode == "backward" and previous is None:
                    baseline = _selection_cv(
                        X_train[features], y_train, task, algorithm, validation_context, cv_folds, objective
                    )
                    results["baselines"]["backward"] = baseline
                    previous = current_metrics({"cv_" + k: v for k, v in baseline["metrics"].items()}, criteria)
                function = _run_forward_step if mode == "forward" else _run_backward_step
                candidate = function(
                    X_train,
                    y_train,
                    X_test,
                    y_test,
                    X_train_raw,
                    X_test_raw,
                    features,
                    step,
                    cv_folds,
                    n_jobs=n_jobs,
                    top_k=top_k,
                    task=task,
                    algorithm=algorithm,
                    validation_context=validation_context,
                    selection_objective=objective,
                )
                if candidate is None:
                    break
                metrics = current_metrics(candidate, criteria)
                changes, reasons = stopping_decision(metrics, previous, criteria, mode)
                candidate.update(
                    pct_changes=changes,
                    change_semantics=results["change_semantics"],
                    search_basis_sha256=basis["sha256"],
                )
                if reasons:
                    results.setdefault("rejected_steps", []).append({**candidate, "rejection_reasons": reasons})
                    update(
                        f"{mode} step rejected: " + "; ".join(reasons),
                        (method_index + step / count) / len(methods),
                        metrics=previous,
                    )
                    break
                steps.append(candidate)
                features, previous = candidate["selected_features"], metrics
                completed.append(candidate)
                results[mode] = steps
                update(f"{mode} step {step} complete", (method_index + step / count) / len(methods), metrics=metrics)
            results[mode] = steps
            if mode == "backward":
                results["backward_remaining_features"] = features
        results["status"] = "completed"
        update("Feature selection completed; evidence is exploratory", 1.0, "completed")
    except Exception as error:
        results.update(status="error", error=str(error))
        if status_callback:
            status_callback(
                {
                    "status": "error",
                    "error": str(error),
                    "message": f"Feature selection failed: {error}",
                    "progress": 0.0,
                    "completed_steps": completed.copy(),
                }
            )
    return results
