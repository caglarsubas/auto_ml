"""Threat probes on one exclusively owned, synthetic private installation."""

import hashlib
import json
import uuid

import private_installation_adopt as adopter
from qualify_private_installation_workflow import Session, owned, require

SCHEMA = "private_installed_threat_model_qualification_v1"
REPORT = "installed-threat-model.json"

PROBE = r'''
import io
import json
import os
import secrets
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, '/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0, '/app/backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'

import django
django.setup()
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from access_control.data_policy import allows
from access_control.models import ProjectAuthorityEvent

def policy(*args):
    out = io.StringIO()
    call_command('private_data_policy', *args, stdout=out)
    return json.loads(out.getvalue())

def refuse(code, *args):
    try:
        policy(*args)
    except CommandError as error:
        assert str(error) == code
    else:
        raise AssertionError('expected_policy_refusal')

v = json.load(sys.stdin)
description = policy('describe')
assert description['active'] is True and connection.vendor == 'postgresql'
assert all(not allows(channel) for channel in (
    'inference', 'discovery', 'embeddings', 'telemetry', 'feedback', 'deployment_bundles', 'unknown_channel'
))
assert allows('browser') and allows('metadata_broker_cache')
# A peer connection on the actual deployment database must prevent maintenance,
# including when the operator has asserted quiescence.
peer = connection.copy()
try:
    peer.ensure_connection()
    refuse('stop_installation_services_before_retention', 'review-upload',
           '--file-id', str(v['file_id']), '--quiescent')
finally:
    peer.close()

# The row was created by the fixture administrator's authenticated HTTPS
# membership restoration, so verification spans the real authority history.
event = ProjectAuthorityEvent.objects.get(pk=v['event_id'], operation='member')
with TemporaryDirectory(prefix='fixture-audit-', dir='/tmp') as root:
    key, checkpoint = Path(root) / 'key', Path(root) / 'checkpoint'
    fd = os.open(key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(secrets.token_hex(32))
    args = ('--scope', v['scope'], '--key-file', str(key), '--checkpoint', str(checkpoint))
    sealed = policy('seal-audit', *args)
    initial = policy('verify-audit', *args)
    assert sealed['captured_rows'] == initial['verified_rows'] > 0
    assert sealed['checkpoint_sha256'] == initial['checkpoint_sha256']
    envelope = json.loads(checkpoint.read_text())
    rows = envelope['payload']['rows']
    assert 'access_control.projectauthorityevent:' + str(event.pk) in rows
    assert any(key.startswith('execution_jobs.jobevent:') for key in rows)
    assert any(key.startswith('access_control.authenticationevent:') for key in rows)
    records = ProjectAuthorityEvent.objects.filter(pk=event.pk)
    assert records.update(reason_code='synthetic_checkpoint_change') == 1
    try:
        refuse('audit_captured_rows_changed_or_missing', 'verify-audit', *args)
    finally:
        assert records.update(reason_code=event.reason_code) == 1
    final = policy('verify-audit', *args)
    assert final['verified_rows'] == initial['verified_rows']
    assert final['checkpoint_sha256'] == initial['checkpoint_sha256']

print(json.dumps({
    'installed_policy_sha256': description['policy_sha256'],
    'installed_policy_version': description['policy']['version'],
    'private_egress_channels': 'denied',
    'concurrent_retention_maintenance': 'refused',
    'captured_audit_rows': final['verified_rows'],
    'audit_checkpoint_sha256': final['checkpoint_sha256'],
    'installed_audit_tampering': 'detected_and_restored',
}, sort_keys=True))
'''


def login(value, parent, accounts, passwords, role):
    session = Session(value, parent)
    guest = session.data("GET", "/api/auth/session/")
    require(guest["authenticated"] is False, "threat_anonymous_session")
    session.csrf = guest["csrf_token"]
    username = "fixture-" + role + "-" + parent.name.removeprefix("declarai-p37-")
    authenticated = session.data("POST", "/api/auth/login/", {"username": username, "password": passwords[role]})
    require(authenticated["authenticated"] is True
            and authenticated["user"]["id"] == accounts["accounts"][role]["subject_user_id"], "threat_login")
    session.csrf = authenticated["csrf_token"]
    return session, username


def set_role(admin, project, username, role, prior):
    path = f"/api/projects/{project}/members/"
    review = admin.data("POST", path, {"username": username, "operation": "preview"})
    require(review["role"] == prior, "threat_membership_initial_role")
    identifier = str(uuid.uuid4())
    admin.data("POST", path, {"username": username, "role": role, "request_id": identifier,
                              "expected": review["expected"]})
    return identifier


def qualify(session, handles, value, accounts, passwords, parent, adopted, command):
    """Use exact installed artifacts, then inject one reversible audit fault."""
    owned(value, parent)
    project = accounts["project_id"]
    dataset = handles[0]["dataset_id"]
    training = handles[0]["training"]
    scoring = handles[0]["scoring"]
    paths = [
        (f'/api/jobs/{training["id"]}/candidate/?sha256={training["result_sha256"]}', handles[0]["export"]),
        (f'/api/jobs/{scoring["id"]}/scores/?sha256={scoring["result_sha256"]}', handles[0]["scores"]),
    ]

    def denied(client, path):
        _content, headers = client.request("GET", path, status=403)
        require("content-disposition" not in headers and "x-declarai-export-sha256" not in headers
                and "x-declarai-receipt-sha256" not in headers, "threat_denied_artifact_headers")

    def matched(client, path, expected):
        content, headers = client.request("GET", path + "&project_id=" + project)
        require("no-store" in headers["cache-control"] and content == expected, "threat_exact_authorized_artifact")

    anonymous = Session(value, parent)
    admin, _ = login(value, parent, accounts, passwords, "admin")
    reviewer, username = login(value, parent, accounts, passwords, "reviewer")
    wrong_project = str(uuid.uuid4())

    for path, expected in paths:
        denied(anonymous, path)
        denied(reviewer, path + "&project_id=" + wrong_project)
        matched(reviewer, path, expected)

    scoring_input = f'/api/jobs/{training["id"]}/scoring-input/?project_id={project}'
    blocked = reviewer.data("POST", scoring_input, {
        "input_file_id": handles[0]["input_file_id"], "training_result_sha256": training["result_sha256"],
    }, 403)
    require(blocked.get("error_code") == "project_access_denied", "threat_reviewer_execution_role")

    set_role(admin, project, username, "none", "reviewer")
    require(reviewer.data("GET", "/api/auth/session/")["authenticated"] is True, "threat_revoked_session_still_valid")
    for path, _ in paths:
        denied(reviewer, path)
    restored = set_role(admin, project, username, "reviewer", "none")
    for path, expected in paths:
        matched(reviewer, path, expected)

    assistant = "/api/ai-assistant/"
    models = session.data("GET", assistant + "models/")
    require(models["models"] == [], "threat_private_model_discovery")
    policy = models["policy_sha256"]
    for route in ("chat", "feedback"):
        rejected = session.data("POST", f"{assistant}{route}/?project_id={project}", {
            "file_id": dataset, "message": "Synthetic private request",
        }, 403)
        require(rejected.get("error_code") == "private_egress_denied" and rejected.get("policy_sha256") == policy,
                "threat_private_transport")
    for route in ("prepare-action", "execute-action"):
        rejected = session.data("POST", f"{assistant}{route}/?project_id={project}", {
            "file_id": dataset, "action_type": "execute_code",
            "payload": {"code": "raise RuntimeError('synthetic expert isolation probe')"},
        }, 400)
        require(rejected.get("error_code") == "expert_isolation_unavailable", "threat_unavailable_isolation")

    read = f"/api/declaration/{dataset}/?project_id={project}"
    rejected = session.data("DELETE", read, status=409)
    require(rejected.get("error_code") == "private_retention_review_required"
            and rejected.get("policy_sha256") == policy and session.data("GET", read)["id"] == dataset,
            "threat_private_retention")

    for client in (reviewer, admin):
        require(client.data("POST", "/api/auth/logout/", {})["authenticated"] is False, "threat_role_logout")

    api = adopted["services"]["api"]["container_id"]
    profile = adopter.resources.inspect("container", api)
    network_name = value["prerequisites"]["networks"][0]["name"]
    network = adopter.resources.inspect("network", network_name)
    require(profile["Image"] == value["images"]["api"] and network.get("Internal") is True
            and set(profile["NetworkSettings"]["Networks"]) == {network_name}
            and not profile["HostConfig"].get("PortBindings"), "threat_internal_api_network")
    probe = command(["exec", "--user", "10001:10001", "-i", api, "python", "-I", "-c", PROBE], data=json.dumps({
        "file_id": dataset, "event_id": restored, "scope": value["request"]["installation_id"],
    }).encode())
    receipt = json.loads(probe)
    require(receipt["installed_policy_sha256"] == policy, "threat_policy_binding")
    return {
        "schema": SCHEMA,
        "result": "passed",
        "synthetic": True,
        "installed_application_images": value["images"],
        "installed_ca_verified_https": "passed",
        "anonymous_or_foreign_project_selector_artifacts": "denied",
        "reviewer_exact_artifact_and_execution_role": "verified",
        "revoked_project_access_with_active_session": "denied",
        "restored_membership_exact_artifacts": "verified",
        "training_artifact_sha256": hashlib.sha256(handles[0]["export"]).hexdigest(),
        "scoring_artifact_sha256": hashlib.sha256(handles[0]["scores"]).hexdigest(),
        "browser_inference_feedback_discovery": "denied",
        "unavailable_application_expert_isolation": "refused",
        "browser_retention_bypass": "refused",
        "api_internal_network_and_unpublished_port": "verified",
        "raw_artifacts_credentials_or_audit_checkpoint_retained": False,
        **receipt,
    }
