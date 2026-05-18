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


def has_active_span() -> bool:
    """Return True if there is currently an active Prometa span in context.

    Used by ``child_only_tool`` to decide whether to emit a span at all.
    When called outside any workflow/tool/agent (e.g. from a REST endpoint
    that doesn't wrap itself in ``@workflow``), this returns False and
    callers should run their work without creating a new root trace.

    Failure modes return False (treat as no parent):
      * Prometa SDK not installed (test env, dev box without endpoint)
      * Prometa not yet initialized (no chat turn has run since boot)
      * ``current_span()`` raised (defensive)
    """
    try:
        from prometa._context import current_span
        return current_span() is not None
    except Exception:
        return False


def child_only_tool(name: str = None, **kwargs):
    """Decorator: wrap a function as a Prometa tool only when a parent
    span is already active. Without a parent the function runs plain,
    so it does NOT appear as a standalone root trace in Trace Explorer.

    Use for infrastructure helpers (Redis ops, etc.) that are useful to
    trace as children of a user-facing workflow (``declarai-chat``,
    ``declarai-action``) but produce noise traces when invoked from
    standalone REST endpoints (``/api/ai/cache_push/``), background
    DB-update hooks (``declaration/views.py``), or ad-hoc shell scripts.

    Composition: the function body is still free to call
    ``set_span_attr()``; those calls become no-ops when no span is
    active in production but are still captured by test fixtures that
    monkeypatch ``set_span_attr`` directly — so existing tests continue
    to work without modification.

    Marks the wrapper with ``_child_only=True`` so structural tests
    can verify the decorator is in place without invoking the SDK.
    """
    def decorator(fn):
        # Build the lazily-traced variant once; we'll choose between
        # it and the plain function at every call based on context.
        traced = tool(name=name, **kwargs)(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kw):
            if has_active_span():
                return traced(*args, **kw)
            return fn(*args, **kw)

        wrapper._child_only = True
        wrapper._tool_name = name
        return wrapper
    return decorator


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


def set_customer_id(customer_id: str) -> None:
    """Stamp ``prometa.customer_id`` on the current span for cross-feature
    correlation (Session Explorer, AML scoring, cost panels, registry).

    Uses the v0.5.0+ ``set_customer_id()`` SDK helper when available; falls
    back to writing the attribute directly so the platform's correlation-id
    resolver can still join by customer even when the helper is missing
    (older SDK or import failure).

    The Prometa contract: the constructor's ``customer_id="..."`` kwarg
    sets an org-wide default; per-span ``set_customer_id(...)`` overrides
    it for the current span AND every nested span via parent-attribute
    inheritance.

    DeclarAI mapping: we use ``str(file_id)`` so each Declaration is its
    own correlation key — every chat turn, action dispatch, cache read,
    and LLM call within a single uploaded dataset's pipeline groups
    under one ``customer_id``.  This is the right choice for our
    single-tenant POC; if/when authenticated end-users land we'd switch
    to the user's external id and demote ``file_id`` to a sub-attribute.

    Synchronous, no-op outside an active span context.
    """
    try:
        from prometa import set_customer_id as _sdk_set_customer_id
        _sdk_set_customer_id(customer_id)
    except ImportError:
        set_span_attr('prometa.customer_id', customer_id)
    except Exception:
        pass


def set_request_model(model: str) -> None:
    """Stamp ``gen_ai.request.model`` on the current span.

    Uses the v0.5.0+ ``set_request_model()`` SDK helper when available;
    falls back to writing the attribute directly.  Both produce the same
    OTel-canonical attribute path that the platform's cost panel, model-
    routing detector (AML F1), and trace UI consume.

    Replaces the manual ``set_span_attr('gen_ai.request.model', ...)``
    pattern; lifts model annotation onto the canonical helper so future
    SDK behavior (e.g. parent-attribute inheritance, normalization) is
    automatically picked up without site-by-site refactors.

    Synchronous, no-op outside an active span context.
    """
    try:
        from prometa import set_request_model as _sdk_set_request_model
        _sdk_set_request_model(model)
    except ImportError:
        set_span_attr('gen_ai.request.model', model)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# AML v0.4 instrumentation helpers (v2.31.0 / Phase 3a of prometa-sdk roadmap).
#
# The v0.4.0 SDK ships 16 typed-span helpers feeding the platform's
# 41-feature AML scoring catalog.  We adopt them piecewise — this file
# wraps the two highest-leverage ones for DeclarAI:
#
#   model_route       (AML F1: Observability — model-routing detector)
#   schema_validate   (AML C4: Reasoning — output-validation detector)
#
# Each wrapper is a context manager that yields a handle on which the
# call site stamps result attributes (e.g. ``mr.cost(...)``,
# ``sv.result(passed=...)``).  When the SDK is unavailable we yield a
# ``_NoOpAMLHandle`` whose every attribute access is a method that
# silently swallows arguments — the call site never has to guard.
# ---------------------------------------------------------------------------


class _NoOpAMLHandle:
    """Fallback handle yielded by AML helper wrappers when the SDK is
    not importable (older SDK pin, sandboxed test env without prometa
    installed at all, etc.).

    Absorbs every attribute access into a do-nothing callable, so the
    call site can write ``handle.result(passed=True, errors=[])`` /
    ``handle.cost(cost_estimate_usd=0.01)`` etc. unconditionally.

    This mirrors the ``_NoOp`` handle the SDK itself yields when the
    Prometa client is unconfigured (no PROMETA_ENDPOINT), so the
    contract is uniform across all three failure modes:
      1. SDK not installed              → our _NoOpAMLHandle
      2. SDK installed, client None     → SDK's own no-op handle
      3. SDK installed, client active   → real span handle
    """

    @staticmethod
    def _noop(*_args, **_kwargs):
        return None

    def __getattr__(self, _name):
        return self._noop


@contextmanager
def schema_validate(schema_id: str):
    """Wrap an output-validation event in a Prometa ``schema.validate``
    AML span (catalog C4).  Forwards to the v0.4.0+ SDK helper when
    available; yields a ``_NoOpAMLHandle`` otherwise.

    Usage::

        with schema_validate("declarai:update-purifier-selection@v1") as sv:
            try:
                _validate(payload)
                sv.result(passed=True)
            except ValidationError as e:
                sv.result(passed=False, errors=[str(e)],
                          downstream_blocked=True)
                raise

    The schema_id is a free-form string; we use the convention
    ``declarai:<action-name>@v<n>`` so platform-side queries can filter
    by validator independently of the surrounding workflow span.

    Body exceptions propagate normally — only ImportError is caught
    (SDK absent), so validation logic still gets to fail loudly.
    """
    try:
        from prometa import schema_validate as _sdk_schema_validate
    except ImportError:
        yield _NoOpAMLHandle()
        return
    with _sdk_schema_validate(schema_id) as handle:
        yield handle


@contextmanager
def model_route(chosen: str, *, candidates_considered, routing_reason: str):
    """Wrap a model-routing decision in a Prometa ``model.route`` AML
    span (catalog F1).  Forwards to the v0.4.0+ SDK helper when
    available; yields a ``_NoOpAMLHandle`` otherwise.

    Usage::

        with model_route(
            chosen=model_cfg['model_id'],
            candidates_considered=available_model_ids,
            routing_reason="user_selected",
        ) as mr:
            response = _call_llm(...)
            # Optional: mr.cost(cost_estimate_usd=...) when known.

    DeclarAI today does not run a complexity-based cascade — the user
    explicitly selects a model in the UI.  We still record the routing
    span so:
      1. The model_route detector has a baseline signal per call.
      2. When/if a real cascade lands (rate-limit fallback, cost-
         capped routing, complexity-tier routing) the same call site
         takes the richer ``routing_reason`` without surface changes.

    ``candidates_considered`` is a sequence; the SDK joins it as a
    comma-separated string in the ``model.candidates_considered``
    span attribute.

    Body exceptions propagate normally — only ImportError is caught.
    """
    try:
        from prometa import model_route as _sdk_model_route
    except ImportError:
        yield _NoOpAMLHandle()
        return
    with _sdk_model_route(
        chosen,
        candidates_considered=candidates_considered,
        routing_reason=routing_reason,
    ) as handle:
        yield handle
