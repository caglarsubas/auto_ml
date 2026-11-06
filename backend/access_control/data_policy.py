"""The sealed private installation's local data policy."""

import hashlib
import json
import os

from django.conf import settings


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def policy():
    return {
        "version": "private_local_data_v1",
        "egress": {
            "inference": "deny",
            "discovery": "deny",
            "embeddings": "deny",
            "telemetry": "deny",
            "feedback": "deny",
            "deployment_bundles": "deny",
            "service_logs": "discard",
            "browser": "authorized_same_origin",
            "metadata_broker_cache": "installation_dependencies",
        },
        "retention": {
            "unused_uploads": "reviewed_operator_purge",
            "used_or_unclassified": "retain",
            "audit_and_recovery_copies": "retain",
        },
        "audit": "operator_keyed_checkpoint_v1",
    }


def policy_digest():
    return hashlib.sha256(canonical(policy())).hexdigest()


def private():
    # Standalone tools can initialize before Django settings.
    return os.environ.get("DECLARAI_RUNTIME_PROFILE") == "private" or (
        settings.configured and getattr(settings, "DECLARAI_RUNTIME_PROFILE", None) == "private"
    )


def allows(channel):
    from execution_jobs.legacy_context import active

    return not (private() or active()) or policy()["egress"].get(channel) in {
        "authorized_same_origin", "installation_dependencies"
    }


class PolicyDenied(ValueError):
    def __init__(self, code="private_egress_denied"):
        super().__init__(code)


def require_egress(channel):
    if not allows(channel):
        raise PolicyDenied()


def refusal(code="private_egress_denied"):
    return {"error_code": code, "policy": policy()["version"], "policy_sha256": policy_digest()}
