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

    df, data_file, file_path = _load_dataframe(file_id)
    cols_before = set(df.columns.tolist())
    rows_before = len(df)

    # Build restricted global namespace
    safe_globals = {
        '__builtins__': _SAFE_BUILTINS,
        'pd': pd,
        'np': np,
    }
    safe_locals = {'df': df}

    try:
        exec(code, safe_globals, safe_locals)
    except Exception as e:
        return {
            'status': 'error',
            'error': f'Code execution failed: {str(e)}',
            'traceback': traceback.format_exc(),
        }

    df_result = safe_locals.get('df', df)
    if not isinstance(df_result, pd.DataFrame):
        return {'status': 'error', 'error': 'Result is not a DataFrame — did you reassign `df`?'}

    # Compute what changed
    cols_after = set(df_result.columns.tolist())
    added = sorted(cols_after - cols_before)
    removed = sorted(cols_before - cols_after)
    rows_after = len(df_result)

    # Save
    _save_dataframe(df_result, data_file, file_path)

    # Update DataDictionary for new columns
    for col_name in added:
        DataDictionary.objects.update_or_create(
            data_file=data_file,
            column_name=col_name,
            defaults={'description': f'AI-created: {description}'}
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
