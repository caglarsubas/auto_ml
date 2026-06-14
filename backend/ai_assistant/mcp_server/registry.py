"""
Tool and action registry for the DeclarAI MCP facade.

This module adapts the assistant's existing OpenAI-style tool schemas into
MCP-facing names.  It deliberately does not reimplement any pipeline logic:
runtime calls still go through ``tool_executor.execute_tool_call`` and
``action_executor.dispatch_action``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ai_assistant.mcp_server import auth
from ai_assistant.tool_definitions import PIPELINE_TOOLS


READ_TOOL_PREFIX = "declarai."
PREPARE_ACTION_PREFIX = "declarai.prepare."
DIRECT_ACTION_PREFIX = "declarai.action."


@dataclass(frozen=True)
class ReadToolSpec:
    """MCP metadata for a read-only assistant tool."""

    mcp_name: str
    internal_name: str
    title: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ActionSpec:
    """MCP metadata for an applyable assistant action."""

    action_type: str
    title: str
    description: str
    risk: str
    scope: str
    destructive: bool

    @property
    def prepare_name(self) -> str:
        return f"{PREPARE_ACTION_PREFIX}{self.action_type}"

    @property
    def direct_name(self) -> str:
        return f"{DIRECT_ACTION_PREFIX}{self.action_type}"


ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        "execute_code",
        "Prepare dataset code execution",
        "Prepare a sandboxed pandas/numpy dataset mutation action.",
        "high",
        auth.SCOPE_DATASET_WRITE,
        True,
    ),
    ActionSpec(
        "update_metadata",
        "Prepare metadata update",
        "Prepare data-dictionary metadata updates.",
        "medium",
        auth.SCOPE_METADATA_WRITE,
        False,
    ),
    ActionSpec(
        "update_config",
        "Prepare configuration update",
        "Prepare pipeline or feature-usage configuration changes.",
        "medium",
        auth.SCOPE_CONFIG_WRITE,
        False,
    ),
    ActionSpec(
        "set_ordinal_ranking",
        "Prepare ordinal ranking",
        "Prepare ordinal category rankings and implied LoM updates.",
        "medium",
        auth.SCOPE_METADATA_WRITE,
        False,
    ),
    ActionSpec(
        "start_sfs",
        "Prepare SFS run",
        "Prepare a Sequential Feature Selection start action.",
        "high",
        auth.SCOPE_PIPELINE_RUN,
        False,
    ),
    ActionSpec(
        "start_data_purifier",
        "Prepare data purifier run",
        "Prepare a preprocessing/data-purifier run action.",
        "high",
        auth.SCOPE_PIPELINE_RUN,
        False,
    ),
    ActionSpec(
        "update_purifier_selection",
        "Prepare purifier selection update",
        "Prepare a no-run Data Purifier checkbox selection change.",
        "medium",
        auth.SCOPE_CONFIG_WRITE,
        False,
    ),
    ActionSpec(
        "apply_encoding",
        "Prepare encoding run",
        "Prepare an Apply Encoding pipeline action.",
        "high",
        auth.SCOPE_PIPELINE_RUN,
        False,
    ),
    ActionSpec(
        "start_modeling",
        "Prepare modeling run",
        "Prepare a model-training pipeline action.",
        "high",
        auth.SCOPE_PIPELINE_RUN,
        False,
    ),
    ActionSpec(
        "start_hyperparameter",
        "Prepare hyperparameter tuning run",
        "Prepare a post-SFS hyperparameter tuning action.",
        "high",
        auth.SCOPE_PIPELINE_RUN,
        False,
    ),
    ActionSpec(
        "update_notes",
        "Prepare note update",
        "Prepare an add, edit, or delete operation for pipeline notes.",
        "low",
        auth.SCOPE_NOTES_WRITE,
        False,
    ),
)


def get_read_tool_specs() -> list[ReadToolSpec]:
    """Return deterministic MCP specs for every OpenAI-style pipeline tool."""
    specs: list[ReadToolSpec] = []
    for tool_definition in PIPELINE_TOOLS:
        function = tool_definition.get("function", {})
        internal_name = function.get("name")
        if not internal_name:
            continue
        input_schema = _schema_with_file_id(function.get("parameters", {}))
        title = internal_name.replace("_", " ").title()
        specs.append(
            ReadToolSpec(
                mcp_name=f"{READ_TOOL_PREFIX}{internal_name}",
                internal_name=internal_name,
                title=title,
                description=function.get("description", ""),
                input_schema=input_schema,
            )
        )
    return specs


def get_action_specs() -> list[ActionSpec]:
    """Return deterministic action specs in dispatcher order."""
    return list(ACTION_SPECS)


def get_action_spec(action_type: str) -> ActionSpec | None:
    """Look up one action spec by internal action type."""
    for spec in ACTION_SPECS:
        if spec.action_type == action_type:
            return spec
    return None


def _schema_with_file_id(parameters: dict[str, Any]) -> dict[str, Any]:
    """Copy an OpenAI parameters schema and make ``file_id`` explicit."""
    schema = copy.deepcopy(parameters) if isinstance(parameters, dict) else {}
    schema.setdefault("type", "object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    schema["properties"] = {
        "file_id": {
            "type": "integer",
            "description": "DeclarAI Declaration file id to inspect.",
        },
        **properties,
    }
    required = list(schema.get("required") or [])
    if "file_id" not in required:
        required.insert(0, "file_id")
    schema["required"] = required
    schema.setdefault("additionalProperties", False)
    return schema
