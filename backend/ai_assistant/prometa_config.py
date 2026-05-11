"""
Prometa SDK integration for DeclarAI AI Assistant.

Initializes a singleton Prometa client for tracing AI workflows, agents, and tools.
All tracing is optional — if the SDK is not installed or not configured, the app
runs normally with no-op decorators.

Configuration via environment variables:
    PROMETA_STAGE                — "staging" or "production" (default: staging)
    PROMETA_ENDPOINT_{STAGE}     — OTLP traces endpoint for this stage (required)
    PROMETA_API_KEY_{STAGE}      — API key for this stage
    PROMETA_SOLUTION_ID          — Solution identifier (default: sol_declarai)
    PROMETA_AGENT_NAME           — Agent display name (default: declarai-assistant)

    Fallback: PROMETA_ENDPOINT / PROMETA_API_KEY (without suffix) are checked
    if the stage-specific vars are not set.
"""

import os
import functools
import logging
import time as _time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_prometa = None
_initialized = False


def get_prometa():
    """Return the singleton Prometa instance, or None if not configured."""
    global _prometa, _initialized
    if _initialized:
        return _prometa
    _initialized = True

    # Disable tracing under pytest so test runs (especially the file_id=99999
    # "missing resource" cases) don't pollute the Session Explorer with
    # sessions like `declarai-file-99999`. `PROMETA_DISABLE=1` is the explicit
    # kill-switch; `PYTEST_CURRENT_TEST` is set by pytest while a test runs.
    if os.environ.get('PROMETA_DISABLE') == '1' or os.environ.get('PYTEST_CURRENT_TEST'):
        logger.info("Prometa tracing disabled (test/PROMETA_DISABLE).")
        return None

    stage = os.environ.get('PROMETA_STAGE', 'staging').lower()
    stage_upper = stage.upper()

    # Resolve stage-specific vars first, fall back to generic ones
    endpoint = (os.environ.get(f'PROMETA_ENDPOINT_{stage_upper}')
                or os.environ.get('PROMETA_ENDPOINT', ''))
    api_key = (os.environ.get(f'PROMETA_API_KEY_{stage_upper}')
               or os.environ.get('PROMETA_API_KEY', ''))

    if not endpoint:
        logger.info("No PROMETA_ENDPOINT for stage '%s' — Prometa tracing disabled.", stage)
        return None

    try:
        from prometa import Prometa
        _prometa = Prometa(
            endpoint=endpoint,
            api_key=api_key,
            solution_id=os.environ.get('PROMETA_SOLUTION_ID', 'sol_declarai'),
            agent_name=os.environ.get('PROMETA_AGENT_NAME', 'declarai-assistant'),
            stage=stage,
            # Default flush_interval_seconds=2.0 is fine — platform v0.3.2+
            # deduplicates by (trace_id, span_id) via ReplacingMergeTree.
        )
        logger.info("Prometa tracing initialized — stage=%s, endpoint=%s", stage, endpoint)

        # Enable LLM client auto-instrumentation.
        # Patches openai.Client to emit gen_ai.* span attributes automatically.
        # Drives the cost panel, token usage, and Conversation panel.
        # v0.3.3+: SDK pre-extracts gen_ai.prompt.user (just the user message)
        # for clean conversation turns; full gen_ai.prompt kept for debugging.
        try:
            from prometa.integrations import openai as prometa_openai
            prometa_openai.install()
            logger.info("Prometa OpenAI auto-instrumentation enabled.")
        except (ImportError, AttributeError):
            logger.info("Prometa OpenAI auto-instrumentation not available.")
        except Exception as exc_ai:
            logger.warning("Prometa OpenAI auto-instrumentation failed: %s", exc_ai)

    except ImportError:
        logger.warning("prometa-sdk not installed — tracing disabled. "
                       "Install with: pip install prometa-sdk")
    except Exception as exc:
        logger.warning("Failed to initialize Prometa: %s", exc)

    return _prometa


def flush():
    """Flush any pending Prometa spans. Safe to call even if Prometa is disabled."""
    p = get_prometa()
    if p:
        try:
            p.flush()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Lazy decorator factories
# ---------------------------------------------------------------------------
# These decorators defer Prometa initialization until the decorated function
# is first called, avoiding import-time side effects.  The real @prometa
# decorator is applied once and cached for subsequent calls.
# ---------------------------------------------------------------------------

def _make_lazy_decorator(kind: str):
    """Create a lazy decorator factory for a given Prometa kind (workflow/agent/tool)."""

    def decorator_factory(name, **kwargs):
        def decorator(fn):
            _traced = [None]  # mutable container for one-time caching

            @functools.wraps(fn)
            def wrapper(*args, **kw):
                if _traced[0] is None:
                    p = get_prometa()
                    if p:
                        real_decorator = getattr(p, kind)(name=name, **kwargs)
                        _traced[0] = real_decorator(fn)
                    else:
                        _traced[0] = fn
                return _traced[0](*args, **kw)
            return wrapper
        return decorator
    return decorator_factory


workflow = _make_lazy_decorator('workflow')
agent = _make_lazy_decorator('agent')
tool = _make_lazy_decorator('tool')


def set_span_attr(key: str, value) -> None:
    """Set an attribute on the current Prometa span (no-op if SDK unavailable)."""
    try:
        from prometa._context import current_span
        span = current_span()
        if span is not None:
            span.attributes[key] = value
    except Exception:
        pass


def stamp_elapsed(prefix: str, t0_ns: int) -> int:
    """Stamp ``<prefix>.elapsed_us`` and ``<prefix>.elapsed_ms`` on the
    current span using a previously captured ``time.perf_counter_ns()``
    reading.

    Redis operations on a local docker network typically complete in
    100-500µs which the Prometa UI rounds to ``0ms`` in the waterfall bar.
    Stamping the elapsed time as an attribute guarantees the real
    duration is always visible in the span detail panel and queryable
    from Trace Explorer.

    Returns the elapsed nanoseconds for the caller's convenience.
    """
    elapsed_ns = _time.perf_counter_ns() - t0_ns
    set_span_attr(f'{prefix}.elapsed_us', elapsed_ns // 1000)
    set_span_attr(f'{prefix}.elapsed_ms', round(elapsed_ns / 1_000_000.0, 3))
    return elapsed_ns


@contextmanager
def span_timer(prefix: str):
    """Context manager that stamps ``<prefix>.elapsed_{us,ms}`` on exit.

    Use inside a ``@prometa_tool``-decorated function so the elapsed time
    lands on the SDK's active span::

        @prometa_tool(name="redis-get")
        def cache_get(file_id, artifact):
            with span_timer('declarai.cache'):
                ...  # real work
    """
    t0 = _time.perf_counter_ns()
    try:
        yield
    finally:
        stamp_elapsed(prefix, t0)


def set_session_id(session_id: str) -> None:
    """Stamp a session/conversation id on the current span for session grouping.

    The platform's Session Explorer groups all traces sharing a session id
    into one row.  Uses the v0.3.2+ set_session_id() helper if available,
    falls back to setting the attribute directly.
    """
    try:
        from prometa import set_session_id as _sdk_set_session_id
        _sdk_set_session_id(session_id)
    except ImportError:
        set_span_attr('gen_ai.conversation.id', session_id)
    except Exception:
        pass
