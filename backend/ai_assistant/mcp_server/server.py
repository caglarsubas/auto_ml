"""
FastMCP server for the DeclarAI Auto-ML assistant.

The server exposes the existing assistant tool/action surface over MCP.  It is a
facade only: all platform logic remains in ``tool_executor`` and
``action_executor``.
"""

from __future__ import annotations

from typing import Any, Literal

from ai_assistant.mcp_server import auth
from ai_assistant.mcp_server.actions import execute_direct_action, prepare_action
from ai_assistant.mcp_server.registry import (
    ActionSpec,
    get_action_specs,
    get_read_tool_specs,
)


PURIFIER_KIND = Literal[
    "col_dedup",
    "row_dedup",
    "zero_var_drop",
    "perfect_corr_drop",
    "corr_drop",
    "sparsity_drop",
    "missing_drop",
    "combined_drop",
    "outlier_quantile_clip",
    "cat_outlier_merge",
]

SFS_DIRECTION = Literal["forward", "backward", "forward_from_backward"]

SERVER_INSTRUCTIONS = """
DeclarAI Auto-ML MCP server. Read tools inspect one uploaded pipeline file by
explicit file_id. Prepare-action tools return reviewable action blocks and do
not mutate state. Direct action tools, when enabled by the operator, execute
through the existing DeclarAI action dispatcher and require scopes plus an
approval_id.
""".strip()


def create_mcp_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    json_response: bool = True,
    include_direct_actions: bool | None = None,
):
    """Create a configured FastMCP server instance."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised before install only
        raise RuntimeError(
            "The DeclarAI MCP server requires the 'mcp' Python package. "
            "Install backend requirements or run: pip install 'mcp>=1.27,<2'."
        ) from exc

    mcp = FastMCP(
        "DeclarAI Auto-ML",
        instructions=SERVER_INSTRUCTIONS,
        host=host,
        port=port,
        json_response=json_response,
    )
    _register_read_tools(mcp)
    _register_prepare_action_tools(mcp)
    if include_direct_actions is None:
        include_direct_actions = auth.direct_actions_enabled()
    elif include_direct_actions and not auth.direct_actions_enabled():
        include_direct_actions = False
    if include_direct_actions:
        _register_direct_action_tools(mcp)
    return mcp


def _run_read_tool(file_id: int, internal_name: str, arguments: dict[str, Any]) -> str:
    auth.require_scope(auth.SCOPE_PIPELINE_READ)
    from ai_assistant.tool_executor import execute_tool_call

    return execute_tool_call(file_id, internal_name, arguments)


def _clean_args(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def _tool_annotations(*, read_only: bool, destructive: bool, idempotent: bool):
    try:
        from mcp.types import ToolAnnotations
    except ImportError:  # pragma: no cover
        return None
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=False,
    )


def _register_read_tools(mcp) -> None:
    read_annotations = _tool_annotations(
        read_only=True,
        destructive=False,
        idempotent=True,
    )
    descriptions = {spec.internal_name: spec.description for spec in get_read_tool_specs()}

    @mcp.tool(
        name="declarai.get_split_validation",
        title="Get split validation",
        description=descriptions["get_split_validation"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_split_validation(file_id: int) -> str:
        return _run_read_tool(file_id, "get_split_validation", {})

    @mcp.tool(
        name="declarai.get_dq_summary",
        title="Get data-quality summary",
        description=descriptions["get_dq_summary"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_dq_summary(file_id: int, feature: str | None = None) -> str:
        return _run_read_tool(file_id, "get_dq_summary", _clean_args(feature=feature))

    @mcp.tool(
        name="declarai.get_feature_stats",
        title="Get feature stats",
        description=descriptions["get_feature_stats"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_feature_stats(file_id: int, feature: str) -> str:
        return _run_read_tool(file_id, "get_feature_stats", {"feature": feature})

    @mcp.tool(
        name="declarai.get_vif_decomposition",
        title="Get VIF decomposition",
        description=descriptions["get_vif_decomposition"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_vif_decomposition(file_id: int, feature: str) -> str:
        return _run_read_tool(file_id, "get_vif_decomposition", {"feature": feature})

    @mcp.tool(
        name="declarai.get_encoding_plan",
        title="Get encoding plan",
        description=descriptions["get_encoding_plan"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_encoding_plan(file_id: int) -> str:
        return _run_read_tool(file_id, "get_encoding_plan", {})

    @mcp.tool(
        name="declarai.get_selected_features",
        title="Get selected features",
        description=descriptions["get_selected_features"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_selected_features(file_id: int, top_n: int | None = None) -> str:
        return _run_read_tool(file_id, "get_selected_features", _clean_args(top_n=top_n))

    @mcp.tool(
        name="declarai.get_shap_details",
        title="Get SHAP details",
        description=descriptions["get_shap_details"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_shap_details(file_id: int, top_n: int | None = None) -> str:
        return _run_read_tool(file_id, "get_shap_details", _clean_args(top_n=top_n))

    @mcp.tool(
        name="declarai.get_sfs_results",
        title="Get SFS results",
        description=descriptions["get_sfs_results"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_sfs_results(file_id: int, direction: SFS_DIRECTION | None = None) -> str:
        return _run_read_tool(file_id, "get_sfs_results", _clean_args(direction=direction))

    @mcp.tool(
        name="declarai.get_cv_results",
        title="Get CV results",
        description=descriptions["get_cv_results"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_cv_results(file_id: int) -> str:
        return _run_read_tool(file_id, "get_cv_results", {})

    @mcp.tool(
        name="declarai.get_pipeline_notes",
        title="Get pipeline notes",
        description=descriptions["get_pipeline_notes"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_pipeline_notes(file_id: int) -> str:
        return _run_read_tool(file_id, "get_pipeline_notes", {})

    @mcp.tool(
        name="declarai.get_pipeline_config",
        title="Get pipeline config",
        description=descriptions["get_pipeline_config"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_pipeline_config(file_id: int) -> str:
        return _run_read_tool(file_id, "get_pipeline_config", {})

    @mcp.tool(
        name="declarai.get_purifier_options",
        title="Get purifier options",
        description=descriptions["get_purifier_options"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_purifier_options(file_id: int, kind: PURIFIER_KIND | None = None) -> str:
        return _run_read_tool(file_id, "get_purifier_options", _clean_args(kind=kind))

    @mcp.tool(
        name="declarai.get_data_dictionary",
        title="Get data dictionary",
        description=descriptions["get_data_dictionary"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_data_dictionary(file_id: int, feature: str | None = None) -> str:
        return _run_read_tool(file_id, "get_data_dictionary", _clean_args(feature=feature))

    @mcp.tool(
        name="declarai.invoke_skill",
        title="Invoke bundled skill",
        description=descriptions["invoke_skill"],
        annotations=read_annotations,
        structured_output=False,
    )
    def invoke_skill(file_id: int, skill_name: str) -> str:
        return _run_read_tool(file_id, "invoke_skill", {"skill_name": skill_name})

    @mcp.tool(
        name="declarai.get_skill_file",
        title="Get skill file",
        description=descriptions["get_skill_file"],
        annotations=read_annotations,
        structured_output=False,
    )
    def get_skill_file(file_id: int, skill_name: str, path: str) -> str:
        return _run_read_tool(
            file_id,
            "get_skill_file",
            {"skill_name": skill_name, "path": path},
        )


def _register_prepare_action_tools(mcp) -> None:
    annotations = _tool_annotations(
        read_only=True,
        destructive=False,
        idempotent=True,
    )
    for spec in get_action_specs():
        mcp.add_tool(
            _make_prepare_action_tool(spec),
            name=spec.prepare_name,
            title=spec.title,
            description=(
                f"{spec.description} This tool is review-only: it returns an "
                "action block and does not execute it."
            ),
            annotations=annotations,
            structured_output=True,
        )


def _register_direct_action_tools(mcp) -> None:
    annotations = _tool_annotations(
        read_only=False,
        destructive=True,
        idempotent=False,
    )
    for spec in get_action_specs():
        mcp.add_tool(
            _make_direct_action_tool(spec),
            name=spec.direct_name,
            title=spec.title.replace("Prepare", "Execute", 1),
            description=(
                f"Execute {spec.action_type} through the DeclarAI action dispatcher. "
                f"Requires scope {spec.scope} and approval_id."
            ),
            annotations=annotations,
            structured_output=True,
        )


def _make_prepare_action_tool(spec: ActionSpec):
    def prepare_tool(
        file_id: int,
        payload: dict[str, Any] | None = None,
        parent_span_id: str | None = None,
    ) -> dict[str, Any]:
        return prepare_action(
            file_id,
            spec.action_type,
            payload,
            parent_span_id=parent_span_id,
        )

    prepare_tool.__name__ = f"prepare_{spec.action_type}"
    prepare_tool.__doc__ = spec.description
    return prepare_tool


def _make_direct_action_tool(spec: ActionSpec):
    def direct_tool(
        file_id: int,
        payload: dict[str, Any] | None = None,
        approval_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> dict[str, Any]:
        return execute_direct_action(
            file_id,
            spec.action_type,
            payload,
            approval_id=approval_id,
            parent_span_id=parent_span_id,
        )

    direct_tool.__name__ = f"execute_{spec.action_type}"
    direct_tool.__doc__ = f"Execute {spec.action_type} through DeclarAI."
    return direct_tool
