"""Frozen historical archive and same-application index fixture boundaries."""

import copy
import gzip
import hashlib
import importlib
import io
import json
import tarfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def reference(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    reader = importlib.import_module("private_reference_source")
    archive = (ROOT / "docs/evidence/p167-previous-source.tar.gz").read_bytes()
    old = (ROOT / "docs/evidence/p165-reference-source.json").read_bytes()
    pin = json.loads((ROOT / "docs/evidence/p167-previous-source.json").read_bytes())
    return reader, archive, old, pin


def test_sealed_previous_archive_matches_all_original_source_hashes(reference):
    reader, archive, old, pin = reference
    spec, files = reader.sources(archive, old, pin)
    assert len(files) == 223 and set(files) == set(spec["source_sha256"])
    assert {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()} == spec["source_sha256"]
    assert spec["qualification_reconstruction_only"] and not spec["customer_release_qualified"]


@pytest.mark.parametrize("fault", ["archive", "reference", "pin", "scope", "release"])
def test_archive_or_scope_tampering_is_refused(reference, fault):
    reader, archive, old, pin = reference
    if fault == "archive":
        archive = archive[:-1] + bytes([archive[-1] ^ 1])
    elif fault == "reference":
        old += b" "
    elif fault == "pin":
        pin["files"] += 1
    elif fault == "scope":
        pin["qualification_reconstruction_only"] = False
    else:
        pin["customer_release_qualified"] = True
    with pytest.raises(reader.ReferenceError):
        reader.sources(archive, old, pin)


@pytest.mark.parametrize("fault", ["traversal", "symlink", "extra", "duplicate", "missing", "content"])
def test_no_archive_member_can_escape_or_weaken_exact_inventory(reference, fault):
    reader, archive, old, pin = reference
    _, files = reader.sources(archive, old, pin)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as stream:
        for index, (name, raw) in enumerate(files.items()):
            if index == 0 and fault == "missing":
                continue
            item = tarfile.TarInfo("../outside" if index == 0 and fault == "traversal" else name)
            if index == 0 and fault == "symlink":
                item.type = tarfile.SYMTYPE
                item.linkname = "/tmp/outside"
                stream.addfile(item)
                continue
            if index == 0 and fault == "content":
                raw += b"changed"
            item.size = len(raw)
            stream.addfile(item, io.BytesIO(raw))
            if index == 0 and fault == "duplicate":
                stream.addfile(copy.copy(item), io.BytesIO(raw))
        if fault == "extra":
            stream.addfile(tarfile.TarInfo("backend/unreviewed.py"), io.BytesIO(b""))
    archive = gzip.compress(output.getvalue(), mtime=0)
    pin["archive_sha256"] = hashlib.sha256(archive).hexdigest()
    with pytest.raises(reader.ReferenceError):
        reader.sources(archive, old, pin)


def test_previous_schema_fixture_preserves_current_application_exactly(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    module = importlib.import_module("qualify_private_upgrade_reference")
    source = {"schema": "private_api_source_v1", "git_commit": "a" * 40,
              "source_sha256": {module.MIGRATION: "b" * 64, "backend/new_legacy.py": "c" * 64}}
    original = copy.deepcopy(source)
    reference = module.previous_schema_reference(source, "sha256:" + "d" * 64, "b" * 64)
    assert source == original
    assert reference["source_sha256"] == {"backend/new_legacy.py": "c" * 64}
    assert reference["fixture_basis"] == "same_current_application_previous_index_schema"
    assert reference["removed_migration"] == {"path": module.MIGRATION, "sha256": "b" * 64}
    assert reference["qualification_reconstruction_only"] and not reference["customer_release_qualified"]


@pytest.mark.parametrize("fault", ["schema", "image", "migration"])
def test_previous_schema_fixture_rejects_unbound_inputs(monkeypatch, fault):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    module = importlib.import_module("qualify_private_upgrade_reference")
    source = {"schema": "private_api_source_v1", "git_commit": "a" * 40,
              "source_sha256": {module.MIGRATION: "b" * 64}}
    image, pin = "sha256:" + "d" * 64, "b" * 64
    if fault == "schema":
        source["schema"] = "historical"
    elif fault == "image":
        image = "latest"
    else:
        pin = "e" * 64
    with pytest.raises(module.planner.PlanError):
        module.previous_schema_reference(source, image, pin)
