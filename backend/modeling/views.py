from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from declaration.models import Declaration
import os
from django.conf import settings
import json
import math
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import accuracy_score, r2_score, roc_auc_score, average_precision_score
from joblib import dump as joblib_dump
import xgboost as xgb
import shap


@method_decorator(csrf_exempt, name='dispatch')
class ModelingStartView(APIView):
    """Accepts processed file info and signals modeling can start.

    Payload: { file_id: number, processed_file: string }
    Returns 200 with echo of inputs. Real training can be hooked here later.
    """

    def post(self, request, *args, **kwargs):
        file_id = request.data.get('file_id')
        processed_file = request.data.get('processed_file')
        algorithm = request.data.get('algorithm')  # optional, e.g., 'xgboost', 'lightgbm', 'catboost'

        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not processed_file:
            return Response({'error': 'processed_file is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate declaration exists
        try:
            Declaration.objects.get(pk=file_id)
        except Declaration.DoesNotExist:
            return Response({'error': f'Declaration with id {file_id} not found'}, status=status.HTTP_404_NOT_FOUND)

        # Validate processed file exists under MEDIA_ROOT
        full_path = os.path.join(settings.MEDIA_ROOT, processed_file) if not os.path.isabs(processed_file) else processed_file
        if not os.path.exists(full_path):
            return Response({'error': f'processed file not found: {processed_file}'}, status=status.HTTP_404_NOT_FOUND)

        # Minimal synchronous "training" stub: compute simple metrics and write a status file
        modeling_dir = os.path.join(settings.MEDIA_ROOT, 'modeling')
        os.makedirs(modeling_dir, exist_ok=True)
        status_path = os.path.join(modeling_dir, f'{file_id}_status.json')

        # mark running
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump({'status': 'running', 'file_id': file_id, 'processed_file': processed_file, 'algorithm': algorithm}, f)
        try:
            print(f"[ModelingStart] Starting training for file_id={file_id}, algo={algorithm}, xgb_version={getattr(xgb, '__version__', 'unknown')}")
        except Exception:
            pass

        # do quick metrics and modeling pass (XGBoost classification preferred)
        model_info = {}
        try:
            df = pd.read_csv(full_path) if full_path.lower().endswith('.csv') else pd.read_excel(full_path)
            metrics = {
                'rows': int(df.shape[0]),
                'features': int(df.shape[1]),
                'columns': list(map(str, df.columns[:50]))  # cap to 50 to keep response light
            }

            # Heuristically choose target
            target_col = None
            for candidate in ['Target', 'target', 'label', 'Label', 'y']:
                if candidate in df.columns:
                    target_col = candidate
                    break
            if target_col is None and len(df.columns) >= 2:
                target_col = df.columns[-1]

            if target_col is not None:
                # Prepare features/target
                y = df[target_col]
                # Keep a raw copy to preserve original NaNs for interactive SHAP visualization
                X_raw = df.drop(columns=[target_col])
                # Use only numeric features for simplicity
                X_raw = X_raw.select_dtypes(include=['number']).copy()
                # Drop columns with all NaNs
                X_raw = X_raw.dropna(axis=1, how='all')
                # Filled copy for modeling
                X = X_raw.fillna(X_raw.mean(numeric_only=True))

                # If no features remain, skip training
                if X.shape[1] >= 1 and len(y) >= 5:
                    # Determine problem type: classification if few unique classes
                    try:
                        n_unique = y.nunique(dropna=True)
                        is_classification = 2 <= n_unique <= 50
                    except Exception:
                        is_classification = True

                    if is_classification:
                        # Encode categories to integers (handles string labels)
                        y_encoded, y_categories = pd.factorize(y)
                        # Train/valid split with stratification for stability
                        X_train, X_valid, y_train, y_valid = train_test_split(
                            X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
                        )
                        # Raw (unfilled) view for the same validation rows
                        try:
                            X_valid_raw = X_raw.loc[X_valid.index]
                        except Exception:
                            X_valid_raw = X_valid.copy()

                        num_classes = int(len(np.unique(y_train)))
                        objective = 'binary:logistic' if num_classes == 2 else 'multi:softprob'
                        eval_metric = 'logloss' if num_classes == 2 else 'mlogloss'

                        # Build params compatible across versions
                        params = {
                            'objective': objective,
                            'tree_method': 'hist',
                            'eval_metric': eval_metric,

                            'eta': 0.05,
                            'max_depth': 4,
                            'min_child_weight': 2,
                            'gamma': 0.1,
                            'lambda': 1.5,
                            'alpha': 0.1,

                            'subsample': 0.8,
                            'colsample_bytree': 0.7,
                            'colsample_bylevel': 0.8,
                            'colsample_bynode': 0.8,

                            'max_bin': 256,
                            'sampling_method': 'uniform',

                            'verbosity': 0,
                            'seed': 42,
                        }
                        if num_classes > 2:
                            params['num_class'] = num_classes

                        # DMatrix with feature names for consistent importances/SHAP
                        feature_names = list(map(str, X.columns.tolist()))
                        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_names)
                        dvalid = xgb.DMatrix(X_valid, label=y_valid, feature_names=feature_names)

                        booster = xgb.train(
                            params,
                            dtrain,
                            num_boost_round=500,
                            evals=[(dvalid, 'valid')],
                            early_stopping_rounds=50,
                            verbose_eval=False,
                        )

                        # Quality metric on validation
                        try:
                            # Predict with best iteration (prefer iteration_range; avoid ntree_limit=0 in xgboost>=2)
                            if hasattr(booster, 'best_iteration') and booster.best_iteration is not None and booster.best_iteration >= 0:
                                try:
                                    yhat = booster.predict(dvalid, iteration_range=(0, int(booster.best_iteration) + 1))
                                except Exception:
                                    yhat = booster.predict(dvalid)
                            elif hasattr(booster, 'best_ntree_limit') and booster.best_ntree_limit is not None and int(booster.best_ntree_limit) > 0:
                                yhat = booster.predict(dvalid, ntree_limit=int(booster.best_ntree_limit))
                            else:
                                yhat = booster.predict(dvalid)

                            if num_classes == 2:
                                # yhat shape: (n_samples,) probabilities for class 1
                                y_prob = yhat.ravel()
                                valid_auc = float(roc_auc_score(y_valid, y_prob))
                            else:
                                # multiclass prob matrix
                                valid_auc = None
                        except Exception:
                            valid_auc = None

                        # Built-in gain importances
                        raw_gain = booster.get_score(importance_type='gain') or {}
                        # Map f0.. to column names
                        feat_names = feature_names
                        def _fname_to_col(fn: str) -> str:
                            if fn.startswith('f') and fn[1:].isdigit():
                                idx = int(fn[1:])
                                if 0 <= idx < len(feat_names):
                                    return feat_names[idx]
                            return fn
                        gain_items = sorted(
                            (( _fname_to_col(k), float(v) ) for k, v in raw_gain.items()),
                            key=lambda kv: kv[1], reverse=True
                        )
                        gain_importance = [ {'feature': k, 'score': v} for k, v in gain_items ]

                        # SHAP mean |impact| and compact beeswarm payload
                        try:
                            explainer = shap.TreeExplainer(booster, feature_perturbation='interventional')
                            # limit to at most 5000 rows for performance
                            Xv = X_valid
                            Xv_raw = X_valid_raw
                            if Xv.shape[0] > 5000:
                                Xv = Xv.sample(5000, random_state=42)
                            shap_vals = explainer.shap_values(Xv)
                            if isinstance(shap_vals, list):
                                # multiclass: average mean |shap| across classes
                                mean_abs = np.mean([ np.mean(np.abs(sv), axis=0) for sv in shap_vals ], axis=0)
                            else:
                                # binary/regression shape: (n_samples, n_features)
                                mean_abs = np.mean(np.abs(shap_vals), axis=0)
                            shap_items = sorted(
                                ((feat_names[i], float(mean_abs[i])) for i in range(len(feat_names))),
                                key=lambda kv: kv[1], reverse=True
                            )
                            shap_importance = [ {'feature': k, 'score': v} for k, v in shap_items ]
                            # Selected features (impact > 0) with descriptions
                            try:
                                from declaration.models import DataDictionary
                                selected_features = []
                                for fname, val in shap_items:
                                    if val > 0:
                                        desc = DataDictionary.get_description(file_id, fname) or ''
                                        selected_features.append({'feature': fname, 'description': desc, 'impact': float(val)})
                            except Exception:
                                selected_features = [{'feature': fname, 'description': '', 'impact': float(val)} for fname, val in shap_items if val > 0]
                            # Generate beeswarm image (static) and prepare interactive payload (compact)
                            try:
                                import matplotlib
                                matplotlib.use('Agg')
                                import matplotlib.pyplot as plt
                                import io, base64
                                # Ensure 2D shap matrix (n_samples, n_features)
                                shap_matrix = None
                                if isinstance(shap_vals, list):
                                    try:
                                        # average across classes to get a single 2D matrix preserving sign
                                        shap_matrix = np.mean(np.stack(shap_vals, axis=0), axis=0)
                                    except Exception:
                                        shap_matrix = shap_vals[0]
                                else:
                                    shap_matrix = shap_vals
                                # Draw beeswarm and save the current figure
                                shap.summary_plot(shap_matrix, Xv, plot_type='dot', show=False, max_display=40)
                                fig = plt.gcf()
                                buf = io.BytesIO()
                                fig.tight_layout()
                                fig.savefig(buf, format='png', dpi=150)
                                plt.close(fig)
                                beeswarm_png = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8')
                            except Exception as e:
                                try:
                                    print(f"[ModelingStart] Beeswarm generation failed: {e}")
                                except Exception:
                                    pass
                                beeswarm_png = None

                            # Interactive beeswarm compact payload (top_k features; per-sample shap and feature values)
                            try:
                                # Include all features with positive mean |impact|
                                order_sorted = np.argsort(-mean_abs)
                                order_idx = np.array([i for i in order_sorted if mean_abs[i] > 0])
                                # Cap rows for transport size
                                Xv_compact = Xv
                                Xv_raw_compact = Xv_raw
                                max_rows = 2000
                                if Xv_compact.shape[0] > max_rows:
                                    Xv_compact = Xv_compact.sample(max_rows, random_state=42)
                                    # keep raw values aligned to the same subset
                                    try:
                                        Xv_raw_compact = Xv_raw.loc[Xv_compact.index]
                                    except Exception:
                                        Xv_raw_compact = Xv_compact.copy()
                                # Index alignment for shap_matrix when we sampled rows above
                                if shap_matrix.shape[0] != Xv_compact.shape[0]:
                                    # Recompute shap on the compact subset to stay aligned
                                    dsub = xgb.DMatrix(Xv_compact.values, feature_names=feature_names)
                                    shap_sub = explainer.shap_values(Xv_compact)
                                    if isinstance(shap_sub, list):
                                        try:
                                            shap_matrix_compact = np.mean(np.stack(shap_sub, axis=0), axis=0)
                                        except Exception:
                                            shap_matrix_compact = shap_sub[0]
                                    else:
                                        shap_matrix_compact = shap_sub
                                else:
                                    shap_matrix_compact = shap_matrix
                                features_ordered = [feat_names[i] for i in order_idx]
                                # Build arrays per feature: shap values and raw feature values
                                feature_values_list = []
                                for i in order_idx:
                                    s = pd.to_numeric(Xv_raw_compact.iloc[:, i], errors='coerce')
                                    # convert NaN -> None so JSON renders as null
                                    s = s.where(s.notna(), None).astype(object)
                                    feature_values_list.append(s.tolist())
                                # sanitize shap values (NaN/Inf -> None) for JSON
                                shap_values_list = []
                                for i in order_idx:
                                    col = shap_matrix_compact[:, i]
                                    safe_col = [ float(x) if np.isfinite(x) else None for x in col ]
                                    shap_values_list.append(safe_col)
                                # Collect metadata per feature: description, PSI/CSI, mean_abs_impact
                                # Metadata order must match features_ordered
                                feature_metadata = []
                                try:
                                    from declaration.models import DataDictionary
                                    # Load data quality summary from JSON saved during preprocessing
                                    dq_summary = None
                                    try:
                                        datq_json_path = os.path.join(settings.MEDIA_ROOT, 'data_quality', f'{file_id}_datq_summary.json')
                                        if os.path.exists(datq_json_path):
                                            with open(datq_json_path, 'r', encoding='utf-8') as f:
                                                datq_records = json.load(f)
                                            # Build dict: variable_name -> {PSI, CSI, ...}
                                            dq_summary = {rec.get('Variable', ''): rec for rec in datq_records if rec.get('Variable')}
                                    except Exception:
                                        pass
                                    for i in order_idx:
                                        fname = feat_names[i]
                                        desc = DataDictionary.get_description(file_id, fname) or ''
                                        # Use mean_abs for consistency with selected_features table
                                        impact_abs = float(mean_abs[i])
                                        # Try to get PSI or CSI from data quality summary
                                        psi_val = None
                                        csi_val = None
                                        if dq_summary and fname in dq_summary:
                                            row = dq_summary[fname]
                                            psi_val = row.get('PSI', None)
                                            csi_val = row.get('CSI', None)
                                        feature_metadata.append({
                                            'feature': fname,
                                            'description': desc,
                                            'impact': impact_abs,
                                            'psi': psi_val,
                                            'csi': csi_val
                                        })
                                except Exception as meta_err:
                                    try:
                                        print(f"[ModelingStart] Feature metadata collection failed: {meta_err}")
                                    except:
                                        pass
                                    # Fallback: minimal metadata
                                    for i in order_idx:
                                        fname = feat_names[i]
                                        feature_metadata.append({
                                            'feature': fname,
                                            'description': '',
                                            'impact': float(mean_abs[i]),
                                            'psi': None,
                                            'csi': None
                                        })
                                shap_beeswarm = {
                                    'features': features_ordered,
                                    'shap_values': shap_values_list,
                                    'feature_values': feature_values_list,
                                    'metadata': feature_metadata,
                                }
                            except Exception as e:
                                try:
                                    print(f"[ModelingStart] SHAP interactive payload failed: {e}")
                                except Exception:
                                    pass
                                shap_beeswarm = None
                        except Exception as e:
                            shap_importance = []
                            selected_features = []
                            beeswarm_png = None
                            shap_beeswarm = None

                        # Cross-Validation metrics (ROC-AUC, PR-AUC) + curve points
                        cv_details = []
                        try:
                            from sklearn.metrics import roc_curve, precision_recall_curve
                            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
                            # grids for consistent interpolation across folds
                            roc_fpr_grid = np.linspace(0.0, 1.0, 101)
                            pr_recall_grid = np.linspace(0.0, 1.0, 101)
                            tpr_fold_list = []
                            prec_fold_list = []
                            pr_raw_folds = []
                            y_all_list = []
                            p_all_list = []
                            base_pr_list = []
                            for tr_idx, va_idx in skf.split(X.values, y_encoded):
                                X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
                                y_tr, y_va = y_encoded[tr_idx], y_encoded[va_idx]
                                dtr = xgb.DMatrix(X_tr, label=y_tr, feature_names=feature_names)
                                dva = xgb.DMatrix(X_va, label=y_va, feature_names=feature_names)
                                bst = xgb.train(params, dtr, num_boost_round=500, evals=[(dva, 'valid')], early_stopping_rounds=50, verbose_eval=False)
                                # predict proba of positive class
                                try:
                                    if hasattr(bst, 'best_iteration') and bst.best_iteration is not None and bst.best_iteration >= 0:
                                        try:
                                            p = bst.predict(dva, iteration_range=(0, int(bst.best_iteration) + 1)).ravel()
                                        except Exception:
                                            p = bst.predict(dva).ravel()
                                    elif hasattr(bst, 'best_ntree_limit') and bst.best_ntree_limit is not None and int(bst.best_ntree_limit) > 0:
                                        p = bst.predict(dva, ntree_limit=int(bst.best_ntree_limit)).ravel()
                                    else:
                                        p = bst.predict(dva).ravel()
                                except Exception:
                                    p = bst.predict(dva).ravel()
                                # AUCs
                                roc = None
                                pr = None
                                try:
                                    roc = float(roc_auc_score(y_va, p))
                                except Exception:
                                    pass
                                try:
                                    pr = float(average_precision_score(y_va, p))
                                except Exception:
                                    pass
                                cv_details.append({'roc_auc': roc, 'pr_auc': pr, 'best_iteration': int(getattr(bst, 'best_iteration', getattr(bst, 'best_ntree_limit', 0)))})
                                # ROC/PR curves on fixed grids
                                try:
                                    fpr, tpr, _ = roc_curve(y_va, p)
                                    tpr_interp = np.interp(roc_fpr_grid, fpr, tpr)
                                    tpr_interp[0] = 0.0
                                    tpr_interp[-1] = 1.0
                                    tpr_fold_list.append(tpr_interp)
                                except Exception:
                                    pass
                                try:
                                    precision, recall, _ = precision_recall_curve(y_va, p)
                                    # keep raw curve for plotting
                                    try:
                                        pr_raw_folds.append({'precision': precision.tolist(), 'recall': recall.tolist(), 'auc': pr})
                                    except Exception:
                                        pass
                                    # Step-wise (previous value) interpolation on a fixed recall grid
                                    # For each r in grid, take precision at last recall <= r
                                    idxs = np.searchsorted(recall, pr_recall_grid, side='right') - 1
                                    idxs = np.clip(idxs, 0, len(precision) - 1)
                                    prec_interp = precision[idxs]
                                    prec_fold_list.append(prec_interp)
                                except Exception:
                                    pass
                                # Baseline (no-skill) level equals positive rate in the validation fold
                                base_pr_list.append(float(np.mean(y_va)))
                                # collect for micro-averaged PR
                                try:
                                    y_all_list.append(y_va)
                                    p_all_list.append(p)
                                except Exception:
                                    pass
                            # aggregate
                            roc_vals = [d['roc_auc'] for d in cv_details if d['roc_auc'] is not None]
                            pr_vals = [d['pr_auc'] for d in cv_details if d['pr_auc'] is not None]
                            mean_tpr = list(np.mean(np.vstack(tpr_fold_list), axis=0)) if tpr_fold_list else None
                            std_tpr = list(np.std(np.vstack(tpr_fold_list), axis=0)) if tpr_fold_list else None
                            mean_prec = list(np.mean(np.vstack(prec_fold_list), axis=0)) if prec_fold_list else None
                            std_prec = list(np.std(np.vstack(prec_fold_list), axis=0)) if prec_fold_list else None
                            # micro-averaged PR across all validation predictions
                            try:
                                if y_all_list and p_all_list:
                                    y_all = np.concatenate(y_all_list)
                                    p_all = np.concatenate(p_all_list)
                                    micro_prec, micro_recall, _ = precision_recall_curve(y_all, p_all)
                                    ap_micro = float(average_precision_score(y_all, p_all))
                                    pr_curve_micro = {
                                        'recall': micro_recall.tolist(),
                                        'precision': micro_prec.tolist(),
                                        'ap': ap_micro,
                                    }
                                else:
                                    pr_curve_micro = None
                            except Exception:
                                pr_curve_micro = None

                            cv_summary = {
                                'n_splits': 5,
                                'roc_auc_mean': float(np.mean(roc_vals)) if roc_vals else None,
                                'roc_auc_std': float(np.std(roc_vals)) if roc_vals else None,
                                'pr_auc_mean': float(np.mean(pr_vals)) if pr_vals else None,
                                'pr_auc_std': float(np.std(pr_vals)) if pr_vals else None,
                                'folds': cv_details,
                                'roc_curve': {
                                    'fpr': list(roc_fpr_grid),
                                    'mean_tpr': mean_tpr,
                                    'std_tpr': std_tpr,
                                    'fold_tpr': [list(arr) for arr in tpr_fold_list]
                                } if tpr_fold_list else None,
                                'pr_curve': {
                                    'recall': list(pr_recall_grid),
                                    'mean_precision': mean_prec,
                                    'std_precision': std_prec,
                                    'fold_precision': [list(arr) for arr in prec_fold_list],
                                    'folds_raw': pr_raw_folds,
                                    'baseline': float(np.mean(base_pr_list)) if base_pr_list else None,
                                } if prec_fold_list else None,
                                'pr_curve_micro': pr_curve_micro,
                            }
                        except Exception:
                            cv_summary = None

                        # Save model
                        models_dir = os.path.join(settings.MEDIA_ROOT, 'models')
                        os.makedirs(models_dir, exist_ok=True)
                        model_path = os.path.join(models_dir, f'{file_id}_xgb_classifier.json')
                        booster.save_model(model_path)

                        model_info = {
                            'model_type': 'xgboost_classifier',
                            'valid_auc': valid_auc,
                            'best_iteration': int(getattr(booster, 'best_iteration', getattr(booster, 'best_ntree_limit', 0))),
                            'model_path': os.path.relpath(model_path, settings.MEDIA_ROOT),
                            'feature_count': int(X.shape[1]),
                            'importances': {
                                'gain': gain_importance,
                                'shap_mean_abs': shap_importance,
                            },
                            'selected_features': selected_features,
                            'cv': cv_summary,
                            'beeswarm_png': beeswarm_png,
                            'shap_beeswarm': shap_beeswarm,
                        }
                    else:
                        # Regression fallback as before
                        y_num = pd.to_numeric(y, errors='coerce')
                        if y_num.notna().sum() >= 5:
                            y_num = y_num.fillna(y_num.mean())
                            X_train, X_test, y_train, y_test = train_test_split(X, y_num, test_size=0.2, random_state=42)
                            reg = LinearRegression()
                            reg.fit(X_train, y_train)
                            y_pred = reg.predict(X_test)
                            score = float(r2_score(y_test, y_pred))
                            model_type = 'linear_regression'
                            models_dir = os.path.join(settings.MEDIA_ROOT, 'models')
                            os.makedirs(models_dir, exist_ok=True)
                            model_path = os.path.join(models_dir, f'{file_id}_linreg.joblib')
                            joblib_dump(reg, model_path)
                        else:
                            score = None
                            model_type = 'linear_regression'
                            model_path = None

                        model_info = {
                            'model_type': model_type,
                            'score': score,
                            'model_path': os.path.relpath(model_path, settings.MEDIA_ROOT) if model_path else None,
                            'feature_count': int(X.shape[1])
                        }
                else:
                    model_info = {'warning': 'Insufficient features or rows to train'}
            else:
                model_info = {'warning': 'No target column detected'}
        except Exception as e:
            err_msg = str(e)
            metrics = {'error': err_msg}
            model_info = {'error': err_msg}
            try:
                print(f"[ModelingStart] ERROR: {err_msg}")
            except Exception:
                pass

        # Helper to sanitize payloads for JSON (replace NaN/Inf with None recursively)
        def _sanitize_json(o):
            try:
                import numpy as np
                if isinstance(o, (float, np.floating)):
                    return float(o) if math.isfinite(o) else None
                if isinstance(o, (np.integer,)):
                    return int(o)
                if isinstance(o, (np.bool_,)):
                    return bool(o)
                if isinstance(o, (np.ndarray,)):
                    return [_sanitize_json(x) for x in o.tolist()]
            except Exception:
                pass
            if isinstance(o, list):
                return [_sanitize_json(x) for x in o]
            if isinstance(o, tuple):
                return [_sanitize_json(x) for x in o]
            if isinstance(o, dict):
                return {k: _sanitize_json(v) for k, v in o.items()}
            if isinstance(o, float):
                return o if math.isfinite(o) else None
            return o

        # mark completed
        # attach algorithm to model info if provided
        if algorithm:
            model_info['requested_algorithm'] = algorithm

        result_payload = {
            'status': 'ok',
            'job_status': 'completed',
            'file_id': file_id,
            'processed_file': processed_file,
            'metrics': metrics,
            'model': model_info,
            'algorithm': algorithm
        }
        safe_payload = _sanitize_json(result_payload)

        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(safe_payload, f)

        return Response(safe_payload, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class ModelingStatusView(APIView):
    """Returns current modeling status and metrics for a file id."""

    def get(self, request, file_id: int, *args, **kwargs):
        modeling_dir = os.path.join(settings.MEDIA_ROOT, 'modeling')
        status_path = os.path.join(modeling_dir, f'{file_id}_status.json')
        if not os.path.exists(status_path):
            return Response({'status': 'unknown', 'file_id': file_id}, status=status.HTTP_200_OK)
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
