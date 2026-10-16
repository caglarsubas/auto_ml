"""File delimiters must not silently rewrite decoded Redis credentials."""

import os
from urllib.parse import quote

import pytest

from tests.unit.test_private_dependency_init import (  # noqa: F401
    app, dependency, planner, compatible, request_value, checker, saved_plan, handoff, image_set,
)

pytestmark = pytest.mark.unit
SECRET = "Synthetic-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789"
SERVICES = [("job-broker", 1, "app/job-broker-url"), ("cache", 0, "app/cache-url")]


def url(host, database, password):
    return ("rediss://:" + quote(password, safe="") + "@" + host + ":6379/" + str(database)).encode()


@pytest.mark.parametrize("host,database,key", SERVICES)
@pytest.mark.parametrize("control", ["\n", "\r", "\r\n"])
def test_decoded_credential_controls_cannot_be_trimmed(dependency, host, database, key, control):
    with pytest.raises(dependency.checker.planner.PlanError, match="^dependency_password_invalid$"):
        dependency.broker_password(url(host, database, SECRET + control), host, database)


@pytest.mark.parametrize("host,database,key", SERVICES)
@pytest.mark.parametrize("control", ["\n", "\r", "\r\n"])
def test_configuration_rejects_controls_in_either_service(dependency, app, saved_plan, host, database, key, control):
    value = dependency.checker.verify(*saved_plan)
    app[key] = url(host, database, SECRET + control)
    with pytest.raises(dependency.checker.planner.PlanError, match="^dependency_password_invalid$") as error:
        dependency.configurations(value, app)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("host,database,key", SERVICES)
@pytest.mark.parametrize("control", ["\n", "\r", "\r\n"])
def test_fresh_initialization_blocks_before_certificates_or_staging(
    dependency, app, saved_plan, monkeypatch, tmp_path, host, database, key, control,
):
    plan, expected = saved_plan
    value = dependency.checker.verify(plan, expected)
    root = tmp_path / "owned-root"
    root.mkdir()
    app[key] = url(host, database, SECRET + control)
    delivered = {"postgres/owner-password": SECRET.encode()}
    monkeypatch.setattr(dependency.sys, "platform", "linux")
    monkeypatch.setattr(dependency.os, "geteuid", lambda: 0)
    monkeypatch.setattr(dependency.resources, "initialization", lambda *args: {
        "plan_manifest_sha256": expected, "initialization_id": "a" * 32,
    })
    monkeypatch.setattr(dependency.checker, "check_paths", lambda *args: None)
    monkeypatch.setattr(dependency.initializer, "trusted_directory", lambda *args: os.open(root, os.O_RDONLY))
    monkeypatch.setattr(dependency, "capture", lambda path, groups, *args:
                        app if groups == value["prerequisites"]["secret_files"] else delivered)

    def forbidden(*args):
        pytest.fail("invalid credential reached certificate handling or dependency staging")

    monkeypatch.setattr(dependency, "certificates", forbidden)
    with pytest.raises(dependency.checker.planner.PlanError, match="^dependency_password_invalid$"):
        dependency.initialize(plan, expected, tmp_path / "delivery")
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("host,database,key", SERVICES)
@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_url_file_delimiters_remain_supported(dependency, host, database, key, ending):
    assert dependency.broker_password(url(host, database, SECRET) + ending, host, database) == SECRET


@pytest.mark.parametrize("host,database,key", SERVICES)
@pytest.mark.parametrize("suffix", ["-unicode-é", '-reserved:/%"\\', "-space inside", "-literal%0A"])
def test_valid_credentials_are_decoded_once_and_preserved_exactly(dependency, app, saved_plan, host, database, key, suffix):
    password = SECRET + suffix
    app[key] = url(host, database, password)
    assert dependency.broker_password(app[key], host, database) == password
    configs = dependency.configurations(dependency.checker.verify(*saved_plan), app)
    escaped = password.replace("\\", "\\\\").replace('"', '\\"')
    assert ('requirepass "' + escaped + '"\n').encode() in configs[host + "/redis.conf"]
