"""Regression coverage for the installed data policy and operator procedures."""

import io
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError
from django.db import connection

from access_control import audit_checkpoint, data_policy, retention
from access_control.models import AuthenticationEvent, ProjectAuthorityEvent
from ai_assistant import feedback, model_registry, prometa_config
from ai_assistant.prometa_runner.client import fetch_bundle
from ai_assistant.rag import embeddings
from declaration.models import Declaration
from tests.unit.test_project_authority import post, world  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def private_world(world, settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    if connection.vendor != "postgresql":
        # The PostgreSQL lane exercises the real maintenance check. SQLite
        # covers receipt, storage and model semantics without claiming custody.
        monkeypatch.setattr(retention, "require_maintenance", lambda: None)
    return world


def upload(client):
    source = io.BytesIO(b"x,target\n1,0\n2,1\n")
    source.name = "synthetic.csv"
    response = client.post("/api/declaration/", {"file": source, "has_header": "true"})
    assert response.status_code == 201, response.content
    return Declaration.objects.get(pk=response.json()["id"])


def command(*args):
    output = io.StringIO()
    call_command("private_data_policy", *args, stdout=output)
    return json.loads(output.getvalue())


def test_private_transport_boundaries_fail_before_using_ambient_credentials(private_world, monkeypatch):
    _, _, _, clients, files, _ = private_world
    client = clients["developer"]
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("LLM_ENGINE_BASE_URL", "https://synthetic.invalid/v1")
    monkeypatch.setenv("PROMETA_API_KEY", "synthetic-telemetry-key")
    monkeypatch.setattr(prometa_config, "_prometa", object())
    monkeypatch.setattr(prometa_config, "_initialized", True)
    trap = AssertionError("private data reached a transport")
    with (patch("openai.OpenAI", side_effect=trap),
          patch("urllib.request.urlopen", side_effect=trap),
          patch("ai_assistant.prometa_runner.client.urlopen", side_effect=trap),
          patch("ai_assistant.rag.embeddings._get_redis", side_effect=trap)):
        models = client.get("/api/ai-assistant/models/")
        assert models.status_code == 200 and models.json()["models"] == []
        described = command("describe")
        assert described["active"] and models.json()["policy_sha256"] == described["policy_sha256"]
        for endpoint in ("chat", "feedback"):
            response = post(client, f"/api/ai-assistant/{endpoint}/", {"file_id": files[0].pk, "message": "private"})
            assert response.status_code == 403, response.content
            assert response.json()["policy_sha256"] == described["policy_sha256"]
            assert response.json()["error_code"] == "private_egress_denied"
        assert model_registry._fetch_engine_models() is None
        assert not embeddings.embeddings_available()
        assert prometa_config.get_prometa() is None
        assert feedback.submit_feedback_to_prometa(None)["status"] == "denied"
        for invoke in (
            lambda: model_registry.call_openai("ignored", [], {}),
            lambda: model_registry.call_engine([], {}),
            lambda: embeddings.embed_texts(["private"]),
            lambda: fetch_bundle(base_url="https://synthetic.invalid", manifest_id="x", token="ignored"),
        ):
            with pytest.raises(data_policy.PolicyDenied):
                invoke()


def test_retention_cli_review_and_idempotent_purge(private_world, settings):
    _, _, _, clients, _, _ = private_world
    dataset = upload(clients["developer"])
    path = Path(settings.MEDIA_ROOT) / dataset.file.name
    registration = ProjectAuthorityEvent.objects.get(operation="upload_registered")
    assert registration.actor.username == "developer" and registration.resource["relative_path"] == dataset.file.name
    file_id = dataset.pk
    request_id = uuid.uuid4()
    if connection.vendor == "postgresql":
        base = ["--file-id", str(file_id), "--quiescent"]
        preview = command("review-upload", *base)
        args = ["purge-upload", *base, "--expected", preview["expected"], "--request-id", str(request_id),
                "--operator-label", "fixture"]
        receipt = command(*args)
        assert command(*args) == receipt
    else:
        with pytest.raises(CommandError, match="private_postgresql_runtime_required"):
            command("review-upload", "--file-id", str(file_id), "--quiescent")
        preview = retention.review(file_id)
        receipt = retention.purge(file_id, preview["expected"], request_id, "fixture")
        assert retention.purge(file_id, preview["expected"], request_id, "fixture") == receipt
    assert receipt["reason_code"] == "upload_removed"
    assert not path.exists() and not Declaration.objects.filter(pk=file_id).exists()
    event = ProjectAuthorityEvent.objects.get(pk=request_id)
    assert event.outcome == "completed" and event.operator_label == "fixture"
    assert event.actor is None and registration.pk != event.pk
    with pytest.raises(retention.RetentionError, match="request_conflict"):
        retention.purge(file_id, preview["expected"], request_id, "other operator")


def test_retention_holds_used_and_unclassified_artifacts(private_world, settings):
    _, _, _, clients, files, pipeline = private_world
    client = clients["developer"]
    with pytest.raises(retention.RetentionError, match="unclassified"):
        retention.review(files[0].pk)
    dataset = upload(client)
    assert client.get(f"/api/declaration/{dataset.pk}/").status_code == 200
    assert client.delete(f"/api/declaration/{dataset.pk}/").json()["error_code"] == "private_retention_review_required"
    assert client.patch(f"/api/declaration/{dataset.pk}/", {"name": "override"},
                        content_type="application/json").json()["error_code"] == "private_upload_immutable"
    assert client.delete(f"/api/pipeline/{pipeline.pk}/").json()["error_code"] == "private_retention_review_required"
    with pytest.raises(retention.RetentionError, match="use_or_evidence"):
        retention.review(dataset.pk)
    dataset.refresh_from_db()
    assert (Path(settings.MEDIA_ROOT) / dataset.file.name).is_file()
    pipeline.refresh_from_db()


def test_stale_review_and_interrupted_storage_removal(private_world, settings):
    dataset = upload(private_world[3]["developer"])
    file_id = dataset.pk
    path = Path(settings.MEDIA_ROOT) / dataset.file.name
    old = retention.review(file_id)["expected"]
    path.write_bytes(path.read_bytes() + b"3,1\n")
    request_id = uuid.uuid4()
    with pytest.raises(retention.RetentionError, match="review_changed"):
        retention.purge(file_id, old, request_id, "fixture")
    assert Declaration.objects.filter(pk=file_id).exists()
    assert not ProjectAuthorityEvent.objects.filter(pk=request_id).exists()
    expected = retention.review(file_id)["expected"]
    with patch("access_control.retention.os.unlink", side_effect=OSError("synthetic I/O failure")):
        with pytest.raises(OSError):
            retention.purge(file_id, expected, request_id, "fixture")
    assert ProjectAuthorityEvent.objects.get(pk=request_id).outcome == "pending_files"
    assert path.exists() and not Declaration.objects.filter(pk=file_id).exists()
    path.unlink()  # Simulate loss of the terminal receipt after successful unlink.
    receipt = retention.purge(file_id, expected, request_id, "fixture")
    assert receipt["reason_code"] == "upload_absence_reconciled"
    assert ProjectAuthorityEvent.objects.get(pk=request_id).outcome == "completed"


def test_retention_refuses_link_and_concurrent_database_client(private_world, settings, tmp_path):
    dataset = upload(private_world[3]["developer"])
    path = Path(settings.MEDIA_ROOT) / dataset.file.name
    alias = tmp_path / "synthetic-alias.csv"
    os.link(path, alias)
    with pytest.raises(retention.RetentionError, match="storage_not_eligible"):
        retention.review(dataset.pk)
    path.unlink()
    path.symlink_to(alias)
    with pytest.raises(OSError):
        retention.review(dataset.pk)
    assert alias.exists() and Declaration.objects.filter(pk=dataset.pk).exists()
    if connection.vendor == "postgresql":
        other = connection.copy()
        try:
            other.ensure_connection()
            with pytest.raises(retention.RetentionError, match="stop_installation_services"):
                retention.require_maintenance()
        finally:
            other.close()


def test_audit_checkpoint_accepts_append_and_detects_row_and_checkpoint_changes(private_world, tmp_path):
    key = bytes(range(32))
    path = tmp_path / "audit.json"
    key_file = tmp_path / "operator.key"
    key_file.write_text(key.hex())
    key_file.chmod(0o600)
    scope = "synthetic-installation"
    event = AuthenticationEvent.objects.create(
        authority_source="fixture", event_type="fixture", outcome="completed",
        details={"sensitive": "payload-only-in-database"},
    )

    if connection.vendor == "postgresql":
        args = ["--scope", scope, "--key-file", str(key_file), "--checkpoint", str(path)]

        def seal():
            return command("seal-audit", *args)

        def verify():
            return command("verify-audit", *args)
    else:
        def seal():
            return audit_checkpoint.seal(key, scope, path)

        def verify():
            return audit_checkpoint.verify(key, scope, path)

    receipt = seal()
    data = path.read_bytes()
    assert b"payload-only-in-database" not in data
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        audit_checkpoint.seal(key, scope, path)
    AuthenticationEvent.objects.create(authority_source="fixture", event_type="append", outcome="completed")
    verified = verify()
    assert verified["verified_rows"] == receipt["captured_rows"] and verified["additional_rows"] == 1
    assert verified["checkpoint_sha256"] == receipt["checkpoint_sha256"]
    for bad_key, bad_scope in ((b"a" * 32, scope), (key, "other")):
        with pytest.raises(ValueError, match="checkpoint_invalid"):
            audit_checkpoint.verify(bad_key, bad_scope, path)
    path.write_bytes(data.replace(b"synthetic-installation", b"altered-installation"))
    with pytest.raises(ValueError, match="checkpoint_invalid"):
        audit_checkpoint.verify(key, scope, path)
    path.write_bytes(data)
    AuthenticationEvent.objects.filter(pk=event.pk).update(details={})
    with pytest.raises(ValueError, match="changed_or_missing"):
        audit_checkpoint.verify(key, scope, path)
    event.delete()
    with pytest.raises(ValueError, match="changed_or_missing"):
        audit_checkpoint.verify(key, scope, path)


def test_runtime_log_boundary_discards_raw_descriptors():
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if not scripts.exists():
        scripts = Path("/app/scripts")  # The native runner imports tests from its mounted source.
    program = """
import sys
from private_service import _exec
_exec(sys.executable, [sys.executable, "-c", "import os; os.write(1,b'raw-data'); os.write(2,b'raw-error')"], True)
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=scripts, capture_output=True, timeout=10)
    assert result.returncode == 0 and result.stdout == result.stderr == b""
