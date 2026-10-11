"""Untrusted installation declarations and exact local ingress build boundary."""

import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def package(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return importlib.import_module("private_ingress_package")


@pytest.mark.parametrize("value", [
    "", "localhost", "https://api.customer.test", "API.customer.test", "api.customer.test/path",
    "api.customer.test;include /private;", "api.customer.test\nserver {}", "api.customer.test$host",
    "*.customer.test", "-api.customer.test", "api..customer.test", "api.customer-.test",
    "api.customer.test:0", "api.customer.test:65536", "api.customer.test:0443",
    "api.customer.test:443:80", "api.customer.test:", "[::1]:8443", None,
    "a" * 64 + ".customer.test",
])
def test_untrusted_authority_cannot_select_routes_or_inject_configuration(package, value):
    with pytest.raises(package.IngressError, match="authority_invalid"):
        package.configuration(value)


@pytest.mark.parametrize("value", [0, 65, -1, True, "50", None])
def test_body_budget_requires_bounded_explicit_integer(package, value):
    with pytest.raises(package.IngressError, match="body_limit_invalid"):
        package.configuration("api.customer.test", value)


def test_canonical_authority_preserves_public_tls_port(package):
    assert package.authority("api.customer.test") == ("api.customer.test", 443)
    assert package.authority("api.customer.test:8443") == ("api.customer.test", 8443)
    standard = package.configuration("api.customer.test:443")
    alternate = package.configuration("api.customer.test:8443")
    assert "proxy_set_header Host api.customer.test;" in standard
    assert "proxy_set_header Host api.customer.test:8443;" in alternate


def test_generated_context_is_immutable_and_contains_no_installation_state(package, tmp_path):
    root = tmp_path / "repo"
    (root / "docker").mkdir(parents=True)
    for name in ["private-ingress.Dockerfile", "private-ingress-entrypoint.sh"]:
        (root / "docker" / name).write_text("fixed runtime")
    (root / "docker/tls.key").write_text("PRIVATE_SENTINEL")
    (root / ".env").write_text("PRIVATE_SENTINEL")
    destination = tmp_path / "context"
    receipt = package.context(destination, "api.customer.test", root=root)
    assert set(p.name for p in destination.iterdir()) == {"Dockerfile", "start-ingress.sh", "nginx.conf", "source-manifest.json", "frontend"}
    assert all("PRIVATE_SENTINEL" not in p.read_text() for p in destination.iterdir() if p.is_file())
    assert set(receipt["source_sha256"]) == {"Dockerfile", "start-ingress.sh", "nginx.conf"}
    with pytest.raises(package.IngressError, match="destination_exists"):
        package.context(destination, "api.customer.test", root=root)
    source = root / "docker/private-ingress-entrypoint.sh"
    source.unlink();source.symlink_to(root / ".env")
    with pytest.raises(package.IngressError, match="source_invalid"):
        package.context(tmp_path / "rejected", "api.customer.test", root=root)
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("base,tag", [
    ("nginx:latest", "declarai-private-ingress:owned"),
    ("sha256:" + "a" * 64, "nginx:customer"),
    ("sha256:" + "a" * 64, "declarai-private-ingress:owned;evil"),
])
def test_build_rejects_mutable_base_and_foreign_tag_before_docker(package, monkeypatch, base, tag):
    def unexpected(*args, **kwargs):
        raise AssertionError("Untrusted build reached Docker")
    monkeypatch.setattr(package.subprocess, "run", unexpected)
    with pytest.raises(package.IngressError):
        package.build(base, tag, "api.customer.test")


@pytest.mark.parametrize("fault", ["tag_exists", "wrong_identity", "wrong_os", "wrong_version", "build_failure"])
def test_build_blocks_unqualified_input_and_releases_only_owned_base_tag(package, monkeypatch, fault):
    base = "sha256:" + "a" * 64
    tag = "declarai-private-ingress:owned"
    commands = []
    monkeypatch.setattr(package.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0 if fault == "tag_exists" else 1))

    def run(argv, **kwargs):
        commands.append(argv)
        if "inspect" in argv:
            return json.dumps([{"Id": "sha256:" + "b" * 64 if fault == "wrong_identity" else base,
                                "Os": "windows" if fault == "wrong_os" else "linux"}]).encode()
        if "run" in argv:
            return ("nginx version: nginx/0.0.0" if fault == "wrong_version" else "nginx version: nginx/" + package.VERSION).encode()
        if "build" in argv:
            raise package.IngressError("private_ingress_command_failed")
        return b""

    monkeypatch.setattr(package, "run", run)
    with pytest.raises(package.IngressError):
        package.build(base, tag, "api.customer.test")
    removed = [argv for argv in commands if argv[:3] == ["docker", "image", "rm"]]
    if fault == "build_failure":
        assert len(removed) == 1 and removed[0][3].startswith("declarai-ingress-base:")
        assert removed[0][3] not in (base, tag)
        assert "--network=none" in next(argv for argv in commands if "build" in argv)
    else:
        assert not removed


def test_docker_failure_is_neutral_and_retains_no_command_output(package, monkeypatch):
    monkeypatch.setattr(package.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b"PRIVATE_SENTINEL", stderr=b"PRIVATE_SENTINEL"))
    with pytest.raises(package.IngressError) as error:
        package.run(["docker", "inspect", "owned"])
    assert "PRIVATE_SENTINEL" not in str(error.value)
