"""
Telemetry correlation helpers for Prometa-bundled DeclarAI runs.
"""

from __future__ import annotations

from ai_assistant.prometa_config import set_span_attrs


def stamp_bundle_identity(
    agent_id: str,
    solution_id: str | None = None,
    solution_name: str | None = None,
    agent_name: str | None = None,
) -> None:
    """Stamp Prometa bundle identity on the active span.

    Prometa ingests ``prometa.agent_id`` as the primary id-based Agent
    Registry join.  ``prometa.solution_id`` intentionally receives the
    bundle's solution name when present because the platform's fallback
    resolver uses solution-name + agent-name.
    """
    attrs = {
        "gen_ai.agent.id": agent_id,
        "prometa.agent.id": agent_id,
        "prometa.agent_id": agent_id,
        "declarai.prometa.bundle.agent_id": agent_id,
    }
    if agent_name:
        attrs["gen_ai.agent.name"] = agent_name
        attrs["prometa.agent_name"] = agent_name
        attrs["declarai.prometa.bundle.agent_name"] = agent_name
    solution_key = solution_name or solution_id
    if solution_key:
        attrs["prometa.solution.id"] = solution_key
        attrs["prometa.solution_id"] = solution_key
    if solution_id:
        attrs["declarai.prometa.bundle.solution_id"] = solution_id
    if solution_name:
        attrs["declarai.prometa.bundle.solution_name"] = solution_name
    set_span_attrs(attrs)
