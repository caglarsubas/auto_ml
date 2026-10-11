"""Offline image-set trust and all-before-import boundaries, without live Docker."""

import hashlib
import importlib
import io
import json
import os
import shutil
import tarfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def image_set(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return importlib.import_module("private_image_set")


def archive(path, role, *, tags=None):
    config = json.dumps({"architecture": "arm64", "os": "linux", "role": role}).encode()
    image = "sha256:" + hashlib.sha256(config).hexdigest()
    name = image[7:] + ".json"
    files = {
        name: config,
        "layer.tar": b"synthetic layer, never imported",
        "manifest.json": json.dumps([{"Config": name, "RepoTags": tags, "Layers": ["layer.tar"]}]).encode(),
    }
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as output:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            output.addfile(item, io.BytesIO(data))
    return image


def inventory(module):
    files = {name: "a" * 64 for name in module.CONFIG}
    for name in {"index.html", "main.js", "3rdpartylicenses.txt", *module.LICENSES}:
        files["/opt/declarai/frontend/" + name] = "b" * 64
    return {"version": "nginx version: nginx/1.30.5", "files": files}


@pytest.fixture
def handoff(image_set, tmp_path):
    m = image_set
    root = tmp_path / "handoff"
    root.mkdir()
    components = {}
    for role in m.ROLES:
        directory = root / role
        directory.mkdir()
        image = archive(directory / "image.tar", role)
        value = {
            "image_id": image,
            "os": "linux",
            "architecture": "arm64",
            "variant": "",
            "archive": {
                "file": "image.tar",
                "bytes": (directory / "image.tar").stat().st_size,
                "sha256": m.api.sha(directory / "image.tar"),
            },
        }
        if role == "api":
            value.update(
                schema="private_api_package_v1",
                scope="native_api_worker_dispatcher_image_only",
                release_qualified=False,
                expert_isolation_qualified=False,
                runtime={
                    "schema": "private_native_runtime_v1",
                    "python": "3.12.15",
                    "implementation": "CPython",
                    "system": "Linux",
                    "machine": "aarch64",
                    "packages": [{"name": "gunicorn", "version": "26.2.0"}],
                    "source_sha256": {"backend/manage.py": "a" * 64},
                },
            )
        else:
            runtime = (
                inventory(m)
                if role == "ingress"
                else {
                    "version": "postgres (PostgreSQL) 17.11"
                    if role == "postgres"
                    else "Redis server v=7.4.8 sha=00000000:0 malloc=jemalloc bits=64"
                }
            )
            value.update(schema="private_component_image_v1", role=role, runtime=runtime)
        digest = m.record_json(directory / "manifest.json", value)
        components[role] = {"image_id": image, "manifest_sha256": digest}
    value = {
        "schema": "private_image_set_v1",
        "architecture": "arm64",
        "components": components,
        "scope": m.SCOPE,
        "installation_qualified": False,
        "release_qualified": False,
        "expert_isolation_qualified": False,
    }
    expected = m.record_json(root / "manifest.json", value)
    return root, expected


def change(module, root, role, mutate):
    path = root / role / "manifest.json" if role else root / "manifest.json"
    value = json.loads(path.read_text())
    mutate(value)
    digest = module.record_json(path, value)
    if role:
        top = json.loads((root / "manifest.json").read_text())
        top["components"][role]["manifest_sha256"] = digest
        digest = module.record_json(root / "manifest.json", top)
    return digest


def test_complete_set_verifies_without_docker_or_service_adoption(image_set, handoff, monkeypatch):
    root, expected = handoff
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("verification must not call Docker"))
    value = image_set.consume(root, expected)
    assert value["archive_verified"] and not value["loaded"] and not value["installation_qualified"]
    assert set(value["images"]) == set(image_set.ROLES)


@pytest.mark.parametrize("role", [None, "api", "ingress", "postgres", "redis"])
def test_changed_manifest_is_rejected_before_any_import(image_set, handoff, monkeypatch, role):
    root, expected = handoff
    path = root / role / "manifest.json" if role else root / "manifest.json"
    path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("must verify all components first"))
    with pytest.raises(image_set.api.PackageError, match="digest_mismatch"):
        image_set.consume(root, expected, load=True)


@pytest.mark.parametrize("role", ["api", "ingress", "postgres", "redis"])
def test_changed_archive_even_last_role_stops_before_first_import(image_set, handoff, monkeypatch, role):
    root, expected = handoff
    (root / role / "image.tar").write_bytes(b"changed")
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("no partial import of invalid set"))
    with pytest.raises(image_set.api.PackageError, match="archive_digest_mismatch"):
        image_set.consume(root, expected, load=True)


@pytest.mark.parametrize(
    "fault",
    [
        "extra_role",
        "missing_role",
        "extra_file",
        "root_link",
        "component_link",
        "manifest_link",
        "archive_link",
        "fifo",
        "extra_component_file",
    ],
)
def test_layout_and_nonregular_inputs_fail_without_reading_or_importing(
    image_set, handoff, tmp_path, monkeypatch, fault
):
    root, expected = handoff
    if fault == "extra_role":
        (root / "expert").mkdir()
    elif fault == "missing_role":
        shutil.rmtree(root / "redis")
    elif fault == "extra_file":
        (root / ".env").write_text("not a package input")
    elif fault == "root_link":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif fault == "component_link":
        (root / "redis").rename(tmp_path / "outside")
        (root / "redis").symlink_to(tmp_path / "outside", target_is_directory=True)
    elif fault in ["manifest_link", "archive_link", "fifo"]:
        path = root / "redis" / ("manifest.json" if fault == "manifest_link" else "image.tar")
        path.rename(tmp_path / "outside")
        if fault == "fifo":
            os.mkfifo(path)
        else:
            path.symlink_to(tmp_path / "outside")
    else:
        (root / "redis" / "extra.tar").write_bytes(b"extra")
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("invalid source must not call Docker"))
    with pytest.raises((image_set.api.PackageError, OSError)):
        image_set.consume(root, expected, load=True)


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "extra_key",
        "scope",
        "release_claim",
        "installation_claim",
        "expert_claim",
        "missing_role",
        "unknown_arch",
        "bad_pin",
        "pin_fields",
        "id_mismatch",
        "mixed_arch",
    ],
)
def test_semantically_invalid_trusted_manifest_remains_blocked(image_set, handoff, fault):
    root, expected = handoff
    edits = {
        "schema": lambda v: v.update(schema="other"),
        "extra_key": lambda v: v.update(command=["execute"]),
        "scope": lambda v: v.update(scope="installation"),
        "release_claim": lambda v: v.update(release_qualified=True),
        "installation_claim": lambda v: v.update(installation_qualified=True),
        "expert_claim": lambda v: v.update(expert_isolation_qualified=True),
        "missing_role": lambda v: v["components"].pop("redis"),
        "unknown_arch": lambda v: v.update(architecture="other"),
        "bad_pin": lambda v: v["components"]["redis"].update(image_id="redis:latest"),
        "pin_fields": lambda v: v["components"]["redis"].update(tag="redis:latest"),
        "id_mismatch": lambda v: v["components"]["redis"].update(image_id=v["components"]["postgres"]["image_id"]),
    }
    if fault == "mixed_arch":
        expected = change(image_set, root, "redis", lambda v: v.update(architecture="amd64"))
    else:
        expected = change(image_set, root, None, edits[fault])
    with pytest.raises(image_set.api.PackageError):
        image_set.consume(root, expected)


@pytest.mark.parametrize(
    "fault",
    ["version", "files", "missing_index", "missing_license", "extra_path", "hidden", "map", "reserved", "bad_hash"],
)
def test_ingress_inventory_requires_the_sealed_private_frontend(image_set, handoff, fault):
    root, expected = handoff

    def mutate(v):
        r = v["runtime"]
        if fault == "version":
            r["version"] = "nginx version: nginx/1.0.0"
        elif fault == "files":
            r["files"] = []
        elif fault in ["missing_index", "missing_license"]:
            name = "index.html" if fault == "missing_index" else "3rdpartylicenses.txt"
            r["files"].pop("/opt/declarai/frontend/" + name)
        elif fault == "bad_hash":
            r["files"]["/etc/nginx/nginx.conf"] = "invalid"
        else:
            name = {
                "extra_path": "/installation/tls.key",
                "hidden": "/opt/declarai/frontend/.env",
                "map": "/opt/declarai/frontend/main.js.map",
                "reserved": "/opt/declarai/frontend/media/run.js",
            }[fault]
            r["files"][name] = "a" * 64

    expected = change(image_set, root, "ingress", mutate)
    with pytest.raises(image_set.api.PackageError):
        image_set.consume(root, expected)


@pytest.mark.parametrize(
    "role,version",
    [
        ("postgres", "postgres (PostgreSQL) 16.9"),
        ("redis", "Redis server v=8.0.0 other"),
        ("redis", {"version": "malformed"}),
    ],
)
def test_unsupported_dependency_profile_is_explicit(image_set, handoff, role, version):
    root, expected = handoff
    expected = change(image_set, root, role, lambda v: v["runtime"].update(version=version))
    with pytest.raises(image_set.api.PackageError):
        image_set.consume(root, expected)


def test_wrong_engine_platform_stops_before_loading(image_set, handoff, monkeypatch):
    root, expected = handoff
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert args[1] == "info"
        return b"linux x86_64"

    monkeypatch.setattr(image_set.api, "run", run)
    with pytest.raises(image_set.api.PackageError, match="native_platform_required"):
        image_set.consume(root, expected, load=True)
    assert len(calls) == 1


def test_import_uses_frozen_bytes_after_original_source_is_replaced(image_set, handoff, tmp_path, monkeypatch):
    root, expected = handoff
    records = {role: json.loads((root / role / "manifest.json").read_text()) for role in image_set.ROLES}
    original = image_set.snapshot

    def snapshot(source, target):
        original(source, target)
        source.rename(tmp_path / "old-source")
        source.mkdir()
        (source / "manifest.json").write_text("altered source")

    monkeypatch.setattr(image_set, "snapshot", snapshot)
    loads = []

    def run(args, **kwargs):
        if args[1] == "info":
            return b"linux aarch64"
        assert args[:4] == ["docker", "image", "load", "--input"]
        path = Path(args[4])
        assert not path.is_relative_to(root)
        assert image_set.api.sha(path) == records[path.parent.name]["archive"]["sha256"]
        loads.append(path.parent.name)
        return b"loaded"

    monkeypatch.setattr(image_set.api, "run", run)
    monkeypatch.setattr(
        image_set.api,
        "inspect_image",
        lambda image: next(
            {**v, "Id": v["image_id"], "Os": v["os"], "Architecture": v["architecture"], "Variant": v["variant"]}
            for v in records.values()
            if v["image_id"] == image
        ),
    )
    monkeypatch.setattr(image_set, "runtime", lambda role, info: records[role]["runtime"])
    assert image_set.consume(root, expected, load=True)["loaded"]
    assert loads == list(image_set.ROLES)


def test_member_size_budget_stops_before_docker(image_set, handoff, monkeypatch):
    root, expected = handoff
    monkeypatch.setattr(image_set.api, "MAX_IMAGE_BYTES", 100)
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("budget rejection precedes Docker"))
    with pytest.raises(image_set.api.PackageError, match="member_invalid"):
        image_set.consume(root, expected, load=True)


@pytest.mark.parametrize(
    "images",
    [
        {},
        {role: "redis:latest" for role in ["api", "ingress", "postgres", "redis"]},
        {role: "sha256:" + "a" * 64 for role in ["api", "ingress", "postgres", "redis"]},
    ],
)
def test_export_requires_complete_distinct_exact_images(image_set, tmp_path, images):
    with pytest.raises(image_set.api.PackageError):
        image_set.export(images, tmp_path / "new")


@pytest.mark.parametrize("role", [None, "api", "ingress", "postgres", "redis"])
def test_duplicate_json_keys_are_not_an_ambiguous_selection(image_set, handoff, role):
    root, expected = handoff
    path = root / role / "manifest.json" if role else root / "manifest.json"
    text = path.read_text()
    schema = json.loads(text)["schema"]
    path.write_text(text.replace('"schema":', '"schema": "' + schema + '", "schema":', 1))
    if role:
        expected = change(
            image_set, root, None, lambda v: v["components"][role].update(manifest_sha256=image_set.api.sha(path))
        )
    else:
        expected = image_set.api.sha(path)
    with pytest.raises(image_set.api.PackageError, match="duplicate_json_key"):
        image_set.consume(root, expected)


def test_tagged_archive_is_rejected_even_with_consistent_new_digest(image_set, handoff, monkeypatch):
    root, expected = handoff
    old = json.loads((root / "redis/manifest.json").read_text())
    assert archive(root / "redis/image.tar", "redis", tags=["unrelated:current"]) == old["image_id"]
    expected = change(
        image_set, root, "redis", lambda v: v["archive"].update(sha256=image_set.api.sha(root / "redis/image.tar"))
    )
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("tagged archive must stop before Docker"))
    with pytest.raises(image_set.api.PackageError, match="tags_rejected"):
        image_set.consume(root, expected, load=True)


@pytest.mark.parametrize("role", ["postgres", "redis"])
def test_version_probes_cannot_start_networked_or_privileged_services(image_set, monkeypatch, role):
    image = "sha256:" + "b" * 64
    program = "postgres" if role == "postgres" else "redis-server"
    version = (
        b"postgres (PostgreSQL) 17.11"
        if role == "postgres"
        else b"Redis server v=7.4.8 sha=00000000:0 malloc=jemalloc bits=64"
    )
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return version

    monkeypatch.setattr(image_set.api, "run", run)
    result = image_set.runtime(
        role, {"Id": image, "Config": {"Entrypoint": ["docker-entrypoint.sh"], "Cmd": [program]}}
    )
    assert result == {"version": version.decode()}
    assert len(calls) == 1
    args = calls[0]
    assert args[-2:] == [image, "--version"]
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--pull") + 1] == "never"
    assert args[args.index("--user") + 1] == "65534:65534"
    assert "--read-only" in args and "--memory" in args and "--pids-limit" in args
    assert args[args.index("--entrypoint") + 1] == program


@pytest.mark.parametrize(
    "role,base,tag",
    [
        ("expert", "sha256:" + "a" * 64, "declarai-private-expert:local"),
        ("redis", "redis:latest", "declarai-private-redis:local"),
        ("postgres", "sha256:" + "a" * 64, "existing:latest"),
    ],
)
def test_prepare_rejects_arbitrary_roles_bases_or_tags_before_docker(image_set, monkeypatch, role, base, tag):
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: pytest.fail("invalid preparation must not call Docker"))
    with pytest.raises(image_set.api.PackageError):
        image_set.prepare_dependency(role, base, tag)


def test_preparation_cannot_overwrite_an_existing_tag(image_set, monkeypatch):
    monkeypatch.setattr(image_set.api, "run", lambda *a, **k: b"existing-image")
    monkeypatch.setattr(image_set.api, "inspect_image", lambda *a: pytest.fail("existing tag must stop before build"))
    with pytest.raises(image_set.api.PackageError, match="build_tag_exists"):
        image_set.prepare_dependency("postgres", "sha256:" + "a" * 64, "declarai-private-postgres:local")


def test_preparation_preserves_pinned_native_dependency_and_cleans_only_own_reference(image_set, monkeypatch):
    base, result = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    info = {"Id": base, "Architecture": "arm64"}
    calls = []
    monkeypatch.setattr(image_set.api, "inspect_image", lambda name: info if name == base else {**info, "Id": result})
    monkeypatch.setattr(image_set, "runtime", lambda *a: {"version": "postgres (PostgreSQL) 17.11"})

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "build":
            source = (Path(args[-1]) / "Dockerfile").read_text()
            assert base in source and "RUN " not in source and "COPY " not in source
            assert "--provenance=false" in args and "--network=none" in args and "--pull=false" in args
            assert "--platform=linux/arm64" in args
        return b""

    monkeypatch.setattr(image_set.api, "run", run)
    value = image_set.prepare_dependency("postgres", base, "declarai-private-postgres:local")
    assert value["image_id"] == result and value["base_image_id"] == base
    reference = next(args[-1] for args in calls if args[1:3] == ["image", "tag"])
    assert reference.startswith("declarai-private-component-base:")
    assert calls[-1] == ["docker", "image", "rm", reference]


@pytest.mark.parametrize("fault", ["identity", "os", "architecture", "variant", "runtime"])
def test_post_import_mismatch_never_returns_installation_success(image_set, handoff, monkeypatch, fault):
    root, expected = handoff
    records = {role: json.loads((root / role / "manifest.json").read_text()) for role in image_set.ROLES}
    loads = []

    def run(args, **kwargs):
        if args[1] == "info":
            return b"linux aarch64"
        assert args[:4] == ["docker", "image", "load", "--input"]
        loads.append(Path(args[4]).parent.name)
        return b"loaded"

    def inspect(image):
        v = next(v for v in records.values() if v["image_id"] == image)
        info = {"Id": image, "Os": "linux", "Architecture": "arm64", "Variant": ""}
        if image == records["redis"]["image_id"] and fault != "runtime":
            key = {"identity": "Id", "os": "Os", "architecture": "Architecture", "variant": "Variant"}[fault]
            info[key] = "mismatch"
        return info

    monkeypatch.setattr(image_set.api, "run", run)
    monkeypatch.setattr(image_set.api, "inspect_image", inspect)
    monkeypatch.setattr(
        image_set,
        "runtime",
        lambda role, info: (
            {"version": "changed"} if role == "redis" and fault == "runtime" else records[role]["runtime"]
        ),
    )
    with pytest.raises(image_set.api.PackageError, match="loaded_runtime_mismatch"):
        image_set.consume(root, expected, load=True)
    assert loads == list(image_set.ROLES)
