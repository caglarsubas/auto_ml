"""Bound dependency preparation, input semantics and no-replace publication."""

import importlib
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401
from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_check import checker, saved_plan  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def dependency(planner):
    return importlib.import_module("private_dependency_init")


@pytest.fixture
def app():
    return {
        "app/app-password": b"App-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789",
        "app/job-broker-url": b"rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/1",
        "app/postgres-ca.crt": b"approved-postgres-ca",
        "app/job-ca.crt": b"approved-broker-ca",
    }


def test_fixed_profile_is_nonsecret_and_bound_to_exact_versions(dependency, saved_plan):
    plan, expected = saved_plan
    value = dependency.checker.verify(plan, expected)
    p = dependency.profile(value, expected, "a" * 32)
    assert p["plan_manifest_sha256"] == expected and p["initialization_id"] == "a" * 32
    assert p["services"]["postgres"]["image_id"] == value["images"]["postgres"]
    assert (p["services"]["postgres"]["uid"], p["services"]["postgres"]["gid"]) == (70, 70)
    assert (p["services"]["job-broker"]["uid"], p["services"]["job-broker"]["gid"]) == (999, 1000)
    assert p["services"]["cache"]["data"] is None and all(
        s["public_ports"] is False and s["read_only_root"] is True and s["capabilities"] == []
        for s in p["services"].values()
    )
    assert all(p[k] is False for k in ["installation_qualified", "release_qualified", "expert_isolation_qualified"])


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"weak",
        b"a" * 64,
        b"Invalid\x00Password-0123456789abcdefghijklmnopqrstuvwxyz",
        b"Invalid\nPassword-0123456789abcdefghijklmnopqrstuvwxyz",
        b"Invalid\tPassword-0123456789abcdefghijklmnopqrstuvwxyz",
        b"Invalid\x7fPassword-0123456789abcdefghijklmnopqrstuvwxyz",
        b"\xff" * 64,
    ],
)
def test_weak_control_or_undecodable_passwords_cannot_initialize(dependency, bad):
    with pytest.raises(dependency.checker.planner.PlanError, match="password_invalid"):
        dependency.password(bad)


@pytest.mark.parametrize("suffix", [b"", b"\n", b"\r\n"])
def test_single_delivered_password_matches_runtime_newline_semantics(dependency, suffix):
    value = "Valid-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789"
    assert dependency.password(value.encode() + suffix) == value


@pytest.mark.parametrize(
    "bad",
    [
        "redis://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/1",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@external:6379/1",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6380/1",
        "rediss://user:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/1",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/16",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/01",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/1?ssl_cert_reqs=none",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789@job-broker:6379/1#ignored",
        "rediss://:Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789%xx@job-broker:6379/1",
    ],
)
def test_unsupported_broker_transport_endpoint_or_database_is_not_rewritten(dependency, bad):
    with pytest.raises(dependency.checker.planner.PlanError, match="broker_url_invalid"):
        dependency.broker_password(bad.encode())


@pytest.mark.parametrize("database", [0, 1, 15])
def test_supported_broker_database_remains_explicit(dependency, app, database):
    value = app["app/job-broker-url"].replace(b"/1", ("/" + str(database)).encode())
    assert dependency.broker_password(value) == "Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789"


def test_percent_encoded_credentials_are_escaped_without_config_injection(dependency, saved_plan, app):
    plan, expected = saved_plan
    secret = 'Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789"\\#'
    app["app/job-broker-url"] = ("rediss://:" + quote(secret, safe="") + "@job-broker:6379/1").encode()
    configs = dependency.configurations(dependency.checker.verify(plan, expected), app)
    broker = configs["job-broker/redis.conf"].decode()
    assert 'requirepass "Broker-Password-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789\\"\\\\#"\n' in broker
    assert (
        "port 0\n" in broker
        and "appendonly yes\n" in broker
        and "appendfsync everysec\n" in broker
        and "noeviction\n" in broker
    )


def test_postgres_remote_owner_and_cleartext_access_are_rejected(dependency, saved_plan, app):
    plan, expected = saved_plan
    value = dependency.checker.verify(plan, expected)
    configs = dependency.configurations(value, app)
    db = value["request"]["database"]
    hba = configs["postgres/pg_hba.conf"].decode().splitlines()
    assert hba == [
        "local all postgres peer",
        "local all all reject",
        'hostssl "' + db["name"] + '" "' + db["user"] + '" 0.0.0.0/0 scram-sha-256',
        "host all all 0.0.0.0/0 reject",
        "host all all ::/0 reject",
    ]
    assert (
        "appendonly no\n" in configs["cache/redis.conf"].decode()
        and "allkeys-lru\n" in configs["cache/redis.conf"].decode()
    )


@pytest.mark.parametrize("name,user", [("all", "all"), ("replication", "sameuser"), ("sameuser", "replication")])
def test_hba_reserved_tokens_are_literal_names_not_wildcards(dependency, saved_plan, app, name, user):
    plan, expected = saved_plan
    value = dependency.checker.verify(plan, expected)
    value["request"]["database"] = {"name": name, "user": user}
    config = dependency.configurations(value, app)["postgres/pg_hba.conf"].decode()
    assert 'hostssl "' + name + '" "' + user + '" 0.0.0.0/0 scram-sha-256\n' in config


@pytest.mark.parametrize("source", [Path("relative"), Path("/srv/../delivery")])
def test_delivery_path_requires_exact_absolute_ancestors(dependency, source):
    with pytest.raises(dependency.checker.planner.PlanError, match="delivery_path_invalid"):
        dependency.capture(source, dependency.DELIVERY)


def test_untrusted_plan_never_reads_dependency_or_secret_paths(dependency, saved_plan, monkeypatch, tmp_path):
    plan, expected = saved_plan
    (plan / "compose.json").write_text("tampered")
    monkeypatch.setattr(dependency.resources, "initialization", lambda *a: pytest.fail("untrusted plan read host"))
    with pytest.raises(dependency.checker.planner.PlanError, match="digest_mismatch"):
        dependency.initialize(plan, expected, tmp_path)


def test_existing_dependency_root_blocks_before_any_secret_capture(dependency, saved_plan, monkeypatch, tmp_path):
    plan, expected = saved_plan
    monkeypatch.setattr(dependency.sys, "platform", "linux")
    monkeypatch.setattr(dependency.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        dependency.resources,
        "initialization",
        lambda *a: {"initialization_id": "a" * 32, "plan_manifest_sha256": expected},
    )
    monkeypatch.setattr(dependency.checker, "check_paths", lambda *a: None)
    monkeypatch.setattr(dependency.initializer, "trusted_directory", lambda *a: 99)
    monkeypatch.setattr(dependency.os, "close", lambda *a: None)
    monkeypatch.setattr(dependency, "capture", lambda *a: pytest.fail("existing destination read secrets"))

    def occupied(*a):
        raise dependency.checker.planner.PlanError("installation_init_destination_exists")

    monkeypatch.setattr(dependency.initializer, "absent", occupied)
    with pytest.raises(dependency.checker.planner.PlanError, match="destination_exists"):
        dependency.initialize(plan, expected, tmp_path)


@pytest.mark.parametrize("failure", ["verify", "encrypted", "pair", "unavailable", "budget"])
def test_certificate_failures_never_publish_or_expose_private_bytes(dependency, app, monkeypatch, failure):
    calls = []
    delivered = {
        role + "/" + name: b"synthetic-key" if name.endswith("key") else b"synthetic-cert"
        for role in dependency.DELIVERY
        for name in dependency.DELIVERY[role]
        if name != "owner-password"
    }

    def openssl(argv, **kw):
        calls.append((argv, kw))
        if failure == "unavailable":
            raise OSError("synthetic-key")
        if failure == "verify" or failure == "encrypted" and "pkey" in argv:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"synthetic-key")
        if failure == "budget":
            return SimpleNamespace(returncode=0, stdout=b"x" * 65537, stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"other-public" if "pkey" in argv else b"public", stderr=b"")

    monkeypatch.setattr(dependency.subprocess, "run", openssl)
    with pytest.raises(dependency.checker.planner.PlanError) as error:
        dependency.certificates(delivered, app)
    assert "synthetic-key" not in str(error.value)
    assert calls[0][0][0] == "/usr/bin/openssl" and "-no-CApath" in calls[0][0] and "-no-CAstore" in calls[0][0]
    assert calls[0][1]["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def test_exact_selected_ca_hostnames_and_key_pairs_are_checked(dependency, app, monkeypatch):
    calls = []
    delivered = {
        role + "/" + name: b"synthetic-key" if name.endswith("key") else b"synthetic-cert"
        for role in dependency.DELIVERY
        for name in dependency.DELIVERY[role]
        if name != "owner-password"
    }

    def openssl(argv, **kw):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"same-public-key", stderr=b"")

    monkeypatch.setattr(dependency.subprocess, "run", openssl)
    dependency.certificates(delivered, app)
    verify = [args for args in calls if "verify" in args]
    assert [args[args.index("-verify_hostname") + 1] for args in verify] == ["postgres", "job-broker"]
    assert len(calls) == 6 and all("-CAfile" in args and "-purpose" in args for args in verify)
