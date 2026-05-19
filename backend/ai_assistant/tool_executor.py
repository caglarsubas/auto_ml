"""
Tool executor for AI Assistant function calls.

Resolves OpenAI tool_calls by reading pipeline artifacts from the Redis cache.
Each handler retrieves the relevant data and returns a formatted string that
gets injected back into the LLM conversation as a tool response.
"""

import json
import logging
from typing import Any, Optional

from .prometa_config import tool as prometa_tool, set_span_attr, span_timer
from .skill_registry import get_skill, list_skills

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


def _stamp_read_attrs(artifact: str, data: Any) -> None:
    """Stamp common attributes on a ``cache-read:<artifact>`` span."""
    set_span_attr('declarai.cache.artifact', artifact)
    if data is None:
        set_span_attr('declarai.cache.hit', False)
        return
    set_span_attr('declarai.cache.hit', True)
    if isinstance(data, list):
        set_span_attr('declarai.cache.shape', 'list')
        set_span_attr('declarai.cache.length', len(data))
    elif isinstance(data, dict):
        set_span_attr('declarai.cache.shape', 'dict')
        set_span_attr('declarai.cache.keys', ','.join(list(data.keys())[:20]))


# ---------------------------------------------------------------------------
# Raw readers (server-side + LLM-initiated callers share these)
# ---------------------------------------------------------------------------
# Each raw reader wraps a ``cache_get`` with its own ``cache-read:<artifact>``
# span.  This gives the trace waterfall a visible, named row per artifact
# regardless of whether the read was triggered by the LLM (via
# ``tool-call`` -> handler -> reader) or by the server prefetch path
# (``_build_slim_context`` -> reader).  The underlying ``cache_get`` call
# produces a nested ``redis-get`` child span.

@prometa_tool(name="cache-read:split_validation")
def read_split_validation(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_SPLIT_VALIDATION)
        _stamp_read_attrs(ARTIFACT_SPLIT_VALIDATION, data)
        return data


@prometa_tool(name="cache-read:dq_summary")
def read_dq_summary(file_id: int) -> Optional[Any]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_DQ_SUMMARY)
        _stamp_read_attrs(ARTIFACT_DQ_SUMMARY, data)
        return data


@prometa_tool(name="cache-read:feature_stats")
def read_feature_stats(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_FEATURE_STATS)
        _stamp_read_attrs(ARTIFACT_FEATURE_STATS, data)
        return data


@prometa_tool(name="cache-read:vif_decomposition")
def read_vif_decomposition(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_VIF_DECOMPOSITION)
        _stamp_read_attrs(ARTIFACT_VIF_DECOMPOSITION, data)
        return data


@prometa_tool(name="cache-read:encoding_plan")
def read_encoding_plan(file_id: int) -> Optional[Any]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_ENCODING_PLAN)
        _stamp_read_attrs(ARTIFACT_ENCODING_PLAN, data)
        return data


@prometa_tool(name="cache-read:selected_features")
def read_selected_features(file_id: int) -> Optional[Any]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_SELECTED_FEATURES)
        _stamp_read_attrs(ARTIFACT_SELECTED_FEATURES, data)
        return data


@prometa_tool(name="cache-read:shap_details")
def read_shap_details(file_id: int) -> Optional[Any]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_SHAP_DETAILS)
        _stamp_read_attrs(ARTIFACT_SHAP_DETAILS, data)
        return data


@prometa_tool(name="cache-read:sfs_results")
def read_sfs_results(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_SFS_RESULTS)
        _stamp_read_attrs(ARTIFACT_SFS_RESULTS, data)
        return data


# ---------------------------------------------------------------------------
# v2.35.0 — live SFS run-state reader (closes the "assistant unaware SFS is
# running" bug shown in the screenshot for 2026-05-19's ToDoS entry).
# ---------------------------------------------------------------------------
#
# Why this reader is NOT a Redis ``cache-read:*``:
# ──────────────────────────────────────────────
# Pipeline artifacts (DQ summary, encoding plan, SFS *results*, ...) are
# pushed to Redis by the frontend AFTER each step completes — that's why
# their readers are ``cache-read:*``.  But SFS *progress* lives in two
# stores that the frontend never sees:
#
#   1. ``modeling.views.SFS_PROGRESS`` (process-local Python dict) —
#      the background SFS thread updates ``progress`` / ``message`` /
#      ``completed_steps`` here on every step.  Lost on server restart.
#
#   2. ``MEDIA_ROOT/sfs_results/{file_id}_sfs_results.json`` — the
#      same background thread dumps a status field plus partial results
#      here after each completed step (see ``_save_intermediate``).
#      Survives server restart but lags one step behind in-memory.
#
# When a chat turn arrives mid-SFS, the assistant's slim-context
# builder used to read ``cache_get('sfs_results')`` and find either
# nothing (SFS just started) or stale data (previous run) — then the
# LLM cheerfully reported "SFS is not running / no results are available
# yet" while the UI showed step 8/68 of backward elimination.
#
# This reader unifies the two state stores under a single canonical
# shape so ``_build_slim_context`` can inject a ground-truth status
# preamble on every turn, and ``start_sfs`` can refuse to spawn a
# duplicate run.
#
# Status semantics (mirror ``modeling.views.SFSStatusView``):
#   * ``running``        in-memory says running and thread is alive
#   * ``completed``      in-memory says completed, OR no in-memory and disk says completed
#   * ``stopped``        user pressed Stop SFS (partial results saved)
#   * ``interrupted``    no in-memory but disk shows running — server restart killed the thread
#   * ``error``          background thread raised an exception
#   * ``not_started``    no in-memory state and no disk file
#
# We DO NOT expose this reader via the OpenAI tool schema (see
# ``tool_definitions.py``).  The slim-context preamble surfaces status
# proactively on every turn — making the LLM call a tool just to learn
# "is SFS running" would waste a tool round and the corresponding
# tokens.  ``_handle_get_sfs_results`` does call this reader when the
# LLM asks for results (see below) so a status header lands at the
# top of the rendered output.

_SFS_TERMINAL_STATUSES = frozenset({'completed', 'stopped', 'error'})


@prometa_tool(name="state-read:sfs_status")
def read_sfs_status(file_id: int) -> dict:
    """Return the current SFS run-state for ``file_id``.

    Always returns a dict (never ``None``) so callers can render
    unconditionally without null-guarding.  Shape:

        {
            'status': 'running' | 'completed' | 'stopped' |
                      'interrupted' | 'error' | 'not_started',
            'progress': float,            # 0.0..1.0
            'message': str,               # human-readable last step message
            'completed_step_count': int,  # number of steps already finished
            'duration_seconds': float | None,
            'error': str | None,
            'source': 'memory' | 'disk' | 'absent',
        }

    Precedence: in-memory ``SFS_PROGRESS`` wins (freshest), with on-disk
    JSON as the server-restart fallback.  Mirrors
    ``modeling.views.SFSStatusView`` so the assistant and the UI agree
    on what state SFS is in.
    """
    # Local import: ``modeling.views`` imports ``ai_assistant.cache``
    # transitively for tracing decorators; importing it at module load
    # would create a circular dependency.  Inside a function call all
    # apps are fully loaded.
    from django.conf import settings  # noqa: WPS433
    import os as _os                  # noqa: WPS433

    default_payload = {
        'status': 'not_started',
        'progress': 0.0,
        'message': 'SFS has not been started yet',
        'completed_step_count': 0,
        'duration_seconds': None,
        'error': None,
        'source': 'absent',
    }

    # ── 1) In-memory progress dict (freshest, lost on server restart) ──
    try:
        from modeling.views import SFS_PROGRESS  # noqa: WPS433
    except Exception as exc:  # pragma: no cover — safety net
        logger.warning("read_sfs_status: cannot import SFS_PROGRESS: %s", exc)
        SFS_PROGRESS = {}

    mem = SFS_PROGRESS.get(file_id) if isinstance(SFS_PROGRESS, dict) else None
    if isinstance(mem, dict) and mem.get('status'):
        completed = mem.get('completed_steps') or []
        out = {
            **default_payload,
            'status': mem.get('status', 'running'),
            'progress': float(mem.get('progress') or 0.0),
            'message': mem.get('message') or '',
            'completed_step_count': len(completed) if isinstance(completed, list) else 0,
            'duration_seconds': mem.get('duration_seconds'),
            'error': mem.get('error'),
            'source': 'memory',
        }
        set_span_attr('declarai.sfs_status.source', 'memory')
        set_span_attr('declarai.sfs_status.status', out['status'])
        set_span_attr('declarai.sfs_status.progress', out['progress'])
        return out

    # ── 2) On-disk JSON fallback (server-restart case) ──
    try:
        sfs_path = _os.path.join(
            settings.MEDIA_ROOT, 'sfs_results', f'{file_id}_sfs_results.json',
        )
        if _os.path.exists(sfs_path):
            with open(sfs_path, 'r', encoding='utf-8') as f:
                disk = json.load(f) or {}
            disk_status = disk.get('status', 'completed')
            # If the disk file says "running" but in-memory has nothing,
            # the SFS thread was killed (server restart) — surface it
            # as ``interrupted`` to match SFSStatusView and so the LLM
            # can suggest the user click Continue.
            if disk_status == 'running':
                disk_status = 'interrupted'
            completed = []
            for direction in ('forward', 'backward', 'forward_from_backward'):
                completed.extend(disk.get(direction, []) or [])
            out = {
                **default_payload,
                'status': disk_status,
                'progress': 1.0 if disk_status == 'completed' else 0.0,
                'message': (
                    'SFS completed' if disk_status == 'completed'
                    else 'SFS was interrupted by a server restart — partial results saved'
                    if disk_status == 'interrupted'
                    else f'SFS {disk_status}'
                ),
                'completed_step_count': len(completed),
                'error': disk.get('error'),
                'source': 'disk',
            }
            set_span_attr('declarai.sfs_status.source', 'disk')
            set_span_attr('declarai.sfs_status.status', out['status'])
            return out
    except Exception as exc:
        logger.warning("read_sfs_status: disk fallback failed for file_id=%s: %s",
                       file_id, exc)

    # ── 3) Nothing on either side ──
    set_span_attr('declarai.sfs_status.source', 'absent')
    set_span_attr('declarai.sfs_status.status', 'not_started')
    return default_payload


def _format_sfs_status_line(status_payload: dict) -> Optional[str]:
    """Render a one-line status preamble for the slim-context builder.

    Returns ``None`` when status is benign (``not_started`` /
    ``completed``) — those don't need a banner because the rest of the
    context already conveys them.  Returns an emphatic line when SFS is
    actively running, stopped, interrupted, or errored — that's when
    the LLM must know to NOT propose starting SFS.
    """
    status = status_payload.get('status', 'not_started')
    if status in {'not_started', 'completed'}:
        return None

    progress = status_payload.get('progress') or 0.0
    pct = int(round(float(progress) * 100))
    completed = status_payload.get('completed_step_count', 0)
    message = (status_payload.get('message') or '').strip()

    if status == 'running':
        # Strong, capitalised wording — the LLM has historically been
        # eager to "help" by proposing to start SFS again when it sees
        # a partial-results state.  Make the banner unambiguous.
        line = (
            f'⚠ SFS IS CURRENTLY RUNNING — DO NOT propose to start SFS again. '
            f'Progress: {pct}% ({completed} steps completed). '
            f'Latest: {message}.'
        )
    elif status == 'stopped':
        line = (
            f'⚠ SFS was stopped by the user. Partial results available '
            f'({completed} steps completed). DO NOT auto-restart — wait for '
            f'the user to click Continue or explicitly request a new run.'
        )
    elif status == 'interrupted':
        line = (
            f'⚠ SFS was INTERRUPTED (likely a server restart). Partial results '
            f'on disk ({completed} steps). Suggest the user click Continue to '
            f'resume from the saved state.'
        )
    elif status == 'error':
        err = status_payload.get('error') or 'unknown error'
        line = f'⚠ SFS FAILED with error: {err}. The user may need to retry.'
    else:
        line = f'SFS status: {status}'
    return line


@prometa_tool(name="cache-read:cv_results")
def read_cv_results(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_CV_RESULTS)
        _stamp_read_attrs(ARTIFACT_CV_RESULTS, data)
        return data


@prometa_tool(name="cache-read:pipeline_notes")
def read_pipeline_notes(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_PIPELINE_NOTES)
        _stamp_read_attrs(ARTIFACT_PIPELINE_NOTES, data)
        return data


@prometa_tool(name="cache-read:pipeline_config")
def read_pipeline_config(file_id: int) -> Optional[dict]:
    with span_timer('declarai.cache'):
        data = cache_get(file_id, ARTIFACT_PIPELINE_CONFIG)
        _stamp_read_attrs(ARTIFACT_PIPELINE_CONFIG, data)
        return data


@prometa_tool(name="cache-read:data_dictionary")
def read_data_dictionary(file_id: int) -> Optional[list]:
    """Read the data dictionary and backfill missing Feature_Description
    entries from the ``DataDictionary`` DB (the single source of truth).

    The DB backfill is performed here (inside the ``cache-read:data_dictionary``
    span) rather than in every caller so that the returned value is always
    the enriched list regardless of whether the LLM dispatched the read or
    the slim-context prefetch did.  The span covers both the cache hit and
    the optional DB enrichment for easy latency attribution.
    """
    with span_timer('declarai.cache'):
        raw = cache_get(file_id, ARTIFACT_DATA_DICTIONARY)
        if raw is None:
            _stamp_read_attrs(ARTIFACT_DATA_DICTIONARY, None)
            return None
        features = raw if isinstance(raw, list) else raw.get('features', [])
        try:
            from ai_assistant.views import _enrich_dd_with_descriptions
            enriched = _enrich_dd_with_descriptions(file_id, features)
            set_span_attr('declarai.cache.enriched', True)
        except Exception as exc:
            set_span_attr('declarai.cache.enriched', False)
            set_span_attr('declarai.cache.enrich_error', str(exc)[:200])
            enriched = features
        _stamp_read_attrs(ARTIFACT_DATA_DICTIONARY, enriched)
        return enriched


# ---------------------------------------------------------------------------
# Individual tool handlers
# ---------------------------------------------------------------------------

def _handle_get_split_validation(file_id: int, args: dict) -> str:
    data = read_split_validation(file_id)
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
    data = read_dq_summary(file_id)
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
    data = read_feature_stats(file_id)
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
    data = read_vif_decomposition(file_id)
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
    data = read_encoding_plan(file_id)
    if not data:
        return _not_available("encoding plan")
    features = data if isinstance(data, list) else data.get('plan', [])
    lines = [f"Encoding Plan ({len(features)} categorical features):"]
    for f in features:
        # v2.24.0+: expose unique_values AND any existing ranking so the AI
        # can (a) propose a sensible ordinal ranking based on the actual
        # category strings instead of guessing, and (b) skip the
        # `set_ordinal_ranking` chain when a ranking is already recorded
        # (idempotency).  Cap rendered unique values at 12 to keep the
        # tool response readable — the encoding plan stores up to 50.
        uniq_raw = f.get('unique_values', []) or []
        uniq_show = uniq_raw[:12]
        uniq_str = ', '.join(str(v) for v in uniq_show)
        if len(uniq_raw) > 12:
            uniq_str += f' … (+{len(uniq_raw) - 12} more)'
        rank_raw = f.get('ranking')
        # Treat null / empty list / non-list as "no ranking set".
        if isinstance(rank_raw, list) and rank_raw:
            rank_str = ' → '.join(str(v) for v in rank_raw)
            rank_note = f', ranking=[{rank_str}]'
        else:
            needs = f.get('needs_ranking', False)
            rank_note = ', ranking=<NOT SET — call set_ordinal_ranking>' if needs else ''
        lines.append(
            f"  {f.get('feature','?')}: lom={f.get('user_lom','?')}, "
            f"nunique={f.get('nunique','?')}, "
            f"strategy={f.get('fallback_strategy', f.get('primary_strategy', '?'))}, "
            f"unique_values=[{uniq_str}]{rank_note}"
        )
    return '\n'.join(lines)


def _handle_get_selected_features(file_id: int, args: dict) -> str:
    data = read_selected_features(file_id)
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
    # v2.36.0 — closes ToDoS item #1.  Pre-v2.36.0 the frontend's
    # cache-push (model-development.component.ts) read non-existent
    # field names ``f.shap_impact`` / ``f.signed_shap_impact`` instead
    # of the actual ``f.impact`` / ``f.signed_impact`` keys, so the
    # cached ``shap_details`` artifact contained only feature names —
    # this handler dutifully rendered "|impact|=—, signed=—" for every
    # feature and the LLM could not reason about impact direction.
    # v2.36.0 fixes the FE bug AND upgrades this renderer to surface
    # impact direction in PROSE form (UP / DOWN / NEUTRAL) so the LLM
    # can quote it directly to the user without computing sign() from
    # the numeric ``signed_impact``.
    data = read_shap_details(file_id)
    if not data:
        return _not_available("SHAP details")
    features = data if isinstance(data, list) else data.get('features', [])
    top_n = args.get('top_n')
    if top_n and isinstance(top_n, int):
        features = features[:top_n]
    lines = [f"SHAP Feature Impact ({len(features)} features, sorted by |impact|):"]
    for f in features:
        feat_name = f.get('feature', '?')
        impact = f.get('impact')
        signed = f.get('signed_impact')
        # Direction is derived from sign(signed_impact).  Backend writes
        # signed_impact = mean_abs * direction where direction ∈ {-1, +1, 0}
        # (see modeling/views.py:488), so:
        #   signed > 0   → feature pushes the prediction UP
        #   signed < 0   → feature pushes the prediction DOWN
        #   signed == 0  → no monotonic pattern detected (unusual)
        if isinstance(signed, (int, float)) and signed > 0:
            direction = 'UP'
        elif isinstance(signed, (int, float)) and signed < 0:
            direction = 'DOWN'
        else:
            direction = 'NEUTRAL'
        # Tail context: VIF if available (pairs SHAP magnitude with
        # collinearity warning so the LLM can flag "high impact AND
        # high VIF" features for SFS-cluster-resolution suggestions).
        tail_parts = []
        vif = f.get('vif')
        if isinstance(vif, (int, float)):
            tail_parts.append(f"VIF={vif:.2f}")
        sm = f.get('signed_mean')
        if isinstance(sm, (int, float)):
            tail_parts.append(f"raw_mean_signed={sm:+.4f}")
        tail = (' — ' + ', '.join(tail_parts)) if tail_parts else ''
        # Prose direction first, raw numerics second — the LLM tends
        # to copy the first salient phrase per line, so leading with
        # "direction=DOWN" makes responses about impact direction
        # more accurate.
        if isinstance(signed, (int, float)):
            signed_str = f"{signed:+.4f}"
        else:
            signed_str = '—'
        lines.append(
            f"  {feat_name}: direction={direction}, "
            f"|impact|={_fmt(impact)}, signed={signed_str}{tail}"
        )
    return '\n'.join(lines)


def _handle_get_sfs_results(file_id: int, args: dict) -> str:
    # v2.35.0: surface live run-state at the very top of the rendered
    # output BEFORE returning early on missing cache data.  Pre-v2.35.0
    # this handler returned "Information about SFS results is not
    # available yet" when the Redis cache was empty, even when the
    # background SFS thread was actively running step 8/68 — see the
    # ToDoS screenshot for the in-flight bug this closes.
    status_payload = read_sfs_status(file_id)
    status_header_lines: list = []
    status_line = _format_sfs_status_line(status_payload)
    if status_line:
        status_header_lines.append(status_line)
    if status_payload.get('status') == 'running':
        # Echo the live progress numerically too — the LLM benefits
        # from seeing both the prose banner AND the structured fields
        # so it can quote them faithfully when explaining state to
        # the user.
        status_header_lines.append(
            f"  status_payload: status={status_payload.get('status')}, "
            f"progress={status_payload.get('progress'):.2f}, "
            f"completed_step_count={status_payload.get('completed_step_count')}"
        )

    data = read_sfs_results(file_id)
    if not data:
        # Even with no cached results, the status header is the most
        # useful signal we can return.  Pair it with a clear message so
        # the LLM knows the cache miss is expected (SFS still running)
        # rather than an unconfigured pipeline.
        if status_header_lines:
            status_header_lines.append(
                'No SFS step results have been pushed to the cache yet — '
                'the background thread saves them as each step completes.'
            )
            return '\n'.join(status_header_lines)
        return _not_available("SFS results")
    direction_filter = args.get('direction')
    lines = list(status_header_lines)  # status header first, if any
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
    data = read_cv_results(file_id)
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
    data = read_pipeline_notes(file_id)
    if not data:
        return "No pipeline notes have been saved."
    lines = ["Pipeline Notes:"]
    for position, content in data.items():
        if content and content.strip():
            lines.append(f"  [{position}]: {content.strip()}")
    return '\n'.join(lines) if len(lines) > 1 else "No pipeline notes have been saved."


def _handle_get_pipeline_config(file_id: int, args: dict) -> str:
    # NOTE: the dict keys below MUST match what the frontend writes in
    # ``model-development.component.ts::getPipelineConfig`` (the cache
    # producer).  v2.26.0 and earlier silently mismatched four keys
    # (``row_count_before``/``row_count_after``/``purifier_steps`` vs
    # the frontend's ``rows_before``/``rows_after``/``selected_purifier_steps``),
    # which made this tool report ``Rows: ? → ?`` and drop the purifier
    # step list entirely — the LLM, finding no real config, fell back
    # to general-toolkit hallucinations.  Keep this in sync; the
    # regression test ``test_get_pipeline_config_keys_match_frontend``
    # in ``tests/test_unit.py`` guards against drift.
    data = read_pipeline_config(file_id)
    if not data:
        return _not_available("pipeline configuration")
    lines = [
        "Pipeline Configuration:",
        f"  Pipeline type: {data.get('pipeline_type', '?')}",
        f"  Target definition: {data.get('target_definition', '?')}",
        f"  Split strategy: {data.get('split_strategy', '?')}",
        f"  Rows: {data.get('rows_before', '?')} → {data.get('rows_after', '?')}",
        f"  Rows removed: {data.get('rows_removed', '?')}",
    ]
    purifier = data.get('selected_purifier_steps', [])
    if purifier:
        lines.append(f"  Selected purifier steps ({len(purifier)}):")
        for s in purifier:
            lines.append(f"    • {s}")
    return '\n'.join(lines)


def _handle_get_data_dictionary(file_id: int, args: dict) -> str:
    # ``read_data_dictionary`` already does cache read + DB backfill inside
    # its own ``cache-read:data_dictionary`` span.
    features = read_data_dictionary(file_id)
    if features is None:
        return _not_available("data dictionary")
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


@prometa_tool(name="skill-invoke")
def _load_skill_traced(skill_name: str) -> str:
    """Load a skill's markdown body inside its own Prometa tool span.

    Each invocation produces a distinct child span in the trace so platform
    operators can see exactly when (and which) skill the assistant pulled.
    Span attributes:
      - declarai.skill.name         requested skill name
      - declarai.skill.found        whether the skill resolved
      - declarai.skill.body_chars   payload size when found
      - declarai.skill.path         on-disk location when found
      - declarai.skill.file_count   number of supplementary files discovered
      - declarai.skill.elapsed_us   elapsed time in microseconds
      - declarai.skill.elapsed_ms   elapsed time in milliseconds
    """
    with span_timer('declarai.skill'):
        set_span_attr('declarai.skill.name', skill_name)
        skill = get_skill(skill_name)
        if not skill:
            set_span_attr('declarai.skill.found', False)
            available = ', '.join(sorted(list_skills().keys())) or '(none)'
            return (f"Skill '{skill_name}' is not bundled. "
                    f"Available skills: {available}.")
        body = skill.body()
        files = skill.list_files()
        set_span_attr('declarai.skill.found', True)
        set_span_attr('declarai.skill.path', skill.path)
        set_span_attr('declarai.skill.body_chars', len(body))
        set_span_attr('declarai.skill.file_count', len(files))
        if not body:
            return f"Skill '{skill.name}' is registered but its body is empty."
        file_list = ''
        if files:
            file_list = (
                "\n\nSupplementary files (request via get_skill_file when needed):\n"
                + '\n'.join(f"  - {p}" for p in files)
            )
        return (
            f"Skill: {skill.name}\n"
            f"Description: {skill.description}\n"
            f"--- BEGIN SKILL CONTENT ---\n"
            f"{body}\n"
            f"--- END SKILL CONTENT ---"
            f"{file_list}"
        )


def _handle_get_purifier_options(file_id: int, args: dict) -> str:
    """Return the canonical 34-option purifier catalog as a structured listing.

    The catalog (preprocessing/purifier_catalog.py) is the single source of
    truth shared by the Run-Preprocessing UI checkboxes, the backend
    dispatcher in _apply_options, and the GET /api/preprocessing/options/
    endpoint.  This tool exposes it to the LLM so that when the user asks
    for a specific purifier behavior in natural language (e.g. "set the
    outlier interval to 0.05/0.95"), the assistant can look up the integer
    option ID it should pass in start_data_purifier.purifier_options.

    Unlike the other ``get_*`` tools, this one does NOT read from Redis or
    depend on file_id — the catalog is a static, code-shipped resource.

    Optional ``args``:
      * ``kind`` — filter to a single transform kind, e.g.
        ``"outlier_quantile_clip"``, ``"sparsity_drop"``,
        ``"missing_drop"``, ``"combined_drop"``, ``"corr_drop"``,
        ``"cat_outlier_merge"``, ``"col_dedup"``, ``"row_dedup"``,
        ``"zero_var_drop"``, ``"perfect_corr_drop"``.

    Result format (one line per option) matches what the LLM can copy
    directly into a start_data_purifier action:

        ID 29 [outlier_quantile_clip / outlier_num] "Outlier-cleaning
        [lower-upper] quantiles = [0.05-0.95]" range=(0.05, 0.95)
    """
    # Imported lazily so importing this module never triggers a Django
    # apps registry walk through preprocessing's own imports.
    from preprocessing.purifier_catalog import (
        PURIFIER_OPTIONS,
        DEFAULT_SELECTED_IDS,
    )

    kind_filter = (args.get('kind') or '').strip() or None
    set_span_attr('declarai.tool.purifier_options.kind_filter', kind_filter or '(all)')

    if kind_filter:
        entries = [e for e in PURIFIER_OPTIONS if e['kind'] == kind_filter]
        if not entries:
            available_kinds = sorted({e['kind'] for e in PURIFIER_OPTIONS})
            return (
                f"No purifier options match kind={kind_filter!r}. "
                f"Valid kinds: {', '.join(available_kinds)}."
            )
    else:
        entries = list(PURIFIER_OPTIONS)

    set_span_attr('declarai.tool.purifier_options.count', len(entries))

    defaults = set(DEFAULT_SELECTED_IDS)
    lines = [
        f"Data Purifier Options Catalog ({len(entries)} of {len(PURIFIER_OPTIONS)} total entries):",
    ]
    if not kind_filter:
        lines.append(
            f"Default selected IDs (pre-checked when the user lands on Data "
            f"Purifier Declaration): {sorted(DEFAULT_SELECTED_IDS)}"
        )
    lines.append(
        "Group rules: within a group only ONE option may be selected at a time "
        "(UI radio-style). Standalone options (group=None) never disable each other."
    )
    lines.append("---")

    # Group identifier → human label so the LLM doesn't have to guess.
    group_label = {
        None: 'standalone',
        1: 'corr_drop_group',
        2: 'sparsity_drop_group',
        3: 'missing_drop_group',
        4: 'combined_drop_group',
        5: 'outlier_num_group',
        6: 'outlier_cat_group',
    }

    for e in entries:
        oid = e['id']
        kind = e['kind']
        group = group_label.get(e.get('group'), str(e.get('group')))
        name = e['name']
        threshold = e.get('threshold')
        qrange = e.get('quantile_range')
        is_default = ' (DEFAULT)' if oid in defaults else ''

        bits = [f'ID {oid:>2}', f'[{kind} / {group}]', f'"{name}"']
        if threshold is not None:
            bits.append(f'threshold={threshold}')
        if qrange is not None:
            bits.append(f'quantile_range={qrange}')
        if is_default:
            bits.append(is_default.strip())
        lines.append(' '.join(bits))

    lines.append("---")
    lines.append(
        "To execute these, emit a start_data_purifier ACTION BLOCK with "
        "purifier_options=[<id>, <id>, ...]. IDs outside 1..34 are dropped "
        "silently by the action handler."
    )
    return '\n'.join(lines)


def _handle_invoke_skill(file_id: int, args: dict) -> str:
    skill_name = (args.get('skill_name') or args.get('name') or '').strip()
    if not skill_name:
        available = ', '.join(sorted(list_skills().keys())) or '(none)'
        return f"invoke_skill requires 'skill_name'. Available skills: {available}."
    return _load_skill_traced(skill_name)


@prometa_tool(name="skill-file-read")
def _load_skill_file_traced(skill_name: str, rel_path: str) -> str:
    """Read a supplementary file from a skill bundle, in its own span.

    Span attributes:
      - declarai.skill.name           skill name requested
      - declarai.skill.file_path      relative path requested
      - declarai.skill.file_found     whether the read succeeded
      - declarai.skill.file_chars     payload size when found
      - declarai.skill.elapsed_us     elapsed time in microseconds
      - declarai.skill.elapsed_ms     elapsed time in milliseconds
    """
    with span_timer('declarai.skill'):
        set_span_attr('declarai.skill.name', skill_name)
        set_span_attr('declarai.skill.file_path', rel_path)
        skill = get_skill(skill_name)
        if not skill:
            set_span_attr('declarai.skill.file_found', False)
            available = ', '.join(sorted(list_skills().keys())) or '(none)'
            return f"Skill '{skill_name}' is not bundled. Available skills: {available}."
        text, err = skill.read_file(rel_path)
        if err:
            set_span_attr('declarai.skill.file_found', False)
            listing = ', '.join(skill.list_files()) or '(none)'
            return f"Cannot read '{rel_path}' from skill '{skill.name}': {err}. Available files: {listing}."
        set_span_attr('declarai.skill.file_found', True)
        set_span_attr('declarai.skill.file_chars', len(text))
        return (
            f"Skill: {skill.name}\n"
            f"File: {rel_path}\n"
            f"--- BEGIN FILE CONTENT ---\n"
            f"{text}\n"
            f"--- END FILE CONTENT ---"
        )


def _handle_get_skill_file(file_id: int, args: dict) -> str:
    skill_name = (args.get('skill_name') or args.get('name') or '').strip()
    rel_path = (args.get('path') or args.get('file_path') or args.get('rel_path') or '').strip()
    if not skill_name or not rel_path:
        return ("get_skill_file requires both 'skill_name' and 'path'. "
                "Call invoke_skill first to see the file listing.")
    return _load_skill_file_traced(skill_name, rel_path)


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
    'get_purifier_options': _handle_get_purifier_options,
    'invoke_skill': _handle_invoke_skill,
    'get_skill_file': _handle_get_skill_file,
}


@prometa_tool(name="tool-call")
def execute_tool_call(file_id: int, tool_name: str, arguments: dict) -> str:
    """
    Execute a single LLM-initiated tool call and return the result as a string.

    Emits a ``tool-call`` span (renamed from ``rag-tool-dispatch`` — we never
    did retrieval-augmented generation; this is straight function-calling
    against a Redis cache).  Span attributes:
      - declarai.tool.name           which tool the LLM invoked
      - declarai.tool.file_id        pipeline file id
      - declarai.tool.args_keys      comma-separated argument names
      - declarai.tool.ok             whether the handler ran to completion
      - declarai.tool.unknown        True when tool_name has no registered handler
      - declarai.tool.result_chars   length of the formatted result string
      - declarai.tool.elapsed_us     elapsed time in microseconds
      - declarai.tool.elapsed_ms     elapsed time in milliseconds
      - declarai.tool.error          truncated error message on exception

    The child spans (``cache-read:<artifact>`` and ``redis-get``) make the
    actual work this dispatcher delegates to fully observable.

    Args:
        file_id: The pipeline file ID for cache lookups.
        tool_name: The function name from the OpenAI tool_call.
        arguments: The parsed arguments dict from the tool_call.

    Returns:
        A human-readable string with the tool result.
    """
    with span_timer('declarai.tool'):
        set_span_attr('declarai.tool.name', tool_name)
        set_span_attr('declarai.tool.file_id', file_id)
        set_span_attr('declarai.tool.args_keys',
                      ','.join(sorted(arguments.keys())) if arguments else '')
        handler = _HANDLERS.get(tool_name)
        if not handler:
            set_span_attr('declarai.tool.unknown', True)
            set_span_attr('declarai.tool.ok', False)
            result = f"Unknown tool: {tool_name}"
            set_span_attr('declarai.tool.result_chars', len(result))
            return result
        try:
            result = handler(file_id, arguments)
            set_span_attr('declarai.tool.ok', True)
            set_span_attr('declarai.tool.result_chars', len(result))
            logger.info("Tool %s executed for file_id=%s (result length=%d)", tool_name, file_id, len(result))
            return result
        except Exception as exc:
            set_span_attr('declarai.tool.ok', False)
            set_span_attr('declarai.tool.error', str(exc)[:200])
            logger.error("Tool execution error (%s): %s", tool_name, exc)
            result = f"Error executing {tool_name}: {exc}"
            set_span_attr('declarai.tool.result_chars', len(result))
            return result
