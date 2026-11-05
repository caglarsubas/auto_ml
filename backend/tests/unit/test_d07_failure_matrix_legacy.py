"""Independent legacy matrix work unit; every original fault and fit is retained."""

import subprocess
import time
import uuid
from pathlib import Path

import pytest

from execution_jobs import service, legacy_execution as legacy
from tests.unit.test_durable_legacy_execution import options as legacy_options
from tests.unit.test_durable_training_search import world as native_world  # noqa: F401
from tests.unit.test_d07_failure_matrix import row, fences, execute_with_lost_ack, report

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


def test_legacy_operation_failure_matrix(native_world, monkeypatch):
    w = native_world
    actor = w.users["developer"]

    def admit(operation, options):
        preview = legacy.preview(actor, w.file_id, operation, options)
        data = {"kind": legacy.KIND, "operation": operation, "options": options,
                "request_id": str(uuid.uuid4()), "plan_sha256": preview["plan_sha256"],
                "inputs_sha256": preview["inputs_sha256"]}
        queued = service.submit(actor, w.file_id, data)
        assert service.submit(actor, w.file_id, data)["id"] == queued["id"]
        return queued["id"]

    source_id = admit("training", legacy_options(w))
    service.execute(source_id)
    source = row(source_id)
    assert source.state == "succeeded"
    binding = {"file_id": w.file_id, "source_job_id": source_id, "source_result_sha256": source.result_sha256,
               "execution_id": source.result["payload"]["execution_id"]}
    values = {"training": legacy_options(w),
              "sfs": {**binding, "methods": ["backward"], "stopping_criteria": {"min_features": 1},
                      "top_k": 1, "cv_folds": 2, "n_jobs": 1},
              "hpo": {**binding, "n_iter": 2, "cv_folds": 2, "n_jobs": 1, "validation_curve_points": 2,
                      "search_method": "random", "fixed_params": {"n_estimators": 5}},
              "champion": {**binding, "features": ["x"], "hyperparam": {"n_estimators": 5}}}
    records = {}
    for operation, options in values.items():
        factory = lambda: admit(operation, options)
        records["legacy_" + operation] = fences(factory, actor) + [execute_with_lost_ack(factory, monkeypatch)]
    assert not (w.root / "modeling" / f"{w.file_id}_status.json").exists()
    report("legacy", records)



def test_child_does_not_announce_readiness_before_model_handlers_import(native_world, monkeypatch):
    from execution_jobs import legacy_process
    from tests.unit.test_durable_legacy_execution import launch

    w = native_world
    original = subprocess.Popen
    observed = []

    def start(args, **kwargs):
        control = Path(args[-1])
        arrived, release = control / "import-arrived", control / "import-release"
        hook = (
            "import builtins,time;from pathlib import Path;original_import=builtins.__import__\n"
            "def import_gate(name,globals=None,locals=None,fromlist=(),level=0):\n"
            " if name=='modeling' and 'views' in (fromlist or ()):\n"
            f"  Path({str(arrived)!r}).touch();limit=time.monotonic()+10\n"
            f"  while not Path({str(release)!r}).exists():\n"
            "   assert time.monotonic()<limit;time.sleep(.01)\n"
            " return original_import(name,globals,locals,fromlist,level)\n"
            "builtins.__import__=import_gate\n"
        )
        command = list(args)
        command[command.index("-c") + 1] = hook + command[command.index("-c") + 1]
        child = original(command, **kwargs)
        try:
            deadline = time.monotonic() + 10
            while not arrived.exists():
                assert child.poll() is None and time.monotonic() < deadline
                time.sleep(.01)
            assert not (control / "started.json").exists(), "readiness preceded handler imports"
            observed.append(True)
        except BaseException:
            child.kill()
            child.wait(timeout=3)
            raise
        finally:
            release.touch()
        return child

    identifier, _, _ = launch(w, "training", legacy_options(w))
    monkeypatch.setattr(legacy_process.subprocess, "Popen", start)
    service.execute(identifier)
    assert observed == [True] and row(identifier).state == "succeeded"

