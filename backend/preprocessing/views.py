import json
import math
import os
import time
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from declaration.models import Declaration
from .data_quality import Data_Quality
import pandas as pd
import numpy as np


@method_decorator(csrf_exempt, name='dispatch')
class PreprocessingApplyView(APIView):
    """Accepts selected preprocessing option IDs for a given file and stores them for later steps."""

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            file_id = data.get('file_id')
            options = data.get('options', [])

            if file_id is None:
                return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Validate file exists
            try:
                _ = Declaration.objects.get(pk=file_id)
            except Declaration.DoesNotExist:
                return Response({'error': f'Declaration with id {file_id} not found'}, status=status.HTTP_404_NOT_FOUND)

            if not isinstance(options, list) or not all(isinstance(x, int) for x in options):
                return Response({'error': 'options must be a list of integers'}, status=status.HTTP_400_BAD_REQUEST)

            # Persist the configuration under media/configs as JSON for now
            configs_dir = os.path.join(settings.MEDIA_ROOT, 'configs')
            os.makedirs(configs_dir, exist_ok=True)
            cfg_path = os.path.join(configs_dir, f'preprocess_{file_id}.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump({'file_id': file_id, 'options': options}, f)

            return Response({'status': 'ok', 'file_id': file_id, 'options': options}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class PreprocessingDatqTimeseriesView(APIView):
    """Returns monthly rolling PSI series (3m and 6m) for a selected variable.

    Payload: { file_id: number, processed_file: string, column: string, date_column: string, metric?: 'psi'|'csi',
               split?: { strategy?: 'random'|'oot', date_column?: string, cutoff?: string, percent?: number },
               windows?: list[int], min_bin_share_allowed?: float }
    Currently implements PSI; CSI aliases to PSI for compatibility.
    """

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            file_id = data.get('file_id')
            processed_file = data.get('processed_file')
            column = data.get('column') or data.get('variable')
            date_column = data.get('date_column')
            metric = (data.get('metric') or 'psi').lower()
            # normalize metric aliases
            if metric in ('wasserstein', 'emd', 'earth_mover', 'earthmover', 'w1'):
                metric = 'wd'
            split = data.get('split') if isinstance(data.get('split'), dict) else None
            windows = data.get('windows') if isinstance(data.get('windows'), (list, tuple)) else None
            try:
                windows = [int(w) for w in (windows or [3, 6]) if int(w) >= 1]
            except Exception:
                windows = [3, 6]
            windows = sorted(list(dict.fromkeys(windows)))  # unique & sorted
            min_bin_share_allowed = data.get('min_bin_share_allowed')
            try:
                min_bin_share_allowed = float(min_bin_share_allowed) if min_bin_share_allowed is not None else 0.05
            except Exception:
                min_bin_share_allowed = 0.05

            if file_id is None:
                return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            if not processed_file:
                return Response({'error': 'processed_file is required'}, status=status.HTTP_400_BAD_REQUEST)
            if not column:
                return Response({'error': 'column is required'}, status=status.HTTP_400_BAD_REQUEST)
            if not date_column:
                return Response({'error': 'date_column is required for timeseries analysis'}, status=status.HTTP_400_BAD_REQUEST)

            # Validate declaration exists
            try:
                _ = Declaration.objects.get(pk=file_id)
            except Declaration.DoesNotExist:
                return Response({'error': f'Declaration with id {file_id} not found'}, status=status.HTTP_404_NOT_FOUND)

            # Resolve file path (allow either relative under MEDIA_ROOT or absolute)
            full_path = processed_file
            if not os.path.isabs(full_path):
                full_path = os.path.join(settings.MEDIA_ROOT, processed_file)
            if not os.path.exists(full_path):
                return Response({'error': f'processed_file not found at {full_path}'}, status=status.HTTP_404_NOT_FOUND)

            # Read processed dataframe
            lower = full_path.lower()
            if lower.endswith('.csv'):
                df = pd.read_csv(full_path)
            elif lower.endswith(('.xls', '.xlsx')):
                try:
                    df = pd.read_excel(full_path, engine='openpyxl')
                except Exception:
                    df = pd.read_excel(full_path, engine='xlrd')
            else:
                df = pd.read_csv(full_path)

            if column not in df.columns:
                return Response({'error': f'column {column} not in processed file'}, status=status.HTTP_400_BAD_REQUEST)
            if date_column not in df.columns:
                return Response({'error': f'date_column {date_column} not in processed file'}, status=status.HTTP_400_BAD_REQUEST)

            # Preserve full frame for overall PSI; build a timeseries frame filtered by valid dates
            df_full = df.copy()
            # Prepare time axis (monthly) on a copy for rolling windows
            dt = pd.to_datetime(df[date_column], errors='coerce', dayfirst=True)
            valid_mask = dt.notna()
            df_ts = df.loc[valid_mask].copy()
            dt = dt.loc[valid_mask]
            # Also build a month index for the full frame to align with split indices
            dt_full = pd.to_datetime(df_full[date_column], errors='coerce', dayfirst=True)
            months_full = dt_full.dt.to_period('M').dt.to_timestamp()
            if df_ts.empty:
                return Response({'series': [], 'message': 'No valid datetime rows after parsing.'}, status=status.HTTP_200_OK)

            months = dt.dt.to_period('M').dt.to_timestamp()
            df_ts['_month'] = months
            uniq_months = sorted(df_ts['_month'].dropna().unique().tolist())
            if len(uniq_months) < 2:
                return Response({'series': [], 'message': 'Not enough distinct months to compute rolling PSI.'}, status=status.HTTP_200_OK)

            # Helper classes (as used in other endpoints)
            class _ArgDecl:
                def __init__(self, target_name: str | None):
                    self.numerical_col_sparcity_degree_value_upper_treshold = 0.99
                    self.min_bin_share_allowed = min_bin_share_allowed
                    self.min_bin_count_allowed = 2
                    self.data_target_feature = target_name

            class _VarDemystify:
                def __init__(self, frame: pd.DataFrame, target_name: str | None):
                    num_cols = set(frame.select_dtypes(include=[np.number]).columns.tolist())
                    obj_cols = [c for c in frame.columns if c not in num_cols]
                    # Promote mostly-numeric object columns
                    def _mostly_numeric(series: pd.Series) -> bool:
                        try:
                            ser = series
                            if len(ser) > 5000:
                                ser = ser.sample(5000, random_state=42)
                            s0 = ser.astype(str).str.replace(' ', '', regex=False)
                            s_en = s0.str.replace(',', '', regex=False)
                            p_en = pd.to_numeric(s_en, errors='coerce')
                            s_eu = s0.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                            p_eu = pd.to_numeric(s_eu, errors='coerce')
                            parsed = p_en if p_en.notna().mean() >= p_eu.notna().mean() else p_eu
                            ratio = parsed.notna().mean()
                            nun = parsed.nunique(dropna=True)
                            return (ratio >= 0.5) and (nun >= 2)
                        except Exception:
                            return False
                    for c in obj_cols:
                        try:
                            if _mostly_numeric(frame[c]):
                                num_cols.add(c)
                        except Exception:
                            pass
                    num_cols = list(num_cols)
                    cat_cols = [c for c in frame.columns if c not in num_cols]
                    self.numerical_model_features_list = num_cols
                    self.categorical_model_features_list = cat_cols
                    # Meta info for Data_Quality
                    meta_index = frame.columns
                    miss = frame.isna().mean()
                    sparsity_bound = pd.Series(0.0, index=meta_index)
                    sparsity_ratio = pd.Series(0.0, index=meta_index)
                    for c in meta_index:
                        if c in self.numerical_model_features_list and np.issubdtype(frame[c].dtype, np.number):
                            try:
                                q1 = frame[c].quantile(0.01)
                                sparsity_bound[c] = (frame[c] <= q1).mean()
                                sparsity_ratio[c] = (frame[c] == 0).mean()
                            except Exception:
                                sparsity_bound[c] = 0.0
                                sparsity_ratio[c] = 0.0
                        else:
                            try:
                                mode_val = frame[c].mode(dropna=True)
                                top = mode_val.iloc[0] if not mode_val.empty else None
                                sparsity_bound[c] = (frame[c] == top).mean() if top is not None else 0.0
                                sparsity_ratio[c] = 0.0
                            except Exception:
                                sparsity_bound[c] = 0.0
                                sparsity_ratio[c] = 0.0
                    self.data_meta_info_df = pd.DataFrame({
                        '%_Missing_Value': miss,
                        'Sparcity_Bound_Quantile': sparsity_bound,
                        '%_Sparcity': sparsity_ratio,
                    })

            target_name = 'Target' if 'Target' in df_full.columns else None

            # Build train/test split consistent with Data Quality summary logic
            def _build_split_indices(frame: pd.DataFrame):
                try:
                    if isinstance(split, dict) and split.get('strategy') == 'oot':
                        # Prefer explicit date_column from split, otherwise use payload's date_column
                        dc = split.get('date_column') or date_column
                        if dc and dc in frame.columns:
                            ser = pd.to_datetime(frame[dc], errors='coerce')
                            # Percent-based split support
                            pct = split.get('percent')
                            if pct is not None:
                                try:
                                    pctf = float(pct)
                                except Exception:
                                    pctf = None
                                if pctf is not None and 0 < pctf < 100:
                                    order = ser.sort_values(kind='mergesort').index
                                    k = int(len(order) * (1 - pctf / 100.0))
                                    k = max(0, min(len(order), k))
                                    return order[:k], order[k:]
                            cutoff = split.get('cutoff')
                            if cutoff:
                                mask_train = ser <= pd.to_datetime(cutoff)
                                return frame.index[mask_train], frame.index[~mask_train]
                except Exception as e:
                    print(f"[DatqTimeseries] OOT split failed: {e}, falling back to random")
                rng = np.random.RandomState(42)
                m = rng.rand(len(frame)) < 0.7
                return frame.index[m], frame.index[~m]

            def _psi_between(frame: pd.DataFrame, train_idx, test_idx) -> float | None:
                try:
                    class _Splitter:
                        def __init__(self, tr, te):
                            self.train_data_indeces = tr
                            self.test_data_indeces = te
                    dq = Data_Quality(_ArgDecl(target_name), _VarDemystify(frame, target_name), data_splitter=_Splitter(train_idx, test_idx))
                    dq.feature_psi(frame)
                    detailed = getattr(dq, 'feature_psi_detailed_dict', {})
                    if column in detailed:
                        psi_value, _tbl = detailed[column]
                        try:
                            return float(psi_value)
                        except Exception:
                            return None
                    return None
                except Exception as e:
                    print(f"[DatqTimeseries] PSI computation failed for {column}: {e}")
                    return None

            def _coerce_numeric(ser: pd.Series) -> pd.Series:
                try:
                    s = pd.to_numeric(ser, errors='coerce')
                    return s.dropna()
                except Exception:
                    return pd.Series(dtype=float)

            def _sanitize_for_calc(arr: np.ndarray) -> np.ndarray:
                """Remove NaNs and infs from a numpy array for safe calculations."""
                return arr[np.isfinite(arr)]

            def _ks_between(frame: pd.DataFrame, train_idx, test_idx) -> float | None:
                try:
                    s_tr_raw = _coerce_numeric(frame.loc[train_idx, column])
                    s_te_raw = _coerce_numeric(frame.loc[test_idx, column])
                    s_tr = _sanitize_for_calc(s_tr_raw.values)
                    s_te = _sanitize_for_calc(s_te_raw.values)
                    if s_tr.size < 2 or s_te.size < 2:
                        return None
                    # Empirical CDF based KS statistic
                    v = np.sort(np.unique(np.concatenate([s_tr, s_te])))
                    if v.size == 0:
                        return None
                    # Compute CDFs at each v
                    cdf_tr = np.searchsorted(np.sort(s_tr), v, side='right') / s_tr.size
                    cdf_te = np.searchsorted(np.sort(s_te), v, side='right') / s_te.size
                    d = np.max(np.abs(cdf_tr - cdf_te))
                    return float(d)
                except Exception as e:
                    print(f"[DatqTimeseries] KS computation failed for {column}: {e}")
                    return None

            def _jsd_between(frame: pd.DataFrame, train_idx, test_idx, bins: int = 10) -> float | None:
                try:
                    s_tr_raw = frame.loc[train_idx, column]
                    s_te_raw = frame.loc[test_idx, column]
                    # numeric path
                    x_tr_raw = _coerce_numeric(s_tr_raw)
                    x_te_raw = _coerce_numeric(s_te_raw)
                    x_tr = _sanitize_for_calc(x_tr_raw.values)
                    x_te = _sanitize_for_calc(x_te_raw.values)
                    if x_tr.size >= 2 and x_te.size >= 2:
                        # train-quantile based bins to keep baseline consistent
                        qs = np.linspace(0, 1, bins + 1)
                        try:
                            edges = np.unique(np.quantile(x_tr, qs))
                        except Exception:
                            edges = np.unique(np.linspace(float(x_tr.min()), float(x_tr.max()), bins + 1))
                        if edges.size < 2:
                            return None
                        p, _ = np.histogram(x_tr, bins=edges)
                        q, _ = np.histogram(x_te, bins=edges)
                    else:
                        # categorical fallback using value counts over union of categories
                        vc_tr = s_tr_raw.astype(str).value_counts()
                        vc_te = s_te_raw.astype(str).value_counts()
                        cats = sorted(list(set(vc_tr.index).union(set(vc_te.index))))
                        if len(cats) < 2:
                            return None
                        p = np.array([vc_tr.get(c, 0) for c in cats], dtype=float)
                        q = np.array([vc_te.get(c, 0) for c in cats], dtype=float)
                    if p.sum() == 0 or q.sum() == 0:
                        return None
                    p = p / p.sum()
                    q = q / q.sum()
                    m = 0.5 * (p + q)
                    eps = 1e-12
                    def _kl(a, b):
                        a = np.clip(a, eps, 1.0)
                        b = np.clip(b, eps, 1.0)
                        return float(np.sum(a * np.log(a / b)))
                    jsd = 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
                    return float(jsd)
                except Exception as e:
                    print(f"[DatqTimeseries] JSD computation failed for {column}: {e}")
                    return None

            def _wd_between(frame: pd.DataFrame, train_idx, test_idx) -> float | None:
                try:
                    x_raw = _coerce_numeric(frame.loc[train_idx, column]).values
                    y_raw = _coerce_numeric(frame.loc[test_idx, column]).values
                    x = _sanitize_for_calc(x_raw)
                    y = _sanitize_for_calc(y_raw)
                    if x.size == 0 or y.size == 0:
                        return None
                    # 1D Wasserstein (Earth Mover's) via CDF difference integral
                    xs = np.sort(x)
                    ys = np.sort(y)
                    all_values = np.concatenate([xs, ys])
                    ux = np.unique(all_values[np.isfinite(all_values)])
                    if ux.size < 2:
                        return 0.0
                    Fx = np.searchsorted(xs, ux, side='right') / xs.size
                    Fy = np.searchsorted(ys, ux, side='right') / ys.size
                    # integrate |Fx - Fy| over x using trapezoidal rule between knots
                    diffs = np.abs(Fx - Fy)
                    dx = np.diff(ux)
                    area = np.sum(0.5 * (diffs[:-1] + diffs[1:]) * dx)
                    return float(area)
                except Exception as e:
                    print(f"[DatqTimeseries] Wasserstein computation failed for {column}: {e}")
                    return None

            # Establish train/test split once for consistency with overall
            try:
                tr_idx, te_idx = _build_split_indices(df_full)
            except Exception:
                tr_idx, te_idx = df_full.index[:0], df_full.index[:0]

            out_series = []
            for m in uniq_months:
                rec = {'month': m.strftime('%Y-%m')}
                try:
                    idx_m = uniq_months.index(m)
                except ValueError:
                    idx_m = -1
                for w in windows:
                    key_prefix = 'psi' if metric in ('psi', 'csi') else ('ks' if metric == 'ks' else ('jsd' if metric == 'jsd' else 'wd'))
                    key = f"{key_prefix}_{w}m"
                    nkey = f"n_{w}m"
                    if idx_m >= (w - 1) and len(tr_idx) > 0:
                        win = uniq_months[idx_m - (w - 1): idx_m + 1]
                        maskw = months_full.isin(win)
                        tew = te_idx[maskw.loc[te_idx]]
                        if len(tew) > 0:
                            if metric in ('psi', 'csi'):
                                rec[key] = _psi_between(df_full, tr_idx, tew)
                            elif metric == 'ks':
                                rec[key] = _ks_between(df_full, tr_idx, tew)
                            elif metric == 'jsd':
                                rec[key] = _jsd_between(df_full, tr_idx, tew)
                            elif metric == 'wd':
                                rec[key] = _wd_between(df_full, tr_idx, tew)
                            else:
                                rec[key] = None
                        else:
                            rec[key] = None
                        try:
                            rec[nkey] = int(len(tew))
                        except Exception:
                            rec[nkey] = None
                    else:
                        rec[key] = None
                        rec[nkey] = None
                out_series.append(rec)

            # Overall (non-rolling) PSI/CSI: match Data Quality summary split (random 70/30 default)
            overall = None
            try:
                tr_idx, te_idx = _build_split_indices(df_full)
                if metric in ('psi', 'csi'):
                    overall = _psi_between(df_full, tr_idx, te_idx)
                elif metric == 'ks':
                    overall = _ks_between(df_full, tr_idx, te_idx)
                elif metric == 'jsd':
                    overall = _jsd_between(df_full, tr_idx, te_idx)
                elif metric == 'wd':
                    overall = _wd_between(df_full, tr_idx, te_idx)
            except Exception:
                overall = None

            return Response({'series': out_series, 'metric': metric, 'overall': overall}, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            print("[PreprocessingDatqTimeseriesView] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class PreprocessingRunView(APIView):
    """Runs preprocessing on the uploaded file using selected options and returns a small preview.

    Payload: { file_id: number, options?: number[] }
    If options is omitted, it will try to read MEDIA_ROOT/configs/preprocess_<file_id>.json
    """

    def post(self, request, *args, **kwargs):
        try:
            t0 = time.monotonic()
            data = request.data
            file_id = data.get('file_id')
            options = data.get('options')
            split = data.get('split')  # {'strategy': 'random'|'oot', 'date_column': str, 'cutoff': str}

            if file_id is None:
                return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Validate declaration
            try:
                decl = Declaration.objects.get(pk=file_id)
            except Declaration.DoesNotExist:
                return Response({'error': f'Declaration with id {file_id} not found'}, status=status.HTTP_404_NOT_FOUND)

            # Load options from saved config if not provided
            if options is None:
                cfg_path = os.path.join(settings.MEDIA_ROOT, 'configs', f'preprocess_{file_id}.json')
                if not os.path.exists(cfg_path):
                    return Response({'error': 'No options provided and no saved configuration found'}, status=status.HTTP_400_BAD_REQUEST)
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                options = cfg.get('options', [])

            if not isinstance(options, list) or not all(isinstance(x, int) for x in options):
                return Response({'error': 'options must be a list of integers'}, status=status.HTTP_400_BAD_REQUEST)

            file_path = decl.file.path
            if not os.path.exists(file_path):
                return Response({'error': 'Source file not found'}, status=status.HTTP_404_NOT_FOUND)

            # Read CSV/Excel
            t_read_start = time.monotonic()
            df = self._read_dataframe(file_path)
            print(f"[PreprocessingRun] read_dataframe ok in {time.monotonic()-t_read_start:.3f}s shape={df.shape}")
            rows_before = len(df)
            cols_before = list(df.columns)

            # Apply transformations
            t_apply_start = time.monotonic()
            preserve_cols: set[str] | None = None
            try:
                if isinstance(split, dict) and split.get('strategy') == 'oot' and split.get('date_column'):
                    preserve_cols = {str(split.get('date_column'))}
            except Exception:
                preserve_cols = None
            df_processed, dropped_columns, dropped_by_step = self._apply_options(df, set(options), preserve=preserve_cols)
            print(f"[PreprocessingRun] apply_options ok in {time.monotonic()-t_apply_start:.3f}s dropped={len(dropped_columns)} shape={df_processed.shape}")

            # Save processed file
            out_name = f"processed_{file_id}_{self._safe_timestamp()}.csv"
            out_rel = os.path.join('data_files', out_name)
            out_full = os.path.join(settings.MEDIA_ROOT, out_rel)
            os.makedirs(os.path.dirname(out_full), exist_ok=True)
            t_save_start = time.monotonic()
            df_processed.to_csv(out_full, index=False)
            print(f"[PreprocessingRun] saved processed csv in {time.monotonic()-t_save_start:.3f}s -> {out_rel}")

            # Build split indices helper
            def _build_split_indices(frame: pd.DataFrame):
                try:
                    if isinstance(split, dict) and split.get('strategy') == 'oot':
                        date_col = split.get('date_column')
                        # Determine a series to base the split: prefer processed frame; else fall back to original df aligned to frame index
                        ser = None
                        if date_col and date_col in frame.columns:
                            ser = pd.to_datetime(frame[date_col], errors='coerce', dayfirst=True)
                        elif date_col and 'df' in locals() and isinstance(df, pd.DataFrame) and date_col in df.columns:
                            base = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
                            try:
                                ser = base.loc[frame.index]
                            except Exception:
                                # last resort: reindex with intersection
                                inter = frame.index.intersection(base.index)
                                ser = base.loc[inter]
                                frame = frame.loc[inter]
                        if ser is None or ser.shape[0] == 0:
                            print("[PreprocessingRun] OOT split: date_column missing/unaligned; falling back to random")
                        else:
                            pct = split.get('percent')
                            if pct is not None:
                                try:
                                    pctf = float(pct)
                                except Exception:
                                    pctf = None
                                if pctf is not None and 0 < pctf < 100:
                                    order = ser.sort_values(kind='mergesort').index  # stable sort
                                    k = int(len(order) * (1 - pctf / 100.0))
                                    k = max(0, min(len(order), k))
                                    train_idx = order[:k]
                                    test_idx = order[k:]
                                    print(f"[PreprocessingRun] OOT percent split using {date_col} percent={pctf}% -> train={len(train_idx)} test={len(test_idx)}")
                                    return train_idx, test_idx
                            cutoff = split.get('cutoff')
                            if cutoff:
                                mask_train = ser <= pd.to_datetime(cutoff, dayfirst=True)
                                train_idx = ser.index[mask_train]
                                test_idx = ser.index[~mask_train]
                                print(f"[PreprocessingRun] OOT cutoff split using {date_col} cutoff={cutoff} train={len(train_idx)} test={len(test_idx)}")
                                return train_idx, test_idx
                except Exception as e:
                    print(f"[PreprocessingRun] OOT split failed: {e}, falling back to random")
                # random default
                rng = np.random.RandomState(42)
                m = rng.rand(len(frame)) < 0.7
                return frame.index[m], frame.index[~m]

            # Build Data Quality summary safely
            datq_summary_records = None
            try:
                # Soft guard: if data is excessively large, skip summary to avoid long blocking
                max_cells = int(os.environ.get('DATQ_MAX_CELLS', '20000000'))  # 20M default
                sample_rows = int(os.environ.get('DATQ_SAMPLE_ROWS', '20000'))  # 20k default
                n_cells = df_processed.shape[0] * max(1, df_processed.shape[1])
                if n_cells > max_cells:
                    print(f"[PreprocessingRun] datq_summary skipped due to size n_cells={n_cells} > max_cells={max_cells}")
                    datq_summary_records = None
                else:
                    # Optionally sample rows to keep PSI/binning fast on large datasets
                    if df_processed.shape[0] > sample_rows:
                        df_for_datq = df_processed.sample(n=sample_rows, random_state=42)
                        print(f"[PreprocessingRun] datq using sampled rows: {sample_rows}/{df_processed.shape[0]}")
                    else:
                        df_for_datq = df_processed
                # Construct splitter based on requested strategy on the frame being analyzed (df_for_datq)
                train_idx, test_idx = _build_split_indices(df_for_datq)
                class _Splitter:
                    def __init__(self, tr, te):
                        self.train_data_indeces = tr
                        self.test_data_indeces = te
                # Minimal stubs for required collaborators
                class _ArgDecl:
                    def __init__(self, target_name: str | None):
                        # Defaults that are sensible for binning
                        self.numerical_col_sparcity_degree_value_upper_treshold = 0.99
                        self.min_bin_share_allowed = 0.05
                        self.min_bin_count_allowed = 2
                        self.data_target_feature = target_name

                class _VarDemystify:
                    def __init__(self, frame: pd.DataFrame, target_name: str | None):
                        # Start with dtype-based detection
                        num_cols = set(frame.select_dtypes(include=[np.number]).columns.tolist())
                        obj_cols = [c for c in frame.columns if c not in num_cols]
                        # Promote object columns that are mostly numeric (robust parse):
                        # Use full column if small, else sample up to 5000 rows.
                        def _mostly_numeric(series: pd.Series) -> bool:
                            try:
                                ser = series
                                if len(ser) > 5000:
                                    ser = ser.sample(5000, random_state=42)
                                s0 = ser.astype(str).str.replace(' ', '', regex=False)
                                # EN style: 1,234.56
                                s_en = s0.str.replace(',', '', regex=False)
                                p_en = pd.to_numeric(s_en, errors='coerce')
                                # EU style: 1.234,56
                                s_eu = s0.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                                p_eu = pd.to_numeric(s_eu, errors='coerce')
                                parsed = p_en if p_en.notna().mean() >= p_eu.notna().mean() else p_eu
                                ratio = parsed.notna().mean()
                                nun = parsed.nunique(dropna=True)
                                return (ratio >= 0.5) and (nun >= 2)
                            except Exception:
                                return False
                        for c in obj_cols:
                            try:
                                if _mostly_numeric(frame[c]):
                                    num_cols.add(c)
                            except Exception:
                                pass
                        num_cols = list(num_cols)
                        cat_cols = [c for c in frame.columns if c not in num_cols]
                        # exclude target from lists if present
                        if target_name in num_cols:
                            num_cols = [c for c in num_cols if c != target_name]
                        if target_name in cat_cols:
                            cat_cols = [c for c in cat_cols if c != target_name]
                        self.numerical_model_features_list = num_cols
                        self.categorical_model_features_list = cat_cols
                        # Meta info with the columns referenced in Data_Quality
                        meta_index = frame.columns
                        miss = frame.isna().mean()
                        # For sparsity bound, use share of values equal to the 1st percentile for numerics; top-category share for categoricals
                        sparsity_bound = pd.Series(0.0, index=meta_index)
                        sparsity_ratio = pd.Series(0.0, index=meta_index)
                        for c in meta_index:
                            if c in self.numerical_model_features_list and np.issubdtype(frame[c].dtype, np.number):
                                try:
                                    q1 = frame[c].quantile(0.01)
                                    sparsity_bound[c] = (frame[c] <= q1).mean()
                                    sparsity_ratio[c] = (frame[c] == 0).mean()
                                except Exception:
                                    sparsity_bound[c] = 0.0
                                    sparsity_ratio[c] = 0.0
                            else:
                                try:
                                    mode_val = frame[c].mode(dropna=True)
                                    top = mode_val.iloc[0] if not mode_val.empty else None
                                    sparsity_bound[c] = (frame[c] == top).mean() if top is not None else 0.0
                                    sparsity_ratio[c] = 0.0
                                except Exception:
                                    sparsity_bound[c] = 0.0
                                    sparsity_ratio[c] = 0.0
                        self.data_meta_info_df = pd.DataFrame({
                            '%_Missing_Value': miss,
                            'Sparcity_Bound_Quantile': sparsity_bound,
                            '%_Sparcity': sparsity_ratio,
                        })

                target_name = 'Target' if 'Target' in df_for_datq.columns else None
                t_datq_start = time.monotonic()
                dq = Data_Quality(_ArgDecl(target_name), _VarDemystify(df_for_datq, target_name), data_splitter=_Splitter(train_idx, test_idx))
                dq.datq_summary_table(df_for_datq)
                # Sanitize for JSON: convert tuples to lists; NaN/Inf to None recursively
                def _sanitize(o):
                    try:
                        if isinstance(o, (np.floating, float)):
                            f = float(o)
                            if math.isfinite(f):
                                return f
                            return None
                        if isinstance(o, (np.integer, int)):
                            return int(o)
                        if isinstance(o, (np.bool_, bool)):
                            return bool(o)
                        if o is None:
                            return None
                        if isinstance(o, tuple):
                            return [_sanitize(x) for x in o]
                        if isinstance(o, list):
                            return [_sanitize(x) for x in o]
                        if isinstance(o, dict):
                            return {k: _sanitize(v) for k, v in o.items()}
                        # Pandas NA types
                        try:
                            if pd.isna(o):
                                return None
                        except Exception:
                            pass
                        return o
                    except Exception:
                        return None

                # Work on a copy and expand pair-valued columns into Train/Test
                df_all = dq.datq_summary_df.copy()
                # Ensure index has a proper name for frontend column header
                try:
                    df_all.index.name = 'Variable'
                except Exception:
                    pass
                # Add alternative shift metrics (KS, JSD, Wasserstein) computed on the same split
                try:
                    def _coerce_numeric(ser: pd.Series) -> pd.Series:
                        try:
                            s = pd.to_numeric(ser, errors='coerce')
                            return s.dropna()
                        except Exception:
                            return pd.Series(dtype=float)

                    def _ks_col(frame: pd.DataFrame, col: str) -> float | None:
                        try:
                            s_tr = _coerce_numeric(frame.loc[train_idx, col])
                            s_te = _coerce_numeric(frame.loc[test_idx, col])
                            if len(s_tr) < 2 or len(s_te) < 2:
                                return None
                            v = np.sort(np.unique(np.concatenate([s_tr.values, s_te.values])))
                            if v.size == 0:
                                return None
                            cdf_tr = np.searchsorted(np.sort(s_tr.values), v, side='right') / len(s_tr)
                            cdf_te = np.searchsorted(np.sort(s_te.values), v, side='right') / len(s_te)
                            d = np.max(np.abs(cdf_tr - cdf_te))
                            return float(d)
                        except Exception:
                            return None

                    def _jsd_col(frame: pd.DataFrame, col: str, bins: int = 10) -> float | None:
                        try:
                            s_tr_raw = frame.loc[train_idx, col]
                            s_te_raw = frame.loc[test_idx, col]
                            x_tr = _coerce_numeric(s_tr_raw)
                            x_te = _coerce_numeric(s_te_raw)
                            if len(x_tr) >= 2 and len(x_te) >= 2:
                                qs = np.linspace(0, 1, bins + 1)
                                try:
                                    edges = np.unique(np.quantile(x_tr.values, qs))
                                except Exception:
                                    edges = np.unique(np.linspace(float(x_tr.min()), float(x_tr.max()), bins + 1))
                                if edges.size < 2:
                                    return None
                                p, _ = np.histogram(x_tr.values, bins=edges)
                                q, _ = np.histogram(x_te.values, bins=edges)
                            else:
                                vc_tr = s_tr_raw.astype(str).value_counts()
                                vc_te = s_te_raw.astype(str).value_counts()
                                cats = sorted(list(set(vc_tr.index).union(set(vc_te.index))))
                                if len(cats) < 2:
                                    return None
                                p = np.array([vc_tr.get(c, 0) for c in cats], dtype=float)
                                q = np.array([vc_te.get(c, 0) for c in cats], dtype=float)
                            if p.sum() == 0 or q.sum() == 0:
                                return None
                            p = p / p.sum(); q = q / q.sum(); m = 0.5 * (p + q)
                            eps = 1e-12
                            def _kl(a, b):
                                a = np.clip(a, eps, 1.0); b = np.clip(b, eps, 1.0)
                                return float(np.sum(a * np.log(a / b)))
                            return float(0.5 * _kl(p, m) + 0.5 * _kl(q, m))
                        except Exception:
                            return None

                    def _wd_col(frame: pd.DataFrame, col: str) -> float | None:
                        try:
                            x = _coerce_numeric(frame.loc[train_idx, col]).values
                            y = _coerce_numeric(frame.loc[test_idx, col]).values
                            if x.size == 0 or y.size == 0:
                                return None
                            xs = np.sort(x); ys = np.sort(y)
                            ux = np.unique(np.concatenate([xs, ys]))
                            if ux.size < 2:
                                return 0.0
                            Fx = np.searchsorted(xs, ux, side='right') / xs.size
                            Fy = np.searchsorted(ys, ux, side='right') / ys.size
                            diffs = np.abs(Fx - Fy)
                            dx = np.diff(ux)
                            area = np.sum(0.5 * (diffs[:-1] + diffs[1:]) * dx)
                            return float(area)
                        except Exception:
                            return None

                    # Compute per variable present in the summary index
                    ks_vals = {}
                    jsd_vals = {}
                    wd_vals = {}
                    for var in df_all.index.tolist():
                        if var in df_for_datq.columns:
                            ks_vals[var] = _ks_col(df_for_datq, var)
                            jsd_vals[var] = _jsd_col(df_for_datq, var)
                            wd_vals[var] = _wd_col(df_for_datq, var)
                    df_all['KS'] = pd.Series(ks_vals)
                    df_all['JSD'] = pd.Series(jsd_vals)
                    df_all['Wasserstein'] = pd.Series(wd_vals)
                except Exception as _alt_err:
                    print(f"[PreprocessingRun] alternative metrics failed: {_alt_err}")
                try:
                    def _is_len2_seq(v):
                        try:
                            import numpy as _np
                            if v is None:
                                return False
                            if isinstance(v, (list, tuple)):
                                return len(v) == 2
                            if isinstance(v, _np.ndarray):
                                return v.ndim == 1 and v.size == 2
                            return False
                        except Exception:
                            return False

                    expandable_cols = []
                    for c in list(df_all.columns):
                        values = list(df_all[c].values)
                        def _is_null(v):
                            try:
                                return (v is None) or (pd.isna(v))
                            except Exception:
                                return v is None
                        non_null = [v for v in values if not _is_null(v)]
                        if not non_null:
                            continue
                        any_len2 = any(_is_len2_seq(v) for v in non_null)
                        all_len2_or_null = all((_is_len2_seq(v) or _is_null(v)) for v in values)
                        if any_len2 and all_len2_or_null:
                            expandable_cols.append(c)

                    for c in expandable_cols:
                        series = df_all[c]
                        df_all[c+"_Train"] = series.apply(lambda v: (v[0] if _is_len2_seq(v) else None))
                        df_all[c+"_Test"] = series.apply(lambda v: (v[1] if _is_len2_seq(v) else None))
                        df_all.drop(columns=[c], inplace=True)
                except Exception:
                    pass

                df_reset = df_all.reset_index()
                # apply per-cell sanitize
                try:
                    df_reset = df_reset.map(_sanitize)
                except Exception:
                    # Fallback to row-wise sanitize after to_dict
                    pass
                records = df_reset.to_dict(orient='records')
                datq_summary_records = [_sanitize(r) for r in records]
                print(f"[PreprocessingRun] datq_summary_table ok in {time.monotonic()-t_datq_start:.3f}s rows={len(datq_summary_records) if datq_summary_records else 0}")
            except Exception as dq_err:
                datq_summary_records = None
                print(f"[PreprocessingRun] datq_summary error: {dq_err}")

            # Save datq_summary as JSON for later use in modeling
            if datq_summary_records:
                try:
                    datq_dir = os.path.join(settings.MEDIA_ROOT, 'data_quality')
                    os.makedirs(datq_dir, exist_ok=True)
                    datq_json_path = os.path.join(datq_dir, f'{file_id}_datq_summary.json')
                    with open(datq_json_path, 'w', encoding='utf-8') as f:
                        json.dump(datq_summary_records, f)
                    print(f"[PreprocessingRun] saved datq_summary JSON -> {datq_json_path}")
                except Exception as e:
                    print(f"[PreprocessingRun] failed to save datq_summary JSON: {e}")

            preview = {
                'file_id': file_id,
                'options': options,
                'split': split if isinstance(split, dict) else {'strategy': 'random'},
                'row_count_before': rows_before,
                'row_count_after': len(df_processed),
                'rows_removed_total': int(max(0, rows_before - len(df_processed))),
                'dropped_columns': dropped_columns,
                'dropped_columns_by_step': dropped_by_step,
                'original_columns_count': len(cols_before),
                'new_columns_count': len(df_processed.columns),
                'head': df_processed.head(5).replace({np.nan: None}).to_dict(orient='records'),
                'processed_file': out_rel,
                'datq_summary': datq_summary_records,
            }

            # Final sanitize for JSON safety
            def _final_sanitize(o):
                try:
                    if isinstance(o, (np.floating, float)):
                        f = float(o)
                        return f if math.isfinite(f) else None
                    if isinstance(o, (np.integer, int)):
                        return int(o)
                    if isinstance(o, (np.bool_, bool)):
                        return bool(o)
                    if o is None:
                        return None
                    if isinstance(o, tuple):
                        return [_final_sanitize(x) for x in o]
                    if isinstance(o, list):
                        return [_final_sanitize(x) for x in o]
                    if isinstance(o, dict):
                        return {k: _final_sanitize(v) for k, v in o.items()}
                    try:
                        if pd.isna(o):
                            return None
                    except Exception:
                        pass
                    return o
                except Exception:
                    return None

            preview = _final_sanitize(preview)

            print(f"[PreprocessingRun] completed in {time.monotonic()-t0:.3f}s")
            return Response(preview, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            print("[PreprocessingRun] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _read_dataframe(self, path: str) -> pd.DataFrame:
        lower = path.lower()
        if lower.endswith('.csv'):
            return pd.read_csv(path)
        elif lower.endswith(('.xls', '.xlsx')):
            # try openpyxl, fallback xlrd
            try:
                return pd.read_excel(path, engine='openpyxl')
            except Exception:
                return pd.read_excel(path, engine='xlrd')
        else:
            # default try csv
            return pd.read_csv(path)

    def _apply_options(self, df: pd.DataFrame, options: set[int], preserve: set[str] | None = None):
        dropped_cols: list[str] = []
        breakdown: list[dict] = []
        work = df.copy()

        # 1: Column-wise duplicate drop
        if 1 in options:
            _rows_before = len(work)
            before_cols = list(work.columns)
            work = work.T.drop_duplicates().T
            dc = [c for c in before_cols if c not in work.columns]
            if preserve:
                dc = [c for c in dc if c not in preserve]
            dropped_cols += dc
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            # Always record the step outcome (even if no columns removed)
            breakdown.append({'step': 'Column-wise duplicate drop', 'option_ids': [1], 'columns': dc, 'rows_removed': _rows_removed})

        # 2: Row-wise duplicate drop
        if 2 in options:
            _rows_before = len(work)
            work = work.drop_duplicates()
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Row-wise duplicate drop', 'option_ids': [2], 'columns': [], 'rows_removed': _rows_removed})

        # 3: Zero-variance drop
        if 3 in options:
            _rows_before = len(work)
            nunique = work.nunique(dropna=False)
            to_drop = nunique[nunique <= 1].index.tolist()
            if preserve:
                to_drop = [c for c in to_drop if c not in preserve]
            work = work.drop(columns=to_drop)
            dropped_cols += to_drop
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Zero-variance drop', 'option_ids': [3], 'columns': to_drop, 'rows_removed': _rows_removed})

        # 4: Perfect-correlation drop
        if 4 in options:
            _rows_before = len(work)
            num = work.select_dtypes(include=[np.number])
            if not num.empty:
                corr = num.corr().abs()
                upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
                to_drop = [column for column in upper.columns if any(upper[column] == 1.0)]
                if preserve:
                    to_drop = [c for c in to_drop if c not in preserve]
                work = work.drop(columns=to_drop, errors='ignore')
                dropped_cols += to_drop
            else:
                to_drop = []
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Perfect-correlation drop', 'option_ids': [4], 'columns': to_drop, 'rows_removed': _rows_removed})

        # 5-8: Corr-drop thresholds
        corr_thresholds = {5: 0.95, 6: 0.90, 7: 0.85, 8: 0.80}
        selected_corr = [t for k, t in corr_thresholds.items() if k in options]
        if selected_corr:
            thr = min(selected_corr)  # be conservative: drop more if multiple selected
            selected_corr_ids = [k for k in corr_thresholds.keys() if k in options]
            _rows_before = len(work)
            num = work.select_dtypes(include=[np.number])
            if not num.empty:
                corr = num.corr().abs()
                cols = set(num.columns)
                removed = set()
                for i in corr.columns:
                    if i in removed:
                        continue
                    for j in corr.columns:
                        if i == j or j in removed:
                            continue
                        if corr.loc[i, j] >= thr:
                            removed.add(j)
                if preserve:
                    removed = {c for c in removed if c not in preserve}
                work = work.drop(columns=list(removed), errors='ignore')
                dropped_cols += list(removed)
                cols_removed_list = list(removed)
            else:
                cols_removed_list = []
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Correlation drop (threshold)', 'option_ids': selected_corr_ids, 'threshold': thr, 'columns': cols_removed_list, 'rows_removed': _rows_removed})

        # 9-13: Missing-drop thresholds
        miss_thresholds = {9: 0.20, 10: 0.30, 11: 0.40, 12: 0.50, 13: 0.60}
        selected_miss = [t for k, t in miss_thresholds.items() if k in options]
        if selected_miss:
            thr = min(selected_miss)
            selected_miss_ids = [k for k in miss_thresholds.keys() if k in options]
            _rows_before = len(work)
            miss_ratio = work.isna().mean()
            to_drop = miss_ratio[miss_ratio >= thr].index.tolist()
            if preserve:
                to_drop = [c for c in to_drop if c not in preserve]
            work = work.drop(columns=to_drop)
            dropped_cols += to_drop
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Missing-drop (threshold)', 'option_ids': selected_miss_ids, 'threshold': thr, 'columns': to_drop, 'rows_removed': _rows_removed})

        # 14-18: Sparsity (zeros) drop thresholds
        sparse_thresholds = {14: 0.20, 15: 0.30, 16: 0.40, 17: 0.50, 18: 0.60}
        selected_sparse = [t for k, t in sparse_thresholds.items() if k in options]
        if selected_sparse:
            thr = min(selected_sparse)
            selected_sparse_ids = [k for k in sparse_thresholds.keys() if k in options]
            _rows_before = len(work)
            num = work.select_dtypes(include=[np.number])
            if not num.empty:
                zero_ratio = (num == 0).mean()
                to_drop = zero_ratio[zero_ratio >= thr].index.tolist()
                if preserve:
                    to_drop = [c for c in to_drop if c not in preserve]
                work = work.drop(columns=to_drop)
                dropped_cols += to_drop
            else:
                to_drop = []
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Sparsity zeros drop (threshold)', 'option_ids': selected_sparse_ids, 'threshold': thr, 'columns': to_drop, 'rows_removed': _rows_removed})

        # 19-23: Combined sparsity + missing thresholds
        combo_thresholds = {19: 0.95, 20: 0.90, 21: 0.85, 22: 0.80, 23: 0.75}
        selected_combo = [t for k, t in combo_thresholds.items() if k in options]
        if selected_combo:
            thr = min(selected_combo)
            selected_combo_ids = [k for k in combo_thresholds.keys() if k in options]
            _rows_before = len(work)
            num = work.select_dtypes(include=[np.number])
            zero_ratio = (num == 0).mean() if not num.empty else pd.Series(0, index=[])
            miss_ratio = work.isna().mean()
            combo = miss_ratio.copy()
            for c in zero_ratio.index:
                combo[c] = max(combo.get(c, 0), zero_ratio[c])
            to_drop = combo[combo >= thr].index.tolist()
            if preserve:
                to_drop = [c for c in to_drop if c not in preserve]
            work = work.drop(columns=to_drop)
            dropped_cols += to_drop
            _rows_after = len(work)
            _rows_removed = int(max(0, _rows_before - _rows_after))
            breakdown.append({'step': 'Combined sparsity+missing drop (threshold)', 'option_ids': selected_combo_ids, 'threshold': thr, 'columns': to_drop, 'rows_removed': _rows_removed})

        # 28-30: Outlier cleaning via quantile clipping
        quantiles = {28: (0.01, 0.99), 29: (0.05, 0.95), 30: (0.10, 0.90)}
        selected_q = [q for k, q in quantiles.items() if k in options]
        if selected_q:
            lo, hi = selected_q[0]  # pick the first specified
            num = work.select_dtypes(include=[np.number])
            if not num.empty:
                lower = num.quantile(lo)
                upper = num.quantile(hi)
                num_clipped = num.clip(lower=lower, upper=upper, axis=1)
                for c in num_clipped.columns:
                    work[c] = num_clipped[c]

        return work, list(dict.fromkeys(dropped_cols)), breakdown

    def _safe_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().strftime('%Y%m%d%H%M%S')


@method_decorator(csrf_exempt, name='dispatch')
class PreprocessingDatqDetailView(APIView):
    """Returns a detailed PSI report for a selected variable from the processed file.

    Payload: { file_id: number, processed_file: string, column: string }
    """

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            file_id = data.get('file_id')
            processed_file = data.get('processed_file')
            column = data.get('column') or data.get('variable')
            split = data.get('split')

            if file_id is None:
                return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            if not processed_file:
                return Response({'error': 'processed_file is required'}, status=status.HTTP_400_BAD_REQUEST)
            if not column:
                return Response({'error': 'column is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Validate declaration exists
            try:
                _ = Declaration.objects.get(pk=file_id)
            except Declaration.DoesNotExist:
                return Response({'error': f'Declaration with id {file_id} not found'}, status=status.HTTP_404_NOT_FOUND)

            # Resolve file path (allow either relative under MEDIA_ROOT or absolute)
            full_path = processed_file
            if not os.path.isabs(full_path):
                full_path = os.path.join(settings.MEDIA_ROOT, processed_file)
            if not os.path.exists(full_path):
                return Response({'error': f'processed_file not found at {full_path}'}, status=status.HTTP_404_NOT_FOUND)

            # Read processed dataframe
            lower = full_path.lower()
            if lower.endswith('.csv'):
                df = pd.read_csv(full_path)
            elif lower.endswith(('.xls', '.xlsx')):
                try:
                    df = pd.read_excel(full_path, engine='openpyxl')
                except Exception:
                    df = pd.read_excel(full_path, engine='xlrd')
            else:
                df = pd.read_csv(full_path)

            if column not in df.columns:
                return Response({'error': f'column {column} not in processed file'}, status=status.HTTP_400_BAD_REQUEST)

            # Build Data Quality and compute PSI for detail
            # Minimal stubs as in PreprocessingRunView
            class _ArgDecl:
                def __init__(self, target_name: str | None):
                    self.numerical_col_sparcity_degree_value_upper_treshold = 0.99
                    self.min_bin_share_allowed = 0.05
                    self.min_bin_count_allowed = 2
                    self.data_target_feature = target_name

            class _VarDemystify:
                def __init__(self, frame: pd.DataFrame, target_name: str | None):
                    num_cols = set(frame.select_dtypes(include=[np.number]).columns.tolist())
                    obj_cols = [c for c in frame.columns if c not in num_cols]
                    def _mostly_numeric(series: pd.Series) -> bool:
                        try:
                            ser = series
                            if len(ser) > 5000:
                                ser = ser.sample(5000, random_state=42)
                            s0 = ser.astype(str).str.replace(' ', '', regex=False)
                            s_en = s0.str.replace(',', '', regex=False)
                            p_en = pd.to_numeric(s_en, errors='coerce')
                            s_eu = s0.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                            p_eu = pd.to_numeric(s_eu, errors='coerce')
                            parsed = p_en if p_en.notna().mean() >= p_eu.notna().mean() else p_eu
                            ratio = parsed.notna().mean()
                            nun = parsed.nunique(dropna=True)
                            return (ratio >= 0.5) and (nun >= 2)
                        except Exception:
                            return False
                    for c in obj_cols:
                        try:
                            if _mostly_numeric(frame[c]):
                                num_cols.add(c)
                        except Exception:
                            pass
                    num_cols = list(num_cols)
                    cat_cols = [c for c in frame.columns if c not in num_cols]
                    if target_name in num_cols:
                        num_cols = [c for c in num_cols if c != target_name]
                    if target_name in cat_cols:
                        cat_cols = [c for c in cat_cols if c != target_name]
                    self.numerical_model_features_list = num_cols
                    self.categorical_model_features_list = cat_cols
                    meta_index = frame.columns
                    miss = frame.isna().mean()
                    sparsity_bound = pd.Series(0.0, index=meta_index)
                    sparsity_ratio = pd.Series(0.0, index=meta_index)
                    for c in meta_index:
                        if c in self.numerical_model_features_list and np.issubdtype(frame[c].dtype, np.number):
                            try:
                                q1 = frame[c].quantile(0.01)
                                sparsity_bound[c] = (frame[c] <= q1).mean()
                                sparsity_ratio[c] = (frame[c] == 0).mean()
                            except Exception:
                                sparsity_bound[c] = 0.0
                                sparsity_ratio[c] = 0.0
                        else:
                            try:
                                mode_val = frame[c].mode(dropna=True)
                                top = mode_val.iloc[0] if not mode_val.empty else None
                                sparsity_bound[c] = (frame[c] == top).mean() if top is not None else 0.0
                                sparsity_ratio[c] = 0.0
                            except Exception:
                                sparsity_bound[c] = 0.0
                                sparsity_ratio[c] = 0.0
                    self.data_meta_info_df = pd.DataFrame({
                        '%_Missing_Value': miss,
                        'Sparcity_Bound_Quantile': sparsity_bound,
                        '%_Sparcity': sparsity_ratio,
                    })

            target_name = 'Target' if 'Target' in df.columns else None
            # Build split indices based on requested strategy
            def _build_split_indices(frame: pd.DataFrame):
                try:
                    if isinstance(split, dict) and split.get('strategy') == 'oot':
                        date_col = split.get('date_column')
                        if date_col and date_col in frame.columns:
                            ser = pd.to_datetime(frame[date_col], errors='coerce')
                            # Percent-based split support
                            pct = split.get('percent')
                            if pct is not None:
                                try:
                                    pctf = float(pct)
                                except Exception:
                                    pctf = None
                                if pctf is not None and 0 < pctf < 100:
                                    order = ser.sort_values(kind='mergesort').index
                                    k = int(len(order) * (1 - pctf / 100.0))
                                    k = max(0, min(len(order), k))
                                    return order[:k], order[k:]
                            cutoff = split.get('cutoff')
                            if cutoff:
                                mask_train = ser <= pd.to_datetime(cutoff)
                                return frame.index[mask_train], frame.index[~mask_train]
                except Exception as e:
                    print(f"[DatqDetail] OOT split failed: {e}, falling back to random")
                rng = np.random.RandomState(42)
                m = rng.rand(len(frame)) < 0.7
                return frame.index[m], frame.index[~m]

            tr_idx, te_idx = _build_split_indices(df)
            class _Splitter:
                def __init__(self, tr, te):
                    self.train_data_indeces = tr
                    self.test_data_indeces = te

            dq = Data_Quality(_ArgDecl(target_name), _VarDemystify(df, target_name), data_splitter=_Splitter(tr_idx, te_idx))
            dq.feature_psi(df)

            detailed = getattr(dq, 'feature_psi_detailed_dict', {})
            if column not in detailed:
                return Response({'error': f'No PSI detail computed for {column}'}, status=status.HTTP_400_BAD_REQUEST)

            psi_value, psi_table = detailed[column]
            try:
                psi_table = psi_table.reset_index()
                # Ensure a consistent column name for the bin/category label
                bin_col = psi_table.columns[0]
                psi_table = psi_table.rename(columns={bin_col: 'bin'})
                psi_records = psi_table.replace({np.nan: None}).to_dict(orient='records')
            except Exception:
                psi_records = []

            var_type = 'numerical' if column in getattr(dq.variable_demystifier, 'numerical_model_features_list', []) else (
                'categorical' if column in getattr(dq.variable_demystifier, 'categorical_model_features_list', []) else 'unknown'
            )

            # Missing ratios for context
            train_missing = float(df.loc[dq._train_idx, column].isna().mean()) if len(dq._train_idx) else 0.0
            test_missing = float(df.loc[dq._test_idx, column].isna().mean()) if len(dq._test_idx) else 0.0

            resp = {
                'file_id': file_id,
                'processed_file': processed_file,
                'variable': column,
                'variable_type': var_type,
                'psi': float(psi_value) if psi_value is not None else None,
                'psi_table': psi_records,
                'train_missing_ratio': round(train_missing, 6),
                'test_missing_ratio': round(test_missing, 6),
                'train_count': int(len(dq._train_idx) if dq._train_idx is not None else 0),
                'test_count': int(len(dq._test_idx) if dq._test_idx is not None else 0),
            }

            return Response(resp, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
