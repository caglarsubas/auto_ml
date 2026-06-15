"""
Governance checks for Prometa deployment bundle execution.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
READ_ONLY_SIDE_EFFECTS = frozenset({"", "none", "read", "read-only", "read_only"})


class BundlePolicyError(PermissionError):
    """Raised when a bundle or tool call violates Prometa governance."""


def manifest(content: Mapping[str, Any]) -> Mapping[str, Any]:
    value = content.get("manifest")
    if not isinstance(value, Mapping):
        raise BundlePolicyError("Prometa bundle content is missing manifest.")
    return value


def require_deployable(content: Mapping[str, Any]) -> None:
    if manifest(content).get("deployable") is not True:
        raise BundlePolicyError("Prometa bundle is not deployable.")


def require_agent_identity(content: Mapping[str, Any]) -> tuple[str, str | None]:
    m = manifest(content)
    agent_id = m.get("agentId")
    solution_id = m.get("solutionId")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise BundlePolicyError("Prometa bundle manifest is missing agentId.")
    if solution_id is not None and not isinstance(solution_id, str):
        raise BundlePolicyError("Prometa bundle manifest solutionId must be a string.")
    return agent_id, solution_id


def preflight_bundle(content: Mapping[str, Any]) -> None:
    require_deployable(content)
    require_agent_identity(content)
    for tool in bundle_tools(content):
        require_tool_scopes(content, tool)


def bundle_tools(content: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    tools = content.get("tools")
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        return []
    return [tool for tool in tools if isinstance(tool, Mapping)]


def find_tool(content: Mapping[str, Any], operation: str) -> Mapping[str, Any]:
    matches = [
        tool for tool in bundle_tools(content) if tool.get("operation") == operation
    ]
    if not matches:
        raise BundlePolicyError(f"Tool operation is not in Prometa bundle: {operation}")
    if len(matches) > 1:
        raise BundlePolicyError(
            f"Tool operation is ambiguous in Prometa bundle: {operation}"
        )
    return matches[0]


def require_tool_call_allowed(
    content: Mapping[str, Any],
    tool: Mapping[str, Any],
    *,
    approval_id: str | None = None,
) -> None:
    require_deployable(content)
    require_agent_identity(content)
    require_tool_scopes(content, tool)
    required_guardrails = guardrails_required_for_tool(tool)
    missing = [
        guardrail
        for guardrail in required_guardrails
        if not bundle_has_guardrail(content, guardrail)
    ]
    if missing:
        operation = str(tool.get("operation") or "")
        raise BundlePolicyError(
            f"Tool {operation} is missing required guardrails: {', '.join(missing)}"
        )
    if approval_required_for_tool(tool) and not (approval_id or "").strip():
        operation = str(tool.get("operation") or "")
        raise BundlePolicyError(f"Tool {operation} requires approval_id.")


def require_tool_scopes(
    content: Mapping[str, Any],
    tool: Mapping[str, Any],
) -> None:
    required = set(_str_list(tool.get("scopes")))
    if not required:
        return
    identity_scopes = set(_identity_granted_scopes(content))
    bundle_granted = set(_str_list(content.get("grantedScopes")))
    granted = identity_scopes | bundle_granted
    missing = sorted(required - granted)
    if missing:
        operation = str(tool.get("operation") or "")
        raise BundlePolicyError(
            f"Tool {operation} requires scopes not granted by bundle identity: "
            f"{', '.join(missing)}"
        )


def approval_required_for_tool(tool: Mapping[str, Any]) -> bool:
    explicit = _optional_bool(tool.get("approvalRequired"))
    if explicit is None:
        explicit = _optional_bool(tool.get("approval_required"))
    if explicit is not None:
        return explicit
    operation = str(tool.get("operation") or "")
    if operation.startswith("declarai.action."):
        return True
    side_effects = _normalize(str(tool.get("sideEffects") or ""))
    return side_effects not in {_normalize(v) for v in READ_ONLY_SIDE_EFFECTS}


def guardrails_required_for_tool(tool: Mapping[str, Any]) -> list[str]:
    explicit = _str_list(tool.get("requiredGuardrails"))
    if not explicit:
        explicit = _str_list(tool.get("required_guardrails"))
    if explicit:
        return [_normalize_guardrail(value) for value in explicit]

    required: list[str] = []
    if approval_required_for_tool(tool):
        required.append("human_approval")
    if _risk_rank(tool) >= RISK_ORDER["high"]:
        required.append("risk_gate")
    operation = str(tool.get("operation") or "")
    if operation == "declarai.action.execute_code":
        required.append("dataset_backup")
    return required


def bundle_has_guardrail(content: Mapping[str, Any], guardrail: str) -> bool:
    wanted = _normalize_guardrail(guardrail)
    guardrails = content.get("guardrails")
    if not isinstance(guardrails, Sequence) or isinstance(guardrails, (str, bytes)):
        return False
    for entry in guardrails:
        if not isinstance(entry, Mapping):
            continue
        tokens = {
            _normalize_guardrail(str(entry.get("name") or "")),
            _normalize_guardrail(str(entry.get("guardrailType") or "")),
            _normalize_guardrail(str(entry.get("approvalFor") or "")),
        }
        if wanted in tokens:
            return True
        if wanted == "risk_gate" and "mcpriskgate" in tokens:
            return True
        if wanted == "human_approval" and any(
            token in tokens
            for token in {"humanapproval", "approval", "approvalgate"}
        ):
            return True
    return False


def _identity_granted_scopes(content: Mapping[str, Any]) -> list[str]:
    identity = content.get("identity")
    if not isinstance(identity, Mapping):
        return []
    return _str_list(identity.get("grantedScopes"))


def _risk_rank(tool: Mapping[str, Any]) -> int:
    risk = str(tool.get("riskLevel") or tool.get("risk") or "low").lower()
    return RISK_ORDER.get(risk, 0)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_guardrail(value: str) -> str:
    normalized = _normalize(value)
    aliases = {
        "humanapproval": "human_approval",
        "humanapprovalguardrail": "human_approval",
        "approval": "human_approval",
        "approvalgate": "human_approval",
        "mcpriskgate": "risk_gate",
        "riskgate": "risk_gate",
        "datasetbackup": "dataset_backup",
        "backup": "dataset_backup",
        "reviewactionblock": "review_action_block",
    }
    return aliases.get(normalized, normalized)
