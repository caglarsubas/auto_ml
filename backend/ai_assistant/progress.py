"""Turn-level progress events for the AI Assistant.

The chat turn is a single long request that internally runs several distinct
phases — intent classification, context assembly, knowledge-bank retrieval,
one or more LLM rounds, tool calls, and a synthesis pass.  Until now all of
that was invisible to the user: the panel showed a three-dot typing indicator
for the whole 5-60s turn.

This module is the plumbing that lets ``_chat_workflow`` narrate itself.  It
is deliberately tiny and dependency-free:

  * ``bind_sink`` binds a sink to the current context (a ``contextvars``
    variable, so it is per-thread / per-task).
  * ``emit`` / ``step`` publish events to whatever sink is bound.
  * With **no** sink bound every call is a no-op.  That is the normal case
    for the non-streaming ``POST /api/ai-assistant/chat/`` path, the Codeline
    cells, and the whole pytest suite — so instrumenting the workflow costs
    nothing when nobody is listening.

Event shape (one JSON object per NDJSON line on the wire)::

    {"type": "step", "id": "retrieval", "label": "Searching the knowledge bank",
     "state": "running" | "done" | "error", "detail": "3 sources",
     "seq": 4, "elapsed_ms": 118}

``id`` is the identity the frontend de-duplicates on: a ``running`` event
creates the row, a later ``done``/``error`` with the same id updates it in
place.  Ids for repeatable phases carry an ordinal (``llm:2``,
``tool:get_dq_summary:1``) so concurrent rounds never collapse into one row.

What this module deliberately does NOT cover: everything that happens after
the request leaves us and before the first token comes back — inference-engine
queue wait, model load, prompt eval, and generation.  That needs engine-side
signals; see ``docs/engine-feedback/turn-progress-telemetry.md``.
"""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

__all__ = [
    'ProgressSink',
    'bind_sink',
    'emit',
    'step',
    'is_active',
]


class ProgressSink:
    """Collects progress events and hands them to ``publish``.

    ``publish`` is called synchronously from the workflow thread, so it must
    not block — the streaming view passes ``queue.Queue.put_nowait``.
    """

    def __init__(self, publish: Callable[[dict], None]) -> None:
        self._publish = publish
        self._seq = 0
        self._started_at = time.monotonic()

    def emit(self, event: dict) -> None:
        self._seq += 1
        event['type'] = 'step'
        event['seq'] = self._seq
        event['elapsed_ms'] = int((time.monotonic() - self._started_at) * 1000)
        try:
            self._publish(event)
        except Exception:  # pragma: no cover - never let telemetry break a turn
            pass


_sink: contextvars.ContextVar[Optional[ProgressSink]] = contextvars.ContextVar(
    'declarai_progress_sink', default=None,
)


@contextmanager
def bind_sink(sink: ProgressSink):
    """Bind ``sink`` for the duration of the block (context-local)."""
    token = _sink.set(sink)
    try:
        yield sink
    finally:
        _sink.reset(token)


def is_active() -> bool:
    """True when someone is listening — lets callers skip expensive detail."""
    return _sink.get() is not None


def emit(step_id: str, label: str, state: str = 'running',
         detail: Optional[str] = None, **extra: Any) -> None:
    """Publish one progress event.  No-op when no sink is bound."""
    sink = _sink.get()
    if sink is None:
        return
    event = {'id': step_id, 'label': label, 'state': state}
    if detail:
        event['detail'] = detail
    event.update(extra)
    sink.emit(event)


@contextmanager
def step(step_id: str, label: str, detail: Optional[str] = None):
    """Emit ``running`` on entry and ``done`` (or ``error``) on exit.

    The block receives a small handle so it can refine the label/detail once
    it knows more than it did at entry — e.g. retrieval only learns the source
    count after the search returns::

        with step('retrieval', 'Searching the knowledge bank') as s:
            hits = retrieve(...)
            s.detail = f'{len(hits)} sources'
    """

    class _Handle:
        def __init__(self) -> None:
            self.label = label
            self.detail = detail

    handle = _Handle()
    emit(step_id, label, 'running', detail)
    try:
        yield handle
    except Exception as exc:
        emit(step_id, handle.label, 'error', str(exc)[:160])
        raise
    else:
        emit(step_id, handle.label, 'done', handle.detail)
