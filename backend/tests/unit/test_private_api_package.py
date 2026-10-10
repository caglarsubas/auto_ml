"""Private packaging trust, allocation and startup boundaries; no live Docker."""

import hashlib
import importlib
import io
import json
import os
import stat
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.unit
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return tuple(
        importlib.import_module(name) for name in ("private_api_package", "private_runtime_manifest", "private_service")
    )


@pytest.mark.parametrize(
    "name,allowed",
    [
        ("backend/modeling/views.py", True),
        ("backend/modeling/migrations/0001_initial.py", True),
        ("backend/manage.py", True),
        ("backend/ai_assistant/skills/feature-engineering/SKILL.md", True),
        ("docs/knowledge-bank/model-governance-review-checklist.md", True),
        ("backend/db_backup_20240922.sqlite3", False),
        ("backend/media/data_files/customer.csv", False),
        ("backend/.chroma/index.json", False),
        ("backend/.env", False),
        ("backend/tests/unit/test_modeling.py", False),
        ("backend/modeling/tests.py", False),
        ("backend/modeling/model.pkl", False),
        ("backend/modeling/../../private.py", False),
        ("/backend/modeling/views.py", False),
        ("backend//modeling/views.py", False),
        ("backend/unknown_extension/plugin.py", False),
    ],
)
def test_source_allowlist_excludes_even_tracked_installation_state(modules, name, allowed):
    package, _, _ = modules
    assert package.allowed_source(name) is allowed


def test_context_copies_captured_source_only_and_rejects_symlinks(modules, monkeypatch, tmp_path):
    package, _, _ = modules
    root = tmp_path / "repo"
    root.mkdir()
    names = sorted(
        package.RUNTIME_FILES
        | {
            "backend/manage.py",
            "backend/modeling/views.py",
            "backend/media/customer.csv",
            "backend/db_backup.sqlite3",
            ".env",
        }
    )
    for name in names + [
        "docker/private-api.requirements.lock",
        "docker/private-api.Dockerfile",
        "docker/private-dependencies.Dockerfile",
    ]:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("accepted source" if package.allowed_source(name) else "PRIVATE_SENTINEL")

    def run(argv, **kwargs):
        return ("\0".join(names) + "\0").encode() if "ls-files" in argv else b"a" * 40

    monkeypatch.setattr(package, "run", run)
    target = tmp_path / "context"
    result = package.context(target, root)
    assert set(result["source_sha256"]) == set(n for n in names if package.allowed_source(n))
    assert not (target / "app/backend/media").exists()
    assert not (target / "app/backend/db_backup.sqlite3").exists()
    assert not (target / "app/.env").exists()
    with pytest.raises(package.PackageError, match="destination_exists"):
        package.context(target, root)
    path = root / "backend/modeling/views.py"
    path.unlink()
    path.symlink_to(root / ".env")
    with pytest.raises(package.PackageError, match="source_symlink"):
        package.context(tmp_path / "symlink-context", root)
    assert not (tmp_path / "symlink-context").exists()


@pytest.fixture
def runtime(modules, monkeypatch, tmp_path):
    _, inventory, _ = modules
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "application.py").write_text("approved native source")
    monkeypatch.setattr(
        inventory.importlib.metadata,
        "distributions",
        lambda: [SimpleNamespace(metadata={"Name": "gunicorn"}, version=inventory.GUNICORN_VERSION)],
    )
    monkeypatch.setattr(inventory.importlib.metadata, "version", lambda name: inventory.GUNICORN_VERSION)
    value = inventory.snapshot(root)
    (root / "runtime-manifest.json").write_text(json.dumps(value))
    return root, value


@pytest.mark.parametrize(
    "fault", ["source", "extra", "missing", "symlink", "version", "platform", "invalid_json", "oversized"]
)
def test_runtime_verification_rejects_changed_native_installation(modules, runtime, monkeypatch, fault):
    _, inventory, _ = modules
    root, value = runtime
    assert inventory.verify(root) == value
    if fault == "source":
        (root / "application.py").write_text("altered")
    elif fault == "extra":
        (root / "unexpected.csv").write_text("data must not be in source")
    elif fault == "missing":
        (root / "application.py").unlink()
    elif fault == "symlink":
        (root / "alias.py").symlink_to(root / "application.py")
    elif fault == "version":
        monkeypatch.setattr(inventory.importlib.metadata, "version", lambda name: "unqualified")
    elif fault == "platform":
        monkeypatch.setattr(inventory.platform, "machine", lambda: "unqualified")
    elif fault == "invalid_json":
        (root / "runtime-manifest.json").write_text("{")
    else:
        monkeypatch.setattr(inventory, "LIMIT", 10)
    with pytest.raises(inventory.ManifestError):
        inventory.verify(root)


def write_archive(path, *, tags=None, extra=None, config_override=None, layer_missing=False):
    config = b'{"architecture":"arm64","os":"linux"}'
    image_id = "sha256:" + hashlib.sha256(config).hexdigest()
    name = "blobs/sha256/" + image_id[7:]
    manifest = [{"Config": name, "RepoTags": tags, "Layers": ["layer.tar"]}]
    files = {
        "manifest.json": json.dumps(manifest).encode(),
        name: config if config_override is None else config_override,
    }
    if not layer_missing:
        files["layer.tar"] = b"synthetic layer bytes, never imported by unit tests"
    if extra:
        files.update(extra)
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as archive:
        for name, value in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))
    return image_id


@pytest.mark.parametrize(
    "fault",
    [
        "tags",
        "extra_index",
        "traversal",
        "config",
        "missing_layer",
        "truncated",
        "checksum",
        "extension",
        "metadata_budget",
    ],
)
def test_archive_rejects_ambiguous_image_graphs_before_import(modules, tmp_path, monkeypatch, fault):
    package, _, _ = modules
    file = tmp_path / "image.tar"
    kwargs = {}
    if fault == "tags":
        kwargs["tags"] = ["unrelated:current"]
    if fault == "extra_index":
        kwargs["extra"] = {"index.json": b"unrelated OCI image"}
    if fault == "traversal":
        kwargs["extra"] = {"../unrelated": b"escape"}
    if fault == "config":
        kwargs["config_override"] = b"altered configuration"
    if fault == "missing_layer":
        kwargs["layer_missing"] = True
    image = write_archive(file, **kwargs)
    if fault == "truncated":
        file.write_bytes(file.read_bytes()[:700])
    if fault == "checksum":
        value = bytearray(file.read_bytes())
        value[0] ^= 1
        file.write_bytes(value)
    if fault == "extension":
        info = tarfile.TarInfo("oversized-extension")
        info.type = tarfile.XHDTYPE
        info.size = 4 * 1024**3
        file.write_bytes(info.tobuf(format=tarfile.USTAR_FORMAT))
    if fault == "metadata_budget":
        monkeypatch.setattr(package, "MAX_METADATA_BYTES", 10)
    with pytest.raises(package.PackageError):
        package.verify_archive(file, image)


@pytest.fixture
def handoff(modules, tmp_path):
    package, _, _ = modules
    directory = tmp_path / "package"
    directory.mkdir()
    image = write_archive(directory / "image.tar")
    value = {
        "schema": "private_api_package_v1",
        "image_id": image,
        "os": "linux",
        "architecture": "arm64",
        "variant": "v8",
        "archive": {
            "file": "image.tar",
            "bytes": (directory / "image.tar").stat().st_size,
            "sha256": package.sha(directory / "image.tar"),
        },
        "runtime": {
            "schema": "private_native_runtime_v1",
            "python": "3.12.15",
            "implementation": "CPython",
            "system": "Linux",
            "machine": "aarch64",
            "packages": [{"name": "gunicorn", "version": "26.2.0"}],
            "source_sha256": {"backend/manage.py": "a" * 64},
        },
        "scope": "native_api_worker_dispatcher_image_only",
        "release_qualified": False,
        "expert_isolation_qualified": False,
    }
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(value))
    return directory, value, package.sha(manifest)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_digest",
        "altered_manifest",
        "altered_archive",
        "extra_file",
        "symlink",
        "oversized",
        "noninteger_size",
        "missing_inventory",
        "claimed_release",
        "bad_source",
        "wrong_inventory_platform",
    ],
)
def test_package_verification_never_calls_docker_for_invalid_handoff(modules, handoff, monkeypatch, fault):
    package, _, _ = modules
    directory, value, expected = handoff
    run = Mock(side_effect=AssertionError("Docker must not run before trust checks"))
    monkeypatch.setattr(package, "run", run)
    assert package.verify_package(directory, expected) == value
    if fault == "missing_digest":
        expected = ""
    elif fault == "altered_manifest":
        (directory / "manifest.json").write_text("{}")
    elif fault == "altered_archive":
        (directory / "image.tar").write_bytes(b"altered")
    elif fault == "extra_file":
        (directory / "other-image.tar").write_bytes(b"altered")
    elif fault == "symlink":
        saved = directory.parent / "saved.tar"
        (directory / "image.tar").rename(saved)
        (directory / "image.tar").symlink_to(saved)
    elif fault == "oversized":
        monkeypatch.setattr(package, "MAX_IMAGE_BYTES", 10)
    elif fault == "noninteger_size":
        value["archive"]["bytes"] = True
    elif fault == "missing_inventory":
        value.pop("runtime")
    elif fault == "claimed_release":
        value["release_qualified"] = True
    elif fault == "bad_source":
        value["runtime"]["source_sha256"] = {"../../private": "a" * 64}
    else:
        value["runtime"]["machine"] = "x86_64"
    if fault in ("noninteger_size", "missing_inventory", "claimed_release", "bad_source", "wrong_inventory_platform"):
        (directory / "manifest.json").write_text(json.dumps(value))
        expected = package.sha(directory / "manifest.json")
    with pytest.raises((package.PackageError, OSError)):
        package.load(directory, expected)
    run.assert_not_called()


def test_load_imports_verified_private_snapshot_even_if_original_path_changes(modules, handoff, monkeypatch):
    package, _, _ = modules
    directory, value, expected = handoff
    original = (directory / "image.tar").read_bytes()
    verify = package.verify_package

    def verified(stage, digest):
        result = verify(stage, digest)
        (directory / "image.tar").write_bytes(b"external path changed after verification")
        return result

    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["docker", "info"]:
            return b"linux aarch64"
        assert argv[:3] == ["docker", "image", "load"]
        staged = Path(argv[-1])
        assert staged.parent != directory and staged.read_bytes() == original
        return b""

    monkeypatch.setattr(package, "verify_package", verified)
    monkeypatch.setattr(package, "run", run)
    monkeypatch.setattr(
        package, "inspect_image", lambda image: {"Id": image, "Os": "linux", "Architecture": "arm64", "Variant": "v8"}
    )
    monkeypatch.setattr(package, "native_manifest", lambda image: value["runtime"])
    assert package.load(directory, expected)["offline_image_verified"] is True
    assert len(calls) == 2
    assert not Path(calls[1][-1]).exists()


def test_load_rejects_cross_architecture_before_import(modules, handoff, monkeypatch):
    package, _, _ = modules
    directory, value, expected = handoff
    command = Mock(return_value=b"linux x86_64")
    monkeypatch.setattr(package, "run", command)
    with pytest.raises(package.PackageError, match="native_platform_required"):
        package.load(directory, expected)
    assert command.call_count == 1 and command.call_args.args[0][:2] == ["docker", "info"]


@pytest.mark.parametrize(
    "fault", ["role", "profile", "uid", "override", "settings", "ingress", "manifest", "preflight"]
)
def test_private_launcher_blocks_before_server_execution(modules, monkeypatch, fault):
    _, inventory, service = modules
    monkeypatch.setenv("DECLARAI_RUNTIME_PROFILE", "private")
    monkeypatch.setenv("DJANGO_TRUST_PROXY_TLS", "true")
    for name in (
        "GUNICORN_CMD_ARGS",
        "FORWARDED_ALLOW_IPS",
        "PYTHONPATH",
        "PYTHONHOME",
        "PROMETA_SKILLS_DIR",
        "DJANGO_SETTINGS_MODULE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service.os, "geteuid", lambda: 10001)
    monkeypatch.setattr(service.os, "getegid", lambda: 10001)
    verification = Mock(return_value={})
    check = Mock(return_value=SimpleNamespace(returncode=0))
    execute = Mock(side_effect=AssertionError("Server must not execute"))
    monkeypatch.setattr(service, "verify", verification)
    monkeypatch.setattr(service.subprocess, "run", check)
    monkeypatch.setattr(service.os, "execv", execute)
    monkeypatch.setattr(service.os, "chdir", lambda path: None)
    args = ["api"]
    if fault == "role":
        args = ["api", "--workers=999"]
    elif fault == "profile":
        monkeypatch.setenv("DECLARAI_RUNTIME_PROFILE", "development")
    elif fault == "uid":
        monkeypatch.setattr(service.os, "geteuid", lambda: 0)
    elif fault == "override":
        monkeypatch.setenv("GUNICORN_CMD_ARGS", "--bind=0.0.0.0:8001")
    elif fault == "settings":
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "other.settings")
    elif fault == "ingress":
        monkeypatch.setenv("DJANGO_TRUST_PROXY_TLS", "false")
    elif fault == "manifest":
        verification.side_effect = inventory.ManifestError("runtime_manifest_mismatch")
    else:
        check.return_value.returncode = 1
    with pytest.raises(inventory.ManifestError):
        service.launch(args)
    execute.assert_not_called()
    if fault not in ("manifest", "preflight"):
        verification.assert_not_called()
    if fault != "preflight":
        check.assert_not_called()


def test_native_server_config_has_no_untrusted_forwarder_or_control_socket(modules):
    namespace = {}
    exec((SCRIPTS.parent / "docker/private-gunicorn.py").read_text(), namespace)
    assert namespace["bind"] == "unix:/run/declarai/api.sock"
    assert namespace["workers"] == 1 and namespace["worker_class"] == "sync"
    assert namespace["max_requests"] == 0
    assert namespace["control_socket_disable"] is True
    assert namespace["reload"] is False and namespace["proxy_protocol"] is False
    assert namespace["secure_scheme_headers"] == {} and namespace["forwarder_headers"] == []
    assert namespace["umask"] == 0o007 and namespace["accesslog"] is None


@pytest.mark.parametrize(
    "base,tag",
    [
        ("declarai-core:latest", "declarai-private-api:owned"),
        ("sha256:" + "a" * 64, "unrelated:latest"),
        ("sha256:" + "a" * 64 + "\n", "declarai-private-api:owned"),
    ],
)
def test_build_requires_exact_dependency_digest_and_owned_tag(modules, monkeypatch, base, tag):
    package, _, _ = modules
    docker = Mock(side_effect=AssertionError("No Docker mutation before argument checks"))
    monkeypatch.setattr(package, "run", docker)
    with pytest.raises(package.PackageError):
        package.build(base, tag)
    docker.assert_not_called()


def test_normalization_drops_oci_index_and_exports_only_one_tag_free_graph(modules, tmp_path):
    package, _, _ = modules
    source, target = tmp_path / "trusted-save.tar", tmp_path / "package.tar"
    image = write_archive(source, extra={"index.json": b"potential alternate graph", "oci-layout": b"metadata"})
    package.normalize_save(source, target)
    package.verify_archive(target, image)
    with tarfile.open(target) as archive:
        assert len(archive.getnames()) == 3
        assert "index.json" not in archive.getnames()
