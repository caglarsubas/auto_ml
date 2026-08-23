"""
Prometa SDK integration for DeclarAI AI Assistant.

Initializes a singleton Prometa client for tracing AI workflows, agents, and tools.
All tracing is optional — if the SDK is not installed or not configured, the app
runs normally with no-op decorators.

Configuration via environment variables:
    PROMETA_STAGE                — "staging" or "production" (default: staging)
    PROMETA_ENDPOINT_{STAGE}     — OTLP traces endpoint for this stage (required)
    PROMETA_API_KEY_{STAGE}      — API key for this stage
    PROMETA_SOLUTION_ID          — Solution identifier (default: declarai-assistant)
    PROMETA_AGENT_NAME           — Agent display name (default: declarai-agent)
    PROMETA_AGENT_ID             — Stable customer-owned Agent id/slug.
                                   Defaults to ``{agent_name}-{stage}``, e.g.
                                   ``declarai-agent-staging``. We pass it
                                   explicitly so the SDK never falls back to a
                                   random per-process id while Prometa's Agent
                                   auto-registration design is still pending.

    v2.40.2 (2026-05-21): reverted to Stream A naming on platform-team
    request — the previous (solution_id='sol_declarai', agent_name=
    'declarai-assistant') pair created a duplicate Agent row that the
    platform team soft-deprecated. The auto-register dedupes by
    ``(orgId, solutionId, agentName)`` — without this revert, the next
    trace would either flip the deprecated row back to active OR mint
    a fresh duplicate. See screenshot from prometa-team dated 2026-05-21.

    Fallback: PROMETA_ENDPOINT / PROMETA_API_KEY (without suffix) are checked
    if the stage-specific vars are not set.
"""

import os
import re
import functools
import logging
import time as _time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# v2.40.2: Stream A naming — DO NOT revert without coordinating with the
# Prometa platform team.  See the module docstring for the dedup-key
# rationale ((orgId, solutionId, agentName) on the auto-register side).
DEFAULT_PROMETA_SOLUTION_ID = 'declarai-assistant'
DEFAULT_PROMETA_AGENT_NAME = 'declarai-agent'
DEFAULT_DECLARAI_MCP_SERVER_NAME = 'declarai'

_prometa = None
_initialized = False


def _slugify_agent_part(value: str, fallback: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or fallback


def _resolve_agent_id(agent_name: str, stage: str) -> tuple[str, str]:
    """Return a stable Prometa agent id and its source.

    Prometa SDK 0.7.0 accepts any non-empty string as ``agent_id``. Until
    Prometa mirrors Tool auto-registration for Agents, DeclarAI owns a
    human-readable slug instead of copy-pasting a platform UUID.
    """
    from_env = (os.environ.get('PROMETA_AGENT_ID') or '').strip()
    if from_env:
        return from_env, 'env'
    agent_slug = _slugify_agent_part(agent_name, DEFAULT_PROMETA_AGENT_NAME)
    stage_slug = _slugify_agent_part(stage, 'staging')
    return f'{agent_slug}-{stage_slug}', 'default-slug'


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
        solution_id = os.environ.get('PROMETA_SOLUTION_ID', DEFAULT_PROMETA_SOLUTION_ID)
        agent_name = os.environ.get('PROMETA_AGENT_NAME', DEFAULT_PROMETA_AGENT_NAME)
        agent_id, agent_id_source = _resolve_agent_id(agent_name, stage)

        # Prometa platform feedback tracked in
        # docs/prometa-feedback/agent-id-auto-registration.md asks upstream
        # to auto-register Agents like Tools. Until that lands, pass a stable
        # customer-owned slug so the SDK never emits a fresh random id per
        # process. This preserves platform joins without requiring operators
        # to copy a UUID from the Prometa UI.
        prometa_kwargs: dict = {
            'endpoint': endpoint,
            'api_key': api_key,
            'solution_id': solution_id,
            'agent_name': agent_name,
            'agent_id': agent_id,
            'stage': stage,
            # Default flush_interval_seconds=2.0 is fine — platform v0.3.2+
            # deduplicates by (trace_id, span_id) via ReplacingMergeTree.
        }
        _prometa = Prometa(**prometa_kwargs)
        logger.info(
            "Prometa tracing initialized — stage=%s, endpoint=%s, agent_id=%s (%s)",
            stage, endpoint, agent_id, agent_id_source,
        )

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

        # v2.42.0 (AML A4): enable dual-channel raw capture.  The
        # auto-instrumentation above stamps ``gen_ai.prompt`` with a
        # ``safe_json(messages)`` blob TRUNCATED to 32 000 bytes
        # (``prometa/integrations/_llm_common.py:MAX_TEXT_ATTR_BYTES``).
        # In production our messages array routinely exceeds 32 KB
        # (system prompt + slim context + auto-routed skill body +
        # history + tool defs), so the truncation knife lands AFTER the
        # leading system prompt but BEFORE any ``"role":"user"`` marker.
        # The platform's A4 detector then sees "no user role" and flags
        # the span as `absent`.
        #
        # Turning raw_channel on lets us stamp the FULL role-tagged
        # messages JSON as ``prometa.raw.rendered_prompt`` (no
        # truncation; the platform routes it to the short-TTL
        # ``spans_raw`` table) AND stamp the user query alone as
        # ``prometa.raw.input`` — both via the helpers in
        # ``ai_assistant/views.py`` and the canonical
        # ``prompt_render`` context manager.  See plan:
        # /Users/caglarsubasi/.windsurf/plans/plan-c19801.md.
        try:
            from prometa import _raw_channel as prometa_raw_channel
            prometa_raw_channel.enable()
            logger.info("Prometa raw-channel enabled (A4 prompt isolation contract).")
        except (ImportError, AttributeError):
            logger.info("Prometa raw-channel helper not available (SDK <0.7).")
        except Exception as exc_rc:
            logger.warning("Prometa raw-channel enable failed: %s", exc_rc)

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
            traced_fn = fn
            if kind == 'tool':
                marker_name = name or getattr(fn, '__name__', 'tool')

                @functools.wraps(fn)
                def traced_fn(*args, **kw):
                    stamp_mcp_tool_marker(marker_name)
                    return fn(*args, **kw)

            @functools.wraps(fn)
            def wrapper(*args, **kw):
                if _traced[0] is None:
                    p = get_prometa()
                    if p:
                        real_decorator = getattr(p, kind)(name=name, **kwargs)
                        _traced[0] = real_decorator(traced_fn)
                    else:
                        _traced[0] = traced_fn
                return _traced[0](*args, **kw)
            return wrapper
        return decorator
    return decorator_factory


workflow = _make_lazy_decorator('workflow')
agent = _make_lazy_decorator('agent')
tool = _make_lazy_decorator('tool')


# ---------------------------------------------------------------------------
# v2.42.0 — prompt.render contract (AML A4 / B7 / C4 / C5 / C6)
# ---------------------------------------------------------------------------
# Lazy import + safe-no-op fallback for ``prometa.prompt_render``.
#
# Why a wrapper?  Direct ``from prometa import prompt_render`` would
# break import on older SDKs (the symbol landed in v0.4.x and crystallized
# in v0.7.x) and would also raise inside pytest where ``PROMETA_DISABLE=1``
# turns the whole SDK into a no-op.  The wrapper below is a context
# manager with the same interface — when the real helper is unavailable,
# it yields a stand-in handle whose ``.assembled(...)`` method is a no-op.
#
# Call site (``ai_assistant/views.py::_chat_workflow``) is unconditional:
# ``with prompt_render(template_version=..., raw_rendered_prompt=...) as p:
#       p.assembled(role_boundaries=..., system_token_count=..., ...)``
# so the contract attributes (``prompt.role_boundaries``,
# ``prompt.template_version``, optional ``prometa.raw.rendered_prompt``)
# land on a dedicated ``prompt.render`` span when the SDK is live and
# silently drop on the floor in test/dev environments.
# ---------------------------------------------------------------------------

class _NoOpPromptRenderHandle:
    """Stand-in returned when the SDK's prompt_render helper is unavailable.

    Mirrors ``prometa.prompt._PromptRenderHandle.assembled`` signature so
    call sites don't need to special-case the no-op path.  Every kwarg
    accepted by the real helper is also accepted here — kwargs are
    ignored.
    """

    def assembled(self, **_kwargs) -> None:  # noqa: D401 - thin wrapper
        return None


@contextmanager
def prompt_render(*, template_version: str = None,
                  raw_rendered_prompt: str = None):
    """Emit a ``prompt.render`` span for the AML A4 detector.

    Thin wrapper over ``prometa.prompt_render`` that degrades cleanly:
      * Real SDK available + Prometa initialized → yields the SDK's
        ``_PromptRenderHandle`` which stamps ``prompt.template_version`` +
        ``prometa.raw.rendered_prompt`` (when raw_channel is enabled) on
        the span, and whose ``.assembled(...)`` writes
        ``prompt.role_boundaries`` + token counts.
      * SDK missing OR Prometa not initialized OR helper raises →
        yields ``_NoOpPromptRenderHandle()`` which absorbs ``.assembled``
        calls silently.

    The raw_channel toggle (enabled in ``get_prometa()``) gates whether
    ``raw_rendered_prompt`` actually lands on the span — the platform's
    short-TTL ``spans_raw`` table is opt-in.
    """
    # Fast path: ensure Prometa is initialized; if not, yield no-op.
    p = get_prometa()
    if p is None:
        yield _NoOpPromptRenderHandle()
        return
    try:
        from prometa import prompt_render as _real_prompt_render
    except (ImportError, AttributeError):
        # v0.6.x and earlier — symbol absent.  In production we require
        # prometa-sdk>=0.18.2 (see requirements.txt) so this branch only
        # fires in legacy/test environments.
        yield _NoOpPromptRenderHandle()
        return
    try:
        with _real_prompt_render(
            template_version=template_version,
            raw_rendered_prompt=raw_rendered_prompt,
        ) as handle:
            yield handle
    except Exception as exc:  # pragma: no cover - defensive
        # Never let an observability bug take down the chat workflow.
        logger.warning("prompt_render span failed: %s", exc)
        yield _NoOpPromptRenderHandle()


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


def _set_span_attr_direct(key: str, value) -> None:
    """Fallback for SDKs that predate the public set_attribute helper."""
    try:
        from prometa._context import current_span
        span = current_span()
        if span is not None:
            span.attributes[key] = value
    except Exception:
        pass


def set_span_attr(key: str, value) -> None:
    """Set an attribute on the current Prometa span.

    SDK 0.18.2 exposes the public ``set_attribute`` helper used for
    producer-owned metadata such as ``declarai.mcp.*``.  Keep the direct span
    fallback so older local/test SDKs still degrade safely.
    """
    try:
        from prometa import set_attribute as _sdk_set_attribute
        _sdk_set_attribute(key, value)
    except (ImportError, AttributeError):
        _set_span_attr_direct(key, value)
    except Exception:
        _set_span_attr_direct(key, value)


def set_span_attrs(attributes: dict) -> None:
    """Set several attributes on the current Prometa span."""
    if not attributes:
        return
    try:
        from prometa import set_attributes as _sdk_set_attributes
        _sdk_set_attributes(dict(attributes))
    except (ImportError, AttributeError):
        for key, value in attributes.items():
            set_span_attr(key, value)
    except Exception:
        for key, value in attributes.items():
            _set_span_attr_direct(key, value)


def stamp_codeline_capability(
    *,
    kind: str,
    position: str = None,
    mode: str = None,
    source: str = 'codeline',
    auto_correction_attempt: int = None,
    turn_kind: str = None,
    iteration: int = None,
) -> None:
    """Stamp Codeline capability footprints on the active Prometa span.

    ``kind`` is ``'communication'`` (inline cell chat) or ``'execution'``
    (inline cell Run / Apply).  Attributes are OTLP scalars only and are
    no-ops when no span is active (via ``set_span_attr``).

    ``turn_kind`` (v3.5.0) separates a Codeline's first ask (``'intent'``)
    from an iteration on the same cell — user feedback (``'refine'``) or an
    automatic error correction (``'auto_fix'``).  ``iteration`` is the
    1-based index of this turn within the cell's thread, so a trace shows
    how many rounds a Codeline answer took to converge.
    """
    if kind not in ('communication', 'execution'):
        return
    resolved_source = (source or 'codeline').strip().lower() or 'codeline'
    if kind == 'communication':
        set_span_attr('declarai.capability.inline_cell_communication', True)
        set_span_attr('declarai.chat_source', resolved_source)
    else:
        set_span_attr('declarai.capability.inline_cell_execution', True)
        set_span_attr('declarai.action.source', resolved_source)
        if mode:
            set_span_attr('declarai.execute_code.mode', str(mode))
    if position:
        set_span_attr('declarai.codeline.position', str(position))
    if auto_correction_attempt is not None:
        set_span_attr(
            'declarai.codeline.auto_correction_attempt',
            int(auto_correction_attempt),
        )
    if turn_kind:
        set_span_attr('declarai.codeline.turn_kind', str(turn_kind))
    if iteration is not None:
        set_span_attr('declarai.codeline.iteration', int(iteration))


def stamp_mcp_tool_marker(
    tool_name: str,
    *,
    mcp_tool_name: str = None,
    server_name: str = DEFAULT_DECLARAI_MCP_SERVER_NAME,
) -> None:
    """Stamp the standard MCP discovery markers on a tool-like span.

    Prometa's MCP telemetry discovery keys off either ``mcp.*`` attributes or
    the namespaced ``declarai.mcp.*`` producer metadata.  Use this helper on
    every DeclarAI tool/cache/skill span, including spans that are reached via
    the legacy in-process dispatcher rather than an external MCP ``tools/call``.

    ``tool_name`` is the local classifier/display name already used by
    ``gen_ai.tool.name`` and ``prometa.tool_name``. ``mcp_tool_name`` can be the
    fully-qualified MCP catalog name when it differs, for example
    ``declarai.get_pipeline_config`` for the internal ``get_pipeline_config``
    dispatcher call.
    """
    if not tool_name:
        return
    resolved_mcp_tool_name = mcp_tool_name or tool_name
    attrs = {
        'mcp.server.name': server_name,
        'mcp.tool.name': resolved_mcp_tool_name,
        'declarai.mcp.tool_name': resolved_mcp_tool_name,
        'gen_ai.tool.name': tool_name,
        'prometa.tool_name': tool_name,
    }
    for key, value in attrs.items():
        set_span_attr(key, value)


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
def plan_generate(plan_id: str):
    """Wrap a plan-generation event in a Prometa ``plan.generate`` AML
    span (catalog C2).  Forwards to the v0.4.0+ SDK helper when
    available; yields a ``_NoOpAMLHandle`` otherwise.

    Usage::

        with plan_generate('declarai-file-42-1234567890') as p:
            p.emitted(
                steps=[
                    {'order': 1, 'action': 'update_purifier_selection',
                     'tool': 'update_purifier_selection', 'depends_on': []},
                ],
                complexity_estimate=1,
            )

    DeclarAI mapping: the LLM in ``_chat_workflow`` may emit one or
    more ``<<<ACTION:action_type>>>...payload...<<<END_ACTION>>>``
    blocks in its response.  ``_extract_actions`` parses them into a
    list of ``{action_type, payload}`` dicts — that IS the generated
    plan.  We emit ``plan.generate`` only when the parse yields ≥1
    action (pure conversational replies don't produce plans).

    Each action becomes one plan step.  DeclarAI actions are
    independent suggestions (the user applies any subset via the
    chat-panel UI) so ``depends_on=[]`` on every step; we don't
    encode false ordering constraints.

    Body exceptions propagate normally — only ImportError is caught.
    """
    try:
        from prometa import plan_generate as _sdk_plan_generate
    except ImportError:
        yield _NoOpAMLHandle()
        return
    with _sdk_plan_generate(plan_id) as handle:
        yield handle


@contextmanager
def cache_lookup(kind: str, *, key: str):
    """Wrap a cache fetch in a Prometa ``cache.lookup`` AML span
    (catalog B1).  Forwards to the v0.4.0+ SDK helper when available;
    yields a ``_NoOpAMLHandle`` otherwise.

    ``kind`` MUST be one of ``{response, tool_call, embedding}`` — the
    SDK enforces this with a ValueError that we deliberately let
    propagate (it's a programmer error, not a runtime failure).

    Usage::

        with cache_lookup('tool_call', key=cache_key) as ch:
            raw = r.get(cache_key)
            if raw is None:
                ch.miss()
                return None
            ch.hit()  # optional: ch.hit(ttl_remaining_seconds=r.ttl(key))
            return json.loads(raw)

    DeclarAI mapping: every ``cache_get(file_id, artifact)`` in
    ai_assistant/cache.py is a tool-call cache lookup — when the LLM
    invokes a tool like ``get_dataset_summary`` we first check the
    Redis artifact cache.  Hits short-circuit the recompute; misses
    fall through to the slow path that recomputes and writes back.
    So ``kind='tool_call'`` is the canonical value for our surface.

    Body exceptions propagate normally — only ImportError is caught.
    """
    try:
        from prometa import cache_lookup as _sdk_cache_lookup
    except ImportError:
        yield _NoOpAMLHandle()
        return
    with _sdk_cache_lookup(kind, key=key) as handle:
        yield handle


@contextmanager
def retrieval_query(
    system: str,
    *,
    query_text: str,
    top_k: int,
    namespace: str = None,
    raw_retrieved: str = None,
):
    """Wrap a RAG / keyword fetch in a Prometa ``retrieval.query`` AML
    span (catalog B1).  Forwards to the SDK helper when available;
    yields a ``_NoOpAMLHandle`` otherwise.

    ``system`` MUST be one of ``{vector, graph, keyword, hybrid}`` — the
    SDK enforces this with a ValueError that we deliberately let
    propagate (programmer error, not a runtime failure).

    ``namespace`` is the searched corpus / collection identifier stamped
    as ``retrieval.namespace``.  Prefer the Chroma collection name when
    the vector path selects one; use the same value for lexical retrieval
    over the same corpus.

    Usage::

        with retrieval_query(
            "hybrid",
            query_text=query,
            top_k=4,
            namespace="declarai-knowledge-bank",
        ) as r:
            payload = _retrieve(query)
            r.results(
                result_ids=[item["chunk_id"] for item in payload["results"]],
                scores=[item["score"] for item in payload["results"]],
                permissions_enforced=False,
            )
            # Raw content is usually unknown at enter-time; stamp it on
            # the active retrieval span after materializing results:
            record_retrieval_raw(payload["context"])

    DeclarAI mapping: ``retrieve_knowledge_context`` (vector/hybrid) and
    ``retrieve_knowledge_context_lexical`` (keyword fallback) are the
    two call sites.  Lexical mode maps to ``system='keyword'``.

    ``raw_retrieved`` may be passed at enter when already known; the SDK
    only stamps it when the raw channel is enabled.  Prefer
    :func:`record_retrieval_raw` after fetch when the concatenated
    snippets are produced inside the ``with`` block.

    Body exceptions propagate normally — only ImportError is caught.
    """
    try:
        from prometa import retrieval_query as _sdk_retrieval_query
    except ImportError:
        yield _NoOpAMLHandle()
        return
    with _sdk_retrieval_query(
        system,
        query_text=query_text,
        top_k=top_k,
        namespace=namespace,
        raw_retrieved=raw_retrieved,
    ) as handle:
        yield handle


def record_retrieval_raw(raw_retrieved: str) -> None:
    """Stamp ``prometa.raw.retrieved_content`` on the active span.

    The SDK's ``retrieval_query(..., raw_retrieved=...)`` only accepts
    content at context-manager enter, but RAG materializes snippets
    inside the block.  Call this after building ``context`` while still
    inside ``with retrieval_query(...)`` so A3 indirect-injection scans
    see the retrieved text.  No-ops when raw channel is off / SDK absent.
    """
    if not raw_retrieved:
        return
    try:
        from prometa import _raw_channel as prometa_raw_channel
        if not prometa_raw_channel.is_enabled():
            return
    except Exception:
        return
    set_span_attr("prometa.raw.retrieved_content", raw_retrieved)


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


# ---------------------------------------------------------------------------
# v2.38.0: cross-trace data-flow refs (Prometa SDK ``refs`` module).
#
# DeclarAI splits each AI action into two HTTP requests — and therefore
# two separate Prometa traces:
#
#   1. POST /api/ai-assistant/chat/         → ``declarai-chat`` workflow
#      The LLM emits ``<<<ACTION:...>>>`` text blocks parsed into a list
#      of action proposals.  No execution happens here; the chat trace
#      ends with a ``plan.generate`` AML span and returns to the
#      frontend.
#
#   2. POST /api/ai-assistant/execute-action/  → ``declarai-action`` workflow
#      Fires only when the user clicks the green "Apply" button on the
#      action card.  Dispatches to the matching handler in HANDLERS,
#      writes back to Redis, returns the applied result.
#
# Without explicit linking these two traces appear as unrelated rows in
# Prometa's Trace Explorer — making the user think "Acting" is missing
# from the chat waterfall.  They share ``session_id =
# declarai-file-{file_id}`` so Session Explorer groups them, but the
# data-flow relationship "the action trace consumed the chat trace's
# proposal output" is invisible.
#
# The SDK provides the right primitive via ``prometa.refs``:
# ``set_input_ref(other_span_id)`` stamps the canonical
# ``prometa.input_ref`` attribute on the active span, which Prometa's
# trace UI renders as a clickable "Input from" row in the
# Causal-context block.  See ``orchestra-python-sdk/prometa/refs.py``
# docstring — it literally describes our use case:
#
#     "an LLM emits a tool_call, the agent dispatches a sibling tool
#      span. Without an explicit ref the platform can only infer the
#      link from temporal proximity..."
#
# Failure modes — both wrappers degrade gracefully (no exceptions):
#   1. SDK not installed              → ``current_span_id`` returns
#                                        None; ``set_input_ref`` returns
#                                        False.
#   2. SDK installed, no active span  → same (no-op contract).
#   3. SDK active, span available     → forwards to the real SDK call.
# ---------------------------------------------------------------------------


def current_span_id():
    """Return the span_id of the currently-active Prometa span, or None.

    Thin wrapper around ``prometa.current_span_id()`` (v0.4.0+) with
    SDK-absent fallback to None.  Used by ``_chat_workflow`` to snapshot
    the chat-turn span id and stamp it into the response so the frontend
    can pass it back when applying actions.

    Returns:
        str | None: the active span's id (opaque to us — Prometa's
        internal representation), or None when:
          * the SDK isn't installed (test env, dev box without endpoint)
          * no span is active (call happened outside ``@workflow`` /
            ``@tool`` / ``@agent`` context)
          * any internal SDK failure

    Synchronous, side-effect-free.
    """
    try:
        from prometa import current_span_id as _sdk_current_span_id
    except ImportError:
        return None
    try:
        return _sdk_current_span_id()
    except Exception:
        return None


def current_trace_id():
    """Return the trace_id of the currently-active Prometa span, or None.

    Prometa SDK 0.9.0 exposes ``current_span_id()`` publicly, while trace
    id access still lives on the active span object.  This wrapper keeps
    that best-effort lookup in one place so callers can target feedback
    records without depending on SDK-private modules directly.
    """
    try:
        from prometa import _context
        span = _context.current_span()
        return getattr(span, 'trace_id', None) if span is not None else None
    except Exception:
        return None


def set_input_ref(ref_span_id) -> bool:
    """Declare that the active span consumed ``ref_span_id``'s output.

    Thin wrapper around ``prometa.set_input_ref()`` (v0.4.0+) with
    SDK-absent / empty-input fallback to False.  Used by
    ``dispatch_action`` to link the action-execution trace back to the
    chat trace that proposed it.

    The platform reads ``prometa.input_ref`` from the span at OTLP
    ingest and surfaces it in the trace UI's Causal-context block as a
    clickable "Input from" row.  This collapses the two-trace
    propose-then-execute split into a single navigable flow in the UI
    without requiring actual span-parent nesting (which would need a
    custom OTel context propagator).

    Args:
        ref_span_id: the producer span's id (whatever
            ``current_span_id()`` returned upstream).  Falsy values
            (None, empty string) are treated as "no link" and the
            attribute is left unset rather than cleared — symmetric
            with the upstream chat trace having no span id at all
            (e.g. SDK disabled in test mode).

    Returns:
        bool: True if the attribute was successfully stamped on an
        active span, False on any of:
          * SDK not installed
          * no active span (call outside a Prometa-traced block)
          * empty/falsy ref_span_id
          * any internal SDK failure

    Synchronous, no exceptions surface to the caller.
    """
    if not ref_span_id:
        return False
    try:
        from prometa import set_input_ref as _sdk_set_input_ref
    except ImportError:
        return False
    try:
        return bool(_sdk_set_input_ref(str(ref_span_id)))
    except Exception:
        return False


def set_user_feedback(**kwargs) -> bool:
    """Stamp user feedback on the currently-active Prometa span if possible.

    This is the in-trace path.  UI-submitted feedback normally arrives
    after ``declarai-chat`` has ended and should use
    ``record_user_feedback`` instead.
    """
    try:
        from prometa import set_user_feedback as _sdk_set_user_feedback
    except ImportError:
        return False
    try:
        return bool(_sdk_set_user_feedback(**kwargs))
    except Exception:
        return False


def record_user_feedback(**kwargs) -> bool:
    """Emit a standalone Prometa ``feedback.record`` span if configured."""
    p = get_prometa()
    if p is None:
        return False
    try:
        from prometa import record_user_feedback as _sdk_record_user_feedback
    except ImportError:
        return False
    try:
        return bool(_sdk_record_user_feedback(**kwargs))
    except Exception:
        return False
