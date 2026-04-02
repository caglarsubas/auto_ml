"""
AI Assistant endpoint — proxies user questions + pipeline context to OpenAI GPT-5.3
and returns advisory, insight-rich responses.
"""
import json
import os
import traceback

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# ---------------------------------------------------------------------------
# System prompt that shapes the assistant persona
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are DeclarAI Assistant — a practical, hands-on AI advisor embedded in a
credit-risk / ML model-development pipeline. You are fluent in data science, machine learning,
and statistics: their jargon, terminology, technical details, and industry rule-of-thumbs.

The user is a data scientist or risk analyst building a supervised binary classification model
(typically XGBoost / LightGBM / CatBoost boosting pipeline).

═══ COMMUNICATION STYLE ═══
• Give CONCRETE, PRACTICAL, SIMPLIFIED answers — not textbook theory.
• Always ground your response in the ACTUAL DATA provided in the context.
  Quote specific feature names, values, and numbers from the context.
• Keep answers relevant to the user's CURRENT pipeline step and ongoing flow.
  Example: if user is at Data Quality, mention what to watch for before Encoding; if at
  Modeling, reference what the next SFS step could reveal.
• Use well-known rule-of-thumbs when applicable (e.g., PSI > 0.25 = population shift,
  VIF > 5 = multicollinearity concern, missing > 30% = consider dropping, etc.).
• Prefer bullet points, short paragraphs, and tables. Highlight key takeaways first.
• Do NOT deep-dive into math, formulas, or theoretical proofs UNLESS the user explicitly asks.
  If the user asks "why?" or "explain this metric", then go deeper.
• When flagging an issue, always pair it with a practical suggestion on what to do about it.
• Do NOT hallucinate data — only discuss what is provided in the context.

═══ PIPELINE STAGES ═══
1. Data Declaration — upload, preview, data dictionary
2. Data Purifier — preprocessing: missing value handling, outlier removal, constant/quasi-constant drops
3. Data Quality Summary — PSI/CSI stability, distribution stats, missing %, Model_Usage flags
4. Categorical Feature Encoding — native categorical handling + fallback strategies, LOM assignment
5. Modeling — cross-validation (ROC-AUC, PR-AUC), SHAP beeswarm, feature importance, selected features
6. Sequential Feature Selection (SFS) — forward, backward, forward-from-backward search
"""


@method_decorator(csrf_exempt, name='dispatch')
class AIAssistantView(APIView):
    """
    POST /api/ai-assistant/chat/
    Body: {
        "message": "user question",
        "context": { ... pipeline section data ... },
        "section": "data_quality|encoding|cv|shap|selected_features|sfs",
        "history": [ {"role": "user"|"assistant", "content": "..."}, ... ]
    }
    """

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            user_message = data.get('message', '').strip()
            context = data.get('context', {})
            section = data.get('section', '')
            history = data.get('history', [])

            if not user_message:
                return Response(
                    {'error': 'Message is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            api_key = os.environ.get('OPENAI_API_KEY', '')
            if not api_key:
                return Response(
                    {'error': 'OpenAI API key not configured. Set OPENAI_API_KEY environment variable.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # Build messages array for OpenAI
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]

            # Add context as a system-level injection so the model knows what the user sees
            if context:
                context_str = self._format_context(context, section)
                messages.append({
                    'role': 'system',
                    'content': f'The user is currently viewing the following pipeline output '
                               f'(section: {section}):\n\n{context_str}',
                })

            # Add conversation history (last 20 messages to stay within token limits)
            for msg in history[-20:]:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role in ('user', 'assistant') and content:
                    messages.append({'role': role, 'content': content})

            # Add current user message
            messages.append({'role': 'user', 'content': user_message})

            # Call OpenAI API
            import httpx
            resp = httpx.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': 'gpt-4.1',
                    'messages': messages,
                    'temperature': 0.4,
                    'max_tokens': 4096,
                },
                timeout=60.0,
            )

            if resp.status_code != 200:
                error_body = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text
                return Response(
                    {'error': f'OpenAI API error: {error_body}'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            result = resp.json()
            assistant_message = result['choices'][0]['message']['content']

            return Response({
                'message': assistant_message,
                'usage': result.get('usage', {}),
            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response(
                {'error': f'AI Assistant error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _format_context(self, context: dict, section: str) -> str:
        """Format pipeline context into a readable string for the LLM.

        Uses the actual field names produced by the Data_Quality backend and
        the frontend table columns so the LLM can reference concrete numbers.
        """
        parts = []

        if section == 'data_quality':
            summary = context.get('summary', [])
            if summary:
                parts.append(f'Data Quality Summary ({len(summary)} features):\n')
                # Build a compact per-feature table with the real column names
                for row in summary[:50]:  # up to 50 features
                    var = row.get('Variable', row.get('variable', row.get('index', '?')))
                    vtype = row.get('Variable_Type', '?')
                    psi = row.get('PSI')
                    csi = row.get('CSI')
                    decision = row.get('Datq_Decision', '?')
                    model_usage = row.get('MODEL_USAGE', row.get('Model_Usage', 'Yes'))
                    # Missing % — may be Train/Test split columns
                    miss_tr = row.get('%_Missing_Change_Train', row.get('%_Missing_Value', None))
                    miss_te = row.get('%_Missing_Change_Test', None)
                    # Distribution stats (Train side)
                    mean_tr = row.get('Mean_Change_Train', None)
                    std_tr = row.get('STD_Change_Train', None)
                    min_tr = row.get('Min_Change_Train', None)
                    max_tr = row.get('Max_Change_Train', None)
                    skew_tr = row.get('Skewness_Change_Train', None)
                    # Alternative shift metrics
                    ks = row.get('KS', None)
                    jsd = row.get('JSD', None)

                    def _fmt(v):
                        if v is None:
                            return '-'
                        if isinstance(v, float):
                            return f'{v:.4f}'
                        return str(v)

                    line = f"  {var} [{vtype}]:"
                    stability = f"PSI={_fmt(psi)}" if psi is not None else f"CSI={_fmt(csi)}"
                    line += f" {stability}, Decision={decision}"
                    if miss_tr is not None:
                        line += f", Missing(train)={_fmt(miss_tr)}"
                    if miss_te is not None:
                        line += f", Missing(test)={_fmt(miss_te)}"
                    if mean_tr is not None:
                        line += f", Mean(train)={_fmt(mean_tr)}"
                    if std_tr is not None:
                        line += f", Std(train)={_fmt(std_tr)}"
                    if min_tr is not None and max_tr is not None:
                        line += f", Range(train)=[{_fmt(min_tr)}, {_fmt(max_tr)}]"
                    if skew_tr is not None:
                        line += f", Skew(train)={_fmt(skew_tr)}"
                    if ks is not None:
                        line += f", KS={_fmt(ks)}"
                    if jsd is not None:
                        line += f", JSD={_fmt(jsd)}"
                    if model_usage and str(model_usage).lower() == 'no':
                        line += ", MODEL_USAGE=No (excluded)"
                    parts.append(line)

            purifier = context.get('purifier_summary', {})
            if purifier:
                rows_before = purifier.get('rows_before', '?')
                rows_after = purifier.get('rows_after', '?')
                rows_removed = purifier.get('rows_removed', 0)
                total_cols_dropped = purifier.get('total_columns_dropped', purifier.get('total_dropped', '?'))
                parts.append(f"\n═══ Preprocessing Treatment Effect ═══")
                parts.append(f"  Rows: {rows_before} → {rows_after} ({rows_removed} removed, "
                             f"{round(rows_removed / max(1, rows_before if isinstance(rows_before, (int, float)) else 1) * 100, 1)}% loss)")
                parts.append(f"  Total columns dropped: {total_cols_dropped}")
                # Per-step breakdown
                dropped_by_step = purifier.get('dropped_by_step', [])
                if dropped_by_step:
                    parts.append(f"  Purifier steps:")
                    for step in dropped_by_step:
                        step_name = step.get('step', '?')
                        cols = step.get('columns', [])
                        rows_rm = step.get('rows_removed', 0)
                        note = step.get('note', '')
                        cols_preview = ', '.join(cols[:10])
                        if len(cols) > 10:
                            cols_preview += f' ... (+{len(cols) - 10} more)'
                        line = f"    - {step_name}: {len(cols)} columns dropped"
                        if rows_rm:
                            line += f", {rows_rm} rows removed"
                        if cols_preview:
                            line += f" [{cols_preview}]"
                        if note:
                            line += f" — {note}"
                        parts.append(line)

            split_val = context.get('split_validation', {})
            if split_val and isinstance(split_val, dict):
                splits = split_val.get('splits', [])
                if splits:
                    parts.append(f"\n═══ Train/Test Split Validation ═══")
                    for sp in splits:
                        name = sp.get('name', '?')
                        count = sp.get('count', '?')
                        target_mean = sp.get('target_mean', '?')
                        parts.append(f"  {name}: n={count}, target_rate={target_mean}")

            model_usage = context.get('model_usage', {})
            if model_usage:
                excluded = [k for k, v in model_usage.items() if str(v).lower() == 'no']
                if excluded:
                    parts.append(f"\nExcluded from model (Model_Usage=No): {', '.join(excluded)}")

        elif section == 'encoding':
            plan = context.get('plan', [])
            if plan:
                parts.append(f'Encoding Plan ({len(plan)} categorical features):')
                for entry in plan[:30]:
                    parts.append(f"  - {entry.get('feature', '?')}: "
                                 f"LOM={entry.get('user_lom', entry.get('lom', '?'))}, "
                                 f"unique={entry.get('nunique', '?')}, "
                                 f"strategy={entry.get('fallback_strategy', '?')}")

        elif section == 'cv':
            cv = context.get('cv', {})
            if cv:
                parts.append(f"Cross-Validation Results:")
                parts.append(f"  ROC-AUC (mean ± std): {cv.get('roc_auc_mean', '?')} ± {cv.get('roc_auc_std', '?')}")
                parts.append(f"  PR-AUC (mean ± std): {cv.get('pr_auc_mean', '?')} ± {cv.get('pr_auc_std', '?')}")
                # Include fold-level data if available
                folds = cv.get('fold_scores', cv.get('folds', []))
                if folds:
                    parts.append(f"  Per-fold ROC-AUC: {folds}")
            model = context.get('model_info', {})
            if model:
                parts.append(f"  Model type: {model.get('model_type', '?')}")
                parts.append(f"  Number of features: {model.get('features', '?')}")
                parts.append(f"  Score: {model.get('score', '?')}")

        elif section == 'shap':
            features = context.get('features', [])
            if features:
                parts.append(f'SHAP Beeswarm — top {len(features)} features by |impact|:')
                for f in features[:20]:
                    parts.append(f"  - {f.get('feature', '?')}: "
                                 f"|impact|={f.get('impact', '?')}, "
                                 f"signed_impact={f.get('signed_impact', '?')}")

        elif section == 'selected_features':
            features = context.get('features', [])
            if features:
                parts.append(f'Selected Features ({len(features)} total, sorted by Combined Score):')
                for f in features[:30]:
                    parts.append(f"  - {f.get('feature', '?')}: "
                                 f"combined_score={f.get('combined_score', '?')}, "
                                 f"SHAP_percentile={f.get('shap_percentile', '?')}, "
                                 f"Gain_percentile={f.get('gain_percentile', '?')}, "
                                 f"VIF={f.get('vif', '?')}, "
                                 f"usage={f.get('usage', 'keep')}")

        elif section == 'sfs':
            for direction in ['forward', 'backward', 'forward_from_backward']:
                steps = context.get(direction, [])
                if steps:
                    parts.append(f'\n{direction.replace("_", " ").title()} Selection ({len(steps)} steps):')
                    for s in steps[:20]:
                        feat = s.get('feature_name', s.get('feature', '?'))
                        parts.append(f"  Step {s.get('step', '?')}: "
                                     f"{feat} — "
                                     f"CV ROC-AUC={s.get('cv_roc_auc', s.get('roc_auc', '?'))}, "
                                     f"Test ROC-AUC={s.get('test_roc_auc', '?')}, "
                                     f"PR-AUC={s.get('cv_pr_auc', s.get('pr_auc', '?'))}, "
                                     f"Model PSI={s.get('model_psi', '?')}")

        else:
            # Generic: dump first 3000 chars of JSON
            try:
                ctx_str = json.dumps(context, indent=2, default=str)
                parts.append(ctx_str[:3000])
            except Exception:
                parts.append(str(context)[:3000])

        # ── Always append pipeline configuration if present ──
        pipeline_cfg = context.get('pipeline_config', {})
        if pipeline_cfg:
            parts.append(f"\n═══ Pipeline Configuration ═══")
            parts.append(f"  Pipeline type: {pipeline_cfg.get('pipeline_type', '?')}")
            parts.append(f"  Current step: {pipeline_cfg.get('current_step', '?')}")
            parts.append(f"  Detailed step: {pipeline_cfg.get('detailed_step', '?')}")
            parts.append(f"  Preprocessing initiated: {pipeline_cfg.get('preprocessing_initiated', False)}")
            parts.append(f"  Modeling available: {pipeline_cfg.get('modeling_available', False)}")

            steps = pipeline_cfg.get('selected_purifier_steps', [])
            if steps:
                parts.append(f"  Selected purifier steps ({len(steps)}):")
                for s in steps:
                    parts.append(f"    • {s}")

            split = pipeline_cfg.get('split_strategy', '?')
            split_details = pipeline_cfg.get('split_details', {})
            if split == 'oot':
                parts.append(f"  Split strategy: Out-of-Time (OOT)")
                parts.append(f"    Mode: {split_details.get('mode', '?')}, "
                             f"OOT%: {split_details.get('oot_percent', '?')}, "
                             f"Date column: {split_details.get('date_column', '?')}, "
                             f"Cutoff: {split_details.get('cutoff', '?')}")
            else:
                parts.append(f"  Split strategy: Random")
                parts.append(f"    OOS%: {split_details.get('oos_percent', '?')}")

            rows_b = pipeline_cfg.get('rows_before', 0)
            rows_a = pipeline_cfg.get('rows_after', 0)
            rows_rm = pipeline_cfg.get('rows_removed', 0)
            if rows_b:
                pct = round(rows_rm / max(1, rows_b) * 100, 1)
                parts.append(f"  Rows: {rows_b} → {rows_a} ({rows_rm} removed, {pct}% loss)")

            total_dropped = pipeline_cfg.get('total_columns_dropped', 0)
            parts.append(f"  Total columns dropped: {total_dropped}")

            dropped_by_step = pipeline_cfg.get('dropped_by_step', [])
            if dropped_by_step:
                parts.append(f"  Columns dropped per purifier step:")
                for step_info in dropped_by_step:
                    sname = step_info.get('step', '?')
                    cols = step_info.get('columns', [])
                    rows_rm_s = step_info.get('rows_removed', 0)
                    cols_preview = ', '.join(cols[:8])
                    if len(cols) > 8:
                        cols_preview += f' ... (+{len(cols) - 8} more)'
                    line = f"    - {sname}: {len(cols)} cols"
                    if rows_rm_s:
                        line += f", {rows_rm_s} rows removed"
                    if cols_preview:
                        line += f" [{cols_preview}]"
                    parts.append(line)

            exclusions = pipeline_cfg.get('model_usage_exclusions', [])
            if exclusions:
                parts.append(f"  Features excluded (Model_Usage=No): {', '.join(exclusions)}")

            # ── Data Dictionary (raw metadata per feature) ──
            dd = pipeline_cfg.get('data_dictionary', [])
            if dd:
                parts.append(f"\n═══ Data Dictionary ({len(dd)} features) ═══")
                for feat in dd:
                    fname = feat.get('Feature_Name', '?')
                    dtype = feat.get('Data_Type', '?')
                    lom = feat.get('Level_of_Measurement', '?')
                    uniq = feat.get('Unique_Values', '?')
                    miss = feat.get('Missing_Ratio', '?')
                    mode_r = feat.get('Mode_Ratio', '?')
                    usage = feat.get('Model_Usage_YN', '?')
                    desc = feat.get('Feature_Description')
                    line = f"  {fname}: type={dtype}, LOM={lom}, unique={uniq}, missing={miss}%, mode_ratio={mode_r}%, usage={usage}"
                    if desc:
                        line += f", desc=\"{desc}\""
                    parts.append(line)

            # ── Encoding Plan ──
            enc = pipeline_cfg.get('encoding_plan', [])
            if enc:
                parts.append(f"\n═══ Encoding Plan ({len(enc)} categorical features) ═══")
                for e in enc:
                    parts.append(f"  {e.get('feature', '?')}: LOM={e.get('lom', '?')}, "
                                 f"unique={e.get('nunique', '?')}, "
                                 f"strategy={e.get('strategy', '?')}, "
                                 f"needs_ranking={e.get('needs_ranking', False)}")

            # ── Shared helpers for stats formatting ──
            num_metrics = ['Mean', 'Median', 'Std', 'Min', 'Max', 'Skewness', 'Kurtosis',
                           'Q01', 'Q05', 'Q25', 'Q75', 'Q95', 'Q99', 'Missing_Pct', 'Unique', 'N']
            cat_metrics = ['Mode', 'Mode_Pct', 'Num_Categories', 'Missing_Pct', 'Unique', 'N']

            def _fmt_val(v):
                if v is None:
                    return '-'
                if isinstance(v, float):
                    return f'{v:.4f}'
                return str(v)

            def _render_stats_comparison(before_list, after_list, title, label_before='before', label_after='after'):
                """Render a before/after stats comparison block for a list of features."""
                b_map = {s.get('Feature_Name'): s for s in before_list} if before_list else {}
                a_map = {s.get('Feature_Name'): s for s in after_list} if after_list else {}
                all_f = list(dict.fromkeys(
                    [s.get('Feature_Name') for s in (before_list or [])] +
                    [s.get('Feature_Name') for s in (after_list or [])]
                ))
                if not all_f:
                    return
                parts.append(f"\n═══ {title} ({len(all_f)} features) ═══")
                parts.append(f"  (Format: metric={label_before}/{label_after})")
                for fname in all_f:
                    b = b_map.get(fname, {})
                    a = a_map.get(fname, {})
                    dtype = b.get('Data_Type') or a.get('Data_Type', '?')
                    use_m = num_metrics if dtype == 'numeric' else cat_metrics
                    line = f"  {fname} [{dtype}]:"
                    m_parts = []
                    for m in use_m:
                        bv = b.get(m)
                        av = a.get(m)
                        if bv is None and av is None:
                            continue
                        m_parts.append(f"{m}={_fmt_val(bv)}/{_fmt_val(av)}")
                    if m_parts:
                        line += ' ' + ', '.join(m_parts)
                    else:
                        if fname in b_map and fname not in a_map:
                            line += ' [DROPPED by preprocessing]'
                        else:
                            line += ' [no stats]'
                    parts.append(line)

            # ── Per-Step Before/After Stats (e.g. outlier cleaning) ──
            step_stats = pipeline_cfg.get('preprocessing_step_stats') or []
            for ss in step_stats:
                step_name = ss.get('step', 'Unknown step')
                sb = ss.get('stats_before') or []
                sa = ss.get('stats_after') or []
                extra = ''
                qr = ss.get('quantile_range')
                if qr and isinstance(qr, list) and len(qr) == 2:
                    extra = f' [{qr[0]*100:.0f}%-{qr[1]*100:.0f}%]'
                _render_stats_comparison(
                    sb, sa,
                    title=f"Before/After {step_name}{extra}",
                    label_before=f'before {step_name}',
                    label_after=f'after {step_name}',
                )

            # ── Overall Before/After Preprocessing Feature Stats ──
            stats_before = pipeline_cfg.get('feature_stats_before') or []
            stats_after = pipeline_cfg.get('feature_stats_after') or []
            if stats_before or stats_after:
                _render_stats_comparison(
                    stats_before, stats_after,
                    title='Before/After Entire Preprocessing',
                    label_before='raw data',
                    label_after='after all preprocessing',
                )

            # ── Pipeline Commentary Notes (user annotations) ──
            notes = pipeline_cfg.get('pipeline_notes', {})
            active_notes = {k: v for k, v in notes.items() if v and str(v).strip()}
            if active_notes:
                parts.append(f"\n═══ User Pipeline Notes ═══")
                for position, content in active_notes.items():
                    label = position.replace('_', ' ').title()
                    parts.append(f"  [{label}]: {content}")

        return '\n'.join(parts) if parts else json.dumps(context, default=str)[:3000]
