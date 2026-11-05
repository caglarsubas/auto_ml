"""Installed HTTPS legacy kernels on the existing bounded private queue.

Synthetic qualification only. No client-held HTTP request, user code or uploaded
fitted state is an execution boundary. Original qualification cases stay intact.
"""

import copy
import hashlib
import json
import time
import uuid
from urllib.parse import urlsplit

from qualify_private_installation_workflow import require
from qualify_private_workload_envelope import dataset

KINDS = ("xgboost", "lightgbm", "catboost")
PARAMETERS = (
    "n_estimators",
    "max_depth",
    "learning_rate",
    "min_child_weight",
    "subsample",
    "colsample_bytree",
    "gamma",
    "reg_alpha",
    "reg_lambda",
)


def hpo_options():
    space = {key: {"enabled": key == "max_depth"} for key in PARAMETERS}
    space["max_depth"].update(min=1, max=2)
    return {
        "param_space": space,
        "fixed_params": {"n_estimators": 8},
        "n_iter": 2,
        "cv_folds": 2,
        "n_jobs": 1,
        "search_method": "random",
        "validation_curve_points": 2,
    }


def launch(session, file_id, operation, options):
    options = {**options, "file_id": file_id}
    preview = session.data(
        "POST",
        f"/api/jobs/datasets/{file_id}/legacy-input/",
        {"operation": operation, "options": options},
    )
    require(
        preview["kind"] == "legacy_native_execution_v1"
        and preview["budget"]["max_active"] == 2
        and preview["budget"]["seconds"] == 120
        and preview["runtime"]["native_child"]["database"] == "dummy",
        "legacy_profile",
    )
    path = (
        "/api/modeling/start/"
        if operation == "training"
        else (
            "/api/modeling/"
            + ("sfs" if operation == "sfs" else "hyperparam")
            + "/start/"
        )
    )
    request = {
        **options,
        "execution_request": {
            "request_id": str(uuid.uuid4()),
            "plan_sha256": preview["plan_sha256"],
            "inputs_sha256": preview["inputs_sha256"],
        },
    }
    queued = session.data("POST", path, request, 202)
    require(
        session.data("POST", path, request)["native_job_id"] == queued["native_job_id"],
        "legacy_launch_replay",
    )
    return queued["native_job_id"]


def finished(session, ids, seconds=135):
    deadline = time.monotonic() + seconds
    while True:
        # Legacy results permit 8 MiB, plus bounded request/event metadata.
        # Preserve the default 1 MiB limit for every original workflow request.
        rows = [json.loads(session.request("GET", "/api/jobs/" + item + "/", response_limit=10 * 1024**2)[0]) for item in ids]
        require(
            not any(r["state"] in ("blocked", "failed", "cancelled") for r in rows),
            "legacy_native_job_failed",
        )
        if all(r["state"] == "succeeded" for r in rows):
            for row in rows:
                result = row["result"]
                require(
                    row["result_sha256"]
                    and result["files"]
                    and result["files_sha256"]
                    and result["job_id"] == row["id"]
                    and row["attempts"] >= 1
                    and all(
                        result[k] is False
                        for k in (
                            "legacy_projection_updated",
                            "model_adopted",
                            "review_approved",
                            "production_use_approved",
                        )
                    ),
                    "legacy_candidate_receipt",
                )
            return rows
        require(time.monotonic() < deadline, "legacy_terminal_deadline")
        time.sleep(0.2)


def upload(session, project, task, rows=40, features=2):
    raw, semantic = dataset(task, rows, features, "random")
    file_id = session.upload(raw, "legacy-" + task + ".csv", project)
    row = session.data("GET", f"/api/declaration/{file_id}/")
    path = urlsplit(row["file"]).path
    require(path.startswith("/media/"), "legacy_uploaded_path")
    return (
        file_id,
        {
            "processed_file": path.removeprefix("/media/"),
            "business_understanding": semantic["business_understanding"],
        },
        hashlib.sha256(raw).hexdigest(),
    )


def source(row):
    return {
        "source_job_id": row["id"],
        "source_result_sha256": row["result_sha256"],
        "execution_id": row["result"]["payload"]["execution_id"],
    }


def qualify(session, value, accounts, parent, prepared, adopted, command):
    began = time.monotonic()
    records, trained = [], []
    for task in ("classification", "regression"):
        file_id, options, input_sha = upload(session, accounts["project_id"], task)
        algorithms = (
            [*KINDS, "logistic_regression", "scorecard", "isolation_forest"]
            if task == "classification"
            else list(KINDS)
        )
        for offset in range(0, len(algorithms), 2):
            pair = algorithms[offset : offset + 2]
            ids = []
            for algorithm in pair:
                request = copy.deepcopy(options)
                if algorithm == "isolation_forest":
                    request["business_understanding"]["problem_type"] = "anomaly"
                ids.append(
                    launch(
                        session,
                        file_id,
                        "training",
                        {**request, "algorithm": algorithm},
                    )
                )
            rows = finished(session, ids)
            for algorithm, row in zip(pair, rows):
                expected_task = "anomaly" if algorithm == "isolation_forest" else task
                require(
                    row["result"]["payload"]["model"]["task"] == expected_task,
                    "legacy_task_semantics",
                )
                records.append(
                    {
                        "job_id": row["id"],
                        "result_sha256": row["result_sha256"],
                        "task": expected_task,
                        "algorithm": algorithm,
                        "operation": "training",
                        "input_sha256": input_sha,
                        "elapsed_seconds": row["result"]["elapsed_seconds"],
                    }
                )
                if algorithm in KINDS:
                    trained.append((file_id, algorithm, task, row))
    for file_id, algorithm, task, row in trained:
        selection = launch(
            session,
            file_id,
            "sfs",
            {
                **source(row),
                "methods": ["backward"],
                "stopping_criteria": {"min_features": 1},
                "top_k": 1,
                "cv_folds": 2,
                "n_jobs": 1,
            },
        )
        tuning = launch(session, file_id, "hpo", {**source(row), **hpo_options()})
        searches = finished(session, [selection, tuning])
        for operation, search in zip(("sfs", "hpo"), searches):
            require(
                search["result"]["source"]
                == {
                    "job_id": row["id"],
                    "result_sha256": row["result_sha256"],
                    "execution_id": row["result"]["payload"]["execution_id"],
                },
                "legacy_source_binding",
            )
            records.append(
                {
                    "job_id": search["id"],
                    "result_sha256": search["result_sha256"],
                    "task": task,
                    "algorithm": algorithm,
                    "operation": operation,
                    "elapsed_seconds": search["result"]["elapsed_seconds"],
                }
            )
    # Explicit exact-candidate selection is separate from queue completion.
    chosen = searches[-1]
    preview = session.data("GET", f"/api/jobs/{chosen['id']}/legacy-selection/")
    choice = preview["candidates"][0]["execution_id"]
    request = {
        "request_id": str(uuid.uuid4()),
        "result_sha256": chosen["result_sha256"],
        "execution_id": choice,
        "expected_projection_sha256": preview["expected_projection_sha256"],
    }
    selected = session.data(
        "POST", f"/api/jobs/{chosen['id']}/legacy-selection/", request
    )
    replay = session.data(
        "POST", f"/api/jobs/{chosen['id']}/legacy-selection/", request
    )
    require(
        selected["currently_selected"]
        and replay["replayed"]
        and replay["currently_selected"]
        and selected["review_approved"] is selected["production_use_approved"] is False,
        "legacy_selection",
    )
    current = session.data("GET", f"/api/modeling/status/{file_id}/?selected=true")
    require(
        current["execution_id"] == choice and current["selected_for_development"],
        "legacy_selected_status",
    )
    require(len(records) == 21, "legacy_matrix_incomplete")
    from qualify_private_selection_race import qualify as qualify_race

    race = qualify_race(session, value, parent, searches)
    report = {
        "schema": "private_legacy_execution_qualification_v1",
        "installation_id": value["request"]["installation_id"],
        "application_images": value["images"],
        "synthetic_only": True,
        "customer_accepted": False,
        "release_qualified": False,
        "cases": records,
        "case_count": len(records),
        "worker_concurrency": 2,
        "max_native_seconds": 120,
        "client_disconnect_independent": True,
        "explicit_development_selection_and_replay": "passed",
        "concurrent_selection": race,
        "elapsed_seconds": time.monotonic() - began,
    }
    (parent / "legacy-execution.json").write_text(
        json.dumps(report, sort_keys=True, indent=2)
    )
    return report


# This fault kills only the exact prefork process bound to an owned fixture job.
# Neither state nor lease timestamps are edited. The child must stop on parent
# death, and the production reconciler must recover after the original lease.
LOSS = r"""
import json,os,signal,sys,time
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django;django.setup()
from execution_jobs.models import NativeJob
from execution_jobs.legacy_execution import job_root
v=json.load(sys.stdin);job=NativeJob.objects.get(pk=v['id'])
assert job.state=='running' and job.attempts==1 and job.specification['kind']=='legacy_native_execution_v1'
control=job_root(job.pk)/'attempts'/str(job.lease_token)/'control'
started=json.loads((control/'started.json').read_bytes())
request=json.loads((control/'request.json').read_bytes())
assert started['job_id']==str(job.pk) and request['job_id']==str(job.pk)
parent,child=started['parent_pid'],started['pid']
assert parent>1 and child>1 and request['parent_pid']==parent and parent!=os.getpid()
assert Path('/proc')/str(parent) != Path('/proc')/str(os.getpid())
assert not (control/'result.json').exists()
os.kill(parent,signal.SIGKILL)
deadline=time.monotonic()+5
while True:
    path=Path('/proc')/str(child)/'stat'
    if not path.exists() or path.read_text().split()[2]=='Z':break
    assert time.monotonic()<deadline
    time.sleep(.05)
job.refresh_from_db();assert job.state=='running' and job.result is None
assert not (control/'result.json').exists()
print(json.dumps({'job_id':str(job.pk),'parent_loss':'SIGKILL','child_stopped':True,
                  'lease_seconds':180,'job_state':'running','partial_publication':False}))
"""


class LossProbe:
    def before_stop(self, session, accounts, adopted, command):
        self.file_id, options, _ = upload(
            session, accounts["project_id"], "classification", rows=300, features=8
        )
        initial = launch(
            session, self.file_id, "training", {**options, "algorithm": "xgboost"}
        )
        self.trained = finished(session, [initial])[0]
        self.binding = source(self.trained)
        data = {
            **self.binding,
            **hpo_options(),
            "n_iter": 100,
            "fixed_params": {"n_estimators": 5000},
        }
        self.orphan = launch(session, self.file_id, "hpo", data)
        deadline = time.monotonic() + 30
        while True:
            row = session.data("GET", f"/api/jobs/{self.orphan}/")
            require(
                row["state"] not in ("succeeded", "failed", "blocked"),
                "legacy_loss_not_in_flight",
            )
            if any(e["event_type"] == "legacy_child_started" for e in row["events"]):
                break
            require(time.monotonic() < deadline, "legacy_child_start_deadline")
            time.sleep(0.1)
        self.source_pin = self.trained["result_sha256"]
        # The source fixture owns this worker ID; no other container is touched.
        raw = command(
            [
                "exec",
                "-i",
                adopted["services"]["worker"]["container_id"],
                "python",
                "-c",
                LOSS,
            ],
            data=json.dumps({"id": self.orphan}).encode(),
        )
        self.loss = json.loads(raw)
        from qualify_private_native_loss import NativeLossProbe

        self.native = NativeLossProbe()
        self.native.before_stop(session, accounts, adopted, command)
        # Cancel another request without assuming that a dispatcher race cannot
        # claim it. Both queued and in-flight cancellation must remain terminal.
        self.cancelled = launch(
            session,
            self.file_id,
            "sfs",
            {
                **self.binding,
                "methods": ["backward"],
                "stopping_criteria": {"min_features": 1},
                "top_k": 1,
                "cv_folds": 2,
                "n_jobs": 1,
            },
        )
        session.data("POST", f"/api/jobs/{self.cancelled}/", {"action": "cancel"})

    def after_restore(self, session, api, boundary):
        # Keep the original 100-trial request immutable. It obeys its exact
        # 120-second deadline; it must succeed or this qualification fails.
        rows = finished(session, [self.orphan])
        row = rows[0]
        require(
            row["attempts"] == 2
            and row["result"]["source"]
            == {
                "job_id": self.trained["id"],
                "result_sha256": self.source_pin,
                "execution_id": self.binding["execution_id"],
            },
            "legacy_loss_recovery_binding",
        )
        retained = session.data("GET", f"/api/jobs/{self.trained['id']}/")
        cancelled = session.data("GET", f"/api/jobs/{self.cancelled}/")
        require(
            retained["result_sha256"] == self.source_pin
            and cancelled["state"] == "cancelled",
            "legacy_restore_completed_or_cancelled_changed",
        )
        ids = [self.trained["id"], self.orphan, self.cancelled]
        before = boundary(api, "evidence", ids=ids)
        boundary(api, "duplicates", ids=ids)
        deadline = time.monotonic() + 30
        while any(boundary(api, "broker").values()):
            require(time.monotonic() < deadline, "legacy_duplicate_drain")
            time.sleep(0.2)
        require(
            boundary(api, "evidence", ids=ids) == before, "legacy_duplicate_publication"
        )
        return {
            "schema": "private_legacy_worker_loss_v1",
            "native_worker_loss": self.native.after_restore(session, api, boundary),
            "synthetic_only": True,
            "parent_loss": self.loss,
            "original_lease_seconds": 180,
            "lease_clock_modified": False,
            "completed_source_preserved": True,
            "cancelled_preserved": True,
            "recovered_attempts": row["attempts"],
            "result_sha256": row["result_sha256"],
            "duplicate_delivery": "no_state_or_result_change",
            "customer_accepted": False,
        }
