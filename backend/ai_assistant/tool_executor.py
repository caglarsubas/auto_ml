"""
Tool executor for AI Assistant function calls.

Resolves OpenAI tool_calls by reading pipeline artifacts from the Redis cache.
Each handler retrieves the relevant data and returns a formatted string that
gets injected back into the LLM conversation as a tool response.
"""

import json
import logging
from typing import Any, Optional

from .prometa_config import tool as prometa_tool

from .cache import (
    cache_get,
    ARTIFACT_SPLIT_VALIDATION,
    ARTIFACT_DQ_SUMMARY,
    ARTIFACT_FEATURE_STATS,
    ARTIFACT_VIF_DECOMPOSITION,
    ARTIFACT_ENCODING_PLAN,
    ARTIFACT_SELECTED_FEATURES,
    ARTIFACT_SHAP_DETAILS,
    ARTIFACT_SFS_RESULTS,
    ARTIFACT_CV_RESULTS,
    ARTIFACT_PIPELINE_NOTES,
    ARTIFACT_PIPELINE_CONFIG,
    ARTIFACT_DATA_DICTIONARY,
)

logger = logging.getLogger(__name__)


def _fmt(value: Any) -> str:
    """Format a numeric value for display."""
    if value is None:
        return '—'
    if isinstance(value, float):
        return f'{value:.4f}'
    return str(value)


def _not_available(name: str) -> str:
    return f"No {name} data is available in the cache. The user may not have completed this pipeline step yet."


# ---------------------------------------------------------------------------
# Individual tool handlers
# ---------------------------------------------------------------------------

def _handle_get_split_validation(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_SPLIT_VALIDATION)
    if not data:
        return _not_available("split validation")
    splits = data.get('splits', [])
    lines = [f"Target column: {data.get('target_column', '?')}"]
    for sp in splits:
        lines.append(
            f"  {sp.get('name','?')}: n={sp.get('count','?')}, "
            f"target_mean={_fmt(sp.get('target_mean'))}, "
            f"target=0: {sp.get('label_counts', {}).get('0', '?')}, "
            f"target=1: {sp.get('label_counts', {}).get('1', '?')}"
        )
    return '\n'.join(lines)


def _handle_get_dq_summary(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_DQ_SUMMARY)
    if not data:
        return _not_available("data quality summary")
    features = data if isinstance(data, list) else data.get('summary', [])
    feature_filter = args.get('feature')
    if feature_filter:
        features = [f for f in features if f.get('Variable', '') == feature_filter]
        if not features:
            return f"Feature '{feature_filter}' not found in the data quality summary."
    lines = [f"Data Quality Summary ({len(features)} features):"]
    for f in features[:50]:
        lines.append(
            f"  {f.get('Variable','?')}: type={f.get('Variable_Type','?')}, "
            f"PSI={_fmt(f.get('PSI'))}, "
            f"missing%={_fmt(f.get('Missing_Pct', f.get('missing_pct')))}, "
            f"decision={f.get('Datq_Decision', '?')}"
        )
    if len(features) > 50:
        lines.append(f"  ... and {len(features) - 50} more features")
    return '\n'.join(lines)


def _handle_get_feature_stats(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_FEATURE_STATS)
    if not data:
        return _not_available("feature statistics")
    feature = args.get('feature', '')
    if not feature:
        return "Please specify which feature you want stats for."
    before = data.get('before', {}).get(feature)
    after = data.get('after', {}).get(feature)
    if not before and not after:
        return f"No statistics found for feature '{feature}'."
    lines = [f"Feature: {feature}"]
    if before:
        lines.append(f"  Before preprocessing: mean={_fmt(before.get('mean'))}, "
                      f"std={_fmt(before.get('std'))}, min={_fmt(before.get('min'))}, "
                      f"max={_fmt(before.get('max'))}, missing%={_fmt(before.get('missing_pct'))}")
    if after:
        lines.append(f"  After preprocessing: mean={_fmt(after.get('mean'))}, "
                      f"std={_fmt(after.get('std'))}, min={_fmt(after.get('min'))}, "
                      f"max={_fmt(after.get('max'))}, missing%={_fmt(after.get('missing_pct'))}")
    return '\n'.join(lines)


def _handle_get_vif_decomposition(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_VIF_DECOMPOSITION)
    if not data:
        return _not_available("VIF decomposition")
    feature = args.get('feature', '')
    if not feature:
        available = list(data.keys()) if isinstance(data, dict) else []
        return f"Please specify a feature. Available: {', '.join(available[:20])}"
    decomp = data.get(feature) if isinstance(data, dict) else None
    if not decomp:
        available = list(data.keys()) if isinstance(data, dict) else []
        return (f"No VIF decomposition for '{feature}'. "
                f"Available features: {', '.join(available[:20])}")
    lines = [f"VIF Decomposition for {feature} (overall VIF={_fmt(decomp.get('vif'))}):"]
    for c in decomp.get('top_correlations', []):
        lines.append(
            f"  ↔ {c.get('feature','?')}: |corr|={_fmt(c.get('correlation'))}, "
            f"signed_r={_fmt(c.get('signed_correlation'))}, "
            f"vif_drop={_fmt(c.get('vif_drop'))}"
        )
    return '\n'.join(lines)


def _handle_get_encoding_plan(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_ENCODING_PLAN)
    if not data:
        return _not_available("encoding plan")
    features = data if isinstance(data, list) else data.get('plan', [])
    lines = [f"Encoding Plan ({len(features)} categorical features):"]
    for f in features:
        lines.append(
            f"  {f.get('feature','?')}: lom={f.get('user_lom','?')}, "
            f"nunique={f.get('nunique','?')}, "
            f"strategy={f.get('fallback_strategy', f.get('primary_strategy', '?'))}"
        )
    return '\n'.join(lines)


def _handle_get_selected_features(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_SELECTED_FEATURES)
    if not data:
        return _not_available("selected features")
    features = data if isinstance(data, list) else data.get('features', [])
    top_n = args.get('top_n')
    if top_n and isinstance(top_n, int):
        features = features[:top_n]
    lines = [f"Selected Features ({len(features)} shown):"]
    for f in features:
        lines.append(
            f"  {f.get('feature','?')}: combined={_fmt(f.get('combined_score'))}, "
            f"SHAP%={_fmt(f.get('shap_percentile'))}, "
            f"Gain%={_fmt(f.get('gain_percentile'))}, "
            f"VIF={_fmt(f.get('vif'))}, "
            f"usage={f.get('usage', 'keep')}"
        )
    return '\n'.join(lines)


def _handle_get_shap_details(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_SHAP_DETAILS)
    if not data:
        return _not_available("SHAP details")
    features = data if isinstance(data, list) else data.get('features', [])
    top_n = args.get('top_n')
    if top_n and isinstance(top_n, int):
        features = features[:top_n]
    lines = [f"SHAP Feature Impact ({len(features)} shown):"]
    for f in features:
        lines.append(
            f"  {f.get('feature','?')}: |impact|={_fmt(f.get('impact'))}, "
            f"signed={_fmt(f.get('signed_impact'))}"
        )
    return '\n'.join(lines)


def _handle_get_sfs_results(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_SFS_RESULTS)
    if not data:
        return _not_available("SFS results")
    direction_filter = args.get('direction')
    lines = []
    # Config
    cfg = data.get('config', {})
    if cfg:
        sc = cfg.get('stopping_criteria', {})
        metrics = sc.get('metrics', [])
        lines.append("SFS Configuration:")
        for m in metrics:
            lines.append(f"  Stopping: {m.get('metric','?')}, pct_change={m.get('pct_change','?')}%")
        lines.append(f"  Min features: {sc.get('min_features','?')}, Max: {sc.get('max_features','?')}")
        lines.append(f"  Top-K: {cfg.get('top_k','?')}")
    # Results
    for direction in ['forward', 'backward', 'forward_from_backward']:
        if direction_filter and direction != direction_filter:
            continue
        steps = data.get(direction, [])
        if not steps:
            continue
        last = steps[-1] if steps else {}
        remaining = last.get('remaining', last.get('selected_features', []))
        rem_count = len(remaining) if isinstance(remaining, list) else remaining
        lines.append(f"\n{direction.replace('_',' ').title()} ({len(steps)} steps, "
                      f"{rem_count} features after last step):")
        for s in steps:
            feat = s.get('feature_name', '?')
            metric_val = s.get('cv_roc_auc', s.get('metric_value', '?'))
            lines.append(f"  Step {s.get('step','?')}: {feat}, metric={_fmt(metric_val)}")
    return '\n'.join(lines) if lines else _not_available("SFS results")


def _handle_get_cv_results(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_CV_RESULTS)
    if not data:
        return _not_available("cross-validation results")
    lines = [
        f"Cross-Validation Results:",
        f"  ROC-AUC: {_fmt(data.get('roc_auc_mean'))} ± {_fmt(data.get('roc_auc_std'))}",
        f"  PR-AUC: {_fmt(data.get('pr_auc_mean'))} ± {_fmt(data.get('pr_auc_std'))}",
        f"  Folds: {data.get('n_splits', '?')}",
    ]
    pr_curve = data.get('pr_curve', {})
    baseline = pr_curve.get('baseline')
    if baseline is not None:
        lines.append(f"  Target rate (baseline): {_fmt(baseline)} ({baseline*100:.2f}%)")
    return '\n'.join(lines)


def _handle_get_pipeline_notes(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_PIPELINE_NOTES)
    if not data:
        return "No pipeline notes have been saved."
    lines = ["Pipeline Notes:"]
    for position, content in data.items():
        if content and content.strip():
            lines.append(f"  [{position}]: {content.strip()}")
    return '\n'.join(lines) if len(lines) > 1 else "No pipeline notes have been saved."


def _handle_get_pipeline_config(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_PIPELINE_CONFIG)
    if not data:
        return _not_available("pipeline configuration")
    lines = [
        "Pipeline Configuration:",
        f"  Pipeline type: {data.get('pipeline_type', '?')}",
        f"  Target definition: {data.get('target_definition', '?')}",
        f"  Split strategy: {data.get('split_strategy', '?')}",
        f"  Rows: {data.get('row_count_before', '?')} → {data.get('row_count_after', '?')}",
        f"  Rows removed: {data.get('rows_removed', '?')}",
    ]
    purifier = data.get('purifier_steps', [])
    if purifier:
        lines.append(f"  Purifier steps: {', '.join(str(s) for s in purifier)}")
    return '\n'.join(lines)


def _handle_get_data_dictionary(file_id: int, args: dict) -> str:
    data = cache_get(file_id, ARTIFACT_DATA_DICTIONARY)
    if not data:
        return _not_available("data dictionary")
    features = data if isinstance(data, list) else data.get('features', [])
    feature_filter = args.get('feature')
    if feature_filter:
        features = [f for f in features if f.get('Feature_Name', f.get('feature', '')) == feature_filter]
        if not features:
            return f"Feature '{feature_filter}' not found in the data dictionary."
    lines = [f"Data Dictionary ({len(features)} features):"]
    for f in features:
        name = f.get('Feature_Name', f.get('feature', '?'))
        desc = f.get('Feature_Description', f.get('description', '—'))
        dtype = f.get('Data_Type', f.get('data_type', '?'))
        nunique = f.get('Unique_Values', f.get('nunique', '?'))
        lom = f.get('Level_of_Measurement', f.get('lom', ''))
        excluded = f.get('excluded', False)
        usage = 'EXCLUDED' if excluded else 'included'
        lines.append(f"  {name}: {desc} (type={dtype}, nunique={nunique}, lom={lom}, {usage})")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS = {
    'get_split_validation': _handle_get_split_validation,
    'get_dq_summary': _handle_get_dq_summary,
    'get_feature_stats': _handle_get_feature_stats,
    'get_vif_decomposition': _handle_get_vif_decomposition,
    'get_encoding_plan': _handle_get_encoding_plan,
    'get_selected_features': _handle_get_selected_features,
    'get_shap_details': _handle_get_shap_details,
    'get_sfs_results': _handle_get_sfs_results,
    'get_cv_results': _handle_get_cv_results,
    'get_pipeline_notes': _handle_get_pipeline_notes,
    'get_pipeline_config': _handle_get_pipeline_config,
    'get_data_dictionary': _handle_get_data_dictionary,
}


@prometa_tool(name="rag-tool-dispatch")
def execute_tool_call(file_id: int, tool_name: str, arguments: dict) -> str:
    """
    Execute a single tool call and return the result as a string.
    Traced as a Prometa tool span so each Redis lookup is visible.

    Args:
        file_id: The pipeline file ID for cache lookups.
        tool_name: The function name from the OpenAI tool_call.
        arguments: The parsed arguments dict from the tool_call.

    Returns:
        A human-readable string with the tool result.
    """
    handler = _HANDLERS.get(tool_name)
    if not handler:
        return f"Unknown tool: {tool_name}"
    try:
        result = handler(file_id, arguments)
        logger.info("Tool %s executed for file_id=%s (result length=%d)", tool_name, file_id, len(result))
        return result
    except Exception as exc:
        logger.error("Tool execution error (%s): %s", tool_name, exc)
        return f"Error executing {tool_name}: {exc}"
