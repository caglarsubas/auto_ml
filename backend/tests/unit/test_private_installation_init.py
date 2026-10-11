"""Fresh installation publication, bounded secret capture and safe retry boundaries."""

import copy
import importlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_private_image_set import handoff, image_set  # noqa: F401
from tests.unit.test_private_installation_plan import compatible, planner, request_value  # noqa: F401

pytestmark = pytest.mark.unit


@pytest.fixture
def initializer(planner):
    return importlib.import_module("private_installation_init")


def values():
    return {
        "app/django-key": b"Synthetic-Key-Only-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789",
        "app/app-password": b"synthetic-not-a-real-password",
        "app/job-broker-url": b"rediss://:synthetic@job-broker:6379/1",
        "app/postgres-ca.crt": b"synthetic opaque certificate",
        "app/job-ca.crt": b"synthetic opaque certificate",
        "tls/tls.crt": b"synthetic opaque certificate",
        "tls/tls.key": b"synthetic opaque key",
    }


@pytest.fixture
def fresh_plan(initializer, handoff, request_value, tmp_path):
    request = copy.deepcopy(request_value)
    request["root"] = str(tmp_path / "installation")
    root, digest = compatible(initializer.checker.planner, handoff, request)
    source = tmp_path / "request.json"
    source.write_bytes(initializer.checker.planner.encoded(request))
    plan = tmp_path / "plan"
    rendered = initializer.checker.planner.render(source, root, digest, plan)
    return plan, rendered["plan_manifest_sha256"], Path(request["root"])


@pytest.fixture
def portable_identity(initializer, monkeypatch):
    """Portable ownership simulation; native Linux qualification uses real identities."""
    original = os.fstat

    def info(fd):
        result = original(fd)
        attrs = {name: getattr(result, name) for name in dir(result) if name.startswith("st_")}
        attrs.update(st_uid=10001, st_gid=10001)
        return SimpleNamespace(**attrs)

    monkeypatch.setattr(initializer.os, "fstat", info)
    monkeypatch.setattr(initializer.os, "fchown", lambda *a: None)
    monkeypatch.setattr(initializer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(initializer.sys, "platform", "linux")
    monkeypatch.setattr(initializer, "trusted_directory", lambda p: os.open(p, initializer.DIRECTORY_FLAGS))
    monkeypatch.setattr(initializer.checker, "open_directory", lambda p: os.open(p, initializer.DIRECTORY_FLAGS))
    monkeypatch.setattr(initializer.checker, "no_directory_acl", lambda d: None)

    def rename(parent, source, target):
        initializer.absent(parent, target)
        os.rename(source, target, src_dir_fd=parent, dst_dir_fd=parent)

    monkeypatch.setattr(initializer, "rename_noreplace", rename)


@pytest.fixture
def secret_delivery(tmp_path):
    source = tmp_path / "delivery"
    source.mkdir(mode=0o700)
    for group in ("app", "tls"):
        (source / group).mkdir(mode=0o700)
    for name, data in values().items():
        (source / name).write_bytes(data)
        (source / name).chmod(0o400)
    return source


def test_fresh_publication_preserves_exact_secret_bytes_and_has_safe_receipt(
    initializer, fresh_plan, secret_delivery, portable_identity
):
    plan, expected, target = fresh_plan
    result = initializer.initialize(plan, expected, secret_delivery)
    assert result["filesystem_initialized"] and result["secret_files_delivered"] == 7
    assert not result["services_adopted"] and not result["installation_qualified"]
    assert not result["certificate_trust_verified"] and not result["encrypted_storage_verified"]
    for name, data in values().items():
        file = target / "secrets" / name
        assert file.read_bytes() == data and stat.S_IMODE(file.stat().st_mode) == 0o400
        assert (secret_delivery / name).read_bytes() == data
        assert data.decode() not in json.dumps(result)
    assert not list((target / "artifacts").iterdir())
    assert json.loads((target / "initialization.json").read_bytes()) == result
    assert stat.S_IMODE(target.stat().st_mode) == 0o750
    assert not list(target.parent.glob(".declarai-init-*"))


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "dangling_symlink"])
def test_existing_target_blocks_before_any_delivery_read(initializer, fresh_plan, portable_identity, monkeypatch, kind):
    plan, expected, target = fresh_plan
    if kind == "directory":
        target.mkdir()
        (target / "sentinel").write_text("unchanged")
    elif kind == "file":
        target.write_text("unchanged")
    else:
        target.symlink_to(target.parent if kind == "symlink" else target.parent / "missing")
    monkeypatch.setattr(initializer, "delivery", lambda *a: pytest.fail("existing target must block secret reads"))
    with pytest.raises(initializer.checker.planner.PlanError, match="destination_exists"):
        initializer.initialize(plan, expected, Path("/unused"))
    assert target.exists() or target.is_symlink()


@pytest.mark.parametrize(
    "fault", ["mode", "empty", "oversized", "hardlink", "link", "fifo", "extra", "group_mode", "root_extra"]
)
def test_bad_delivery_does_not_create_target_or_leave_staging(
    initializer, fresh_plan, secret_delivery, portable_identity, fault
):
    plan, expected, target = fresh_plan
    file = secret_delivery / "app/app-password"
    if fault == "mode":
        file.chmod(0o644)
    elif fault == "empty":
        file.chmod(0o600)
        file.write_bytes(b"")
        file.chmod(0o400)
    elif fault == "oversized":
        file.chmod(0o600)
        file.write_bytes(b"x" * 4097)
        file.chmod(0o400)
    elif fault == "hardlink":
        os.link(file, secret_delivery.parent / "outside")
    elif fault in {"link", "fifo"}:
        file.unlink()
        file.symlink_to(secret_delivery / "app/django-key") if fault == "link" else os.mkfifo(file)
    elif fault == "extra":
        (secret_delivery / "app/extra").write_text("unapproved")
    elif fault == "root_extra":
        (secret_delivery / "extra").write_text("unapproved")
    else:
        (secret_delivery / "app").chmod(0o750)
    with pytest.raises((initializer.checker.planner.PlanError, OSError)):
        initializer.initialize(plan, expected, secret_delivery)
    assert not target.exists() and not list(target.parent.glob(".declarai-init-*"))


@pytest.mark.parametrize(
    "name,value",
    [
        ("django-key", b"x" * 60),
        ("django-key", b"short"),
        ("django-key", b"django-insecure-" + b"abcdef" * 10),
        ("app-password", b""),
        ("app-password", b"line\nbreak"),
        ("app-password", b"invalid\xff"),
        ("app-password", b"nul\x00byte"),
        ("job-broker-url", b"redis://:pw@job-broker:6379/1"),
        ("job-broker-url", b"rediss://:pw@external:6379/1"),
        ("job-broker-url", b"rediss://:pw@job-broker:6380/1"),
        ("job-broker-url", b"rediss://:pw@job-broker:6379/1?ssl_cert_reqs=none"),
        ("job-broker-url", b"rediss://:pw@job-broker:6379/1#ignored"),
        ("job-broker-url", b"rediss://:pw@job-broker:6379/01"),
        ("job-broker-url", b"rediss://:pw@job-broker:6379/100"),
        ("job-broker-url", b"rediss://user:pw@job-broker:6379/1"),
        ("job-broker-url", b"rediss://job-broker:6379/1"),
    ],
)
def test_application_secret_shape_and_exact_broker_endpoint_fail_closed(initializer, name, value):
    files = values()
    files["app/" + name] = value
    with pytest.raises(initializer.checker.planner.PlanError, match="secret_value_invalid") as error:
        initializer.validate_secrets(files)
    assert repr(value) not in str(error.value)


@pytest.mark.parametrize("phase", ["write", "sync", "publish", "competing_empty_directory"])
def test_interruption_and_competing_publication_preserve_existing_target(
    initializer, fresh_plan, secret_delivery, portable_identity, monkeypatch, phase
):
    plan, expected, target = fresh_plan
    if phase in {"write", "sync"}:

        def fail(*args):
            raise OSError("synthetic failure")

        monkeypatch.setattr(
            initializer if phase == "write" else initializer.os, "write_file" if phase == "write" else "fsync", fail
        )
    else:
        original = initializer.rename_noreplace

        def publish(parent, source, destination):
            if phase == "competing_empty_directory":
                target.mkdir()
                original(parent, source, destination)
            raise initializer.checker.planner.PlanError("synthetic_publish_failure")

        monkeypatch.setattr(initializer, "rename_noreplace", publish)
    with pytest.raises((initializer.checker.planner.PlanError, OSError)):
        initializer.initialize(plan, expected, secret_delivery)
    assert not list(target.parent.glob(".declarai-init-*"))
    assert target.is_dir() if phase == "competing_empty_directory" else not target.exists()
    assert all((secret_delivery / name).read_bytes() == data for name, data in values().items())


def test_untrusted_plan_blocks_before_any_installation_or_secret_access(initializer, fresh_plan, monkeypatch):
    plan, expected, _ = fresh_plan
    (plan / "compose.json").write_text("tampered")
    monkeypatch.setattr(initializer, "trusted_directory", lambda *a: pytest.fail("bad plan touched installation"))
    with pytest.raises(initializer.checker.planner.PlanError, match="digest_mismatch"):
        initializer.initialize(plan, expected, Path("/unused"))


def test_init_requires_linux_root_before_secret_reads(initializer, fresh_plan, monkeypatch):
    plan, expected, _ = fresh_plan
    monkeypatch.setattr(initializer.sys, "platform", "darwin")
    monkeypatch.setattr(initializer, "delivery", lambda *a: pytest.fail("unsupported host read delivery"))
    with pytest.raises(initializer.checker.planner.PlanError, match="linux_root_required"):
        initializer.initialize(plan, expected, Path("/unused"))


@pytest.mark.parametrize(
    "code,reason", [(17, "destination_exists"), (38, "atomic_publish_failed"), (22, "atomic_publish_failed")]
)
def test_atomic_publication_never_falls_back_to_replacing_rename(initializer, monkeypatch, code, reason):
    class Function:
        def __call__(self, *args):
            assert args[-1] == 1 and args[0] == args[2] == 42
            return -1

    monkeypatch.setattr(initializer.ctypes, "CDLL", lambda *a, **k: SimpleNamespace(renameat2=Function()))
    monkeypatch.setattr(initializer.ctypes, "get_errno", lambda: code)
    monkeypatch.setattr(initializer.os, "rename", lambda *a, **k: pytest.fail("weak rename fallback"))
    with pytest.raises(initializer.checker.planner.PlanError, match=reason):
        initializer.rename_noreplace(42, "stage", "installation")


def test_missing_atomic_api_fails_closed(initializer, monkeypatch):
    monkeypatch.setattr(initializer.ctypes, "CDLL", lambda *a, **k: SimpleNamespace())
    with pytest.raises(initializer.checker.planner.PlanError, match="atomic_publish_unavailable"):
        initializer.rename_noreplace(42, "stage", "installation")


@pytest.mark.parametrize("path", [Path("relative"), Path("/srv/../delivery")])
def test_delivery_path_rejects_relative_or_traversal_before_open(initializer, monkeypatch, path):
    monkeypatch.setattr(initializer.checker, "open_directory", lambda *a: pytest.fail("invalid delivery path opened"))
    with pytest.raises(initializer.checker.planner.PlanError, match="delivery_path_invalid"):
        initializer.delivery(path, {"app": [], "tls": []})


def test_changed_secret_is_rejected_before_staging(
    initializer, fresh_plan, secret_delivery, portable_identity, monkeypatch
):
    plan, expected, target = fresh_plan
    original = initializer.os.fstat
    calls = {}

    def changed(fd):
        info = original(fd)
        if stat.S_ISREG(info.st_mode) and info.st_size == len(values()["app/django-key"]):
            calls[fd] = calls.get(fd, 0) + 1
            if calls[fd] == 2:
                info.st_ctime_ns += 1
        return info

    monkeypatch.setattr(initializer.os, "fstat", changed)
    with pytest.raises(initializer.checker.planner.PlanError, match="delivery_file_changed"):
        initializer.initialize(plan, expected, secret_delivery)
    assert not target.exists() and not list(target.parent.glob(".declarai-init-*"))


def test_post_publication_error_preserves_target_and_blocks_replay(
    initializer, fresh_plan, secret_delivery, portable_identity, monkeypatch
):
    plan, expected, target = fresh_plan
    original = initializer.os.fchmod

    def fail(fd, mode):
        if target.exists():
            raise OSError("synthetic post-publication error")
        return original(fd, mode)

    monkeypatch.setattr(initializer.os, "fchmod", fail)
    with pytest.raises(OSError):
        initializer.initialize(plan, expected, secret_delivery)
    assert target.is_dir() and stat.S_IMODE(target.stat().st_mode) == 0o700
    assert not list(target.parent.glob(".declarai-init-*"))
    monkeypatch.setattr(initializer, "delivery", lambda *a: pytest.fail("published destination replayed"))
    with pytest.raises(initializer.checker.planner.PlanError, match="destination_exists"):
        initializer.initialize(plan, expected, secret_delivery)


def test_qualifier_blocks_operator_scope_before_docker(initializer, fresh_plan, monkeypatch, tmp_path):
    qualifier = importlib.import_module("qualify_private_installation_init")
    plan, expected, _ = fresh_plan
    monkeypatch.setattr(qualifier, "command", lambda *a, **k: pytest.fail("operator fixture touched Docker"))
    image = initializer.checker.verify(plan, expected)["images"]["api"]
    with pytest.raises(initializer.checker.planner.PlanError, match="fixture_scope_required"):
        qualifier.qualify(plan, expected, image, tmp_path)
