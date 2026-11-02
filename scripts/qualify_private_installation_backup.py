"""Quiescent baseline-backup qualification inside an exclusively owned fixture.

This does not restore an installation, establish operator key custody or qualify
machine-loss recovery. Raw database/artifact bytes never enter public reports.
"""

import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path

from qualify_private_installation_workflow import owned, require

MAX_BYTES = 64 * 1024**2


def artifact_bytes(root):
    require(root.is_dir() and not root.is_symlink(), "backup_root")
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    files = {}
    total = 0
    for folder, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(folder) / name
            info = path.lstat()
            require(not stat.S_ISLNK(info.st_mode), "backup_symlink")
            if name in dirs:
                require(stat.S_ISDIR(info.st_mode), "backup_directory")
                continue
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_BYTES, "backup_file")
            total += info.st_size
            require(total <= MAX_BYTES and len(files) < 1024, "backup_budget")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                require(identity(os.fstat(stream.fileno())) == identity(info), "backup_file_changed")
                raw = stream.read(MAX_BYTES + 1)
                require(identity(os.fstat(stream.fileno())) == identity(info) and len(raw) == info.st_size, "backup_file_changed")
            files[path.relative_to(root).as_posix()] = raw
    require(bool(files), "backup_artifacts_empty")
    return dict(sorted(files.items()))


def qualify(value, expected, parent, postgres, command):
    owned(value, parent)
    import private_installation_adopt as adopter
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    project = adopter.checker.planner.composition(value["request"], value["images"])
    require(not adopter.project_containers(project["name"]), "backup_applications_active")
    # Application containers were validated and stopped/removed by the caller;
    # no writer, API or worker remains while both stores are captured.
    before = artifact_bytes(parent / "installation" / "artifacts")
    dump = command(["exec", "--user", "70:70", postgres, "pg_dump", "-U", "postgres", "-Fc", value["request"]["database"]["name"]])
    require(dump.startswith(b"PGDMP") and len(dump) <= MAX_BYTES, "backup_database")
    listing = command(["exec", "--user", "70:70", "-i", postgres, "pg_restore", "--list"], data=dump)
    require(b"declaration_declaration" in listing and b"execution_jobs_nativejob" in listing and b"auth_user" in listing, "backup_catalog")
    require(before == artifact_bytes(parent / "installation" / "artifacts"), "backup_artifacts_changed")
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    inventory = {name: {"bytes": len(raw), "sha256": digest(raw)} for name, raw in before.items()}
    manifest = {"schema": "private_fixture_baseline_backup_v1", "plan_manifest_sha256": expected,
                "images": value["images"], "database": {"bytes": len(dump), "sha256": digest(dump)}, "artifacts": inventory,
                "quiescent_application_services": True, "restore_qualified": False, "operator_key_custody_qualified": False}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    files = {"manifest.json": encoded, "database.dump": dump, **{"artifacts/" + k: v for k, v in before.items()}}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(raw), 0o600, 0
            archive.addfile(info, io.BytesIO(raw))
    require(stream.tell() <= 2 * MAX_BYTES, "backup_archive_budget")
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    aad = expected.encode()
    ciphertext = nonce + AESGCM(key).encrypt(nonce, stream.getvalue(), aad)
    target = parent / "baseline-backup.aesgcm"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(ciphertext)
    retained = target.read_bytes()
    verified = AESGCM(key).decrypt(retained[:12], retained[12:], aad)
    with tarfile.open(fileobj=io.BytesIO(verified), mode="r:") as archive:
        require(set(archive.getnames()) == set(files) and len(archive.getnames()) == len(files), "backup_members")
        for item in archive:
            require(item.isfile() and archive.extractfile(item).read() == files[item.name], "backup_integrity")
    for payload, binding in ((retained[12:-1] + bytes([retained[-1] ^ 1]), aad), (retained[12:], b"wrong-plan")):
        try:
            AESGCM(key).decrypt(retained[:12], payload, binding)
        except InvalidTag:
            pass
        else:
            require(False, "backup_tamper_not_refused")
    require(before == artifact_bytes(parent / "installation" / "artifacts"), "backup_source_changed")
    return {"schema": "private_installed_baseline_backup_qualification_v1", "plan_manifest_sha256": expected,
            "database_archive_catalog": "verified", "artifact_files": len(inventory), "backup_manifest_sha256": digest(encoded),
            "encrypted_archive_sha256": digest(ciphertext), "encrypted_archive_bytes": len(ciphertext),
            "decrypted_all_members_and_hashes": "passed", "tamper_and_wrong_plan_binding": "refused",
            "quiescent_database_and_artifact_capture": "passed", "credential_or_backup_bytes_retained_in_reports": False,
            "fixture_key_and_archive_removed_with_owned_root": True, "restore_qualified": False, "operator_key_custody_qualified": False}
