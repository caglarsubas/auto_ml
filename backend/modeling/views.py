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
                        # Encode binary targets to 0/1 ensuring 1 == positive class, else fallback to factorize
                        try:
                            y_num = pd.to_numeric(y, errors='coerce')
                            uniq = y_num.dropna().unique().tolist()
                            uniq_int = sorted({int(v) for v in uniq if float(v) in (0.0, 1.0)})
                            if len(uniq_int) == 2 and set(uniq_int) == {0, 1}:
                                y_encoded = y_num.fillna(0).astype(int)
                            else:
                                raise ValueError('not binary 0/1')
                        except Exception:
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
                                try:
                                    Xv_raw = Xv_raw.loc[Xv.index]
                                except Exception:
                                    Xv_raw = Xv.copy()
                            shap_vals = explainer.shap_values(Xv)
                            if isinstance(shap_vals, list):
                                try:
                                    shap_matrix = np.mean(np.stack(shap_vals, axis=0), axis=0)
                                except Exception:
                                    shap_matrix = shap_vals[0]
                            else:
                                shap_matrix = shap_vals
                            mean_abs = np.mean(np.abs(shap_matrix), axis=0)
                            mean_signed = np.mean(shap_matrix, axis=0)
                            shap_details: list[dict[str, object]] = []
                            for idx, fname in enumerate(feat_names):
                                mean_abs_val = float(mean_abs[idx]) if np.isfinite(mean_abs[idx]) else 0.0
                                signed_mean_val = float(mean_signed[idx]) if np.isfinite(mean_signed[idx]) else 0.0
                                # Direction from SHAP behavior vs feature value:
                                # 1) Prefer robust top-vs-bottom quantile mean SHAP difference
                                # 2) Fallback to Spearman correlation
                                # 3) Fallback to signed mean
                                direction = 0.0
                                try:
                                    fv = pd.to_numeric(Xv_raw.iloc[:, idx], errors='coerce').to_numpy()
                                except Exception:
                                    fv = Xv.iloc[:, idx].to_numpy() if hasattr(Xv, 'iloc') else np.asarray([])
                                sv = shap_matrix[:, idx] if shap_matrix.ndim == 2 else np.asarray([])
                                if fv.size and sv.size and fv.shape[0] == sv.shape[0]:
                                    mask = np.isfinite(fv) & np.isfinite(sv)
                                    if np.sum(mask) > 2:
                                        fv_m = fv[mask]
                                        sv_m = sv[mask]
                                        try:
                                            q_low = np.nanpercentile(fv_m, 25)
                                            q_high = np.nanpercentile(fv_m, 75)
                                            top = sv_m[fv_m >= q_high]
                                            bot = sv_m[fv_m <= q_low]
                                            if top.size >= 5 and bot.size >= 5:
                                                diff = float(np.nanmean(top) - np.nanmean(bot))
                                                if np.isfinite(diff) and diff != 0.0:
                                                    direction = float(np.sign(diff))
                                        except Exception:
                                            pass
                                        # Fallback to Spearman if still undecided
                                        if direction == 0.0:
                                            fv_rank = pd.Series(fv_m).rank(method='average').to_numpy()
                                            sv_rank = pd.Series(sv_m).rank(method='average').to_numpy()
                                            corr = np.corrcoef(fv_rank, sv_rank)[0, 1]
                                            if not np.isfinite(corr):
                                                corr = np.corrcoef(fv_m, sv_m)[0, 1]
                                            if np.isfinite(corr) and corr != 0.0:
                                                direction = float(np.sign(corr))
                                if direction == 0.0 and signed_mean_val != 0.0:
                                    direction = float(np.sign(signed_mean_val))
                                if direction == 0.0 and mean_abs_val > 0.0:
                                    direction = 1.0
                                shap_details.append({
                                    'index': idx,
                                    'feature': fname,
                                    'mean_abs': mean_abs_val,
                                    'direction': direction,
                                    'signed_mean': signed_mean_val,
                                })
                            shap_details_sorted = sorted(shap_details, key=lambda item: item['mean_abs'], reverse=True)
                            shap_importance = [
                                {'feature': item['feature'], 'score': item['mean_abs']}
                                for item in shap_details_sorted
                                if item['mean_abs'] > 0
                            ]

                            try:
                                from declaration.models import DataDictionary
                                selected_features = []
                                for item in shap_details_sorted:
                                    if item['mean_abs'] <= 0:
                                        continue
                                    desc = DataDictionary.get_description(file_id, item['feature']) or ''
                                    selected_features.append({
                                        'feature': item['feature'],
                                        'description': desc,
                                        'impact': item['mean_abs'],
                                        'signed_impact': item['mean_abs'] * item['direction'],
                                        'signed_mean': item['signed_mean'],
                                    })
                            except Exception:
                                selected_features = []
                                for item in shap_details_sorted:
                                    if item['mean_abs'] <= 0:
                                        continue
                                    selected_features.append({
                                        'feature': item['feature'],
                                        'description': '',
                                        'impact': item['mean_abs'],
                                        'signed_impact': item['mean_abs'] * item['direction'],
                                        'signed_mean': item['signed_mean'],
                                    })

                            try:
                                import matplotlib
                                matplotlib.use('Agg')
                                import matplotlib.pyplot as plt
                                import io, base64
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
                                # Build beeswarm payload
                                shap_beeswarm = {
                                    'features': features_ordered,
                                    'shap_values': shap_values_list,
                                    'feature_values': feature_values_list,
                                    'metadata': feature_metadata,
                                }
                                # Re-derive direction using the exact compact data used in the UI
                                try:
                                    direction_map = {}
                                    for i in order_idx:
                                        try:
                                            fv = pd.to_numeric(Xv_raw_compact.iloc[:, i], errors='coerce').to_numpy()
                                        except Exception:
                                            fv = Xv_compact.iloc[:, i].to_numpy()
                                        sv = shap_matrix_compact[:, i]
                                        mask = np.isfinite(fv) & np.isfinite(sv)
                                        dir_val = 0.0
                                        if np.sum(mask) > 2:
                                            fv_m = fv[mask]
                                            sv_m = sv[mask]
                                            try:
                                                ql = np.nanpercentile(fv_m, 25)
                                                qh = np.nanpercentile(fv_m, 75)
                                                top = sv_m[fv_m >= qh]
                                                bot = sv_m[fv_m <= ql]
                                                if top.size >= 5 and bot.size >= 5:
                                                    d = float(np.nanmean(top) - np.nanmean(bot))
                                                    if np.isfinite(d) and d != 0.0:
                                                        dir_val = float(np.sign(d))
                                            except Exception:
                                                pass
                                            if dir_val == 0.0:
                                                fv_rank = pd.Series(fv_m).rank(method='average').to_numpy()
                                                sv_rank = pd.Series(sv_m).rank(method='average').to_numpy()
                                                corr = np.corrcoef(fv_rank, sv_rank)[0, 1]
                                                if not np.isfinite(corr):
                                                    corr = np.corrcoef(fv_m, sv_m)[0, 1]
                                                if np.isfinite(corr) and corr != 0.0:
                                                    dir_val = float(np.sign(corr))
                                        direction_map[feat_names[i]] = dir_val
                                    # Override signed_impact in selected_features when available
                                    try:
                                        for row in selected_features:
                                            fname = row.get('feature')
                                            if fname in direction_map:
                                                row['signed_impact'] = float(row.get('impact', 0.0)) * float(direction_map[fname])
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
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


@method_decorator(csrf_exempt, name='dispatch')
class FeatureExplainabilityView(APIView):
    """Returns SHAP explainability data for a single feature: beeswarm and partial dependence.
    
    Payload: { file_id: number, feature_name: string, processed_file?: string, n_samples?: number }
    """

    def post(self, request, *args, **kwargs):
        file_id = request.data.get('file_id')
        feature_name = request.data.get('feature_name')
        processed_file = request.data.get('processed_file')
        n_samples = request.data.get('n_samples', 500)

        print(f"[FeatureExplainability] Request for file_id={file_id}, feature={feature_name}")

        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not feature_name:
            return Response({'error': 'feature_name is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Load model
            models_dir = os.path.join(settings.MEDIA_ROOT, 'models')
            model_path = os.path.join(models_dir, f'{file_id}_xgb_classifier.json')
            if not os.path.exists(model_path):
                return Response({'error': 'Model not found. Please train a model first.'}, status=status.HTTP_404_NOT_FOUND)
            
            booster = xgb.Booster()
            booster.load_model(model_path)

            # Load processed data
            if processed_file:
                full_path = os.path.join(settings.MEDIA_ROOT, processed_file) if not os.path.isabs(processed_file) else processed_file
            else:
                # Try to find from status
                modeling_dir = os.path.join(settings.MEDIA_ROOT, 'modeling')
                status_path = os.path.join(modeling_dir, f'{file_id}_status.json')
                if os.path.exists(status_path):
                    with open(status_path, 'r', encoding='utf-8') as f:
                        status_data = json.load(f)
                    processed_file = status_data.get('processed_file')
                    if processed_file:
                        full_path = os.path.join(settings.MEDIA_ROOT, processed_file) if not os.path.isabs(processed_file) else processed_file
                    else:
                        return Response({'error': 'processed_file not found in modeling status'}, status=status.HTTP_404_NOT_FOUND)
                else:
                    return Response({'error': 'processed_file required'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not os.path.exists(full_path):
                return Response({'error': f'processed file not found: {processed_file}'}, status=status.HTTP_404_NOT_FOUND)

            # Load data
            df = pd.read_csv(full_path) if full_path.lower().endswith('.csv') else pd.read_excel(full_path)
            
            # Heuristically choose target
            target_col = None
            for candidate in ['Target', 'target', 'label', 'Label', 'y']:
                if candidate in df.columns:
                    target_col = candidate
                    break
            if target_col is None and len(df.columns) >= 2:
                target_col = df.columns[-1]
            
            if target_col is None or target_col not in df.columns:
                return Response({'error': 'Target column not found'}, status=status.HTTP_400_BAD_REQUEST)

            y = df[target_col]
            X_raw = df.drop(columns=[target_col])
            X_raw = X_raw.select_dtypes(include=['number']).copy()
            X_raw = X_raw.dropna(axis=1, how='all')
            X = X_raw.fillna(X_raw.mean(numeric_only=True))

            # Check if feature was used in the trained model FIRST (before checking data)
            # This ensures we give the correct message for features excluded during modeling
            model_features = booster.feature_names
            print(f"[FeatureExplainability] Model has {len(model_features) if model_features else 0} features")
            print(f"[FeatureExplainability] Feature '{feature_name}' in model: {feature_name in model_features if model_features else 'N/A'}")
            if model_features:
                print(f"[FeatureExplainability] Model features: {model_features[:10]}")  # First 10
            
            if model_features and feature_name not in model_features:
                print(f"[FeatureExplainability] Feature '{feature_name}' NOT in model - returning feature_not_in_model response")
                return Response({
                    'error': f'Feature "{feature_name}" was not selected during the modeling phase.',
                    'reason': 'feature_not_in_model',
                    'detail': 'This feature was excluded from the model, likely due to zero or very low predictive impact. Explainability analysis is only available for features used in the trained model.'
                }, status=status.HTTP_404_NOT_FOUND)

            # Only check if feature exists in data if it's in the model
            # (If it's in the model but not in current data, that's a real error)
            if feature_name not in X.columns:
                return Response({
                    'error': f'Feature {feature_name} not found in processed data',
                    'reason': 'feature_not_in_data',
                    'detail': 'This feature is in the model but not available in the current processed dataset. Please ensure preprocessing was completed correctly.'
                }, status=status.HTTP_404_NOT_FOUND)

            # Sample for performance
            if X.shape[0] > n_samples:
                sample_idx = X.sample(n_samples, random_state=42).index
                X_sampled = X.loc[sample_idx]
                X_raw_sampled = X_raw.loc[sample_idx]
            else:
                X_sampled = X
                X_raw_sampled = X_raw

            # Compute SHAP values
            feature_names = list(map(str, X.columns.tolist()))
            dmatrix = xgb.DMatrix(X_sampled, feature_names=feature_names)
            explainer = shap.TreeExplainer(booster, feature_perturbation='interventional')
            shap_vals = explainer.shap_values(X_sampled)
            if isinstance(shap_vals, list):
                try:
                    shap_matrix = np.mean(np.stack(shap_vals, axis=0), axis=0)
                except Exception:
                    shap_matrix = shap_vals[0]
            else:
                shap_matrix = shap_vals

            # Get feature index
            feat_idx = list(X.columns).index(feature_name)
            
            # Beeswarm data for this feature
            shap_values_feature = shap_matrix[:, feat_idx].tolist()
            feature_values_raw = X_raw_sampled[feature_name].tolist()
            feature_values_filled = X_sampled[feature_name].tolist()

            # Partial dependence plot (SHAP-aligned: use raw output margin)
            # Compute base value (expected value of model output on the dataset)
            dmatrix_base = xgb.DMatrix(X_sampled, feature_names=feature_names)
            base_preds = booster.predict(dmatrix_base, output_margin=True)
            base_value = float(np.mean(base_preds))
            
            # Create a grid of values for this feature
            # Use 0.5th-99.5th percentile to capture more distribution (not cut off important regions)
            feat_vals = X_sampled[feature_name].values
            feat_vals_clean = feat_vals[~np.isnan(feat_vals)]
            
            if len(feat_vals_clean) > 0:
                feat_min, feat_max = np.percentile(feat_vals_clean, [0.5, 99.5])
            else:
                feat_min, feat_max = 0, 1
                
            if feat_min == feat_max:
                feat_min = np.nanmin(feat_vals)
                feat_max = np.nanmax(feat_vals)
            if feat_min == feat_max:
                feat_min -= 1
                feat_max += 1
            
            grid_size = 50
            grid = np.linspace(feat_min, feat_max, grid_size)
            
            # Create histogram for feature distribution (for background visualization)
            hist_bins = 30
            hist_counts, hist_edges = np.histogram(feat_vals_clean, bins=hist_bins, range=(feat_min, feat_max))
            hist_centers = (hist_edges[:-1] + hist_edges[1:]) / 2
            
            # For each grid point, set feature to that value and predict (using raw margin output)
            X_pd = X_sampled.copy()
            ice_curves = []
            pdp_mean = []
            
            for grid_val in grid:
                X_pd[feature_name] = grid_val
                dmatrix_pd = xgb.DMatrix(X_pd, feature_names=feature_names)
                # Use output_margin=True to get raw predictions (before sigmoid)
                # This aligns with SHAP values which are in logit space
                preds_margin = booster.predict(dmatrix_pd, output_margin=True)
                
                ice_curves.append(preds_margin.tolist())
                pdp_mean.append(float(np.mean(preds_margin)))
            
            # Transpose ice_curves for easier consumption (each row is one sample's curve)
            ice_curves_transposed = np.array(ice_curves).T.tolist()

            # Generate static SHAP partial dependence plot
            shap_pdp_image_base64 = None
            try:
                import matplotlib
                matplotlib.use('Agg')  # Non-interactive backend
                import matplotlib.pyplot as plt
                import io
                import base64
                
                # Create wrapper function for model prediction that SHAP expects
                def model_predict(data_array):
                    """Wrapper for XGBoost predict that returns raw margin output"""
                    if isinstance(data_array, np.ndarray):
                        # Convert to DataFrame with proper column names
                        data_df = pd.DataFrame(data_array, columns=feature_names)
                    else:
                        data_df = data_array
                    dmat = xgb.DMatrix(data_df, feature_names=feature_names)
                    return booster.predict(dmat, output_margin=True)
                
                # Create figure for SHAP's partial_dependence_plot
                fig, ax = plt.subplots(figsize=(8, 5))
                
                # Use SHAP's built-in partial_dependence_plot
                # Note: We'll show the PDP without the red SHAP overlay line to avoid compatibility issues
                # The main purpose is to show the official SHAP PDP curve for comparison
                shap.partial_dependence_plot(
                    feature_name,
                    model_predict,
                    X_sampled,
                    model_expected_value=True,
                    feature_expected_value=True,
                    show=False,
                    ice=False,
                    ax=ax
                )
                
                plt.tight_layout()
                
                # Save to base64
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
                buf.seek(0)
                img_base64 = base64.b64encode(buf.read()).decode('utf-8')
                shap_pdp_image_base64 = f'data:image/png;base64,{img_base64}'
                plt.close(fig)
                buf.close()
            except Exception as plot_err:
                print(f"[FeatureExplainability] SHAP PDP plot generation failed: {plot_err}")
                import traceback
                traceback.print_exc()

            # Compute expected feature value (mean of feature)
            expected_feature_value = float(np.nanmean(X_sampled[feature_name].values))
            
            # Clean up NaN values for JSON serialization
            # Replace NaN with None in lists (JSON null)
            def clean_for_json(value):
                """Convert NaN/Inf to None for JSON compliance"""
                if isinstance(value, (list, np.ndarray)):
                    return [clean_for_json(v) for v in value]
                elif isinstance(value, float):
                    if np.isnan(value) or np.isinf(value):
                        return None
                    return value
                return value
            
            # Clean all data structures
            grid_clean = clean_for_json(grid.tolist())
            pdp_mean_clean = clean_for_json(pdp_mean)
            ice_curves_clean = clean_for_json(ice_curves_transposed[:100])
            hist_centers_clean = clean_for_json(hist_centers.tolist())
            hist_counts_clean = hist_counts.tolist()  # counts are integers, should be safe
            
            # Clean beeswarm data as well
            shap_values_clean = clean_for_json(shap_values_feature)
            feature_values_raw_clean = clean_for_json(feature_values_raw)
            feature_values_filled_clean = clean_for_json(feature_values_filled)
            
            # Handle expected_feature_value and base_value separately
            if np.isnan(expected_feature_value) or np.isinf(expected_feature_value):
                expected_feature_value = None
            if np.isnan(base_value) or np.isinf(base_value):
                base_value = 0.0  # Default to 0 if base value is invalid
            
            result = {
                'feature_name': feature_name,
                'beeswarm': {
                    'shap_values': shap_values_clean,
                    'feature_values_raw': feature_values_raw_clean,
                    'feature_values_filled': feature_values_filled_clean,
                },
                'partial_dependence': {
                    'grid': grid_clean,
                    'pdp_mean': pdp_mean_clean,
                    'ice_curves': ice_curves_clean,  # Limit to 100 curves for performance
                    'base_value': base_value,  # Expected model output (E[f(x)])
                    'expected_feature_value': expected_feature_value,  # E[feature]
                    'histogram': {
                        'centers': hist_centers_clean,
                        'counts': hist_counts_clean
                    },
                    'shap_static_image': shap_pdp_image_base64  # Static SHAP PDP for comparison
                }
            }

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
