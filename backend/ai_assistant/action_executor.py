"""
General-purpose AI action executor.

Handles all action types that the AI Assistant can trigger:
  - execute_code    : Safe pandas code execution on the dataset
  - update_metadata : Update data dictionary entries (descriptions, LOM, etc.)
  - update_config   : Change pipeline decisions (Model_Usage, preprocessing options, etc.)
  - update_notes    : Add / edit / delete pipeline commentary notes

The design is intentionally open-ended: the AI writes real pandas code
and the executor runs it inside a restricted sandbox.
"""

import base64
import io
import os
import re
import shutil
import sys
import traceback
from typing import Optional

import numpy as np
import pandas as pd
from django.conf import settings
from declaration.models import Declaration, DataDictionary

from .prometa_config import (
    workflow, tool, set_span_attr, set_session_id, set_customer_id,
    schema_validate, set_input_ref, stamp_mcp_tool_marker,
    stamp_codeline_capability,
)


# ---------------------------------------------------------------------------
# Safe code execution sandbox
# ---------------------------------------------------------------------------

# Whitelisted builtins — no __import__, open, exec, eval, compile, etc.
_SAFE_BUILTINS = {
    'abs': abs,
    'all': all,
    'any': any,
    'bool': bool,
    'dict': dict,
    'enumerate': enumerate,
    'filter': filter,
    'float': float,
    'frozenset': frozenset,
    'int': int,
    'isinstance': isinstance,
    'len': len,
    'list': list,
    'map': map,
    'max': max,
    'min': min,
    'print': print,
    'range': range,
    'round': round,
    'set': set,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'tuple': tuple,
    'type': type,
    'zip': zip,
    'True': True,
    'False': False,
    'None': None,
}


def _stamp_action_mcp_marker(action_type: str) -> None:
    """Mark direct action handler spans with their governed MCP tool name."""
    stamp_mcp_tool_marker(
        action_type.replace('_', '-'),
        mcp_tool_name=f'declarai.action.{action_type}',
    )


def _load_dataframe(file_id: int) -> tuple:
    """Load the dataset for a given Declaration file_id.
    Returns (df, data_file, file_path).
    """
    data_file = Declaration.objects.get(pk=file_id)
    file_path = data_file.file.path
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")
    if file_path.lower().endswith(('.xls', '.xlsx')):
        df = pd.read_excel(file_path, engine='openpyxl')
    else:
        df = pd.read_csv(file_path)
    return df, data_file, file_path


def _save_dataframe(df: pd.DataFrame, data_file, file_path: str):
    """Save the (possibly modified) dataframe back to disk."""
    if file_path.lower().endswith(('.xls', '.xlsx')):
        out_path = file_path.rsplit('.', 1)[0] + '.csv'
        from django.core.files.base import ContentFile
        csv_bytes = df.to_csv(index=False).encode('utf-8')
        data_file.file.save(os.path.basename(out_path), ContentFile(csv_bytes), save=True)
    else:
        df.to_csv(file_path, index=False)


def _restore_backup(backup_path: str, file_path: str):
    """Restore dataset from backup after corruption."""
    try:
        shutil.copy2(backup_path, file_path)
        os.remove(backup_path)
    except Exception:
        pass


def _remove_backup(backup_path: str):
    """Remove backup file after successful execution."""
    try:
        os.remove(backup_path)
    except Exception:
        pass


def _build_preview(df: pd.DataFrame) -> dict:
    """Build a preview dict from a dataframe."""
    df_clean = df.replace({np.nan: None})
    return {
        'total_rows': len(df),
        'total_columns': len(df.columns),
        'columns': df.columns.tolist(),
        'top_rows': df_clean.head(5).to_dict(orient='records'),
    }


def _build_series_preview(series: pd.Series) -> dict:
    """Build a small preview for a pandas Series (exploratory display)."""
    clean = series.replace({np.nan: None})
    head = clean.head(20)
    return {
        'total_rows': len(series),
        'total_columns': 1,
        'columns': [series.name or 'value'],
        'top_rows': [{series.name or 'value': v} for v in head.tolist()],
    }


def _strip_import_lines(code: str) -> str:
    """Remove import lines — pd/np (and optionally plt) are injected into the sandbox."""
    return '\n'.join(
        line for line in code.splitlines()
        if not line.strip().startswith(('import ', 'from '))
    )


def _capture_matplotlib_images() -> list:
    """Capture open matplotlib figures as base64 PNG data-URLs. Returns [] if unavailable."""
    images = []
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        for fig_num in plt.get_fignums():
            fig = plt.figure(fig_num)
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode('ascii')
            images.append(f'data:image/png;base64,{b64}')
        plt.close('all')
    except Exception:
        pass
    return images


def _pick_exploratory_preview(sandbox: dict, df_before: pd.DataFrame) -> Optional[dict]:
    """Prefer result / _ / modified df for exploratory table preview."""
    for key in ('result', '_'):
        val = sandbox.get(key)
        if isinstance(val, pd.DataFrame):
            return _build_preview(val)
        if isinstance(val, pd.Series):
            return _build_series_preview(val)

    df_result = sandbox.get('df')
    if isinstance(df_result, pd.DataFrame):
        # Always show a preview of the working frame after exploratory runs
        return _build_preview(df_result)

    return _build_preview(df_before)


def _run_exploratory(file_id: int, code: str, description: str) -> dict:
    """Execute code against a DataFrame copy without mutating the dataset on disk."""
    set_span_attr('declarai.execute_code.mode', 'exploratory')
    df, _data_file, _file_path = _load_dataframe(file_id)
    code = _strip_import_lines(code)

    stdout_buf = io.StringIO()
    sandbox = {
        '__builtins__': _SAFE_BUILTINS,
        'pd': pd,
        'np': np,
        'df': df.copy(),
    }

    # Optional matplotlib for charts in exploratory mode
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.close('all')
        sandbox['plt'] = plt
    except Exception:
        pass

    old_stdout = sys.stdout
    try:
        sys.stdout = stdout_buf
        exec(code, sandbox)
    except Exception as e:
        return {
            'status': 'error',
            'mode': 'exploratory',
            'error': f'Code execution failed: {str(e)}',
            'traceback': traceback.format_exc(),
            'stdout': stdout_buf.getvalue(),
            'preview': None,
            'images': [],
            'changes': None,
        }
    finally:
        sys.stdout = old_stdout

    images = _capture_matplotlib_images()
    preview = _pick_exploratory_preview(sandbox, df)

    return {
        'status': 'success',
        'action_type': 'execute_code',
        'mode': 'exploratory',
        'description': description,
        'stdout': stdout_buf.getvalue(),
        'preview': preview,
        'images': images,
        'changes': None,
    }


# ---------------------------------------------------------------------------
# Feature description generator
# ---------------------------------------------------------------------------

def _generate_feature_description(col_name: str, data_file) -> str:
    """
    Generate a specific, informative description for an AI-created feature
    based on its name pattern and parent feature descriptions from the
    DataDictionary.
    """

    def _parent_desc(var_name: str) -> str:
        desc = DataDictionary.get_description(data_file.pk, var_name)
        return f' ({desc})' if desc else ''

    def _parent_desc_short(var_name: str) -> str:
        desc = DataDictionary.get_description(data_file.pk, var_name)
        return desc or var_name

    # --- LogSigned_<Var> --------------------------------------------------
    m = re.match(r'^LogSigned_(.+)$', col_name)
    if m:
        p = m.group(1)
        return (
            f'Signed log transform of {p}{_parent_desc(p)}. '
            f'Formula: sign({p}) × ln(1 + |{p}|). '
            f'Compresses large magnitudes while preserving sign; '
            f'handles negative values safely.'
        )

    # --- Log1p_<Var>  (numpy log1p) ---------------------------------------
    m = re.match(r'^Log1p_(.+)$', col_name)
    if m:
        p = m.group(1)
        return (
            f'Log-plus-one transform of {p}{_parent_desc(p)}. '
            f'Formula: ln(1 + {p}). The "1p" suffix means "one plus": '
            f'adds 1 before taking the natural logarithm to avoid log(0). '
            f'Compresses right-skewed distributions.'
        )

    # --- Log_<Var>  (plain log) -------------------------------------------
    m = re.match(r'^Log_(.+)$', col_name)
    if m:
        p = m.group(1)
        return (
            f'Natural-log transform of {p}{_parent_desc(p)}. '
            f'Formula: ln({p}). Compresses right-skewed distributions; '
            f'undefined for zero / negative values.'
        )

    # --- <A>_to_<B>  (ratio) ---------------------------------------------
    m = re.match(r'^(.+?)_to_(.+)$', col_name)
    if m:
        a, b = m.group(1), m.group(2)
        return (
            f'Ratio of {a}{_parent_desc(a)} to {b}{_parent_desc(b)}. '
            f'Formula: {a} ÷ {b} (denominator zeros replaced with NaN '
            f'to avoid division by zero).'
        )

    # --- <A>_minus_<B>  (difference) --------------------------------------
    m = re.match(r'^(.+?)_minus_(.+)$', col_name)
    if m:
        a, b = m.group(1), m.group(2)
        return (
            f'Difference: {a}{_parent_desc(a)} minus {b}{_parent_desc(b)}. '
            f'Formula: {a} − {b}.'
        )

    # --- <A>_x_<B>  (categorical interaction) -----------------------------
    m = re.match(r'^(.+?)_x_(.+)$', col_name)
    if m:
        a, b = m.group(1), m.group(2)
        return (
            f'Categorical interaction of {a}{_parent_desc(a)} and '
            f'{b}{_parent_desc(b)}. Values are concatenated as '
            f'"{a}_value__{b}_value" to capture joint category combinations.'
        )

    # --- <A>_times_<B> or <A>_mult_<B> (product) -------------------------
    m = re.match(r'^(.+?)_(times|mult)_(.+)$', col_name)
    if m:
        a, b = m.group(1), m.group(3)
        return (
            f'Product of {a}{_parent_desc(a)} and {b}{_parent_desc(b)}. '
            f'Formula: {a} × {b}.'
        )

    # --- Is_Missing_<Var> or IsMissing_<Var> (missingness flag) -----------
    m = re.match(r'^Is_?Missing_(.+)$', col_name)
    if m:
        p = m.group(1)
        return (
            f'Binary missingness indicator for {p}{_parent_desc(p)}. '
            f'1 if {p} is NaN/missing, 0 otherwise.'
        )

    # --- Datetime-derived features ----------------------------------------
    _DT_DESCRIPTIONS = {
        'Application_Month':
            'Month extracted from Application_Datetime (1–12). '
            'Captures seasonal application patterns.',
        'Application_Quarter':
            'Quarter extracted from Application_Datetime (1–4). '
            'Captures quarterly trends.',
        'Application_DayOfWeek':
            'Day of week from Application_Datetime (0 = Monday … 6 = Sunday). '
            'Captures weekday vs. weekend behaviour.',
        'Application_DayOfMonth':
            'Day of month from Application_Datetime (1–31). '
            'Captures intra-month timing effects.',
        'Application_IsWeekend':
            'Binary flag: 1 if the application was submitted on Saturday or '
            'Sunday, 0 otherwise.',
        'Application_Hour':
            'Hour of day from Application_Datetime (0–23). '
            'Captures time-of-day application behaviour.',
        'Application_IsMonthStart':
            'Binary flag: 1 if the application date is the first day of the '
            'month, 0 otherwise.',
        'Application_IsMonthEnd':
            'Binary flag: 1 if the application date is the last day of the '
            'month, 0 otherwise.',
    }
    if col_name in _DT_DESCRIPTIONS:
        return _DT_DESCRIPTIONS[col_name]

    # --- Row-wise numeric aggregations ------------------------------------
    _AGG_DESCRIPTIONS = {
        'NumVars_Missing_Count':
            'Count of missing (NaN) values across all numeric variables for '
            'this row. Higher values may indicate incomplete applications.',
        'NumVars_Missing_Rate':
            'Proportion of missing values across numeric variables (0.0–1.0).',
        'NumVars_Zero_Count':
            'Count of numeric variables with value exactly 0. May indicate '
            'inactive accounts or zero-balance features.',
        'NumVars_Positive_Count':
            'Count of numeric variables with positive values for this row.',
        'NumVars_Negative_Count':
            'Count of numeric variables with negative values for this row.',
        'NumVars_Mean':
            'Row-wise mean across all numeric variables. Summarises overall '
            'numeric profile magnitude.',
        'NumVars_Std':
            'Row-wise standard deviation across numeric variables. Captures '
            'variability in the applicant\'s numeric profile.',
        'NumVars_Min':
            'Row-wise minimum across all numeric variables.',
        'NumVars_Max':
            'Row-wise maximum across all numeric variables.',
        'NumVars_Range':
            'Row-wise range across numeric variables. '
            'Formula: NumVars_Max − NumVars_Min.',
        'NumVars_Max_to_Mean':
            'Ratio of row-wise max to row-wise mean across numeric variables. '
            'Formula: NumVars_Max ÷ NumVars_Mean. Detects outlier-dominated '
            'profiles.',
        'NumVars_Min_to_Mean':
            'Ratio of row-wise min to row-wise mean across numeric variables. '
            'Formula: NumVars_Min ÷ NumVars_Mean.',
        'ContVars_Mean':
            'Row-wise mean across selected continuous variables.',
        'ContVars_Std':
            'Row-wise standard deviation across selected continuous variables.',
        'ContVars_Min':
            'Row-wise minimum across selected continuous variables.',
        'ContVars_Max':
            'Row-wise maximum across selected continuous variables.',
        'ContVars_Range':
            'Row-wise range across continuous variables. '
            'Formula: ContVars_Max − ContVars_Min.',
        'ContVars_Missing_Count':
            'Count of missing values across continuous variables for this row.',
        'ContVars_Zero_Count':
            'Count of continuous variables with value exactly 0 for this row.',
        'CatVars_Missing_Count':
            'Count of missing values across categorical variables for this row.',
        'CatVars_Missing_Rate':
            'Proportion of missing values across categorical variables '
            '(0.0–1.0).',
    }
    if col_name in _AGG_DESCRIPTIONS:
        return _AGG_DESCRIPTIONS[col_name]

    # --- Generic aggregation suffix patterns ------------------------------
    agg_suffix = re.match(
        r'^(.+?)_(Missing_Count|Missing_Rate|Zero_Count|Positive_Count|'
        r'Negative_Count|Mean|Std|Min|Max|Range|Sum|Median|Skew|Kurt)$',
        col_name,
    )
    if agg_suffix:
        prefix, stat = agg_suffix.group(1), agg_suffix.group(2)
        stat_label = stat.replace('_', ' ').lower()
        return (
            f'Row-wise {stat_label} computed across the {prefix} variable '
            f'group.'
        )

    # --- Fallback: derive what we can from the name -----------------------
    return f'AI-derived feature. Column name: {col_name}.'


# ---------------------------------------------------------------------------
# ACTION: execute_code — run arbitrary pandas code on the dataset
# ---------------------------------------------------------------------------

@tool(name="execute-code")
def execute_code(file_id: int, payload: dict) -> dict:
    """
    Run user/AI-authored pandas code on the dataset in a safe sandbox.

    payload: {
        "code": "df['New_Col'] = df['A'] / df['B']\\ndf.drop(columns=['C'], inplace=True)",
        "description": "Human-readable summary of what the code does",
        "mode": "apply" | "exploratory"   # default: apply
    }

    - apply (default): mutates the dataset on disk (existing behavior).
    - exploratory: runs on a copy, captures stdout/preview/images, never saves.
    """
    _stamp_action_mcp_marker('execute_code')
    code = payload.get('code', '').strip()
    description = payload.get('description', '')
    mode = (payload.get('mode') or 'apply').strip().lower()
    if mode not in ('apply', 'exploratory'):
        mode = 'apply'
    set_span_attr('declarai.execute_code.mode', mode)
    if not code:
        return {'status': 'error', 'error': 'No code provided', 'mode': mode}

    if mode == 'exploratory':
        return _run_exploratory(file_id, code, description)

    # Strip import lines — np and pd are already in the sandbox
    code = _strip_import_lines(code)

    df, data_file, file_path = _load_dataframe(file_id)
    cols_before = list(df.columns)
    cols_before_set = set(cols_before)
    rows_before = len(df)

    # Create backup before execution so we can rollback on corruption
    backup_path = file_path + '.bak'
    shutil.copy2(file_path, backup_path)

    # Build a single namespace so nested functions (closures) can see `df`.
    # When exec() receives separate globals / locals, closures only close
    # over globals — putting df only in locals made it invisible inside
    # helper functions like safe_ratio().
    sandbox = {
        '__builtins__': _SAFE_BUILTINS,
        'pd': pd,
        'np': np,
        'df': df.copy(),
    }

    try:
        exec(code, sandbox)
    except Exception as e:
        _remove_backup(backup_path)
        return {
            'status': 'error',
            'mode': 'apply',
            'error': f'Code execution failed: {str(e)}',
            'traceback': traceback.format_exc(),
        }

    df_result = sandbox.get('df', df)
    if not isinstance(df_result, pd.DataFrame):
        _remove_backup(backup_path)
        return {'status': 'error', 'mode': 'apply', 'error': 'Result is not a DataFrame — did you reassign `df`?'}

    # --- Structural validation: original columns must survive ---
    cols_after = set(df_result.columns)
    missing_original = cols_before_set - cols_after
    # Allow intentional drops (up to 30% of originals), but flag total corruption
    if missing_original and len(missing_original) > len(cols_before) * 0.3:
        _restore_backup(backup_path, file_path)
        return {
            'status': 'error',
            'mode': 'apply',
            'error': (
                f'Code execution corrupted the DataFrame — '
                f'{len(missing_original)} of {len(cols_before)} original columns disappeared. '
                f'Dataset has been restored from backup.'
            ),
        }

    # Verify column names are plausible (not auto-generated ints from lost headers)
    sample_cols = list(df_result.columns)[:10]
    int_like_count = sum(1 for c in sample_cols if isinstance(c, int) or (isinstance(c, str) and c.isdigit() and len(c) <= 3))
    if int_like_count > len(sample_cols) * 0.5 and not any(isinstance(c, int) or (isinstance(c, str) and c.isdigit() and len(c) <= 3) for c in cols_before[:10]):
        _restore_backup(backup_path, file_path)
        return {
            'status': 'error',
            'mode': 'apply',
            'error': (
                'Code execution corrupted column headers (got auto-generated integer names). '
                'Dataset has been restored from backup.'
            ),
        }

    # Compute what changed
    added = sorted(cols_after - cols_before_set)
    removed = sorted(cols_before_set - cols_after)
    rows_after = len(df_result)

    # Save
    _save_dataframe(df_result, data_file, file_path)

    # Verify the saved file can be re-read with correct structure
    try:
        df_verify = pd.read_csv(file_path) if not file_path.lower().endswith(('.xls', '.xlsx')) else df_result
        if set(df_verify.columns) != cols_after:
            raise ValueError("Column mismatch after save/reload")
    except Exception:
        _restore_backup(backup_path, file_path)
        return {
            'status': 'error',
            'mode': 'apply',
            'error': 'File save verification failed — columns corrupted during write. Dataset restored from backup.',
        }

    _remove_backup(backup_path)

    # Update DataDictionary for new columns with feature-specific descriptions
    for col_name in added:
        feat_desc = _generate_feature_description(col_name, data_file)
        DataDictionary.objects.update_or_create(
            data_file=data_file,
            column_name=col_name,
            defaults={'description': feat_desc}
        )
    # Remove DataDictionary entries for dropped columns
    if removed:
        DataDictionary.objects.filter(data_file=data_file, column_name__in=removed).delete()

    return {
        'status': 'success',
        'action_type': 'execute_code',
        'mode': 'apply',
        'description': description,
        'stdout': '',
        'images': [],
        'changes': {
            'columns_added': added,
            'columns_removed': removed,
            'rows_before': rows_before,
            'rows_after': rows_after,
        },
        'preview': _build_preview(df_result),
    }


# ---------------------------------------------------------------------------
# ACTION: update_metadata — modify data dictionary entries
# ---------------------------------------------------------------------------

@tool(name="update-metadata")
def update_metadata(file_id: int, payload: dict) -> dict:
    """
    Update data dictionary entries (Feature_Description, Level_of_Measurement, etc.).

    payload: {
        "updates": [
            {"column": "Var_1", "field": "Feature_Description", "value": "Number of CC apps last month"},
            {"column": "Var_4", "field": "Level_of_Measurement", "value": "continuous"}
        ],
        "description": "..."
    }
    """
    _stamp_action_mcp_marker('update_metadata')
    updates = payload.get('updates', [])
    description = payload.get('description', '')
    if not updates:
        return {'status': 'error', 'error': 'No updates provided'}

    data_file = Declaration.objects.get(pk=file_id)
    applied = []
    errors = []

    for upd in updates:
        col = upd.get('column', '')
        field = upd.get('field', '')
        value = upd.get('value', '')
        if not col or not field:
            errors.append({'column': col, 'error': 'column and field are required'})
            continue
        try:
            if field == 'Feature_Description':
                DataDictionary.objects.update_or_create(
                    data_file=data_file,
                    column_name=col,
                    defaults={'description': str(value)}
                )
                applied.append({'column': col, 'field': field, 'value': value})
            else:
                # For fields stored in the dictionary JSON (LOM, Data_Type, etc.),
                # we return them for the frontend to apply in-memory
                applied.append({'column': col, 'field': field, 'value': value})
        except Exception as e:
            errors.append({'column': col, 'error': str(e)})

    return {
        'status': 'success' if applied else 'error',
        'action_type': 'update_metadata',
        'description': description,
        'applied': applied,
        'errors': errors,
    }


# ---------------------------------------------------------------------------
# ACTION: update_config — change pipeline decisions
# ---------------------------------------------------------------------------

@tool(name="update-config")
def update_config(file_id: int, payload: dict) -> dict:
    """
    Change pipeline decisions. The backend validates and returns the changes;
    the frontend applies them to SharedService / component state.

    payload: {
        "updates": [
            {"key": "model_usage", "column": "AppID", "value": "No"},
            {"key": "model_usage", "column": "Application_Datetime", "value": "No"},
            {"key": "preprocessing_options", "value": [1, 2, 3, 5]},
            {"key": "split_strategy", "value": "random"},
            ...
        ],
        "description": "..."
    }
    """
    _stamp_action_mcp_marker('update_config')
    updates = payload.get('updates', [])
    description = payload.get('description', '')
    if not updates:
        return {'status': 'error', 'error': 'No config updates provided'}

    # Validate columns exist (for model_usage updates)
    try:
        df, _, _ = _load_dataframe(file_id)
        valid_cols = set(df.columns.tolist())
    except Exception:
        valid_cols = set()

    applied = []
    errors = []

    for upd in updates:
        key = upd.get('key', '')
        if key == 'model_usage':
            col = upd.get('column', '')
            val = upd.get('value', '')
            if col and col in valid_cols and val in ('Yes', 'No'):
                applied.append({'key': key, 'column': col, 'value': val})
            else:
                errors.append({'key': key, 'column': col, 'error': 'Invalid column or value'})
        elif key == 'feature_usage':
            # v2.25.0+: mirrors the existing manual UI dropdown in the
            # Selected Features table.  Setting feature_usage='drop' on
            # a feature is the canonical way for the AI to exclude it
            # from SFS without physically removing the column from the
            # dataset (which would invalidate cached modeling artifacts
            # like selected_features, shap_details, encoding_plan).
            # The frontend's existing SFS start flow already passes
            # `featureUsage['col']==='drop'` features as `excluded_features`
            # to the SFS engine.
            col = upd.get('column', '')
            val = upd.get('value', '')
            reason = upd.get('reason', '')
            if not col or not isinstance(col, str):
                errors.append({'key': key, 'column': col, 'error': 'column is required for feature_usage'})
                continue
            if val not in ('keep', 'drop'):
                errors.append({'key': key, 'column': col, 'error': "feature_usage value must be 'keep' or 'drop'"})
                continue
            # Don't validate column against valid_cols here — feature_usage
            # targets the selected_features list, which may include
            # encoded columns (e.g. one-hot expansions) that don't
            # exist as raw dataframe columns.  Validation happens at
            # SFS-start time when excluded_features is intersected
            # with the actual feature matrix.
            entry = {'key': key, 'column': col, 'value': val}
            if reason:
                entry['reason'] = str(reason)
            applied.append(entry)
        elif key in ('preprocessing_options', 'purifier_options'):
            # `purifier_options` is the field name used by
            # update_purifier_selection / start_data_purifier.  Models
            # routinely emit it under update_config instead of the
            # documented `preprocessing_options` key; without this
            # alias the backend returns success ("1 setting(s) changed")
            # while the Data-Purifier checkboxes stay put.  Normalize
            # to preprocessing_options so the frontend apply path has
            # a single key to listen for.
            val = upd.get('value')
            if not isinstance(val, list):
                errors.append({
                    'key': key,
                    'error': 'preprocessing_options/purifier_options value must be a list of integer IDs',
                })
                continue
            coerced: list = []
            seen: set = set()
            for v in val:
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    continue
                if not (1 <= iv <= 34) or iv in seen:
                    continue
                seen.add(iv)
                coerced.append(iv)
            applied.append({'key': 'preprocessing_options', 'value': coerced})
        elif key in ('split_strategy', 'split_date_column',
                     'split_cutoff', 'encoding_strategy', 'algorithm'):
            applied.append({'key': key, 'value': upd.get('value')})
        else:
            # Pass through — frontend decides how to apply
            applied.append({'key': key, 'value': upd.get('value'), 'column': upd.get('column')})

    return {
        'status': 'success' if applied else 'error',
        'action_type': 'update_config',
        'description': description,
        'applied': applied,
        'errors': errors,
    }


# ---------------------------------------------------------------------------
# ACTION: start_sfs — initiate Sequential Feature Selection
# ---------------------------------------------------------------------------
#
# Procedural context: SFS (sequential feature selection) is the
# pipeline step that explores feature-subset performance by either
# adding (forward) or removing (backward) features one at a time and
# tracking CV ROC-AUC/PR-AUC at each step.  The pipeline UI exposes a
# "Start SFS" button alongside form fields for methods, stopping
# criteria, n_jobs, top_k, and a per-feature "Keep / Drop" dropdown.
#
# Before v2.25.0 the AI assistant had no way to actually KICK OFF SFS
# — it could only TALK about doing it.  When the user asked "drop
# Var_3 due to VIF and start SFS" the assistant correctly proposed
# the drop via execute_code but then asserted "SFS Status: Initiated"
# as plain text, with nothing actually starting.  This action closes
# that gap.
#
# Validation rules
# ----------------
# * `methods` must be a non-empty list whose elements are drawn from
#   {'forward', 'backward'}.  Duplicates are deduplicated.
# * `stopping_criteria.metrics` must be a non-empty list of
#   {metric, pct_change} entries; metric ∈ {'roc_auc', 'pr_auc'}.
# * `stopping_criteria.min_features` / `max_features` must be
#   positive ints when present.
# * `excluded_features` (optional) — list of column names the AI
#   wants the SFS engine to skip.  Matches the existing
#   `featureUsage[col] === 'drop'` UI mechanism.
# * `n_jobs` / `top_k` — positive ints, clamped to sane bounds.
#
# Returns the validated config in `applied` for the frontend chat
# panel to forward via `sfsStartRequests$` to the modeling component,
# which mirrors the user clicking "Start SFS" with these settings.

@tool(name="start-sfs")
def start_sfs(file_id: int, payload: dict) -> dict:
    """
    Validate and broadcast an SFS-start request.

    payload: {
        "methods": ["backward"],        # or ["forward"] or ["forward", "backward"]
        "stopping_criteria": {
            "metrics": [{"metric": "roc_auc", "pct_change": 1.0}],
            "min_features": 5,
            "max_features": 15
        },
        "excluded_features": ["Var_3"], # optional — features to skip
        "n_jobs": 3,
        "top_k": 5,
        "description": "Start backward SFS, excluding Var_3 (VIF=9.39)"
    }
    """
    _stamp_action_mcp_marker('start_sfs')
    description = payload.get('description', '')

    # ── v2.35.0: in-flight guard — refuse to spawn a duplicate run ──
    # Without this, the LLM sometimes proposed start_sfs again when it
    # found stale or empty cached results mid-run (see the 2026-05-19
    # ToDoS screenshot).  The slim-context preamble in views.py and the
    # status header in _handle_get_sfs_results both warn the LLM,
    # but the guard here is the last line of defence — even a confused
    # model that bypasses the warnings cannot accidentally start a
    # second SFS run that would clobber SFS_PROGRESS[file_id] and
    # truncate the in-flight intermediate-results file.
    try:
        from .tool_executor import read_sfs_status
        live = read_sfs_status(file_id)
        live_status = live.get('status') if isinstance(live, dict) else None
    except Exception:
        live_status = None
    if live_status == 'running':
        progress = live.get('progress', 0.0) if isinstance(live, dict) else 0.0
        completed = live.get('completed_step_count', 0) if isinstance(live, dict) else 0
        return {
            'status': 'error',
            'action_type': 'start_sfs',
            'description': description,
            'error': (
                f'SFS is already running for file_id={file_id} '
                f'(progress={progress:.0%}, {completed} steps completed). '
                f'Refusing to spawn a duplicate run — wait for the current '
                f'SFS to complete or have the user click Stop SFS first.'
            ),
            'errors': ['sfs_already_running'],
        }

    # ── methods ────────────────────────────────────────────────────
    methods_raw = payload.get('methods', [])
    if not isinstance(methods_raw, list) or not methods_raw:
        return {'status': 'error', 'error': 'methods must be a non-empty list (forward|backward)'}
    methods: list = []
    bad_methods: list = []
    seen = set()
    for m in methods_raw:
        if not isinstance(m, str):
            bad_methods.append(repr(m))
            continue
        ml = m.strip().lower()
        if ml not in ('forward', 'backward'):
            bad_methods.append(m)
            continue
        if ml in seen:
            continue
        seen.add(ml)
        methods.append(ml)
    if not methods:
        return {
            'status': 'error',
            'error': f'methods must contain at least one of forward/backward (got: {bad_methods})',
        }

    # ── stopping_criteria ──────────────────────────────────────────
    sc_in = payload.get('stopping_criteria') or {}
    if not isinstance(sc_in, dict):
        return {'status': 'error', 'error': 'stopping_criteria must be an object'}
    metrics_in = sc_in.get('metrics', [])
    if not isinstance(metrics_in, list) or not metrics_in:
        return {
            'status': 'error',
            'error': 'stopping_criteria.metrics must be a non-empty list of {metric, pct_change}',
        }
    metrics: list = []
    for mc in metrics_in:
        if not isinstance(mc, dict):
            continue
        metric_name = mc.get('metric', '')
        if metric_name not in ('roc_auc', 'pr_auc'):
            continue
        try:
            pct = float(mc.get('pct_change', 0.0))
        except (TypeError, ValueError):
            pct = 0.0
        metrics.append({'metric': metric_name, 'pct_change': pct})
    if not metrics:
        return {
            'status': 'error',
            'error': "stopping_criteria.metrics entries must have metric ∈ {'roc_auc','pr_auc'}",
        }

    def _pos_int(v, default):
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return default
        return iv if iv > 0 else default

    stopping_criteria = {
        'metrics': metrics,
        'min_features': _pos_int(sc_in.get('min_features', 5), 5),
        'max_features': _pos_int(sc_in.get('max_features', 15), 15),
    }

    # ── excluded_features ──────────────────────────────────────────
    excluded_raw = payload.get('excluded_features', []) or []
    if not isinstance(excluded_raw, list):
        excluded = []
    else:
        excluded = [str(c) for c in excluded_raw if isinstance(c, str) and c.strip()]

    # ── n_jobs / top_k (clamped) ────────────────────────────────────
    n_jobs = max(1, min(_pos_int(payload.get('n_jobs', 3), 3), 16))
    top_k = max(1, min(_pos_int(payload.get('top_k', 5), 5), 50))

    # ── v2.37.0: backward_cut_step (forward-from-backward) ─────────
    # When set, the AI is requesting forward-from-backward SFS using
    # the features remaining at the given backward step.  This mirrors
    # the user clicking the radio at that row in the Backward
    # Elimination table, then clicking "Run Forward Selection on
    # These N Features".
    #
    # Before v2.37.0 the AI's only way to mimic this was to enumerate
    # every backward-dropped feature in ``excluded_features`` — fragile
    # (off-by-one in step counting, missed features), conflated with
    # user-drop intent, and never updated the visible cut step
    # display (the green box at the bottom of the backward table).
    #
    # Constraints:
    #   - Must be a positive integer.
    #   - ``methods`` must include 'forward' — the cut step has no
    #     effect on a backward-only run, so accepting it would be
    #     silent corruption.
    #   - The step must exist in the on-disk sfs_results JSON.  If
    #     no backward SFS has been run yet (file missing or
    #     ``backward`` array empty), reject — the cut step is
    #     meaningless without backward results to cut.
    backward_cut_step_raw = payload.get('backward_cut_step', None)
    backward_cut_step = None
    if backward_cut_step_raw is not None:
        try:
            bcs = int(backward_cut_step_raw)
        except (TypeError, ValueError):
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': (
                    f'backward_cut_step must be a positive integer '
                    f'(got: {backward_cut_step_raw!r})'
                ),
                'errors': ['invalid_backward_cut_step'],
            }
        if bcs <= 0:
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': f'backward_cut_step must be a positive integer (got: {bcs})',
                'errors': ['invalid_backward_cut_step'],
            }
        if 'forward' not in methods:
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': (
                    f"backward_cut_step requires methods to include 'forward' "
                    f"(forward-from-backward SFS); got methods={methods}"
                ),
                'errors': ['backward_cut_step_requires_forward_method'],
            }
        # Validate the step exists in the on-disk sfs_results JSON.
        from django.conf import settings as _settings  # local import — avoid Django at module load when settings absent
        import os as _os
        import json as _json
        sfs_path = _os.path.join(
            _settings.MEDIA_ROOT, 'sfs_results', f'{file_id}_sfs_results.json'
        )
        if not _os.path.exists(sfs_path):
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': (
                    f'backward_cut_step={bcs} requires a completed backward SFS run, '
                    f'but no sfs_results file exists for file_id={file_id}'
                ),
                'errors': ['no_sfs_results_for_cut_step'],
            }
        try:
            with open(sfs_path, 'r', encoding='utf-8') as _f:
                sfs_data = _json.load(_f)
        except Exception as _read_err:
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': f'Failed to read sfs_results JSON for file_id={file_id}: {_read_err}',
                'errors': ['sfs_results_read_error'],
            }
        backward_steps = sfs_data.get('backward', []) or []
        valid_steps = {
            int(s.get('step'))
            for s in backward_steps
            if isinstance(s, dict) and isinstance(s.get('step'), (int, float))
        }
        if not valid_steps:
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': (
                    f'backward_cut_step={bcs} requires backward SFS results, '
                    f'but the sfs_results JSON for file_id={file_id} has no backward array'
                ),
                'errors': ['no_backward_results_for_cut_step'],
            }
        if bcs not in valid_steps:
            sorted_steps = sorted(valid_steps)
            return {
                'status': 'error',
                'action_type': 'start_sfs',
                'description': description,
                'error': (
                    f'backward_cut_step={bcs} is not a valid backward step '
                    f'(valid steps: {sorted_steps[0]}..{sorted_steps[-1]}, '
                    f'{len(sorted_steps)} total)'
                ),
                'errors': ['invalid_backward_cut_step_value'],
            }
        backward_cut_step = bcs

    return {
        'status': 'success',
        'action_type': 'start_sfs',
        'description': description,
        'applied': {
            'methods': methods,
            'stopping_criteria': stopping_criteria,
            'excluded_features': excluded,
            'n_jobs': n_jobs,
            'top_k': top_k,
            'backward_cut_step': backward_cut_step,
        },
        'errors': [],
    }


# ---------------------------------------------------------------------------
# ACTION: start_data_purifier — kick off preprocessing/purifier pipeline
# ---------------------------------------------------------------------------
#
# Procedural context: the data purifier is the FIRST run-step in the
# pipeline.  It applies the user's selected purifier options (e.g.
# missing-value imputation, low-variance pruning, outlier cleaning)
# and the chosen train/test split (random or OOT) to produce the
# `processed_file` that all downstream steps (encoding, modeling,
# SFS) consume.  The pipeline UI exposes a "Run Preprocessing" button
# in the model-development component along with checkboxes for
# purifier options and form fields for split config.
#
# Before v2.26.0 the AI assistant could only DISCUSS preprocessing —
# it had no way to actually fire `runPreprocessing()`.  When the
# user asked "run preprocessing" the assistant typically said
# something like "Please click the Run Preprocessing button".
# This action closes that gap.
#
# Validation rules
# ----------------
# * `purifier_options` (optional) — list of integer option IDs (1–34)
#   matching the selectable preprocessing checkboxes.  Invalid IDs
#   are dropped silently; an empty/missing list means "use whatever
#   is currently selected in the UI" (the SharedService cache).
# * `split` (optional) — dict with:
#     - `strategy`: 'random' or 'oot'
#     - `date_column`: required when strategy='oot'
#     - `cutoff`: optional ISO datetime when strategy='oot' + cutoff mode
#     - `percent`: optional 0<x<100 percentage for OOS / OOT-percent mode
#   Missing/invalid → defaults to {'strategy':'random','percent':25}.
#
# Returns the validated config in `applied` for the frontend chat
# panel to forward via `dataPurifierStartRequests$` to the
# model-development component, which mirrors the user clicking
# "Run Preprocessing" with these settings.

@tool(name="start-data-purifier")
def start_data_purifier(file_id: int, payload: dict) -> dict:
    """
    Validate and broadcast a data-purifier (preprocessing) start request.

    payload: {
        "purifier_options": [1, 2, 5, 7],  # optional — checkbox IDs
        "split": {
            "strategy": "random",          # or "oot"
            "percent": 25                  # OOS percentage
        },
        "description": "Run preprocessing with default purifier options"
    }
    """
    _stamp_action_mcp_marker('start_data_purifier')
    description = payload.get('description', '')

    # ── purifier_options ───────────────────────────────────────────
    raw_opts = payload.get('purifier_options', None)
    purifier_options: list = []
    if raw_opts is not None:
        if not isinstance(raw_opts, list):
            return {'status': 'error', 'error': 'purifier_options must be a list of integer option IDs'}
        for v in raw_opts:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            # The pipeline UI exposes options 1..34 (matching
            # purifierOptions in model-development.component).  Any
            # ID outside that range is dropped.
            if 1 <= iv <= 34:
                purifier_options.append(iv)
        # Dedup while preserving order — the AI may double-list
        # options when chaining suggestions.
        seen = set()
        deduped = []
        for iv in purifier_options:
            if iv in seen:
                continue
            seen.add(iv)
            deduped.append(iv)
        purifier_options = deduped

    # ── split ──────────────────────────────────────────────────────
    split_in = payload.get('split', None)
    if split_in is None:
        split = None  # frontend will fall back to its current form values
    elif not isinstance(split_in, dict):
        return {'status': 'error', 'error': 'split must be an object'}
    else:
        strategy = split_in.get('strategy', 'random')
        if strategy not in ('random', 'oot'):
            return {
                'status': 'error',
                'error': "split.strategy must be 'random' or 'oot'",
            }
        split = {'strategy': strategy}

        # percent is optional; if present it must be 0<pct<100.
        pct = split_in.get('percent', None)
        if pct is not None:
            try:
                pct_f = float(pct)
            except (TypeError, ValueError):
                pct_f = None
            if pct_f is not None and 0 < pct_f < 100:
                split['percent'] = pct_f

        if strategy == 'oot':
            date_col = split_in.get('date_column', '')
            if not isinstance(date_col, str) or not date_col.strip():
                return {
                    'status': 'error',
                    'error': "split.date_column is required when split.strategy='oot'",
                }
            split['date_column'] = date_col.strip()
            cutoff = split_in.get('cutoff', None)
            if cutoff is not None:
                if not isinstance(cutoff, str) or not cutoff.strip():
                    return {
                        'status': 'error',
                        'error': 'split.cutoff must be an ISO datetime string',
                    }
                split['cutoff'] = cutoff.strip()

    return {
        'status': 'success',
        'action_type': 'start_data_purifier',
        'description': description,
        'applied': {
            'purifier_options': purifier_options,
            'split': split,
        },
        'errors': [],
    }


# ---------------------------------------------------------------------------
# ACTION: update_purifier_selection — edit the Data-Purifier checkbox UI
# without firing the run (v2.28.0+)
# ---------------------------------------------------------------------------
#
# Procedural context: `start_data_purifier` is fire-and-run.  When the
# AI's advisory voice says "let me consolidate IDs 11+17 into ID 23 for
# you, here's why..." the user deserves a chance to see the new checkbox
# state and review it BEFORE the pipeline actually executes.  This
# action is the no-run sibling of start_data_purifier — it patches the
# UI so the user can review (and optionally tweak) the new selection,
# then they click Run Preprocessing themselves OR ask the AI to fire it
# in the next turn.
#
# Two payload forms (the AI picks whichever is more natural for the
# user's intent):
#
#   1. WHOLESALE — fully specifies the target option set.  Best when
#      the AI knows exactly which IDs should end up checked.  The
#      handler validates the entire set for group conflicts (e.g., two
#      members of the outlier_num_group cannot both be checked because
#      the UI is single-select per group).
#
#        {"purifier_options": [1, 2, 3, 4, 7, 23, 28, 32],
#         "description": "Consolidate IDs 11+17 into ID 23"}
#
#   2. DIFF — incremental add/remove against the user's CURRENT
#      selection.  Best when the AI is making a surgical tweak ("just
#      turn off ID 7") and would otherwise have to re-state the user's
#      whole list.  Group-conflict detection on the diff is deferred
#      to the frontend subscriber (which sees the resolved final state).
#
#        {"add": [23], "remove": [11, 17],
#         "description": "Replace separate sparsity/missing drops with combined-drop"}
#
# Both forms return a single canonical `applied` shape so the frontend
# can render one chat-summary template:
#
#   applied = {
#     "form": "wholesale" | "diff",
#     "purifier_options": list[int] | None,   # wholesale only
#     "add": list[int],                       # diff only
#     "remove": list[int],                    # diff only
#   }
#
# Span attributes (declarai-action workflow span):
#   declarai.purifier.form         "wholesale" | "diff"
#   declarai.purifier.final        comma-joined IDs (wholesale only)
#   declarai.purifier.added        comma-joined IDs (diff only)
#   declarai.purifier.removed      comma-joined IDs (diff only)
#   declarai.purifier.invalid_ids  comma-joined IDs that were rejected
#   declarai.purifier.group_conflict  optional error tag


@tool(name="update-purifier-selection")
def update_purifier_selection(file_id: int, payload: dict) -> dict:
    """
    Validate and broadcast a Data-Purifier checkbox-selection update.

    Unlike start_data_purifier, this action DOES NOT run the
    preprocessing pipeline — it only patches the UI so the user can
    review the new selection and click Run themselves.

    payload accepts EITHER (XOR):
      • {"purifier_options": [1, 2, 5, 7, 23, 28, 32], "description": "..."}
      • {"add": [23], "remove": [11, 17], "description": "..."}

    Errors are returned with status='error' and a structured `error`
    string the AI can interpret on its next turn:
      • "Specify exactly one of `purifier_options` or `add`/`remove`."
      • "ID <N> appears in both add and remove."
      • "Group conflict: IDs <N>, <M> both belong to <group_name>."

    v2.31.0 (Phase 3a): the entire validation flow is wrapped in a
    Prometa ``schema.validate`` AML span (catalog C4).  Each return
    point stamps ``sv.result(passed=..., errors=[...])`` so the
    platform's output-validation detector can score:
      - which schema_id (action) is failing most
      - error categories (form_conflict, group_conflict, diff_conflict,
        invalid_ids, value_error)
      - whether downstream is blocked (errors short-circuit the
        broadcast; success cases don't)
    Existing ``set_span_attr('declarai.purifier.*')`` calls are kept
    on the surrounding span as backwards-compatible debug attrs;
    the AML span is purely additive.

    Args:
        file_id: pipeline file id (not used today; kept for signature
            parity with the other action handlers and future cache
            integration).
        payload: dict described above.

    Returns:
        Action result dict with `applied` shape documented in the
        module-level comment block.
    """
    _stamp_action_mcp_marker('update_purifier_selection')
    # Imported lazily so importing this module never triggers a Django
    # apps registry walk through preprocessing's own imports.  Matches
    # the lazy-import pattern in _handle_get_purifier_options.
    from preprocessing.purifier_catalog import PURIFIER_OPTIONS

    description = payload.get('description', '') if isinstance(payload, dict) else ''

    # ── Build the catalog lookup table (id → entry) for validation.
    catalog_by_id = {e['id']: e for e in PURIFIER_OPTIONS}
    valid_id_range = (1, 34)

    def _coerce_int_list(raw, field_name: str) -> tuple[list[int], list[int]]:
        """Return (valid_ids, invalid_or_dropped) from a raw payload list.

        Non-int entries are dropped silently (same forgiving contract
        as start_data_purifier).  IDs outside 1..34 land in the
        ``invalid`` bucket and are also dropped — but unlike
        start_data_purifier we surface them via a span attribute so the
        AI can see (in tracing) which IDs it guessed wrong.
        """
        if raw is None:
            return [], []
        if not isinstance(raw, list):
            raise ValueError(f"`{field_name}` must be a list of integer option IDs")
        valid: list[int] = []
        invalid: list[int] = []
        seen = set()
        for v in raw:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            if not (valid_id_range[0] <= iv <= valid_id_range[1]):
                invalid.append(iv)
                continue
            if iv in seen:
                continue
            seen.add(iv)
            valid.append(iv)
        return valid, invalid

    has_wholesale = 'purifier_options' in payload
    has_diff = ('add' in payload) or ('remove' in payload)

    # v2.31.0 (Phase 3a): wrap the entire validation flow in a
    # Prometa ``schema.validate`` AML span.  Each return path stamps
    # ``sv.result(...)`` with the outcome before returning so the
    # platform's C4 detector can categorize failures.  Existing
    # set_span_attr('declarai.purifier.*') calls are KEPT on the
    # surrounding span for back-compat (debugging via Trace Explorer).
    with schema_validate('declarai:update-purifier-selection@v1') as sv:
        if has_wholesale and has_diff:
            set_span_attr('declarai.purifier.form_conflict', True)
            sv.result(
                passed=False,
                errors=['form_conflict: both purifier_options and add/remove specified'],
                downstream_blocked=True,
            )
            return {
                'status': 'error',
                'action_type': 'update_purifier_selection',
                'error': (
                    "Specify exactly one of `purifier_options` (wholesale form) "
                    "or `add`/`remove` (diff form), not both."
                ),
            }

        if not has_wholesale and not has_diff:
            # Description-only payloads are a no-op rather than an error —
            # mirrors how the chat panel treats empty action results.
            set_span_attr('declarai.purifier.form', 'noop')
            sv.result(passed=True)  # noop is a valid form, not a failure
            return {
                'status': 'success',
                'action_type': 'update_purifier_selection',
                'description': description,
                'applied': {
                    'form': 'noop',
                    'purifier_options': None,
                    'add': [],
                    'remove': [],
                },
                'errors': [],
            }

        try:
            if has_wholesale:
                wholesale_ids, wholesale_invalid = _coerce_int_list(
                    payload.get('purifier_options'), 'purifier_options',
                )
            else:
                add_ids, add_invalid = _coerce_int_list(payload.get('add'), 'add')
                remove_ids, remove_invalid = _coerce_int_list(payload.get('remove'), 'remove')
        except ValueError as exc:
            sv.result(
                passed=False,
                errors=[f'value_error: {exc}'],
                downstream_blocked=True,
            )
            return {
                'status': 'error',
                'action_type': 'update_purifier_selection',
                'error': str(exc),
            }

        # ── Wholesale-form validation
        if has_wholesale:
            set_span_attr('declarai.purifier.form', 'wholesale')
            if wholesale_invalid:
                set_span_attr(
                    'declarai.purifier.invalid_ids',
                    ','.join(str(i) for i in wholesale_invalid),
                )

            # Group-conflict detection: within any non-None group, at most
            # ONE member may be selected.  The UI enforces this visually
            # via isOptionDisabled(); the backend enforces it here so the
            # AI gets a structured error it can recover from on the next
            # turn instead of producing a silently-malformed selection.
            groups_seen: dict[int, list[int]] = {}
            for oid in wholesale_ids:
                entry = catalog_by_id.get(oid)
                if entry is None:
                    continue
                g = entry.get('group')
                if g is None:
                    continue
                groups_seen.setdefault(g, []).append(oid)
            conflicts = {g: ids for g, ids in groups_seen.items() if len(ids) > 1}
            if conflicts:
                # Build a human-readable error the AI can parse.  We list
                # the conflicting group(s) and their member IDs.
                group_label = {
                    1: 'corr_drop_group',
                    2: 'sparsity_drop_group',
                    3: 'missing_drop_group',
                    4: 'combined_drop_group',
                    5: 'outlier_num_group',
                    6: 'outlier_cat_group',
                }
                parts = [
                    f"{group_label.get(g, f'group_{g}')}: IDs {ids}"
                    for g, ids in conflicts.items()
                ]
                set_span_attr(
                    'declarai.purifier.group_conflict',
                    '; '.join(parts),
                )
                sv.result(
                    passed=False,
                    errors=[f'group_conflict: {p}' for p in parts],
                    downstream_blocked=True,
                )
                return {
                    'status': 'error',
                    'action_type': 'update_purifier_selection',
                    'error': (
                        "Group conflict — at most one option per group may be "
                        "selected. Conflicts: " + '; '.join(parts) +
                        ". Pick a single ID per group."
                    ),
                }

            set_span_attr(
                'declarai.purifier.final',
                ','.join(str(i) for i in wholesale_ids) or '(empty)',
            )

            sv.result(passed=True)
            return {
                'status': 'success',
                'action_type': 'update_purifier_selection',
                'description': description,
                'applied': {
                    'form': 'wholesale',
                    'purifier_options': wholesale_ids,
                    'add': [],
                    'remove': [],
                },
                'errors': [],
            }

        # ── Diff-form validation
        set_span_attr('declarai.purifier.form', 'diff')
        invalid_combined = add_invalid + remove_invalid
        if invalid_combined:
            set_span_attr(
                'declarai.purifier.invalid_ids',
                ','.join(str(i) for i in invalid_combined),
            )

        add_set = set(add_ids)
        remove_set = set(remove_ids)
        conflict_set = add_set & remove_set
        if conflict_set:
            set_span_attr(
                'declarai.purifier.diff_conflict',
                ','.join(str(i) for i in sorted(conflict_set)),
            )
            sv.result(
                passed=False,
                errors=[f'diff_conflict: IDs {sorted(conflict_set)} in both add and remove'],
                downstream_blocked=True,
            )
            return {
                'status': 'error',
                'action_type': 'update_purifier_selection',
                'error': (
                    f"ID(s) {sorted(conflict_set)} appear in both `add` and "
                    "`remove`. Each ID can only go one way per action."
                ),
            }

        if not add_ids and not remove_ids:
            # No-op diff — accept and broadcast nothing.  Avoids surfacing
            # a confusing "I changed nothing" UI flash.
            set_span_attr('declarai.purifier.form', 'diff_noop')
            sv.result(passed=True)  # diff_noop is a valid form, not a failure
            return {
                'status': 'success',
                'action_type': 'update_purifier_selection',
                'description': description,
                'applied': {
                    'form': 'noop',
                    'purifier_options': None,
                    'add': [],
                    'remove': [],
                },
                'errors': [],
            }

        set_span_attr(
            'declarai.purifier.added',
            ','.join(str(i) for i in add_ids) or '(empty)',
        )
        set_span_attr(
            'declarai.purifier.removed',
            ','.join(str(i) for i in remove_ids) or '(empty)',
        )
        sv.result(passed=True)

    return {
        'status': 'success',
        'action_type': 'update_purifier_selection',
        'description': description,
        'applied': {
            'form': 'diff',
            'purifier_options': None,
            'add': add_ids,
            'remove': remove_ids,
        },
        'errors': [],
    }


# ---------------------------------------------------------------------------
# ACTION: apply_encoding — apply the encoding plan and produce encoded file
# ---------------------------------------------------------------------------
#
# Procedural context: after preprocessing produces the processed
# file and the user reviews / edits the encoding plan (one row per
# feature: nominal/ordinal, fallback strategy, ranking if ordinal),
# the "Apply Encoding" button calls
# `dataService.applyEncoding(file_id, processed_file, plan,
# use_native)`.  This produces the encoded file that modeling
# consumes.
#
# Pre-conditions the AI must check before firing:
# * `processed_file` exists (data purifier has run).
# * Encoding plan has been analyzed (encodingPlan length > 0).
# * Every feature with `needs_ranking=true` has a non-empty
#   `ranking` array — otherwise encoding silently downgrades to
#   label_encoding and the ordinal signal is lost.  The AI can
#   verify this via its `get_encoding_plan` tool.
#
# Validation rules
# ----------------
# * `use_native` (optional) — boolean.  Defaults to true (use the
#   native encoding library; false = sklearn fallback).

@tool(name="apply-encoding")
def apply_encoding(file_id: int, payload: dict) -> dict:
    """
    Validate and broadcast an apply-encoding request.

    payload: {
        "use_native": true,                       # optional, default true
        "description": "Apply encoding plan with native library"
    }
    """
    _stamp_action_mcp_marker('apply_encoding')
    description = payload.get('description', '')
    raw_use_native = payload.get('use_native', True)
    if not isinstance(raw_use_native, bool):
        # Coerce truthy values to bool — the LLM occasionally
        # passes "true"/"false" strings.
        if isinstance(raw_use_native, str):
            use_native = raw_use_native.strip().lower() in ('true', '1', 'yes')
        else:
            use_native = bool(raw_use_native)
    else:
        use_native = raw_use_native

    return {
        'status': 'success',
        'action_type': 'apply_encoding',
        'description': description,
        'applied': {
            'use_native': use_native,
        },
        'errors': [],
    }


# ---------------------------------------------------------------------------
# ACTION: start_modeling — kick off the modeling step (train + evaluate)
# ---------------------------------------------------------------------------
#
# Procedural context: after preprocessing + encoding, the modeling
# step trains the chosen algorithm (LightGBM, XGBoost, CatBoost, etc.)
# on the encoded file and produces the modeling artifacts (selected
# features, SHAP details, ROC-AUC/PR-AUC metrics, training data
# snapshot for SFS).  The pipeline UI exposes a "Start Modeling"
# button in the modeling component (the bottom-left button in the
# user's screenshot that they could not get the AI to press).
#
# Before v2.26.0 the AI explicitly told users "I cannot 'start'
# the modeling engine directly (that is a button in your UI)".
# This action closes that gap — it's the dedicated path for the
# AI to fire the modeling step, mirroring a manual click exactly.
#
# Pre-conditions the AI must check before firing:
# * `currentFileId` not null (file uploaded).
# * `processedFilePath` not null (data purifier has run).
# * `availableAlgorithms` empty OR `selectedAlgorithm` chosen.
#
# Validation rules
# ----------------
# * `algorithm` (optional) — string name.  If provided, the frontend
#   sets `selectedAlgorithm` to it before firing; otherwise the
#   current form value is used.  We don't validate against a hard
#   list here because the algorithm catalog is dynamic (loaded from
#   the backend's `/algorithms/` endpoint at component init).
# * `encoding_use_native` (optional) — boolean.  Mirrors the same
#   field used by apply_encoding, since modeling can re-apply
#   encoding internally if needed.

@tool(name="start-modeling")
def start_modeling(file_id: int, payload: dict) -> dict:
    """
    Validate and broadcast a modeling-start request.

    payload: {
        "algorithm": "lightgbm",                  # optional
        "encoding_use_native": true,              # optional, default true
        "description": "Start modeling with LightGBM"
    }
    """
    _stamp_action_mcp_marker('start_modeling')
    description = payload.get('description', '')

    raw_algo = payload.get('algorithm', None)
    if raw_algo is not None and (not isinstance(raw_algo, str) or not raw_algo.strip()):
        return {
            'status': 'error',
            'error': 'algorithm must be a non-empty string when provided',
        }
    algorithm = raw_algo.strip() if isinstance(raw_algo, str) else None

    raw_use_native = payload.get('encoding_use_native', True)
    if not isinstance(raw_use_native, bool):
        if isinstance(raw_use_native, str):
            use_native = raw_use_native.strip().lower() in ('true', '1', 'yes')
        else:
            use_native = bool(raw_use_native)
    else:
        use_native = raw_use_native

    return {
        'status': 'success',
        'action_type': 'start_modeling',
        'description': description,
        'applied': {
            'algorithm': algorithm,
            'encoding_use_native': use_native,
        },
        'errors': [],
    }


# ---------------------------------------------------------------------------
# ACTION: set_ordinal_ranking — record the rank order for ordinal features
# ---------------------------------------------------------------------------
#
# Procedural context: setting an ordinal ranking on a feature only carries
# meaning when that feature's Level_of_Measurement is 'ordinal' — the rank
# order encodes a monotonic relationship the boosting model is supposed to
# learn.  Pre-v2.39.0 the AI had to emit TWO action blocks across one or
# two turns to make this work end-to-end:
#
#   1. update_metadata setting Level_of_Measurement = 'ordinal'
#   2. set_ordinal_ranking with the ranked category values
#
# Smaller models (notably gemma-4-26b through the local inference fabric)
# reliably emitted only step 2 — they internalized the system prompt's
# "RULE 3: One action block per turn" and stopped there.  The cached
# ranking was correct, but the encoding-plan column kept rendering
# 'Nominal' because LoM was never flipped, so the ranking was silently
# invisible in the UI.  The user saw a green "Applied" badge while the
# Categorical Feature Encoding table stayed unchanged.
#
# v2.39.0 closes this gap by treating LoM='ordinal' as an automatic
# *consequence* of any successfully-applied ranking instead of a
# separate prerequisite the model has to remember.  The handler:
#
#   • patches the cached encoding_plan ranking (existing behaviour),
#   • patches the cached data_dictionary so the next get_data_dictionary
#     tool call sees LoM='ordinal' for the same columns,
#   • returns an `implied_metadata_updates` array shaped identically to
#     update_metadata's `applied`, so the frontend can fan it out on
#     the existing metadataUpdates$ stream alongside the existing
#     encodingRankingUpdates$ broadcast — the encoding-plan dropdown
#     flips Nominal → Ordinal in lock-step with the ranking
#     populating, exactly as if both action blocks had run.
#
# The action's input schema is unchanged — every existing payload
# emitted by gpt-5.5 / gpt-5.4-mini / gemma-4-26b continues to work.

@tool(name="set-ordinal-ranking")
def set_ordinal_ranking(file_id: int, payload: dict) -> dict:
    """
    Record the ordinal ranking (rank order of distinct category values) for
    one or more ordinal-labelled features.

    payload: {
        "updates": [
            {
                "column": "Var_36",
                "ranking": ["0", "1", "2", "3", "8", "L", "Others"]
            },
            {
                "column": "Var_2",
                "ranking": ["A", "P", "R"]
            }
        ],
        "description": "Reflect risk severity progression for status codes."
    }

    Validation rules
    ----------------
    * `updates` must be a non-empty list.
    * each entry must have a non-empty `column` (str) and a non-empty
      `ranking` (list of >= 2 unique values).
    * duplicate values inside a ranking are rejected — the rank order
      defines a strict ordinal scale, so each value must appear once.
    * values are coerced to strings to match the encoding plan's
      `unique_values` shape (encoding_utils._compute_stats stores them
      as `[str(v) for v in unique_values[:50]]`).
    * column does NOT need to exist in the current dataframe — the AI may
      legitimately set rankings for features that will be created later
      (e.g. immediately after `execute_code` adds a column).  Validation
      against actual unique values happens at encoding-apply time.

    On success the cached encoding_plan artifact is patched in place so
    the AI's next `get_encoding_plan` call sees the ranking it just set.
    The cached data_dictionary is similarly patched with LoM='ordinal'
    for every applied column (v2.39.0+) so subsequent get_data_dictionary
    calls report the post-action LoM, not the pre-action one.

    The response includes `implied_metadata_updates` — a list shaped
    like update_metadata's `applied` field — that the frontend uses to
    drive the metadataUpdates$ broadcast.  Pre-v2.39.0 callers that
    ignore the new field continue to work; the only behavioural change
    they observe is the encoding-plan dropdown also flipping to
    'Ordinal' when the ranking lands.
    """
    _stamp_action_mcp_marker('set_ordinal_ranking')
    updates = payload.get('updates', [])
    description = payload.get('description', '')
    if not isinstance(updates, list) or not updates:
        return {
            'status': 'error',
            'error': 'No ranking updates provided',
            'applied': [],
            'errors': [],
            'implied_metadata_updates': [],
        }

    applied: list = []
    errors: list = []

    for upd in updates:
        if not isinstance(upd, dict):
            errors.append({'column': '', 'error': 'update entry must be an object'})
            continue
        col = upd.get('column', '')
        ranking = upd.get('ranking', None)
        if not col or not isinstance(col, str):
            errors.append({'column': col, 'error': 'column is required and must be a string'})
            continue
        if not isinstance(ranking, list) or len(ranking) < 2:
            errors.append({
                'column': col,
                'error': 'ranking must be a list of at least 2 distinct values',
            })
            continue
        ranking_str = [str(v) for v in ranking]
        if len(set(ranking_str)) != len(ranking_str):
            errors.append({
                'column': col,
                'error': 'ranking contains duplicate values — each category must appear exactly once',
            })
            continue
        applied.append({'column': col, 'ranking': ranking_str})

    # ── v2.39.0: implied LoM='ordinal' metadata updates ────────────────
    # Built from the validated `applied` list so a partial-success
    # request (one valid ranking + one invalid) only flips LoM for the
    # column whose ranking actually landed.  The shape mirrors
    # update_metadata's `applied` array exactly so the frontend's
    # existing _applyMetadataPatchesToDictionaryCache + emitMetadataUpdates
    # helpers can consume it without a special case.
    implied_metadata_updates = [
        {'column': a['column'], 'field': 'Level_of_Measurement', 'value': 'ordinal'}
        for a in applied
    ]

    # Patch the cached encoding_plan artifact so the AI's NEXT tool call
    # sees the ranking it just set.  Best-effort: if Redis is unavailable
    # the frontend still applies the change in-memory via the action
    # response, and the cache simply lags one chat turn until something
    # else refreshes it.
    if applied:
        try:
            from .cache import cache_get, cache_put, ARTIFACT_ENCODING_PLAN
            cached_plan = cache_get(file_id, ARTIFACT_ENCODING_PLAN)
            if cached_plan:
                plan_list = cached_plan if isinstance(cached_plan, list) else cached_plan.get('plan', [])
                if isinstance(plan_list, list) and plan_list:
                    rank_by_col = {u['column']: u['ranking'] for u in applied}
                    mutated = False
                    for entry in plan_list:
                        if not isinstance(entry, dict):
                            continue
                        feat = entry.get('feature')
                        if isinstance(feat, str) and feat in rank_by_col:
                            entry['ranking'] = list(rank_by_col[feat])
                            mutated = True
                    if mutated:
                        if isinstance(cached_plan, list):
                            cache_put(file_id, ARTIFACT_ENCODING_PLAN, plan_list)
                        else:
                            cached_plan['plan'] = plan_list
                            cache_put(file_id, ARTIFACT_ENCODING_PLAN, cached_plan)
        except Exception:
            # Cache write-through is best-effort; never fail the action
            # because Redis hiccupped.  The frontend has the patch.
            pass

    # ── v2.39.0: patch the cached data_dictionary too ──────────────────
    # Symmetric to the encoding_plan patch above — the next time the AI
    # calls get_data_dictionary, the LoM column for each ranked feature
    # will read 'ordinal' so the assistant's view of the world matches
    # the user's view in the encoding-plan dropdown.  Same best-effort
    # contract: silent on cache miss, never raises through to the
    # action handler.
    if applied:
        try:
            from .cache import cache_get, cache_put, ARTIFACT_DATA_DICTIONARY
            cached_dd = cache_get(file_id, ARTIFACT_DATA_DICTIONARY)
            if cached_dd:
                dd_list = cached_dd if isinstance(cached_dd, list) else cached_dd.get('features', [])
                if isinstance(dd_list, list) and dd_list:
                    cols_to_flip = {u['column'] for u in implied_metadata_updates}
                    mutated = False
                    for entry in dd_list:
                        if not isinstance(entry, dict):
                            continue
                        feat = entry.get('Feature_Name') or entry.get('feature')
                        if isinstance(feat, str) and feat in cols_to_flip:
                            entry['Level_of_Measurement'] = 'ordinal'
                            mutated = True
                    if mutated:
                        if isinstance(cached_dd, list):
                            cache_put(file_id, ARTIFACT_DATA_DICTIONARY, dd_list)
                        else:
                            cached_dd['features'] = dd_list
                            cache_put(file_id, ARTIFACT_DATA_DICTIONARY, cached_dd)
        except Exception:
            pass

    return {
        'status': 'success' if applied else 'error',
        'action_type': 'set_ordinal_ranking',
        'description': description,
        'applied': applied,
        'errors': errors,
        'implied_metadata_updates': implied_metadata_updates,
    }


# ---------------------------------------------------------------------------
# ACTION: start_hyperparameter — initiate hyperparameter tuning
# ---------------------------------------------------------------------------
#
# Procedural context: hyperparameter tuning is the pipeline step AFTER
# SFS.  It runs a random joint search over the boosting model's
# hyperparameters on the SFS-selected feature set and renders a
# per-hyperparameter cross-validation curve for each enabled param.
# The pipeline UI exposes a "Start Hyperparameter Tuning" button with
# an editable search-space table (min/max/log/enabled per param) plus
# n_iter / cv_folds / n_jobs / curve-metric / curve-points controls.
#
# This action mirrors that button click: it forwards a validated config
# the frontend mirrors onto the tuning form fields, then calls the same
# startHyperparam() method a manual click takes (which derives the
# SFS-selected features itself — the AI does NOT specify features).
#
# Validation rules
# ----------------
# * `n_iter` (2..500), `cv_folds` (2..10), `n_jobs` (1..32),
#   `validation_curve_points` (2..25) — clamped positive ints.
# * `primary_metric` ∈ the 8 UI curve metrics; defaults to roc_auc.
# * `enabled_params` (optional) — subset of the known XGBoost knobs to
#   tune; unknown names are dropped.  Omit to keep the form's defaults.
# * `param_space` (optional) — per-param {type,min,max,log,enabled}
#   overrides, restricted to the known param names.  Bad entries are
#   reported in `errors` and skipped.
#
# Returns the validated config in `applied` for the frontend chat panel
# to forward via `hyperparamStartRequests$` to the modeling component.

# Known editable hyperparameter names (mirror frontend hpParamSpace and
# the engine DEFAULT_PARAM_SPACE in modeling/hyperparam_utils.py).
_HP_PARAM_NAMES = frozenset({
    'n_estimators', 'max_depth', 'learning_rate', 'min_child_weight',
    'subsample', 'colsample_bytree', 'gamma', 'reg_alpha', 'reg_lambda',
})
_HP_INT_PARAMS = frozenset({'n_estimators', 'max_depth', 'min_child_weight'})
# Metrics the frontend curve-metric selector supports.
_HP_METRICS = ('roc_auc', 'pr_auc', 'f1', 'f2', 'precision', 'recall', 'accuracy', 'mcc')
# Search methods.  'auto' applies the fit-count heuristic (grid/random/bayesian).
_HP_SEARCH_METHODS = ('auto', 'grid', 'random', 'bayesian')


@tool(name="start-hyperparameter")
def start_hyperparameter(file_id: int, payload: dict) -> dict:
    """
    Validate and broadcast a hyperparameter-tuning start request.

    payload: {
        "search_method": "auto",       # auto|grid|random|bayesian (auto = fit-count heuristic)
        "grid_points_per_param": 5,    # grid resolution per param (2..12)
        "n_iter": 40,                  # search trials for random/bayesian (2..500)
        "cv_folds": 3,                 # CV folds (2..10)
        "n_jobs": 3,                   # parallel workers / compute power (1..32)
        "primary_metric": "roc_auc",   # curve metric (one of the 8 UI metrics)
        "validation_curve_points": 8,  # points per curve (2..25)
        "enabled_params": ["max_depth", "learning_rate"],   # optional subset
        "param_space": {               # optional per-param overrides
            "max_depth": {"type": "int", "min": 3, "max": 8, "log": false, "enabled": true}
        },
        "description": "Tune depth + learning rate, 60 trials"
    }
    """
    _stamp_action_mcp_marker('start_hyperparameter')
    description = payload.get('description', '')

    # ── in-flight guard — refuse to spawn a duplicate run ──
    # Mirrors start_sfs: even if the model bypasses the slim-context
    # warnings, it cannot clobber an in-flight HYPERPARAM_PROGRESS entry.
    try:
        from modeling.views import HYPERPARAM_PROGRESS
        live = HYPERPARAM_PROGRESS.get(file_id) if isinstance(HYPERPARAM_PROGRESS, dict) else None
        live_status = live.get('status') if isinstance(live, dict) else None
    except Exception:
        live, live_status = None, None
    if live_status == 'running':
        progress = live.get('progress', 0.0) if isinstance(live, dict) else 0.0
        return {
            'status': 'error',
            'action_type': 'start_hyperparameter',
            'description': description,
            'error': (
                f'Hyperparameter tuning is already running for file_id={file_id} '
                f'(progress={progress:.0%}). Refusing to spawn a duplicate run — '
                f'wait for it to complete or have the user click Stop first.'
            ),
            'errors': ['hyperparam_already_running'],
        }

    def _pos_int(v, default):
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return default
        return iv if iv > 0 else default

    n_iter = max(2, min(_pos_int(payload.get('n_iter', 40), 40), 500))
    cv_folds = max(2, min(_pos_int(payload.get('cv_folds', 3), 3), 10))
    n_jobs = max(1, min(_pos_int(payload.get('n_jobs', 3), 3), 32))
    validation_curve_points = max(2, min(_pos_int(payload.get('validation_curve_points', 8), 8), 25))

    primary_metric = payload.get('primary_metric', 'roc_auc')
    if not isinstance(primary_metric, str) or primary_metric not in _HP_METRICS:
        primary_metric = 'roc_auc'

    # ── search_method + grid resolution ──
    search_method = payload.get('search_method', 'auto')
    if not isinstance(search_method, str) or search_method.strip().lower() not in _HP_SEARCH_METHODS:
        search_method = 'auto'
    else:
        search_method = search_method.strip().lower()
    grid_points_per_param = max(2, min(_pos_int(payload.get('grid_points_per_param', 5), 5), 12))

    # ── enabled_params (optional subset) ──
    enabled_raw = payload.get('enabled_params', None)
    enabled_params = None
    if isinstance(enabled_raw, list):
        ep = [p for p in enabled_raw if isinstance(p, str) and p in _HP_PARAM_NAMES]
        enabled_params = ep or None  # None → leave the form's enabled set

    # ── param_space (optional per-param overrides, known names only) ──
    space_raw = payload.get('param_space', None)
    param_space = None
    space_errors: list = []
    if isinstance(space_raw, dict):
        cleaned: dict = {}
        for name, spec in space_raw.items():
            if name not in _HP_PARAM_NAMES or not isinstance(spec, dict):
                space_errors.append(str(name))
                continue
            ptype = spec.get('type')
            if ptype not in ('int', 'float'):
                ptype = 'int' if name in _HP_INT_PARAMS else 'float'
            try:
                lo = float(spec.get('min'))
                hi = float(spec.get('max'))
            except (TypeError, ValueError):
                space_errors.append(str(name))
                continue
            if lo > hi:
                lo, hi = hi, lo
            cleaned[name] = {
                'type': ptype,
                'min': int(round(lo)) if ptype == 'int' else lo,
                'max': int(round(hi)) if ptype == 'int' else hi,
                'log': bool(spec.get('log', False)),
                'enabled': bool(spec.get('enabled', True)),
            }
        param_space = cleaned or None

    return {
        'status': 'success',
        'action_type': 'start_hyperparameter',
        'description': description,
        'applied': {
            'param_space': param_space,
            'enabled_params': enabled_params,
            'n_iter': n_iter,
            'cv_folds': cv_folds,
            'n_jobs': n_jobs,
            'primary_metric': primary_metric,
            'validation_curve_points': validation_curve_points,
            'search_method': search_method,
            'grid_points_per_param': grid_points_per_param,
        },
        'errors': space_errors,
    }


# ---------------------------------------------------------------------------
# ACTION: update_notes — add/edit/delete pipeline commentary notes
# ---------------------------------------------------------------------------

@tool(name="update-notes")
def update_notes(file_id: int, payload: dict) -> dict:
    """
    Manage pipeline commentary notes.

    payload: {
        "action": "add" | "edit" | "delete",
        "position": "after_data_preview" | "after_data_dictionary" | ... ,
        "content": "Note text here",
        "description": "..."
    }
    """
    _stamp_action_mcp_marker('update_notes')
    action = payload.get('action', 'add')
    position = payload.get('position', '')
    content = payload.get('content', '')
    description = payload.get('description', '')

    valid_positions = [
        'after_data_preview', 'after_data_dictionary',
        'after_preprocessing_config', 'after_purifier_summary', 'after_data_quality',
        'after_encoding', 'after_modeling_results', 'after_sfs',
    ]

    if position and position not in valid_positions:
        return {'status': 'error', 'error': f'Invalid note position. Valid: {valid_positions}'}

    return {
        'status': 'success',
        'action_type': 'update_notes',
        'description': description,
        'note_action': action,
        'position': position,
        'content': content,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

@tool(name="apply-recommendation")
def apply_recommendation(file_id: int, payload: dict) -> dict:
    """Apply temporary SFS/VIF Model_Usage mutations after user confirmation.

    Two-phase protocol:
      - confirm=false (default): sandbox preview of Model_Usage changes only
      - confirm=true: commit updates for frontend SharedService / dictionary

    payload: {
      "confirm": bool,
      "updates": [{"column": "feat", "value": "No"|"Yes", "reason": "..."}],
      "source": "sfs"|"vif"|"datq"|"assistant",
      "description": "..."
    }
    """
    _stamp_action_mcp_marker('apply_recommendation')
    updates = payload.get('updates') or []
    confirm = bool(payload.get('confirm'))
    description = payload.get('description') or ''
    source = str(payload.get('source') or 'assistant')
    if not updates:
        return {'status': 'error', 'error': 'No recommendation updates provided'}

    sandbox = []
    for upd in updates:
        col = str(upd.get('column') or '').strip()
        value = str(upd.get('value') or 'No').strip()
        if value.lower() in ('no', 'n', 'false', '0'):
            value = 'No'
        elif value.lower() in ('yes', 'y', 'true', '1'):
            value = 'Yes'
        else:
            value = 'No'
        if not col:
            continue
        sandbox.append({
            'column': col,
            'field': 'Model_Usage_YN',
            'key': 'model_usage',
            'value': value,
            'reason': upd.get('reason') or description,
            'source': source,
        })
    if not sandbox:
        return {'status': 'error', 'error': 'No valid column updates'}

    if not confirm:
        return {
            'status': 'success',
            'action_type': 'apply_recommendation',
            'phase': 'sandbox',
            'confirm_required': True,
            'description': description or 'Preview Model_Usage recommendation (not committed).',
            'proposed': sandbox,
            'message': (
                f'Sandbox: {len(sandbox)} Model_Usage change(s) ready. '
                'Re-send with confirm=true after user approval.'
            ),
        }

    # Commit path: return applied rows for frontend to write into Model_Usage
    # (same contract as update_config model_usage).
    return {
        'status': 'success',
        'action_type': 'apply_recommendation',
        'phase': 'committed',
        'confirm_required': False,
        'description': description or f'Applied {len(sandbox)} Model_Usage recommendation(s).',
        'applied': sandbox,
        'updates': [
            {'key': 'model_usage', 'column': u['column'], 'value': u['value']}
            for u in sandbox
        ],
        'source': source,
    }


HANDLERS = {
    'execute_code': execute_code,
    'update_metadata': update_metadata,
    'update_config': update_config,
    'set_ordinal_ranking': set_ordinal_ranking,
    'start_sfs': start_sfs,
    'start_data_purifier': start_data_purifier,
    'update_purifier_selection': update_purifier_selection,
    'apply_encoding': apply_encoding,
    'start_modeling': start_modeling,
    'start_hyperparameter': start_hyperparameter,
    'update_notes': update_notes,
    'apply_recommendation': apply_recommendation,
}


def _build_completion_message(result: dict, action_type: str) -> str:
    """Build a human-readable completion message from an action handler result."""
    if not isinstance(result, dict):
        return str(result)

    status = result.get('status', '')
    if status == 'error':
        return f"Error: {result.get('error', 'unknown error')}"

    desc = result.get('description', '')
    parts = [f"{action_type} completed successfully."]
    if desc:
        parts.append(desc)

    changes = result.get('changes', {})
    if changes:
        added = changes.get('columns_added', [])
        removed = changes.get('columns_removed', [])
        if added:
            parts.append(f"Columns added: {', '.join(added)}")
        if removed:
            parts.append(f"Columns removed: {', '.join(removed)}")
        rows_after = changes.get('rows_after')
        cols = result.get('preview', {}).get('total_columns')
        if rows_after is not None and cols is not None:
            parts.append(f"Dataset now has {cols} columns and {rows_after} rows.")

    updated = result.get('updated_count')
    if updated is not None:
        parts.append(f"{updated} entries updated.")

    return ' '.join(parts) if parts else str(result)


@workflow(name="declarai-action")
def dispatch_action(file_id: int, action_type: str, payload: dict,
                    *, parent_span_id: str = None, source: str = None) -> dict:
    """Route an action to the correct handler.

    Args:
        file_id: pipeline declaration id.
        action_type: HANDLERS key (``update_config``, ``start_sfs`` etc.).
        payload: handler-specific dict.
        parent_span_id: optional Prometa span id of the upstream chat
            turn that PROPOSED this action.  When provided, stamped
            via ``set_input_ref()`` so Prometa's Causal-context block
            renders the action trace with a clickable "Input from
            <chat span>" row, collapsing the two-trace propose-then-
            execute split into one navigable flow.  When None (legacy
            v2.25.0..v2.37.0 callers, internal tests, missing chat-side
            instrumentation), the link is simply omitted — action
            dispatch semantics are unchanged.  Keyword-only so positional
            call sites that pre-date v2.38.0 are stable.
        source: ``'codeline'`` when launched from an inline Codeline cell,
            ``'panel'`` / omitted for the right-side AI Assistant.
    """
    # Set prompt attribute so Prometa Conversation panel shows the action request
    description = payload.get('description', '') if isinstance(payload, dict) else ''
    set_span_attr('gen_ai.prompt', f"[Action: {action_type}] {description}")
    set_span_attr('declarai.file_id', file_id)
    set_session_id(f'declarai-file-{file_id}')
    # v2.30.0 (Phase 2): per-span customer_id override.  Mirrors the
    # _chat_workflow entry point so action dispatches and chat turns
    # share the same correlation key per Declaration.  See
    # ai_assistant/prometa_config.py::set_customer_id for the rationale.
    set_customer_id(str(file_id))
    # v2.38.0: cross-trace data-flow ref back to the chat span that
    # proposed this action (when the frontend passed it through from
    # /chat/'s response).  Stamping happens TWICE on purpose:
    #   (1) set_input_ref → canonical Prometa ``prometa.input_ref``
    #       attribute consumed by the platform's Causal-context UI.
    #       No-op when the SDK is absent or no active span — won't
    #       throw, won't fail dispatch.
    #   (2) set_span_attr → ``declarai.action.parent_span_id`` debug
    #       attribute, visible even in test mode without the real
    #       Prometa endpoint so we can verify the link is being
    #       attempted independent of platform connectivity.
    if parent_span_id:
        set_input_ref(parent_span_id)
        set_span_attr('declarai.action.parent_span_id', parent_span_id)

    action_source = (source or 'panel').strip().lower()
    if action_source not in ('codeline', 'panel'):
        action_source = 'panel'
    set_span_attr('declarai.action.source', action_source)
    if action_source == 'codeline' and action_type == 'execute_code':
        mode = None
        position = None
        attempt_int = None
        if isinstance(payload, dict):
            mode = payload.get('mode') or 'apply'
            position = payload.get('codeline_position')
            attempt = payload.get('auto_correction_attempt')
            try:
                attempt_int = int(attempt) if attempt is not None else None
            except (TypeError, ValueError):
                attempt_int = None
        stamp_codeline_capability(
            kind='execution',
            position=position,
            mode=mode,
            source=action_source,
            auto_correction_attempt=attempt_int,
        )

    handler = HANDLERS.get(action_type)
    if not handler:
        return {'status': 'error', 'error': f'Unknown action type: {action_type}'}
    try:
        result = handler(file_id, payload)
        # Set completion attribute so the action result appears in the Conversation panel
        msg = _build_completion_message(result, action_type)
        set_span_attr('gen_ai.completion', msg[:2000])
        return result
    except Declaration.DoesNotExist:
        set_span_attr('gen_ai.completion', f'Dataset with id={file_id} not found')
        return {'status': 'error', 'error': f'Dataset with id={file_id} not found'}
    except Exception as e:
        traceback.print_exc()
        set_span_attr('gen_ai.completion', f'Error: {e}')
        return {'status': 'error', 'error': str(e)}
