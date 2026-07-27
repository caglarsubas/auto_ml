"""CRISP-DM cycle helpers: business understanding, export pack, monitoring, iteration clone."""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


DEFAULT_SUCCESS_CRITERIA: Dict[str, Any] = {
    'primary_metric': 'roc_auc',
    'direction': 'maximize',
    'floor': None,
    'cost_matrix': {'fn_cost': 1.0, 'fp_cost': 1.0},
}


def empty_business_understanding() -> Dict[str, Any]:
    return {
        'objective': '',
        'decision_use_case': '',
        'prediction_horizon': '',
        'population': '',
        'exclusions': '',
        'target_contract': {
            'event_definition': '',
            'good_bad_window': '',
            'target_column': '',
        },
        'assumptions': '',
        'regulatory_notes': '',
        'forbidden_features': [],
        'success_criteria': dict(DEFAULT_SUCCESS_CRITERIA),
        'hard_block_modeling_without_criteria': False,
        'completed': False,
    }


def normalize_business_understanding(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = empty_business_understanding()
    if not isinstance(raw, dict):
        return base
    for k in ('objective', 'decision_use_case', 'prediction_horizon', 'population',
              'exclusions', 'assumptions', 'regulatory_notes'):
        if raw.get(k) is not None:
            base[k] = str(raw.get(k) or '')
    tc = raw.get('target_contract') if isinstance(raw.get('target_contract'), dict) else {}
    for k in ('event_definition', 'good_bad_window', 'target_column'):
        if tc.get(k) is not None:
            base['target_contract'][k] = str(tc.get(k) or '')
    ff = raw.get('forbidden_features')
    if isinstance(ff, list):
        base['forbidden_features'] = [str(x) for x in ff if str(x).strip()]
    sc = raw.get('success_criteria') if isinstance(raw.get('success_criteria'), dict) else {}
    metric = str(sc.get('primary_metric') or base['success_criteria']['primary_metric']).strip().lower()
    base['success_criteria']['primary_metric'] = metric or 'roc_auc'
    direction = str(sc.get('direction') or 'maximize').strip().lower()
    base['success_criteria']['direction'] = 'minimize' if direction == 'minimize' else 'maximize'
    floor = sc.get('floor', None)
    try:
        base['success_criteria']['floor'] = float(floor) if floor is not None and floor != '' else None
    except (TypeError, ValueError):
        base['success_criteria']['floor'] = None
    cm = sc.get('cost_matrix') if isinstance(sc.get('cost_matrix'), dict) else {}
    try:
        base['success_criteria']['cost_matrix'] = {
            'fn_cost': float(cm.get('fn_cost', 1.0)),
            'fp_cost': float(cm.get('fp_cost', 1.0)),
        }
    except (TypeError, ValueError):
        pass
    base['hard_block_modeling_without_criteria'] = bool(raw.get('hard_block_modeling_without_criteria'))
    base['completed'] = bool(raw.get('completed')) or bool(str(base.get('objective') or '').strip())
    return base


def empty_crisp_dm_state(iteration: int = 1) -> Dict[str, Any]:
    return {
        'iteration_id': int(iteration),
        'phase_status': {
            'business_understanding': 'pending',
            'data_understanding': 'pending',
            'data_preparation': 'pending',
            'modeling': 'pending',
            'evaluation': 'pending',
            'deployment': 'pending',
            'monitoring': 'pending',
        },
        'business_understanding': empty_business_understanding(),
        'governance_checks': {},
        'champion': None,
        'monitoring': None,
        'parent_run_id': None,
    }


def merge_crisp_dm(existing: Optional[Dict[str, Any]], patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = empty_crisp_dm_state()
    if isinstance(existing, dict):
        state['iteration_id'] = int(existing.get('iteration_id') or 1)
        if isinstance(existing.get('phase_status'), dict):
            state['phase_status'].update({k: v for k, v in existing['phase_status'].items() if k in state['phase_status']})
        state['business_understanding'] = normalize_business_understanding(existing.get('business_understanding'))
        if isinstance(existing.get('governance_checks'), dict):
            state['governance_checks'] = dict(existing['governance_checks'])
        state['champion'] = existing.get('champion')
        state['monitoring'] = existing.get('monitoring')
        state['parent_run_id'] = existing.get('parent_run_id')
    if isinstance(patch, dict):
        if 'iteration_id' in patch:
            state['iteration_id'] = int(patch['iteration_id'] or state['iteration_id'])
        if isinstance(patch.get('phase_status'), dict):
            state['phase_status'].update({k: v for k, v in patch['phase_status'].items() if k in state['phase_status']})
        if 'business_understanding' in patch:
            state['business_understanding'] = normalize_business_understanding(patch.get('business_understanding'))
        if isinstance(patch.get('governance_checks'), dict):
            state['governance_checks'] = {**state['governance_checks'], **patch['governance_checks']}
        if 'champion' in patch:
            state['champion'] = patch.get('champion')
        if 'monitoring' in patch:
            state['monitoring'] = patch.get('monitoring')
        if 'parent_run_id' in patch:
            state['parent_run_id'] = patch.get('parent_run_id')
    # Derive BU phase completion
    bu = state['business_understanding']
    if bu.get('completed') and str(bu.get('objective') or '').strip():
        state['phase_status']['business_understanding'] = 'completed'
    return state


def evaluate_success_floors(metrics: Dict[str, Any], success_criteria: Dict[str, Any]) -> Dict[str, Any]:
    """Compare evaluation metrics against BU success floors."""
    sc = success_criteria or DEFAULT_SUCCESS_CRITERIA
    metric = str(sc.get('primary_metric') or 'roc_auc').lower()
    direction = str(sc.get('direction') or 'maximize').lower()
    floor = sc.get('floor')
    value = None
    if isinstance(metrics, dict):
        value = metrics.get(metric)
        if value is None and metric == 'roc_auc':
            value = metrics.get('auc')
    result = {
        'metric': metric,
        'direction': direction,
        'floor': floor,
        'value': float(value) if value is not None and np.isfinite(float(value)) else None,
        'passed': None,
        'message': '',
    }
    if floor is None or result['value'] is None:
        result['message'] = 'No floor set or metric unavailable'
        return result
    v, f = float(result['value']), float(floor)
    if direction == 'minimize':
        result['passed'] = v <= f
    else:
        result['passed'] = v >= f
    result['message'] = (
        f"{metric}={v:.4f} {'meets' if result['passed'] else 'misses'} floor {f:.4f}"
    )
    return result


def expected_cost_table(
    threshold_rows: List[Dict[str, Any]],
    fn_cost: float = 1.0,
    fp_cost: float = 1.0,
) -> List[Dict[str, Any]]:
    """Attach expected business cost to threshold sweep rows when counts exist."""
    out = []
    for row in threshold_rows or []:
        r = dict(row)
        fn = r.get('fn')
        fp = r.get('fp')
        try:
            if fn is not None and fp is not None:
                r['expected_cost'] = float(fn) * float(fn_cost) + float(fp) * float(fp_cost)
            else:
                # Approximate from rates if present
                recall = float(r.get('recall')) if r.get('recall') is not None else None
                precision = float(r.get('precision')) if r.get('precision') is not None else None
                r['expected_cost'] = None
                if recall is not None and precision is not None:
                    # unit-normalized proxy: (1-recall)*fn + (1-precision)*fp
                    r['expected_cost_proxy'] = (1.0 - recall) * float(fn_cost) + (1.0 - precision) * float(fp_cost)
        except (TypeError, ValueError):
            r['expected_cost'] = None
        out.append(r)
    return out


def recommend_threshold_by_cost(cost_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    keyed = [r for r in cost_rows if r.get('expected_cost') is not None or r.get('expected_cost_proxy') is not None]
    if not keyed:
        return None
    return min(
        keyed,
        key=lambda r: float(r['expected_cost'] if r.get('expected_cost') is not None else r['expected_cost_proxy']),
    )


def psi_shift_recommendation(psi_value: Optional[float]) -> str:
    """Map PSI/CSI to keep / investigate / drop recommendation."""
    if psi_value is None or (isinstance(psi_value, float) and not np.isfinite(psi_value)):
        return 'investigate'
    v = float(psi_value)
    if v > 0.25:
        return 'drop'
    if v > 0.10:
        return 'investigate'
    return 'keep'


def enrich_datq_with_recommendations(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in records or []:
        r = dict(row)
        psi = r.get('PSI')
        csi = r.get('CSI')
        score = psi if psi is not None and (not isinstance(psi, float) or np.isfinite(psi)) else csi
        try:
            score_f = float(score) if score is not None and str(score) not in ('', 'nan', 'None') else None
        except (TypeError, ValueError):
            score_f = None
        rec = psi_shift_recommendation(score_f)
        r['Shift_Recommendation'] = rec
        decision = str(r.get('Datq_Decision') or '')
        if not decision or decision == 'nan':
            r['Datq_Decision'] = {
                'keep': 'Stable', 'investigate': 'Investigate', 'drop': 'Shift',
            }.get(rec, 'Investigate')
        out.append(r)
    return out


def build_crisp_export_zip(
    media_root: str,
    file_id: int,
    *,
    business_understanding: Optional[Dict[str, Any]] = None,
    crisp_dm: Optional[Dict[str, Any]] = None,
) -> Tuple[bytes, str]:
    """Assemble audit zip: dictionary/DATQ/purifier/split/lineage/BU."""
    buf = io.BytesIO()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f'crisp_pack_{file_id}_{stamp}.zip'

    candidates = [
        ('datq_summary.json', os.path.join(media_root, 'data_quality', f'{file_id}_datq_summary.json')),
        ('split.json', os.path.join(media_root, 'splits', f'{file_id}_split.json')),
        ('lineage.json', os.path.join(media_root, 'lineage', f'{file_id}_lineage.json')),
        ('modeling_status.json', os.path.join(media_root, 'modeling', f'{file_id}_status.json')),
        ('evaluation.json', os.path.join(media_root, 'evaluation', f'{file_id}_evaluation.json')),
        ('model_card.json', os.path.join(media_root, 'evaluation', f'{file_id}_model_card.json')),
        ('hyperparam.json', os.path.join(media_root, 'hyperparam_results', f'{file_id}_hyperparam.json')),
        ('sfs_results.json', os.path.join(media_root, 'sfs_results', f'{file_id}_sfs_results.json')),
        ('preprocess_config.json', os.path.join(media_root, 'configs', f'preprocess_{file_id}.json')),
    ]
    # purifier artifacts (glob-like)
    purifier_dir = os.path.join(media_root, 'purifier')
    if os.path.isdir(purifier_dir):
        for fn in os.listdir(purifier_dir):
            if str(file_id) in fn and fn.endswith('.json'):
                candidates.append((f'purifier/{fn}', os.path.join(purifier_dir, fn)))

    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            'business_understanding.json',
            json.dumps(normalize_business_understanding(business_understanding), indent=2),
        )
        zf.writestr('crisp_dm.json', json.dumps(merge_crisp_dm(crisp_dm), indent=2))
        zf.writestr(
            'README.txt',
            'DeclarAI CRISP-DM export pack\n'
            f'file_id={file_id}\n'
            f'generated_utc={stamp}\n'
            'Contents: business understanding, DATQ, split, lineage, modeling/eval artifacts when present.\n',
        )
        for arc, path in candidates:
            if os.path.exists(path):
                zf.write(path, arcname=arc)
    return buf.getvalue(), name


def detect_sequential_pattern_candidates(
    df: pd.DataFrame,
    *,
    time_col: Optional[str] = None,
    id_cols: Optional[List[str]] = None,
    max_pairs: int = 25,
) -> List[Dict[str, Any]]:
    """MVP causality/sequential flags: near-duplicate rows with few differing columns over time."""
    if df is None or df.empty or len(df) < 4:
        return []
    work = df.copy()
    tcol = time_col
    if not tcol:
        for c in work.columns:
            cl = str(c).lower()
            if 'date' in cl or 'time' in cl or 'datetime' in cl:
                tcol = c
                break
    if tcol and tcol in work.columns:
        try:
            work = work.sort_values(tcol)
        except Exception:
            pass
    # Sample for cost
    if len(work) > 800:
        work = work.iloc[:: max(1, len(work) // 800)].copy()
    feature_cols = [c for c in work.columns if c != tcol]
    if id_cols:
        feature_cols = [c for c in feature_cols if c not in id_cols]
    if len(feature_cols) < 2:
        return []

    # Hash rows on all-but-one feature groups is expensive; use pairwise on consecutive rows
    candidates: List[Dict[str, Any]] = []
    vals = work[feature_cols].astype(str).fillna('__NA__').values
    idx = list(work.index)
    for i in range(1, len(vals)):
        a, b = vals[i - 1], vals[i]
        diffs = [feature_cols[j] for j in range(len(feature_cols)) if a[j] != b[j]]
        n_diff = len(diffs)
        if 1 <= n_diff <= 3:
            candidates.append({
                'row_a': str(idx[i - 1]),
                'row_b': str(idx[i]),
                'n_diff': n_diff,
                'changed_features': diffs,
                'time_col': tcol,
                'rationale': (
                    f'Consecutive rows differ in {n_diff} feature(s) only — '
                    'possible sequential / near-duplicate pattern.'
                ),
            })
        if len(candidates) >= max_pairs:
            break
    return candidates


def compute_monitoring_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    *,
    score_col: Optional[str] = None,
    target_col: Optional[str] = None,
    baseline_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Offline monitoring: feature PSI vs reference + optional score/target drift."""
    from modeling.sfs_utils import calculate_psi

    common = [c for c in reference_df.columns if c in current_df.columns]
    feature_psi = []
    for c in common[:80]:
        try:
            ref = pd.to_numeric(reference_df[c], errors='coerce')
            cur = pd.to_numeric(current_df[c], errors='coerce')
            if ref.notna().sum() < 5 or cur.notna().sum() < 5:
                continue
            psi = float(calculate_psi(ref.dropna().values, cur.dropna().values))
            feature_psi.append({
                'feature': c,
                'psi': psi,
                'recommendation': psi_shift_recommendation(psi),
            })
        except Exception:
            continue
    feature_psi.sort(key=lambda x: -(x.get('psi') or 0))
    n_shift = sum(1 for x in feature_psi if x.get('recommendation') == 'drop')
    n_invest = sum(1 for x in feature_psi if x.get('recommendation') == 'investigate')

    score_drift = None
    if score_col and score_col in reference_df.columns and score_col in current_df.columns:
        try:
            score_drift = {
                'psi': float(calculate_psi(
                    pd.to_numeric(reference_df[score_col], errors='coerce').dropna().values,
                    pd.to_numeric(current_df[score_col], errors='coerce').dropna().values,
                )),
            }
        except Exception:
            score_drift = None

    metric_drift = None
    if target_col and score_col and target_col in current_df.columns and score_col in current_df.columns:
        try:
            from sklearn.metrics import roc_auc_score
            y = pd.to_numeric(current_df[target_col], errors='coerce')
            s = pd.to_numeric(current_df[score_col], errors='coerce')
            mask = y.notna() & s.notna()
            if mask.sum() > 10 and y[mask].nunique() > 1:
                auc = float(roc_auc_score(y[mask], s[mask]))
                base = None
                if isinstance(baseline_metrics, dict):
                    base = baseline_metrics.get('roc_auc') or baseline_metrics.get('auc')
                metric_drift = {
                    'current_roc_auc': auc,
                    'baseline_roc_auc': float(base) if base is not None else None,
                    'delta': (auc - float(base)) if base is not None else None,
                }
        except Exception:
            metric_drift = None

    alert = n_shift > 0 or (score_drift and score_drift.get('psi', 0) > 0.25)
    return {
        'status': 'alert' if alert else 'ok',
        'n_features_scanned': len(feature_psi),
        'n_shift': n_shift,
        'n_investigate': n_invest,
        'top_feature_psi': feature_psi[:20],
        'score_drift': score_drift,
        'metric_drift': metric_drift,
        'message': (
            f'Monitoring {"ALERT" if alert else "OK"}: '
            f'{n_shift} shifted features, {n_invest} to investigate.'
        ),
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
