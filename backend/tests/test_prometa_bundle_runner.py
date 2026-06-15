"""
Unit tests for the DeclarAI-owned Prometa on-prem bundle runner.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ai_assistant.prometa_runner.canonicalization import canonicalize_bundle_content


def _content(
    *,
    deployable=True,
    tools=None,
    guardrails=None,
    granted_scopes=None,
    agent_id="agt-prometa-1",
):
    granted_scopes = granted_scopes or [
        "declarai.pipeline.read",
        "declarai.action.prepare",
        "declarai.notes.write",
    ]
    return {
        "schemaVersion": 1,
        "manifest": {
            "id": "man-1",
            "name": "Auto-ML Copilot",
            "description": "Drives the pipeline.",
            "version": 3,
            "status": "published",
            "agentId": agent_id,
            "solutionId": "sol-1",
            "deployable": deployable,
        },
        "systemPrompt": "# Auto-ML Copilot",
        "models": [],
        "primaryModel": None,
        "topology": None,
        "tools": tools
        if tools is not None
        else [
            {
                "name": "Prepare note",
                "source": "mcp",
                "mcpServer": "DeclarAI Auto-ML",
                "operation": "declarai.prepare.update_notes",
                "sideEffects": "read-only",
                "riskLevel": "low",
                "authBinding": "service-account",
                "scopes": ["declarai.action.prepare"],
            }
        ],
        "skills": [],
        "knowledge": [],
        "memory": [],
        "subAgents": [],
        "workflows": [],
        "guardrails": guardrails if guardrails is not None else [],
        "identity": {
            "name": "DeclarAI runner",
            "identityType": "service-account",
            "grantedScopes": granted_scopes,
            "secretBinding": "local",
        },
        "triggers": [],
        "evaluation": [],
        "mcpServers": ["DeclarAI Auto-ML"],
        "requiredScopes": [],
        "grantedScopes": granted_scopes,
        "readiness": {"quality": 80, "security": 80, "maturity": 80, "productivity": 80},
    }


def _signed_envelope(content, *, canonicalization="json-sorted-keys-utf8"):
    private_key = Ed25519PrivateKey.generate()
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            Encoding.DER,
            PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("ascii")
    signature = base64.b64encode(
        private_key.sign(canonicalize_bundle_content(content))
    ).decode("ascii")
    return {
        "content": content,
        "algorithm": "ed25519",
        "publicKey": public_key_b64,
        "signature": signature,
        "signed": True,
        "canonicalization": canonicalization,
    }


@pytest.mark.unit
class TestPrometaBundleSignature:
    def test_canonicalization_matches_prometa_stable_json_contract(self):
        content = {"z": 1, "a": {"z": 2, "a": ["x"]}, "text": "Merhaba " + "\u011f"}

        canonical = canonicalize_bundle_content(content)

        assert canonical.startswith(b'{"a":')
        assert b"\\u011f" not in canonical
        assert b"\xc4\x9f" in canonical

    def test_verifies_ed25519_signature(self):
        from ai_assistant.prometa_runner.signature import verify_bundle_signature

        envelope = _signed_envelope(_content())

        assert verify_bundle_signature(envelope) is True

    def test_accepts_previous_canonicalization_label_for_existing_bundles(self):
        from ai_assistant.prometa_runner.signature import verify_bundle_signature

        envelope = _signed_envelope(
            _content(),
            canonicalization="json-stable-sort-keys-utf8-no-ascii-escape-v1",
        )

        assert verify_bundle_signature(envelope) is True

    def test_rejects_tampered_content(self):
        from ai_assistant.prometa_runner.signature import (
            BundleVerificationError,
            verify_bundle_signature,
        )

        envelope = _signed_envelope(_content())
        envelope["content"] = {**envelope["content"], "systemPrompt": "tampered"}

        with pytest.raises(BundleVerificationError, match="verification failed"):
            verify_bundle_signature(envelope)

    def test_rejects_unsupported_canonicalization(self):
        from ai_assistant.prometa_runner.signature import (
            BundleVerificationError,
            verify_bundle_signature,
        )

        envelope = _signed_envelope(_content())
        envelope["canonicalization"] = "not-supported"

        with pytest.raises(BundleVerificationError, match="canonicalization"):
            verify_bundle_signature(envelope)


@pytest.mark.unit
class TestPrometaBundlePolicy:
    def test_runner_rejects_non_deployable_bundle(self):
        from ai_assistant.prometa_runner.policy import BundlePolicyError
        from ai_assistant.prometa_runner.runner import PrometaOnPremBundleRunner

        with pytest.raises(BundlePolicyError, match="not deployable"):
            PrometaOnPremBundleRunner(_signed_envelope(_content(deployable=False)))

    def test_runner_rejects_missing_agent_id(self):
        from ai_assistant.prometa_runner.policy import BundlePolicyError
        from ai_assistant.prometa_runner.runner import PrometaOnPremBundleRunner

        with pytest.raises(BundlePolicyError, match="agentId"):
            PrometaOnPremBundleRunner(_signed_envelope(_content(agent_id=None)))

    def test_policy_rejects_ungranted_tool_scope(self):
        from ai_assistant.prometa_runner.policy import BundlePolicyError
        from ai_assistant.prometa_runner.runner import PrometaOnPremBundleRunner

        tool = {
            "name": "Run modeling",
            "source": "mcp",
            "operation": "declarai.action.start_modeling",
            "sideEffects": "write",
            "riskLevel": "high",
            "authBinding": "service-account",
            "scopes": ["declarai.pipeline.run"],
        }

        with pytest.raises(BundlePolicyError, match="requires scopes"):
            PrometaOnPremBundleRunner(_signed_envelope(_content(tools=[tool])))

    def test_policy_requires_approval_and_guardrails_for_direct_action(self):
        from ai_assistant.prometa_runner.policy import (
            BundlePolicyError,
            find_tool,
            require_tool_call_allowed,
        )

        tool = {
            "name": "Update notes",
            "source": "mcp",
            "operation": "declarai.action.update_notes",
            "sideEffects": "write",
            "riskLevel": "low",
            "authBinding": "service-account",
            "scopes": ["declarai.notes.write"],
        }
        content = _content(
            tools=[tool],
            guardrails=[{"name": "Human approval", "guardrailType": "human-approval"}],
        )

        with pytest.raises(BundlePolicyError, match="approval_id"):
            require_tool_call_allowed(content, find_tool(content, "declarai.action.update_notes"))

        require_tool_call_allowed(
            content,
            find_tool(content, "declarai.action.update_notes"),
            approval_id="approval-1",
        )

    def test_policy_prefers_explicit_required_guardrails_when_present(self):
        from ai_assistant.prometa_runner.policy import guardrails_required_for_tool

        tool = {
            "operation": "declarai.action.execute_code",
            "riskLevel": "high",
            "requiredGuardrails": ["human_approval"],
        }

        assert guardrails_required_for_tool(tool) == ["human_approval"]

    def test_policy_treats_explicit_empty_required_guardrails_as_authoritative(self):
        from ai_assistant.prometa_runner.policy import guardrails_required_for_tool

        tool = {
            "operation": "declarai.action.execute_code",
            "riskLevel": "high",
            "requiredGuardrails": [],
        }

        assert guardrails_required_for_tool(tool) == []


@pytest.mark.unit
class TestPrometaBundleRunner:
    def test_runner_calls_local_mcp_with_bundle_identity_context(self, monkeypatch):
        from ai_assistant.prometa_runner.context import get_current_bundle_identity
        from ai_assistant.prometa_runner.runner import PrometaOnPremBundleRunner

        captured = {}

        class FakeMcp:
            async def call_tool(self, operation, arguments):
                captured["operation"] = operation
                captured["arguments"] = arguments
                captured["identity"] = get_current_bundle_identity()
                return [], {"status": "prepared"}

        runner = PrometaOnPremBundleRunner(
            _signed_envelope(_content()),
            mcp_server=FakeMcp(),
        )

        result = runner.call_tool(
            "declarai.prepare.update_notes",
            {"file_id": 42, "payload": {"action": "add"}},
        )

        assert result["structured"] == {"status": "prepared"}
        assert captured["operation"] == "declarai.prepare.update_notes"
        assert captured["identity"] == ("agt-prometa-1", "sol-1")

    def test_runner_injects_approval_id_for_direct_action(self):
        from ai_assistant.prometa_runner.runner import PrometaOnPremBundleRunner

        captured = {}

        class FakeMcp:
            async def call_tool(self, operation, arguments):
                captured["arguments"] = arguments
                return [], {"status": "executed"}

        tool = {
            "name": "Update notes",
            "source": "mcp",
            "operation": "declarai.action.update_notes",
            "sideEffects": "write",
            "riskLevel": "low",
            "authBinding": "service-account",
            "scopes": ["declarai.notes.write"],
        }
        runner = PrometaOnPremBundleRunner(
            _signed_envelope(
                _content(
                    tools=[tool],
                    guardrails=[
                        {"name": "Human approval", "guardrailType": "human-approval"}
                    ],
                )
            ),
            mcp_server=FakeMcp(),
        )

        runner.call_tool(
            "declarai.action.update_notes",
            {"file_id": 42, "payload": {"action": "add"}},
            approval_id="approval-1",
        )

        assert captured["arguments"]["approval_id"] == "approval-1"
