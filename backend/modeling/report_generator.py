"""
Pipeline Report Generator
Generates standalone HTML reports from PipelineRun state.
"""
import json
import os
from datetime import datetime
from django.conf import settings


def _fmt(val, decimals=4):
    """Format a numeric value for display."""
    if val is None:
        return '—'
    try:
        return f'{float(val):.{decimals}f}'
    except (ValueError, TypeError):
        return str(val)


def _pct(val, decimals=1):
    """Format a value as percentage."""
    if val is None:
        return '—'
    try:
        return f'{float(val) * 100:.{decimals}f}%'
    except (ValueError, TypeError):
        return str(val)


def _load_modeling_status(file_id):
    """Load modeling status JSON from disk."""
    path = os.path.join(settings.MEDIA_ROOT, 'modeling', f'{file_id}_status.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _load_sfs_results(file_id):
    """Load SFS results JSON from disk."""
    path = os.path.join(settings.MEDIA_ROOT, 'sfs_results', f'{file_id}_sfs_results.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _render_inline_note(notes, position):
    """Render an inline note block if one exists for the given position."""
    if not notes:
        return ''
    text = notes.get(position, '')
    if not text or not text.strip():
        return ''
    label = position.replace('_', ' ').title()
    return f'''
        <div class="note-block">
            <div class="note-label">{label}</div>
            <div class="note-text">{text}</div>
        </div>'''


# ---------------------------------------------------------------------------
# HTML Sections
# ---------------------------------------------------------------------------

def _section_header(run, state):
    """Pipeline header with name, type, dates."""
    created = run.created_at.strftime('%Y-%m-%d %H:%M') if run.created_at else '—'
    updated = run.updated_at.strftime('%Y-%m-%d %H:%M') if run.updated_at else '—'
    step_display = (run.current_step or '').replace('_', ' ').title()
    return f'''
    <div class="header">
        <h1>{run.name}</h1>
        <div class="header-meta">
            <span><strong>Pipeline Type:</strong> {(run.pipeline_type or '').title()}</span>
            <span><strong>Current Step:</strong> {step_display}</span>
            <span><strong>Created:</strong> {created}</span>
            <span><strong>Last Updated:</strong> {updated}</span>
        </div>
    </div>'''


def _section_declaration(file_id, notes):
    """Data declaration: file info, data preview, data dictionary."""
    if not file_id:
        return ''
    try:
        from declaration.models import Declaration
        decl = Declaration.objects.get(pk=file_id)
    except Exception:
        return ''

    import pandas as pd

    # File info
    file_name = decl.original_name or '—'
    uploaded = decl.uploaded_at.strftime('%Y-%m-%d %H:%M') if decl.uploaded_at else '—'

    # Load file to get shape and preview
    file_path = decl.get_file_path()
    preview_html = ''
    n_rows = '—'
    n_cols = '—'
    if file_path and os.path.exists(file_path):
        try:
            df_full_shape = pd.read_csv(file_path, nrows=0, sep=',')
            if df_full_shape.shape[1] <= 2:
                df_full_shape = pd.read_csv(file_path, nrows=0, sep=';')
            sep = ',' if df_full_shape.shape[1] > 2 else ';'
            # Count rows efficiently
            with open(file_path, 'r') as fh:
                row_count = sum(1 for _ in fh) - 1  # minus header
            n_rows = f'{row_count:,}'
            n_cols = str(df_full_shape.shape[1])

            # Preview: first 5 rows
            df_preview = pd.read_csv(file_path, nrows=5, sep=sep)
            header_cells = ''.join(f'<th>{c}</th>' for c in df_preview.columns)
            body_rows = ''
            for _, row in df_preview.iterrows():
                cells = ''.join(f'<td>{v}</td>' for v in row.values)
                body_rows += f'<tr>{cells}</tr>'
            preview_html = f'''
        <h4>Data Preview (first 5 rows)</h4>
        <div class="table-scroll">
        <table>
            <thead><tr>{header_cells}</tr></thead>
            <tbody>{body_rows}</tbody>
        </table>
        </div>'''
        except Exception as e:
            preview_html = f'<p class="note">Could not load data preview: {e}</p>'

    # Data Dictionary
    dict_html = ''
    try:
        dd_entries = decl.data_dictionary.all().order_by('id')
        if dd_entries.exists():
            dict_rows = ''
            for i, entry in enumerate(dd_entries, 1):
                dict_rows += f'''
            <tr>
                <td>{i}</td>
                <td><strong>{entry.column_name}</strong></td>
                <td>{entry.description or '—'}</td>
            </tr>'''
            dict_html = f'''
        <h4>Data Dictionary ({dd_entries.count()} variables)</h4>
        <div class="table-scroll">
        <table>
            <thead><tr><th>#</th><th>Variable</th><th>Description</th></tr></thead>
            <tbody>{dict_rows}</tbody>
        </table>
        </div>'''
    except Exception:
        pass

    note_after_preview = _render_inline_note(notes, 'after_data_preview')
    note_after_dict = _render_inline_note(notes, 'after_data_dictionary')

    return f'''
    <div class="section">
        <h2>Data Declaration</h2>
        <div class="kv-grid">
            <div class="kv-item"><span class="kv-label">File Name</span><span class="kv-value" style="font-size:13px;">{file_name}</span></div>
            <div class="kv-item"><span class="kv-label">Rows</span><span class="kv-value">{n_rows}</span></div>
            <div class="kv-item"><span class="kv-label">Columns</span><span class="kv-value">{n_cols}</span></div>
            <div class="kv-item"><span class="kv-label">Uploaded</span><span class="kv-value" style="font-size:13px;">{uploaded}</span></div>
        </div>
        {preview_html}
        {note_after_preview}
        {dict_html}
        {note_after_dict}
    </div>'''


def _section_preprocessing(state, notes):
    """Preprocessing configuration and results."""
    pp = state.get('preprocessing', {})
    if not pp:
        return ''
    strategy = pp.get('split_strategy', 'random')
    rows_before = pp.get('row_count_before', 0)
    rows_after = pp.get('row_count_after', 0)
    rows_removed = pp.get('rows_removed_total', 0)
    oos_pct = pp.get('oos_percent', 25)

    split_info = f'Random ({oos_pct}% test)'
    if strategy == 'oot':
        date_col = pp.get('split_date_column', '—')
        oot_mode = pp.get('oot_mode', 'percent')
        if oot_mode == 'cutoff':
            split_info = f'Out-of-Time (column: {date_col}, cutoff: {pp.get("split_cutoff", "—")})'
        else:
            split_info = f'Out-of-Time (column: {date_col}, last {pp.get("oot_percent", 25)}%)'

    dropped_html = ''
    dropped = pp.get('dropped_columns_by_step', [])
    if dropped:
        dropped_rows = ''
        for step_info in dropped:
            step_name = step_info.get('step', '—')
            cols = step_info.get('columns', [])
            n_rows = step_info.get('rows_removed', 0)
            cols_str = ', '.join(cols[:10])
            if len(cols) > 10:
                cols_str += f' ... (+{len(cols) - 10} more)'
            dropped_rows += f'''
            <tr>
                <td>{step_name}</td>
                <td>{len(cols)}</td>
                <td class="small-text">{cols_str}</td>
                <td>{n_rows}</td>
            </tr>'''
        dropped_html = f'''
        <h4>Dropped Columns by Step</h4>
        <table>
            <thead><tr><th>Step</th><th>Columns Dropped</th><th>Column Names</th><th>Rows Removed</th></tr></thead>
            <tbody>{dropped_rows}</tbody>
        </table>'''

    note_after_config = _render_inline_note(notes, 'after_preprocessing_config')
    note_after_summary = _render_inline_note(notes, 'after_purifier_summary')

    return f'''
    <div class="section">
        <h2>Preprocessing</h2>
        <div class="kv-grid">
            <div class="kv-item"><span class="kv-label">Split Strategy</span><span class="kv-value">{split_info}</span></div>
            <div class="kv-item"><span class="kv-label">Rows Before</span><span class="kv-value">{rows_before:,}</span></div>
            <div class="kv-item"><span class="kv-label">Rows After</span><span class="kv-value">{rows_after:,}</span></div>
            <div class="kv-item"><span class="kv-label">Rows Removed</span><span class="kv-value">{rows_removed:,}</span></div>
        </div>
        {note_after_config}
        {dropped_html}
        {note_after_summary}
    </div>'''


def _section_data_quality(state, notes):
    """Data Quality summary table."""
    dq = state.get('data_quality', {})
    summary = dq.get('datq_summary')
    if not summary or not isinstance(summary, list) or len(summary) == 0:
        return ''

    # Model_Usage is stored separately as a dict {variable_name: 'Yes'|'No'}
    model_usage = dq.get('model_usage', {})

    # Identify the variable name column
    var_col = 'Variable' if 'Variable' in summary[0] else 'variable' if 'variable' in summary[0] else None

    # Pick important columns to show
    all_cols = list(summary[0].keys())
    priority_cols = ['Variable', 'variable', 'Model_Usage', 'PSI', 'Datq_Decision',
                     'Variable_Type', 'CSI', 'KS', 'JSD']
    # Model_Usage is injected (not in all_cols), so we track it separately
    has_model_usage = bool(model_usage)
    display_cols = [c for c in priority_cols if c in all_cols or (c == 'Model_Usage' and has_model_usage)]
    # Add remaining cols not in priority list (capped at 20 total)
    for c in all_cols:
        if c not in display_cols and len(display_cols) < 20:
            display_cols.append(c)

    header_cells = ''.join(f'<th>{c}</th>' for c in display_cols)
    body_rows = ''
    for row in summary[:100]:  # cap at 100 rows
        var_name = row.get(var_col, '') if var_col else ''
        cells = ''
        for c in display_cols:
            if c == 'Model_Usage':
                mu_val = model_usage.get(var_name, 'Yes')
                if mu_val == 'No':
                    cells += '<td style="color:#c62828; font-weight:600;">No</td>'
                else:
                    cells += f'<td>{mu_val}</td>'
            else:
                val = row.get(c, '')
                if isinstance(val, float):
                    cells += f'<td>{_fmt(val)}</td>'
                else:
                    cells += f'<td>{val}</td>'
        body_rows += f'<tr>{cells}</tr>'

    overflow_note = ''
    if len(summary) > 100:
        overflow_note = f'<p class="note">Showing first 100 of {len(summary)} variables.</p>'

    note_after_dq = _render_inline_note(notes, 'after_data_quality')

    return f'''
    <div class="section">
        <h2>Data Quality Summary</h2>
        {overflow_note}
        <div class="table-scroll">
        <table>
            <thead><tr>{header_cells}</tr></thead>
            <tbody>{body_rows}</tbody>
        </table>
        </div>
        {note_after_dq}
    </div>'''


def _section_modeling(modeling_status, state, notes):
    """Modeling results: metrics, selected features, SHAP beeswarm."""
    if not modeling_status or modeling_status.get('status') != 'ok':
        return ''

    model = modeling_status.get('model', {})
    metrics = modeling_status.get('metrics', {})
    algorithm = modeling_status.get('algorithm', model.get('model_type', '—'))
    valid_auc = model.get('valid_auc')
    feature_count = model.get('feature_count', metrics.get('features', '—'))

    # Encoding plan from checkpoint state
    encoding_html = ''
    modeling_state = state.get('modeling', {})
    encoding_plan = modeling_state.get('encodingPlan', [])
    if encoding_plan:
        enc_rows = ''
        for entry in encoding_plan:
            feature = entry.get('feature', '—')
            user_lom = entry.get('user_lom', entry.get('lom', '—'))
            original_lom = entry.get('original_lom', '')
            lom_display = user_lom
            if original_lom and original_lom != user_lom:
                lom_display = f'{user_lom} <span class="small-text" style="color:#e65100;">(was {original_lom})</span>'
            strategy = entry.get('strategy', '—')
            fallback = entry.get('fallback_strategy', '')
            fallback_reason = entry.get('fallback_reason', '')
            strategy_display = strategy
            if fallback and fallback != strategy:
                strategy_display += f' <span class="small-text" style="color:#888;">→ {fallback}</span>'
            nunique = entry.get('nunique', '—')
            ranking = entry.get('ranking', [])
            ranking_display = ', '.join(str(r) for r in ranking) if ranking else '—'
            enc_rows += f'''
            <tr>
                <td><strong>{feature}</strong></td>
                <td>{lom_display}</td>
                <td>{strategy_display}</td>
                <td class="small-text">{fallback_reason}</td>
                <td>{nunique}</td>
                <td class="small-text">{ranking_display}</td>
            </tr>'''
        encoding_html = f'''
        <h4>Categorical Feature Encoding Plan</h4>
        <table>
            <thead><tr><th>Feature</th><th>Level of Measurement</th><th>Strategy</th><th>Fallback Reason</th><th>Unique Values</th><th>Ranking</th></tr></thead>
            <tbody>{enc_rows}</tbody>
        </table>'''

    note_after_encoding = _render_inline_note(notes, 'after_encoding')

    # CV summary
    cv = model.get('cv')
    cv_html = ''
    if cv:
        cv_html = f'''
        <h4>Cross-Validation Summary</h4>
        <div class="kv-grid">
            <div class="kv-item"><span class="kv-label">ROC-AUC (mean &plusmn; std)</span><span class="kv-value">{_fmt(cv.get('roc_auc_mean'))} &plusmn; {_fmt(cv.get('roc_auc_std'))}</span></div>
            <div class="kv-item"><span class="kv-label">PR-AUC (mean &plusmn; std)</span><span class="kv-value">{_fmt(cv.get('pr_auc_mean'))} &plusmn; {_fmt(cv.get('pr_auc_std'))}</span></div>
            <div class="kv-item"><span class="kv-label">Folds</span><span class="kv-value">{len(cv.get('folds', []))}</span></div>
        </div>'''

        # Fold detail table
        folds = cv.get('folds', [])
        if folds:
            fold_rows = ''
            for fold in folds:
                fold_rows += f'''
            <tr>
                <td>Fold {fold.get('fold', '')}</td>
                <td>{_fmt(fold.get('roc_auc'))}</td>
                <td>{_fmt(fold.get('pr_auc'))}</td>
            </tr>'''
            cv_html += f'''
        <table>
            <thead><tr><th>Fold</th><th>ROC-AUC</th><th>PR-AUC</th></tr></thead>
            <tbody>{fold_rows}</tbody>
        </table>'''

    # Selected features table — field names: impact (SHAP), gain, combined_score, description
    selected = model.get('selected_features', [])
    feature_usage = modeling_state.get('featureUsage', {})
    feature_drop_reason = modeling_state.get('featureDropReason', {})
    features_html = ''
    if selected:
        feat_rows = ''
        for i, feat in enumerate(selected, 1):
            name = feat.get('feature', '—')
            desc = feat.get('description', '')
            combined = feat.get('combined_score')
            # SHAP importance: try 'impact', fallback to 'shap_importance'
            shap_val = feat.get('impact', feat.get('shap_importance'))
            # Gain importance: try 'gain', fallback to 'gain_importance'
            gain_val = feat.get('gain', feat.get('gain_importance'))
            vif = feat.get('vif')
            # Usage from user selection (keep/drop + reason)
            usage = feature_usage.get(name, 'keep')
            drop_reason = feature_drop_reason.get(name, '')
            if usage == 'drop':
                usage_display = f'<span style="color:#c62828; font-weight:600;">Drop</span>'
                if drop_reason:
                    usage_display += f' <span class="small-text" style="color:#c62828;">({drop_reason})</span>'
                row_bg = ' style="background:#fff5f5;"'
            else:
                usage_display = '<span style="color:#2e7d32;">Keep</span>'
                row_bg = ''
            feat_rows += f'''
            <tr{row_bg}>
                <td>{i}</td>
                <td><strong>{name}</strong></td>
                <td class="small-text">{desc}</td>
                <td>{_fmt(combined)}</td>
                <td>{_fmt(shap_val)}</td>
                <td>{_fmt(gain_val)}</td>
                <td>{_fmt(vif, 2)}</td>
                <td>{usage_display}</td>
            </tr>'''
        features_html = f'''
        <h4>Selected Features (sorted by Combined Score)</h4>
        <table>
            <thead><tr><th>#</th><th>Feature</th><th>Description</th><th>Combined Score</th><th>SHAP Importance</th><th>Gain Importance</th><th>VIF</th><th>Usage</th></tr></thead>
            <tbody>{feat_rows}</tbody>
        </table>'''

    # SHAP Beeswarm image (base64 PNG from disk)
    beeswarm_html = ''
    beeswarm_png = model.get('beeswarm_png')
    if beeswarm_png:
        # Strip any whitespace/newlines that might have crept into the base64 string
        clean_b64 = beeswarm_png.strip().replace('\n', '').replace('\r', '')
        # The stored value may already include the data URI prefix
        if clean_b64.startswith('data:'):
            img_src = clean_b64
        else:
            img_src = f'data:image/png;base64,{clean_b64}'
        beeswarm_html = f'''
        <h4>SHAP Beeswarm</h4>
        <div class="chart-container">
            <img src="{img_src}" alt="SHAP Beeswarm" style="max-width:100%; height:auto;" />
        </div>'''

    note_after_modeling = _render_inline_note(notes, 'after_modeling_results')

    return f'''
    <div class="section">
        <h2>Modeling Results</h2>
        <div class="kv-grid">
            <div class="kv-item"><span class="kv-label">Algorithm</span><span class="kv-value">{algorithm}</span></div>
            <div class="kv-item"><span class="kv-label">Validation AUC</span><span class="kv-value">{_fmt(valid_auc)}</span></div>
            <div class="kv-item"><span class="kv-label">Feature Count</span><span class="kv-value">{feature_count}</span></div>
        </div>
        {encoding_html}
        {note_after_encoding}
        {cv_html}
        {features_html}
        {beeswarm_html}
        {note_after_modeling}
    </div>'''


def _section_sfs(sfs_data, notes):
    """SFS forward/backward selection results."""
    if not sfs_data:
        return ''

    forward = sfs_data.get('forward', [])
    backward = sfs_data.get('backward', [])
    fwd_from_bwd = sfs_data.get('forward_from_backward', [])

    if not forward and not backward and not fwd_from_bwd:
        return ''

    def _sfs_table(steps, title, description):
        if not steps:
            return ''
        rows = ''
        for s in steps:
            action = s.get('action', '—')
            feature = s.get('feature_name', '—')
            n_feats = len(s.get('selected_features', []))
            rows += f'''
            <tr>
                <td>{s.get('step', '')}</td>
                <td>{action}</td>
                <td><strong>{feature}</strong></td>
                <td>{_fmt(s.get('cv_roc_auc'))}</td>
                <td>{_fmt(s.get('cv_pr_auc'))}</td>
                <td>{_fmt(s.get('test_roc_auc'))}</td>
                <td>{_fmt(s.get('test_pr_auc'))}</td>
                <td>{n_feats}</td>
            </tr>'''
        return f'''
        <h4>{title}</h4>
        <p class="note">{description}</p>
        <div class="table-scroll">
        <table>
            <thead><tr>
                <th>Step</th><th>Action</th><th>Feature</th>
                <th>CV ROC-AUC</th><th>CV PR-AUC</th>
                <th>Test ROC-AUC</th><th>Test PR-AUC</th>
                <th># Features</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
        </div>'''

    sfs_status = sfs_data.get('status', 'completed')
    status_badge = ''
    if sfs_status == 'stopped':
        status_badge = '<span class="badge badge-warning">Partial — stopped by user</span>'
    elif sfs_status == 'running':
        status_badge = '<span class="badge badge-info">Interrupted — partial results</span>'

    note_after_sfs = _render_inline_note(notes, 'after_sfs')

    return f'''
    <div class="section">
        <h2>Sequential Feature Selection (SFS) {status_badge}</h2>
        {_sfs_table(forward, 'Forward Selection', 'Adding features incrementally based on performance improvement.')}
        {_sfs_table(backward, 'Backward Elimination', 'Removing features incrementally based on performance impact.')}
        {_sfs_table(fwd_from_bwd, 'Forward from Backward', 'Forward selection starting from backward-eliminated feature set.')}
        {note_after_sfs}
    </div>'''


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

REPORT_CSS = '''
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        color: #333; background: #fff; padding: 32px; font-size: 13px; line-height: 1.5;
    }
    .header {
        border-bottom: 3px solid #1565c0; padding-bottom: 16px; margin-bottom: 28px;
    }
    .header h1 { color: #1565c0; font-size: 26px; margin-bottom: 8px; }
    .header-meta {
        display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; color: #555;
    }
    .section { margin-bottom: 32px; page-break-inside: avoid; }
    .section h2 {
        color: #1565c0; font-size: 18px; border-bottom: 2px solid #e3f2fd;
        padding-bottom: 6px; margin-bottom: 14px;
    }
    .section h4 { color: #333; font-size: 14px; margin: 16px 0 8px 0; }
    .kv-grid {
        display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px;
    }
    .kv-item {
        background: #f5f7fa; border: 1px solid #e0e0e0; border-radius: 6px;
        padding: 10px 16px; min-width: 160px;
    }
    .kv-label { display: block; font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
    .kv-value { display: block; font-size: 16px; font-weight: 600; color: #333; margin-top: 2px; }
    table {
        width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 12px;
    }
    th, td { padding: 6px 10px; border: 1px solid #e0e0e0; text-align: left; }
    th { background: #f5f7fa; font-weight: 600; color: #555; white-space: nowrap; }
    tr:nth-child(even) { background: #fafafa; }
    .table-scroll { overflow-x: auto; }
    .chart-container { margin: 12px 0; text-align: center; }
    .note { font-size: 12px; color: #888; margin-bottom: 8px; }
    .small-text { font-size: 11px; color: #666; }
    .badge {
        display: inline-block; padding: 3px 10px; border-radius: 10px;
        font-size: 11px; font-weight: 600; vertical-align: middle; margin-left: 8px;
    }
    .badge-warning { background: #fff3e0; color: #e65100; border: 1px solid #ffe0b2; }
    .badge-info { background: #e3f2fd; color: #1565c0; border: 1px solid #bbdefb; }
    .note-block {
        background: #fffde7; border-left: 4px solid #fbc02d; padding: 10px 14px;
        margin-bottom: 10px; border-radius: 0 6px 6px 0;
    }
    .note-label { font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 4px; }
    .note-text { font-size: 13px; color: #333; white-space: pre-wrap; }
    .footer {
        margin-top: 40px; padding-top: 12px; border-top: 1px solid #e0e0e0;
        font-size: 11px; color: #999; text-align: center;
    }
    @media print {
        body { padding: 16px; }
        .section { page-break-inside: avoid; }
    }
'''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pipeline_html(run):
    """
    Generate a standalone HTML report for a PipelineRun instance.
    Returns an HTML string.
    """
    state = run.state or {}
    file_id = state.get('file_id') or run.file_id
    notes = state.get('pipeline_notes', {})

    # Load supplementary data from disk
    modeling_status = _load_modeling_status(file_id) if file_id else None
    sfs_data = _load_sfs_results(file_id) if file_id else None

    # Build sections (notes inlined under their corresponding sections)
    sections = [
        _section_header(run, state),
        _section_declaration(file_id, notes),
        _section_preprocessing(state, notes),
        _section_data_quality(state, notes),
        _section_modeling(modeling_status, state, notes),
        _section_sfs(sfs_data, notes),
    ]

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    body = '\n'.join(s for s in sections if s)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipeline Report — {run.name}</title>
    <style>{REPORT_CSS}</style>
</head>
<body>
    {body}
    <div class="footer">
        Generated on {now} &middot; DeclarAI Pipeline Report
    </div>
</body>
</html>'''
    return html
