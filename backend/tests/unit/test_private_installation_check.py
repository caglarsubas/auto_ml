"""Saved-plan trust boundaries and Linux metadata-only filesystem checks."""

import copy
import hashlib
import importlib
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def checker(planner):
    return importlib.import_module("private_installation_check")


@pytest.fixture
def saved_plan(planner, handoff, request_value, tmp_path):
    root, expected = compatible(planner, handoff, request_value)
    request = tmp_path / "request.json"
    request.write_bytes(planner.encoded(request_value))
    destination = tmp_path / "plan"
    result = planner.render(request, root, expected, destination)
    return destination, result["plan_manifest_sha256"]


def rebind(checker, root, name, mutate):
    value = checker.planner.decode((root / name).read_bytes())
    mutate(value)
    (root / name).write_bytes(checker.planner.encoded(value))
    manifest = checker.planner.decode((root / "manifest.json").read_bytes())
    if name != "manifest.json":
        manifest["files"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        (root / "manifest.json").write_bytes(checker.planner.encoded(manifest))
    return hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()


def test_saved_plan_verifies_without_docker_archive_or_installation_reads(
    checker, saved_plan, monkeypatch
):
    root, expected = saved_plan
    monkeypatch.setattr(
        checker.planner.image_set.api,
        "run",
        lambda *a, **k: pytest.fail("verification must not call Docker"),
    )
    monkeypatch.setattr(
        checker,
        "open_directory",
        lambda *a: pytest.fail("offline verification must not inspect installation"),
    )
    result = checker.receipt(checker.verify(root, expected), expected)
    assert result["plan_verified"] and not result["archives_reverified"]
    assert (
        not result["installation_qualified"]
        and not result["expert_isolation_qualified"]
    )


@pytest.mark.parametrize(
    "name",
    sorted(
        [
            "manifest.json",
            "compose.json",
            "prerequisites.json",
            "request.json",
            "image-set.json",
            "ingress.json",
        ]
    ),
)
def test_altered_bytes_require_the_original_trusted_digest(checker, saved_plan, name):
    root, expected = saved_plan
    (root / name).write_bytes((root / name).read_bytes() + b" ")
    with pytest.raises(checker.planner.PlanError, match="digest_mismatch"):
        checker.verify(root, expected)


@pytest.mark.parametrize(
    "fault",
    ["extra", "missing", "root_link", "file_link", "fifo", "oversized", "duplicate"],
)
def test_layout_links_and_bounded_inputs_fail_before_installation_inspection(
    checker, saved_plan, tmp_path, monkeypatch, fault
):
    root, expected = saved_plan
    if fault == "extra":
        (root / "operator.env").write_text("never read")
    elif fault == "missing":
        (root / "compose.json").unlink()
    elif fault == "root_link":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif fault in {"file_link", "fifo"}:
        source = root / "compose.json"
        source.rename(tmp_path / "outside")
        source.symlink_to(tmp_path / "outside") if fault == "file_link" else os.mkfifo(
            source
        )
    elif fault == "oversized":
        (root / "compose.json").write_bytes(b"x" * (checker.LIMITS["compose.json"] + 1))
    else:
        (root / "manifest.json").write_text('{"schema":1,"schema":2}')
        expected = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    monkeypatch.setattr(
        checker,
        "open_directory",
        lambda *a: pytest.fail("invalid plan must fail before installation access"),
    )
    with pytest.raises((checker.planner.PlanError, OSError)):
        checker.check_paths(root, expected)


@pytest.mark.parametrize(
    "name,mutate",
    [
        ("compose.json", lambda v: v["services"]["worker"].update(privileged=True)),
        (
            "compose.json",
            lambda v: v["services"]["worker"].update(command=["python", "expert.py"]),
        ),
        ("compose.json", lambda v: v["services"]["api"].update(read_only=False)),
    ("compose.json", lambda v: v["services"]["api"].update(read_only=1)),
        (
            "compose.json",
            lambda v: v["services"]["ingress"]["ports"][0].update(host_ip="0.0.0.0"),
        ),
        (
            "compose.json",
            lambda v: v["services"]["api"]["environment"].update(DJANGO_DEBUG="true"),
        ),
        ("prerequisites.json", lambda v: v["secret_file_identity"].update(mode="0644")),
    ("prerequisites.json", lambda v: v["secret_file_identity"].update(uid=10001.0)),
        ("prerequisites.json", lambda v: v["networks"][0].update(internal=False)),
        (
            "request.json",
            lambda v: v.update(environment={"OPENAI_API_KEY": "forbidden"}),
        ),
        ("request.json", lambda v: v.update(authority="other.private.test:8443")),
        ("manifest.json", lambda v: v.update(installation_qualified=True)),
        ("manifest.json", lambda v: v.update(archive_verified_at_render=False)),
        ("manifest.json", lambda v: v.update(architecture="other")),
        ("manifest.json", lambda v: v.update(installation_id="another-installation")),
    ],
)
def test_rehashed_unsupported_profiles_still_fail_closed(
    checker, saved_plan, name, mutate
):
    root, _ = saved_plan
    expected = rebind(checker, root, name, mutate)
    with pytest.raises(checker.planner.PlanError):
        checker.verify(root, expected)


def test_directory_fd_keeps_verified_bytes_when_source_path_is_replaced(
    checker, saved_plan, tmp_path, monkeypatch
):
    root, expected = saved_plan
    original = checker.os.open
    replaced = False

    def changed(path, flags, *args, **kwargs):
        nonlocal replaced
        descriptor = original(path, flags, *args, **kwargs)
        if Path(path) == root and not replaced:
            replaced = True
            root.rename(tmp_path / "captured")
            root.mkdir()
            (root / "manifest.json").write_text("unapproved replacement")
        return descriptor

    monkeypatch.setattr(checker.os, "open", changed)
    assert checker.verify(root, expected)["request"]["installation_id"] == "pilot"
    assert replaced and (root / "manifest.json").read_text() == "unapproved replacement"


@pytest.mark.parametrize("expected", [None, "", "a" * 63, "A" * 64])
def test_trusted_digest_is_required_before_any_read(
    checker, tmp_path, monkeypatch, expected
):
    monkeypatch.setattr(
        checker,
        "read_plan",
        lambda *a: pytest.fail("invalid digest must not read input"),
    )
    with pytest.raises(checker.planner.PlanError, match="trusted_plan_digest"):
        checker.verify(tmp_path, expected)


def test_non_linux_path_checks_block_after_plan_verification(
    checker, saved_plan, monkeypatch
):
    root, expected = saved_plan
    monkeypatch.setattr(checker.sys, "platform", "darwin")
    monkeypatch.setattr(
        checker,
        "open_directory",
        lambda *a: pytest.fail("unsupported platform must not inspect paths"),
    )
    with pytest.raises(checker.planner.PlanError, match="linux_required"):
        checker.check_paths(root, expected)


@pytest.fixture
def metadata_tree(checker, tmp_path, monkeypatch):
    """Portable unit ownership simulation; real UID 10001 is checked in Linux qualification."""
    root = tmp_path / "installation"
    app, tls, artifacts = [
        root / n for n in ("secrets/app", "secrets/tls", "artifacts")
    ]
    for directory in (app, tls, artifacts):
        directory.mkdir(parents=True, mode=0o700)
    files = {
        "app": [
            "django-key",
            "app-password",
            "job-broker-url",
            "postgres-ca.crt",
            "job-ca.crt",
        ],
        "tls": ["tls.crt", "tls.key"],
    }
    for directory in (app, tls):
        for name in files[directory.name]:
            (directory / name).write_text("synthetic metadata fixture")
            (directory / name).chmod(0o400)
    directories = [
        {
            "path": str(p),
            "uid": 10001,
            "gid": 10001,
            "mode": "0700",
            "mount": "read_write" if p == artifacts else "read_only",
        }
        for p in (app, tls, artifacts)
    ]
    value = {
        "request": {"installation_id": "pilot"},
        "manifest": {"architecture": "amd64"},
        "prerequisites": {"directories": directories, "secret_files": files},
    }
    monkeypatch.setattr(checker, "verify", lambda *a: copy.deepcopy(value))
    monkeypatch.setattr(
        checker,
        "open_directory",
        lambda p: os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW),
    )
    original = checker.os.fstat
    owner_fault = {"inode": None}

    def simulated(descriptor):
        item = original(descriptor)
        return SimpleNamespace(
            st_mode=item.st_mode,
            st_size=item.st_size,
            st_nlink=item.st_nlink,
            st_uid=0 if item.st_ino == owner_fault["inode"] else 10001,
            st_gid=10001,
            st_dev=item.st_dev,
            st_ino=item.st_ino,
        )

    monkeypatch.setattr(checker.os, "fstat", simulated)
    return app, tls, artifacts, owner_fault


def test_metadata_check_reads_no_secret_values_or_artifact_descendants(
    checker, metadata_tree
):
    _, _, artifacts, _ = metadata_tree
    os.mkfifo(artifacts / "never-inspect-customer-fifo")
    result = checker.check_paths(Path("unused"), "a" * 64)
    assert (
        result["filesystem_prerequisites"] == "passed"
        and result["secret_metadata_files"] == 7
    )
    assert (
        not result["secret_contents_read"]
        and not result["artifact_descendants_inspected"]
    )
    assert (
        not result["encrypted_storage_verified"]
        and not result["networks_and_socket_verified"]
        and not result["runtime_connectivity_verified"]
    )


@pytest.mark.parametrize(
    "fault",
    [
        "directory_mode",
        "directory_owner",
        "file_mode",
        "file_owner",
        "file_link",
        "hardlink",
        "fifo",
        "empty",
        "oversized_secret",
        "oversized_certificate",
        "extra_secret",
        "missing_secret",
        "directory_link",
    ],
)
def test_metadata_faults_fail_without_repair_or_secret_output(
    checker, metadata_tree, tmp_path, fault
):
    app, tls, _, owner_fault = metadata_tree
    file = app / "app-password"
    if fault == "directory_mode":
        app.chmod(0o750)
    elif fault == "directory_owner":
        owner_fault["inode"] = app.stat().st_ino
    elif fault == "file_mode":
        file.chmod(0o644)
    elif fault == "file_owner":
        owner_fault["inode"] = file.stat().st_ino
    elif fault == "hardlink":
        os.link(file, tmp_path / "linked-value")
    elif fault in {"file_link", "fifo"}:
        file.unlink()
        file.symlink_to(tmp_path / "missing") if fault == "file_link" else os.mkfifo(
            file
        )
    elif fault == "empty":
        file.chmod(0o600)
        file.write_bytes(b"")
        file.chmod(0o400)
    elif fault == "oversized_secret":
        file.chmod(0o600)
        file.write_bytes(b"x" * 4097)
        file.chmod(0o400)
    elif fault == "oversized_certificate":
        cert = tls / "tls.crt"
        cert.chmod(0o600)
        cert.write_bytes(b"x" * 65_537)
        cert.chmod(0o400)
    elif fault == "extra_secret":
        (app / "provider-key").write_text("must not read")
    elif fault == "missing_secret":
        file.unlink()
    else:
        app.rename(tmp_path / "outside")
        app.symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises((checker.planner.PlanError, OSError)):
        checker.check_paths(Path("unused"), "a" * 64)
    if fault == "file_mode":
        assert stat.S_IMODE(file.stat().st_mode) == 0o644
    if fault == "directory_mode":
        assert stat.S_IMODE(app.stat().st_mode) == 0o750


def test_real_ancestor_walk_rejects_writable_tmp_before_descending(checker, tmp_path):
    with pytest.raises(checker.planner.PlanError, match="ancestor_unsafe"):
        checker.open_directory(tmp_path)


def test_unsupported_directory_acl_is_explicit(checker, monkeypatch):
    monkeypatch.setattr(
        checker.os, "listxattr", lambda *a: ["system.posix_acl_default"]
    )
    with pytest.raises(checker.planner.PlanError, match="acl_unsupported"):
        checker.no_directory_acl(123)


@pytest.mark.parametrize("fault", ["image", "root", "installation_id", "reports"])
def test_path_qualifier_rejects_unowned_scope_before_docker(
    checker, tmp_path, monkeypatch, fault
):
    qualifier = importlib.import_module("qualify_private_installation_check")
    image = "sha256:" + "a" * 64
    value = {
        "images": {"api": image},
        "request": {
            "root": "/srv/declarai/qualification",
            "installation_id": "qualification",
        },
    }
    if fault == "root":
        value["request"]["root"] = "/srv/declarai/customer"
    if fault == "installation_id":
        value["request"]["installation_id"] = "customer"
    monkeypatch.setattr(qualifier.checker, "verify", lambda *a: value)
    monkeypatch.setattr(
        qualifier,
        "command",
        lambda *a, **k: pytest.fail("unowned input must not call Docker"),
    )
    reports = tmp_path if fault == "reports" else qualifier.ROOT / "test-reports/p35"
    with pytest.raises(checker.planner.PlanError):
        qualifier.qualify(
            tmp_path,
            "a" * 64,
            "sha256:" + "b" * 64 if fault == "image" else image,
            reports,
        )


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_unexpected_checker_failure_cleans_every_owned_object(
    checker, tmp_path, monkeypatch, cleanup_failure
):
    qualifier = importlib.import_module("qualify_private_installation_check")
    image = "sha256:" + "a" * 64
    value = {
        "images": {"api": image},
        "request": {
            "root": "/srv/declarai/qualification",
            "installation_id": "qualification",
        },
    }
    monkeypatch.setattr(qualifier.checker, "verify", lambda *a: value)
    monkeypatch.setattr(qualifier.checker, "read_plan", lambda *a: {})
    calls = []

    def command(argv, data=None):
        calls.append(argv)
        result = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if "check-paths" in argv:
            result.returncode = 1
            result.stderr = b"unexpected check failure"
        if cleanup_failure and argv[:3] == ["docker", "volume", "rm"]:
            result.returncode = 1
        return result

    monkeypatch.setattr(qualifier, "command", command)
    reason = "cleanup_failed" if cleanup_failure else "check_failed"
    with pytest.raises(checker.planner.PlanError, match=reason):
        qualifier.qualify(
            tmp_path, "a" * 64, image, qualifier.ROOT / "test-reports/p35"
        )
    created = [argv[-1] for argv in calls if argv[:3] == ["docker", "volume", "create"]]
    removed = [argv[-1] for argv in calls if argv[:3] == ["docker", "volume", "rm"]]
    assert len(created) == 2 and removed == created
    assert all(name.startswith("declarai-plan-paths-") for name in created)
    assert (
        len([argv for argv in calls if argv[:3] == ["docker", "container", "rm"]]) == 2
    )
