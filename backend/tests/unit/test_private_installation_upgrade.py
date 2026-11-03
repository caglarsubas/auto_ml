"""Version/compatibility boundaries and immutable staged transition admission."""

import copy
import importlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def upgrade(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return importlib.import_module("private_installation_upgrade")


@pytest.fixture
def versions():
    old = {
        "runtime": {"python": "3.12", "packages": []},
        "requirements_sha256": "a" * 64,
        "files": {"backend/models.py": "b" * 64, "backend/execution_jobs/migrations/0001.py": "c" * 64},
        "graph": {
            "vertices": [{"app": "execution_jobs", "name": "0001", "parents": []}],
            "targets": [["execution_jobs", "0001"]],
        },
        "migrations": {"execution_jobs/0001": {"file_sha256": "c" * 64, "index_only": False, "indexes": []}},
    }
    new = copy.deepcopy(old)
    new["files"]["backend/execution_jobs/migrations/0002.py"] = "d" * 64
    new["graph"]["vertices"].append({"app": "execution_jobs", "name": "0002", "parents": [["execution_jobs", "0001"]]})
    new["graph"]["targets"] = [["execution_jobs", "0002"]]
    new["migrations"]["execution_jobs/0002"] = {
        "file_sha256": "d" * 64,
        "index_only": True,
        "indexes": [
            {"name": "history_idx", "table": "execution_jobs_nativejob", "fields": ["project_id", "-created_at", "-id"]}
        ],
    }
    return old, new


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_index_release_can_upgrade_and_rollback(upgrade, versions, reverse):
    old, new = versions
    source, target = (new, old) if reverse else (old, new)
    result = upgrade.compatibility(source, target)
    assert result["direction"] == ("rollback" if reverse else "upgrade")
    assert result["indexes"][0]["fields"] == ["project_id", "-created_at", "-id"]
    assert result["source_nodes"] != result["target_nodes"]


@pytest.mark.parametrize(
    "fault",
    [
        "python",
        "packages",
        "dependencies",
        "model",
        "removed_file",
        "extra_file",
        "old_migration",
        "parents",
        "same_graph",
        "diverged_graph",
        "data_migration",
        "irreversible",
        "empty_ops",
        "duplicate_index",
        "index_name",
        "table_name",
        "field_expression",
        "empty_fields",
    ],
)
def test_incompatible_software_or_migration_is_refused(upgrade, versions, fault):
    old, new = versions
    op = new["migrations"]["execution_jobs/0002"]
    if fault in {"python", "packages"}:
        new["runtime"][fault] = "different"
    elif fault == "dependencies":
        new["requirements_sha256"] = "e" * 64
    elif fault == "model":
        new["files"]["backend/models.py"] = "e" * 64
    elif fault == "removed_file":
        del new["files"]["backend/models.py"]
    elif fault == "extra_file":
        new["files"]["backend/unapproved.py"] = "e" * 64
    elif fault == "old_migration":
        new["migrations"]["execution_jobs/0001"]["file_sha256"] = "e" * 64
    elif fault == "parents":
        new["graph"]["vertices"][0]["parents"] = [["unknown", "0001"]]
    elif fault == "same_graph":
        new["graph"] = copy.deepcopy(old["graph"])
    elif fault == "diverged_graph":
        new["graph"]["vertices"][0]["name"] = "diverged"
    elif fault in {"data_migration", "irreversible"}:
        op["index_only"] = False
    elif fault == "empty_ops":
        op["indexes"] = []
    elif fault == "duplicate_index":
        op["indexes"] *= 2
    elif fault in {"index_name", "table_name", "field_expression"}:
        key = {"index_name": "name", "table_name": "table", "field_expression": "fields"}[fault]
        op["indexes"][0][key] = ["id); DROP TABLE"] if key == "fields" else "unsafe;DROP"
    else:
        op["indexes"][0]["fields"] = []
    with pytest.raises(upgrade.checker.planner.PlanError):
        upgrade.compatibility(old, new)


@pytest.fixture
def catalogs(upgrade, versions):
    old = {
        "tables": {
            "execution_jobs_nativejob": {
                "columns": [["id", "uuid"]],
                "indexes": [],
                "constraints": [["pk", "p"]],
                "triggers": [["O", "RI"]],
            }
        },
        "sequences": {},
    }
    new = copy.deepcopy(old)
    new["tables"]["execution_jobs_nativejob"]["indexes"] = [
        [
            "history_idx",
            False,
            True,
            True,
            False,
            True,
            "CREATE INDEX history_idx ON public.execution_jobs_nativejob USING btree (project_id, created_at DESC, id DESC)",
        ]
    ]
    return old, new, upgrade.compatibility(*versions)


@pytest.mark.parametrize("reverse", [False, True])
def test_physical_catalog_matches_only_declared_index_delta(upgrade, catalogs, reverse):
    old, new, change = catalogs
    if reverse:
        change["direction"] = "rollback"
    upgrade.verify_catalog(new if reverse else old, old if reverse else new, change)


@pytest.mark.parametrize(
    "fault",
    [
        "unique",
        "invalid",
        "not_ready",
        "exclusion",
        "deferred",
        "wrong_sql",
        "column",
        "constraint",
        "trigger",
        "sequence",
        "extra_index",
        "extra_table",
    ],
)
def test_catalog_drift_is_never_accepted_as_compatible(upgrade, catalogs, fault):
    old, new, change = catalogs
    row = new["tables"]["execution_jobs_nativejob"]["indexes"][0]
    positions = {"unique": 1, "invalid": 2, "not_ready": 3, "exclusion": 4, "deferred": 5}
    if fault in positions:
        row[positions[fault]] = not row[positions[fault]]
    elif fault == "wrong_sql":
        row[-1] += " WHERE true"
    elif fault in {"column", "constraint", "trigger"}:
        key = {"column": "columns", "constraint": "constraints", "trigger": "triggers"}[fault]
        new["tables"]["execution_jobs_nativejob"][key] = []
    elif fault == "sequence":
        new["sequences"]["foreign_seq"] = [1]
    elif fault == "extra_index":
        new["tables"]["execution_jobs_nativejob"]["indexes"].append(["unapproved"])
    else:
        new["tables"]["foreign"] = {}
    with pytest.raises(upgrade.checker.planner.PlanError):
        upgrade.verify_catalog(old, new, change)


def test_only_migration_recorder_metadata_is_excluded_from_data_invariant(upgrade):
    db = {
        "tables": {
            "django_migrations": {"sha256": "a", "bytes": 3, "rows": 1},
            "auth_user": {"sha256": "b", "bytes": 5, "rows": 2, "data": "opaque"},
        },
        "sequences": {"django_migrations_id_seq": [33, True], "auth_user_id_seq": [2, True]},
    }
    assert upgrade.data_identity(db) == {"auth_user": {"sha256": "b", "bytes": 5, "rows": 2}}
    assert upgrade.sequence_identity(db) == {"auth_user_id_seq": [2, True]}


@pytest.fixture
def journal(upgrade, tmp_path, monkeypatch):
    root = tmp_path / "transition"
    root.mkdir(mode=0o700)
    intent = {
        "schema": "private_upgrade_intent_v1",
        "plan_sha256": "a" * 64,
        "target_plan_sha256": "b" * 64,
        "initialization_id": "c" * 32,
        "controller_sha256": upgrade.controller_sha(),
    }
    records = {
        "intent.json": upgrade.recovery.encoded(intent),
        "complete.json": upgrade.recovery.encoded(upgrade.complete(intent)),
    }
    previous = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda p: SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_gid=0) if p == root else previous(p),
    )

    def read(p, *a):
        if p.name not in records:
            raise FileNotFoundError
        return records[p.name]

    monkeypatch.setattr(upgrade.recovery, "private_read", read)
    monkeypatch.setattr(upgrade.resources, "initialization", lambda *a: {"initialization_id": "c" * 32})
    return {"request": {"root": str(tmp_path)}}, intent, records


def test_completed_exact_transition_can_adopt(upgrade, journal):
    value, _, _ = journal
    upgrade.adoption_guard(value, "b" * 64)


@pytest.mark.parametrize("fault", ["pending", "plan", "initialization", "code", "extra", "approval", "complete_digest"])
def test_incomplete_or_stale_transition_cannot_adopt(upgrade, journal, fault):
    value, intent, records = journal
    if fault == "pending":
        del records["complete.json"]
    elif fault in {"approval", "complete_digest"}:
        result = json.loads(records["complete.json"])
        result["model_use_approved" if fault == "approval" else "intent_sha256"] = True
        records["complete.json"] = upgrade.recovery.encoded(result)
    else:
        intent[
            {
                "plan": "target_plan_sha256",
                "initialization": "initialization_id",
                "code": "controller_sha256",
                "extra": "extra",
            }[fault]
        ] = "f" * 64
        records["intent.json"] = upgrade.recovery.encoded(intent)
        records["complete.json"] = upgrade.recovery.encoded(upgrade.complete(intent))
    with pytest.raises(upgrade.checker.planner.PlanError):
        upgrade.adoption_guard(value, "b" * 64)


def test_unrelated_installation_keeps_original_admission(upgrade, tmp_path, monkeypatch):
    monkeypatch.setattr(upgrade.recovery, "private_read", lambda *a: pytest.fail("unrelated transition metadata read"))
    upgrade.adoption_guard({"request": {"root": str(tmp_path)}}, "b" * 64)
