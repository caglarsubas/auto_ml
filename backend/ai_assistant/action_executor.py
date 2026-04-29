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

import os
import re
import shutil
import traceback
import numpy as np
import pandas as pd
from django.conf import settings
from declaration.models import Declaration, DataDictionary

from .prometa_config import workflow, tool, set_span_attr, set_session_id


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
        "description": "Human-readable summary of what the code does"
    }
    """
    code = payload.get('code', '').strip()
    description = payload.get('description', '')
    if not code:
        return {'status': 'error', 'error': 'No code provided'}

    # Strip import lines — np and pd are already in the sandbox
    code = '\n'.join(
        line for line in code.splitlines()
        if not line.strip().startswith(('import ', 'from '))
    )

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
            'error': f'Code execution failed: {str(e)}',
            'traceback': traceback.format_exc(),
        }

    df_result = sandbox.get('df', df)
    if not isinstance(df_result, pd.DataFrame):
        _remove_backup(backup_path)
        return {'status': 'error', 'error': 'Result is not a DataFrame — did you reassign `df`?'}

    # --- Structural validation: original columns must survive ---
    cols_after = set(df_result.columns)
    missing_original = cols_before_set - cols_after
    # Allow intentional drops (up to 30% of originals), but flag total corruption
    if missing_original and len(missing_original) > len(cols_before) * 0.3:
        _restore_backup(backup_path, file_path)
        return {
            'status': 'error',
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
        'description': description,
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
        elif key in ('preprocessing_options', 'split_strategy', 'split_date_column',
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

HANDLERS = {
    'execute_code': execute_code,
    'update_metadata': update_metadata,
    'update_config': update_config,
    'update_notes': update_notes,
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
def dispatch_action(file_id: int, action_type: str, payload: dict) -> dict:
    """Route an action to the correct handler."""
    # Set prompt attribute so Prometa Conversation panel shows the action request
    description = payload.get('description', '') if isinstance(payload, dict) else ''
    set_span_attr('gen_ai.prompt', f"[Action: {action_type}] {description}")
    set_span_attr('declarai.file_id', file_id)
    set_session_id(f'declarai-file-{file_id}')

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
