"""
Telemetry correlation helpers for Prometa-bundled DeclarAI runs.
"""

from __future__ import annotations

from ai_assistant.prometa_config import set_span_attr


def stamp_bundle_identity(agent_id: str, solution_id: str | None = None) -> None:
    """Stamp Prometa bundle identity on the active span.

    ``gen_ai.agent.id`` is the canonical GenAI-semconv-style attribute the
    Prometa SDK/platform already consumes. The ``prometa.*`` and
    ``declarai.prometa.bundle.*`` attributes make the same join key obvious in
    trace detail views and future platform queries.
    """
    set_span_attr("gen_ai.agent.id", agent_id)
    set_span_attr("prometa.agent.id", agent_id)
    set_span_attr("prometa.agent_id", agent_id)
    set_span_attr("declarai.prometa.bundle.agent_id", agent_id)
    if solution_id:
        set_span_attr("prometa.solution.id", solution_id)
        set_span_attr("prometa.solution_id", solution_id)
        set_span_attr("declarai.prometa.bundle.solution_id", solution_id)
