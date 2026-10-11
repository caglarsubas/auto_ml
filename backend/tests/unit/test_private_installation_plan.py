"""Real offline package verification and safe application-layer plan boundaries."""

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def planner(image_set):
    return importlib.import_module("private_installation_plan")


@pytest.fixture
def request_value():
    return {"schema": "private_installation_request_v1", "installation_id": "pilot", "root": "/srv/declarai/pilot", "authority": "api.private.test:8443", "body_mib": 1, "bind_ip": "127.0.0.1", "database": {"name": "declarai", "user": "declarai_app"}}


def compatible(planner, handoff, request_value):
    root, _ = handoff
    path = root / "ingress/manifest.json"
    ingress = json.loads(path.read_bytes())
    files = ingress["runtime"]["files"]
    names = {n.removeprefix("/opt/declarai/frontend/") for n in files if n.startswith("/opt/declarai/frontend/")}
    files["/etc/nginx/nginx.conf"] = hashlib.sha256(planner.configuration(request_value["authority"], request_value["body_mib"], names).encode()).hexdigest()
    digest = planner.image_set.record_json(path, ingress)
    value = json.loads((root / "manifest.json").read_bytes())
    value["components"]["ingress"]["manifest_sha256"] = digest
    return root, planner.image_set.record_json(root / "manifest.json", value)


def test_real_set_renders_without_docker_secret_reads_or_installation_changes(planner, handoff, request_value, tmp_path, monkeypatch):
    root, expected = compatible(planner, handoff, request_value)
    request = tmp_path / "request.json"
    request.write_bytes(planner.encoded(request_value))
    destination = tmp_path / "plan"
    monkeypatch.setattr(planner.image_set.api, "run", lambda *a, **k: pytest.fail("offline plan must not call Docker"))
    result = planner.render(request, root, expected, destination)
    assert result["plan_manifest_sha256"] == planner.image_set.api.sha(destination / "manifest.json")
    manifest = json.loads((destination / "manifest.json").read_bytes())
    assert manifest["archive_verified_at_render"] and not manifest["installation_qualified"]
    assert manifest["image_set_manifest_sha256"] == expected
    assert set(destination.iterdir()) == {destination / n for n in planner.FILES | {"manifest.json"}}
    assert destination.stat().st_mode & 0o777 == 0o700
    for name, digest in manifest["files"].items():
        assert planner.image_set.api.sha(destination / name) == digest
        assert (destination / name).stat().st_mode & 0o777 == 0o600
    compose = json.loads((destination / "compose.json").read_bytes())
    assert compose["name"] == "declarai-pilot"
    assert set(compose["services"]) == {"api", "worker", "dispatcher", "ingress"}
    for role, service in compose["services"].items():
        assert service["image"] == result["images"]["ingress" if role == "ingress" else "api"]
        assert service["pull_policy"] == "never" and service["read_only"]
        assert service["user"] == "10001:10001" and service["cap_drop"] == ["ALL"]
        assert "entrypoint" not in service and "env_file" not in service and "build" not in service
        for mount in service["volumes"]:
            if mount["type"] == "bind":
                assert mount["bind"]["create_host_path"] is False
        if role != "ingress":
            assert "ports" not in service and service["command"] == [role]
            assert service["networks"] == ["private"]
            assert service["environment"]["DJANGO_SECRET_KEY_FILE"] == "/installation/django-key"
            assert service["environment"]["DECLARAI_ALLOWED_ORIGINS"] == "https://api.private.test:8443"
            assert service["environment"]["PROMETA_DISABLE"] == "1"
        else:
            assert "environment" not in service and service["networks"] == ["edge"]
            assert service["ports"] == [{"host_ip": "127.0.0.1", "protocol": "tcp", "published": "8443", "target": 8443}]
            assert all(mount["read_only"] for mount in service["volumes"])
    assert len(compose["services"]["worker"]["volumes"]) == len(compose["services"]["dispatcher"]["volumes"]) == 2
    assert all(v["external"] for v in compose["networks"].values())
    prereq = json.loads((destination / "prerequisites.json").read_bytes())
    assert all(v["internal"] for v in prereq["networks"])
    assert prereq["dependencies"]["postgres"]["image_id"] == result["images"]["postgres"]
    assert not prereq["dependencies"]["postgres"]["application_superuser"]
    assert prereq["directories"][2]["encrypted_storage_required"]


@pytest.mark.parametrize("key,value", [
    ("schema", "unknown"), ("installation_id", "../other"), ("installation_id", "x" * 33),
    ("root", "/"), ("root", "/srv/a/../b"), ("root", "/srv//a/b"), ("root", "/srv/a/b/"),
    ("root", "/etc/private/declarai"), ("root", "/srv/a/$(secret)"), ("root", "/srv/a/$HOME"),
    ("root", "/srv/a/a\nvalue"), ("root", "/srv/a/a b"), ("root", "/srv/a/.hidden"),
    ("authority", "https://api.private.test"), ("authority", "api.private.test:443"),
    ("authority", "API.private.test:8443"), ("authority", "api.private.test:8443/path"),
    ("body_mib", True), ("body_mib", 0), ("body_mib", 65),
    ("bind_ip", "0.0.0.0"), ("bind_ip", "8.8.8.8"), ("bind_ip", "::1"),
    ("bind_ip", "169.254.1.1"), ("bind_ip", "240.0.0.1"),
    ("database", {"name": "postgres", "user": "declarai_app"}),
    ("database", {"name": "declarai", "user": "postgres"}),
    ("database", {"name": "declarai", "user": "declarai_app", "password": "must never enter a plan"}),
    ("database", {"name": "declarai;DROP DATABASE", "user": "declarai_app"}),
    ("database", None), ("environment", {"GUNICORN_CMD_ARGS": "arbitrary override"}),
    ("command", ["python", "expert.py"]),
])
def test_invalid_or_unrecognized_request_is_rejected_before_package_or_output(planner, request_value, tmp_path, monkeypatch, key, value):
    request_value[key] = value
    file = tmp_path / "request.json"
    file.write_bytes(planner.encoded(request_value))
    monkeypatch.setattr(planner.image_set, "snapshot", lambda *a: pytest.fail("invalid request must fail before package copy"))
    with pytest.raises(planner.PlanError, match="request_invalid"):
        planner.render(file, tmp_path / "missing-set", "a" * 64, tmp_path / "plan")
    assert not (tmp_path / "plan").exists()


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "172.20.1.2", "192.168.1.2"])
def test_explicit_private_ipv4_bind_is_supported(planner, request_value, address):
    request_value["bind_ip"] = address
    assert planner.validate_request(request_value) == request_value


@pytest.mark.parametrize("fault", ["duplicate", "oversized", "link", "fifo", "malformed", "empty"])
def test_request_input_is_bounded_regular_unique_json(planner, tmp_path, fault):
    path = tmp_path / "request.json"
    if fault == "link":
        (tmp_path / "other").write_text("{}")
        path.symlink_to(tmp_path / "other")
    elif fault == "fifo":
        os.mkfifo(path)
    else:
        path.write_text({"duplicate": '{"schema":1,"schema":2}', "oversized": "x" * (planner.MAX_REQUEST + 1), "malformed": "{", "empty": ""}[fault])
    with pytest.raises((planner.PlanError, OSError)):
        planner.render(path, tmp_path / "missing-set", "a" * 64, tmp_path / "plan")


@pytest.mark.parametrize("fault", ["authority", "body", "last_archive", "outer_digest", "existing_directory", "existing_file", "destination_link"])
def test_mismatch_and_tampering_do_not_publish_or_overwrite(planner, handoff, request_value, tmp_path, fault):
    root, expected = compatible(planner, handoff, request_value)
    destination = tmp_path / "plan"
    if fault == "authority":
        request_value["authority"] = "other.private.test:8443"
    elif fault == "body":
        request_value["body_mib"] = 2
    elif fault == "last_archive":
        (root / "redis/image.tar").write_bytes(b"altered")
    elif fault == "outer_digest":
        expected = "0" * 64
    elif fault == "existing_directory":
        destination.mkdir()
    elif fault == "existing_file":
        destination.write_text("preserve")
    else:
        destination.symlink_to(tmp_path / "missing")
    request = tmp_path / "request.json"
    request.write_bytes(planner.encoded(request_value))
    with pytest.raises((planner.PlanError, planner.image_set.api.PackageError)):
        planner.render(request, root, expected, destination)
    if fault == "existing_directory":
        assert list(destination.iterdir()) == []
    elif fault == "existing_file":
        assert destination.read_text() == "preserve"
    elif fault == "destination_link":
        assert destination.is_symlink()
    else:
        assert not destination.exists()


def test_deterministic_configuration_and_fixed_prerequisite_layout(planner, request_value):
    images = {role: "sha256:" + str(index) * 64 for index, role in enumerate(planner.image_set.ROLES)}
    before = copy.deepcopy(request_value)
    assert planner.composition(request_value, images) == planner.composition(copy.deepcopy(request_value), images)
    assert request_value == before
    text = planner.encoded(planner.composition(request_value, images))
    assert b"$" not in text and b"DJANGO_SECRET_KEY\"" not in text and b"PASSWORD\"" not in text
