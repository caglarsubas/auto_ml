"""Read-only SQL execution for Postgres and DuckDB lakehouse connections."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

DEFAULT_PREVIEW_LIMIT = 200
DEFAULT_MATERIALIZE_MAX_ROWS = 2_000_000
STATEMENT_TIMEOUT_MS = 30_000

_FORBIDDEN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|'
    r'COPY|ATTACH|DETACH|CALL|EXECUTE|MERGE|REPLACE|VACUUM|PRAGMA|'
    r'INSTALL|LOAD|EXPORT|IMPORT)\b',
    re.IGNORECASE,
)


class SqlValidationError(ValueError):
    """Raised when SQL fails the read-only SELECT allowlist."""


class SqlExecutionError(RuntimeError):
    """Raised when a validated query fails at the engine."""


@dataclass
class QueryResult:
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    truncated: bool = False


def validate_readonly_select(sql: str) -> str:
    """Ensure a single SELECT / WITH ... SELECT statement; return cleaned SQL."""
    if not sql or not str(sql).strip():
        raise SqlValidationError('SQL is empty.')

    cleaned = str(sql).strip()
    # Strip trailing semicolons for single-statement checks.
    while cleaned.endswith(';'):
        cleaned = cleaned[:-1].rstrip()

    if ';' in cleaned:
        raise SqlValidationError('Only a single SQL statement is allowed.')

    # Remove line and block comments for keyword scanning.
    no_line = re.sub(r'--.*?$', '', cleaned, flags=re.MULTILINE)
    no_comments = re.sub(r'/\*.*?\*/', '', no_line, flags=re.DOTALL).strip()
    if not no_comments:
        raise SqlValidationError('SQL is empty after removing comments.')

    if _FORBIDDEN.search(no_comments):
        raise SqlValidationError(
            'Only read-only SELECT queries are allowed (DDL/DML keywords rejected).'
        )

    head = no_comments.lstrip().upper()
    if not (head.startswith('SELECT') or head.startswith('WITH')):
        raise SqlValidationError('Query must start with SELECT or WITH.')

    return cleaned


def wrap_limit(sql: str, limit: int) -> str:
    """Wrap a validated SELECT in an outer LIMIT without relying on dialect LIMIT parsing."""
    lim = max(1, int(limit))
    return f'SELECT * FROM (\n{sql}\n) AS _fc_preview LIMIT {lim}'


def _resolve_password(secret_ref: str) -> Optional[str]:
    ref = (secret_ref or '').strip()
    if not ref:
        return None
    return os.environ.get(ref)


def _postgres_url(config: Dict[str, Any], secret_ref: str) -> str:
    from urllib.parse import quote_plus

    host = str(config.get('host') or 'localhost')
    port = int(config.get('port') or 5432)
    database = str(config.get('database') or config.get('dbname') or 'postgres')
    user = str(config.get('user') or config.get('username') or 'postgres')
    password = _resolve_password(secret_ref)
    if password is None and config.get('password') is not None:
        # Allow explicit password only for tests; production should use secret_ref.
        password = str(config.get('password'))
    auth = quote_plus(user)
    if password is not None:
        auth = f'{quote_plus(user)}:{quote_plus(password)}'
    return f'postgresql+psycopg2://{auth}@{host}:{port}/{database}'


def test_connection(engine: str, config: Dict[str, Any], secret_ref: str = '') -> Dict[str, Any]:
    """Ping the connection; returns {ok, message, engine}."""
    engine = (engine or '').lower().strip()
    try:
        if engine == 'postgres':
            from sqlalchemy import create_engine, text

            url = _postgres_url(config or {}, secret_ref)
            eng = create_engine(url, pool_pre_ping=True)
            with eng.connect() as conn:
                conn.execute(text('SELECT 1'))
            eng.dispose()
            return {'ok': True, 'message': 'PostgreSQL connection successful.', 'engine': engine}
        if engine == 'duckdb':
            import duckdb

            base_path = str((config or {}).get('base_path') or (config or {}).get('path') or '')
            if not base_path:
                raise SqlExecutionError('DuckDB config requires base_path.')
            if not os.path.isdir(base_path):
                raise SqlExecutionError(f'DuckDB base_path does not exist: {base_path}')
            con = duckdb.connect(database=':memory:')
            try:
                # Escape single quotes in path for SQL literal.
                safe = base_path.replace("'", "''")
                con.execute(f"SET file_search_path='{safe}'")
                con.execute('SELECT 1')
            finally:
                con.close()
            return {'ok': True, 'message': f'DuckDB path reachable: {base_path}', 'engine': engine}
        raise SqlExecutionError(f'Unsupported engine: {engine}')
    except SqlExecutionError:
        raise
    except Exception as exc:
        raise SqlExecutionError(str(exc)) from exc


def _run_postgres(sql: str, config: Dict[str, Any], secret_ref: str, max_rows: int) -> pd.DataFrame:
    from sqlalchemy import create_engine, text

    url = _postgres_url(config or {}, secret_ref)
    eng = create_engine(url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text(f"SET statement_timeout = '{STATEMENT_TIMEOUT_MS}'"))
            # fetch one extra row to detect truncation
            limited = wrap_limit(sql, max_rows + 1)
            df = pd.read_sql_query(text(limited), conn)
    finally:
        eng.dispose()
    return df


def _run_duckdb(sql: str, config: Dict[str, Any], max_rows: int) -> pd.DataFrame:
    import duckdb

    base_path = str((config or {}).get('base_path') or (config or {}).get('path') or '')
    if not base_path:
        raise SqlExecutionError('DuckDB config requires base_path.')
    if not os.path.isdir(base_path):
        raise SqlExecutionError(f'DuckDB base_path does not exist: {base_path}')

    con = duckdb.connect(database=':memory:')
    try:
        safe = base_path.replace("'", "''")
        con.execute(f"SET file_search_path='{safe}'")
        # Also chdir-equivalent: register common views for files in root
        limited = wrap_limit(sql, max_rows + 1)
        df = con.execute(limited).df()
    finally:
        con.close()
    return df


def execute_query(
    engine: str,
    config: Dict[str, Any],
    sql: str,
    *,
    secret_ref: str = '',
    limit: Optional[int] = None,
    max_rows: int = DEFAULT_MATERIALIZE_MAX_ROWS,
) -> QueryResult:
    """Validate and execute SQL; return rows (optionally truncated to limit for preview)."""
    cleaned = validate_readonly_select(sql)
    engine = (engine or '').lower().strip()
    fetch_cap = int(limit) if limit is not None else int(max_rows)
    fetch_cap = max(1, fetch_cap)

    try:
        if engine == 'postgres':
            df = _run_postgres(cleaned, config or {}, secret_ref, fetch_cap)
        elif engine == 'duckdb':
            df = _run_duckdb(cleaned, config or {}, fetch_cap)
        else:
            raise SqlExecutionError(f'Unsupported engine: {engine}')
    except (SqlValidationError, SqlExecutionError):
        raise
    except Exception as exc:
        raise SqlExecutionError(str(exc)) from exc

    truncated = len(df) > fetch_cap
    if truncated:
        df = df.iloc[:fetch_cap].copy()

    # Normalize for JSON
    df = df.where(pd.notnull(df), None)
    columns = [str(c) for c in df.columns.tolist()]
    rows: List[Dict[str, Any]] = []
    for record in df.to_dict(orient='records'):
        row = {}
        for k, v in record.items():
            if hasattr(v, 'item'):
                try:
                    v = v.item()
                except Exception:
                    v = str(v)
            elif hasattr(v, 'isoformat'):
                v = v.isoformat()
            row[str(k)] = v
        rows.append(row)

    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
    )


def execute_to_dataframe(
    engine: str,
    config: Dict[str, Any],
    sql: str,
    *,
    secret_ref: str = '',
    max_rows: int = DEFAULT_MATERIALIZE_MAX_ROWS,
) -> Tuple[pd.DataFrame, bool]:
    """Execute and return a DataFrame plus whether the materialize row cap was hit."""
    cleaned = validate_readonly_select(sql)
    engine = (engine or '').lower().strip()
    try:
        if engine == 'postgres':
            df = _run_postgres(cleaned, config or {}, secret_ref, max_rows)
        elif engine == 'duckdb':
            df = _run_duckdb(cleaned, config or {}, max_rows)
        else:
            raise SqlExecutionError(f'Unsupported engine: {engine}')
    except (SqlValidationError, SqlExecutionError):
        raise
    except Exception as exc:
        raise SqlExecutionError(str(exc)) from exc

    truncated = len(df) > max_rows
    if truncated:
        df = df.iloc[:max_rows].copy()
    return df, truncated


def infer_column_schema(columns: Sequence[str], sample_rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    schema = []
    for col in columns:
        dtype = 'unknown'
        if sample_rows:
            for row in sample_rows:
                val = row.get(col)
                if val is None:
                    continue
                if isinstance(val, bool):
                    dtype = 'boolean'
                elif isinstance(val, int) and not isinstance(val, bool):
                    dtype = 'integer'
                elif isinstance(val, float):
                    dtype = 'float'
                else:
                    dtype = 'string'
                break
        schema.append({'name': str(col), 'dtype': dtype})
    return schema
