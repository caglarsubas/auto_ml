"""Coherent synthetic workflow on the caller's owned, installed HTTPS services.

No fixture worker, client-side training, direct database seed or test-client
shortcut is used. This is installation qualification, not model-use approval.
"""

import hashlib
import json
import os
import sys
import time
import uuid
from http.cookies import SimpleCookie
from pathlib import Path

import private_schema_init as schema_init

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ("final_holdout_accessed", "legacy_projection_updated", "model_adopted", "review_approved", "production_use_approved")

OFFLINE_CODE = r"""
import json,sys
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from deployment import native_candidate as n
v=json.load(sys.stdin)
raw=bytes.fromhex(v['export']);data=bytes.fromhex(v['input']);pin=v['sha256']
left=n.score(raw,pin,data,chunk_size=1)
assert left==n.score(raw,pin,data,chunk_size=10000)
sys.stdout.buffer.write(n.canonical(left))
"""


def require(condition, code):
    if not condition:
        raise schema_init.checker.planner.PlanError("installed_workflow_" + code)


def owned(value, parent):
    require(sys.platform == "linux" and os.geteuid() == 0 and parent.parent == Path("/srv")
            and schema_init.resources.re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
            and value["request"]["root"] == str(parent / "installation"), "scope_required")


def offline_score(value, prepared, raw_export, export_sha, raw_input, command):
    """Use the exact installed image; the build host may have another Python.

    No network, installation mounts, credentials, Docker socket or pickle is
    available to this fixed safe-JSON reader. Only synthetic input uses stdin.
    """
    m = schema_init.resources
    binding = schema_init.startup.labels(value, prepared)
    labels = {**binding, m.LABEL + "role": "installation-offline-scoring"}
    args = ["container", "create", "--name", "declarai-offline-" + uuid.uuid4().hex, "--pull", "never",
            "--network", "none", "--read-only", "--user", "10001:10001", "--cap-drop", "ALL", "--security-opt",
            "no-new-privileges:true", "--cpus", "1", "--memory", "1g", "--pids-limit", "64", "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700", "--entrypoint", "python", "-i"]
    for key, item in labels.items():
        args += ["--label", key + "=" + item]
    identifier = command([*args, value["images"]["api"], "-I", "-c", OFFLINE_CODE]).decode().strip()
    require(bool(m.re.fullmatch(r"[0-9a-f]{64}", identifier)), "offline_identity")
    try:
        info = m.inspect("container", identifier)
        host, config = info["HostConfig"], info["Config"]
        require(info["Image"] == value["images"]["api"] and config["Labels"] == labels
                and config["User"] == "10001:10001" and config["Entrypoint"] == ["python"]
                and config["Cmd"] == ["-I", "-c", OFFLINE_CODE] and config["OpenStdin"] is True
                and host["NetworkMode"] == "none" and host["ReadonlyRootfs"] is True and host["Privileged"] is False
                and host["CapDrop"] == ["ALL"] and not host.get("CapAdd") and host["SecurityOpt"] == ["no-new-privileges:true"]
                and host["PidsLimit"] == 64 and host["NanoCpus"] == 1_000_000_000 and host["Memory"] == 1024**3
                and not host.get("Binds") and not host.get("Mounts") and not host.get("VolumesFrom")
                and not host.get("PortBindings") and not host.get("Devices") and not host.get("DeviceRequests")
                and all(mount["Type"] == "tmpfs" and mount["Destination"] == "/tmp" for mount in info.get("Mounts", [])), "offline_profile")
        payload = json.dumps({"export": raw_export.hex(), "input": raw_input.hex(), "sha256": export_sha}).encode()
        require(len(payload) <= 3 * 1024**2, "offline_input_budget")
        output = command(["container", "start", "--attach", "--interactive", identifier], data=payload)
        state = m.inspect("container", identifier)["State"]
        require(state["Running"] is False and state["ExitCode"] == 0 and len(output) <= 1024**2, "offline_exit")
        return json.loads(output)
    finally:
        info = m.inspect("container", identifier)
        require(info["Config"].get("Labels") == labels, "offline_cleanup_owner")
        command(["container", "rm", "--force", identifier])


class Session:
    def __init__(self, value, parent):
        self.value = value
        self.context = schema_init.adopter.client_context(parent / "server.crt")
        self.host, self.port = schema_init.checker.planner.authority(value["request"]["authority"])
        self.cookies = SimpleCookie()
        self.csrf = None

    def request(self, method, path, body=None, status=200, content_type="application/json"):
        require(path.startswith("/api/") and len(path) < 1024, "path_invalid")
        authority = self.value["request"]["authority"]
        headers = {"Host": authority, "Origin": "https://" + authority}
        if self.cookies:
            headers["Cookie"] = "; ".join(k + "=" + v.value for k, v in self.cookies.items())
        if self.csrf:
            headers["X-CSRFToken"] = self.csrf
        if body is not None:
            headers["Content-Type"] = content_type
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
        connection = schema_init.adopter.DeclaredHTTPS(self.value["request"]["bind_ip"], self.port, self.host, self.context)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(1024 * 1024 + 1)
            # Do not emit credentials, cookies, response bodies or arbitrary errors.
            require(response.status == status and len(raw) <= 1024 * 1024, "https_status_or_size")
            for key, value in response.getheaders():
                if key.lower() == "set-cookie":
                    self.cookies.load(value)
            return raw, dict((k.lower(), v) for k, v in response.getheaders())
        finally:
            connection.close()

    def data(self, method, path, body=None, status=200):
        raw, _ = self.request(method, path, body, status)
        return json.loads(raw)

    def upload(self, raw, name, project):
        boundary = "installation-" + uuid.uuid4().hex
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="column_separator"\r\n\r\ncomma\r\n'
                   f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                   'Content-Type: text/csv\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
        response, _ = self.request("POST", "/api/declaration/?project_id=" + project, payload, 201,
                                   "multipart/form-data; boundary=" + boundary)
        identifier = json.loads(response)["id"]
        require(type(identifier) is int and identifier > 0, "dataset_invalid")
        return identifier

    def finished(self, identifier):
        deadline = time.monotonic() + 30
        while True:
            job = self.data("GET", "/api/jobs/" + identifier + "/")
            if job["state"] in {"succeeded", "failed", "cancelled"}:
                require(job["state"] == "succeeded", "durable_job_failed")
                return job
            require(time.monotonic() < deadline, "durable_job_deadline")
            time.sleep(.2)


def qualify(value, accounts, passwords, parent, prepared, command, observer=None):
    owned(value, parent)
    session = Session(value, parent)
    anonymous = session.data("GET", "/api/auth/session/")
    session.csrf = anonymous["csrf_token"]
    login = session.data("POST", "/api/auth/login/", {
        "username": "fixture-developer-" + parent.name.removeprefix("declarai-p37-"), "password": passwords["developer"]})
    require(login["authenticated"] is True and login["user"]["id"] == accounts["accounts"]["developer"]["subject_user_id"], "login")
    session.csrf = login["csrf_token"]
    project = accounts["project_id"]
    input_raw = b"z,x\n,0.1\n3,0.6\n9,0.9\n"
    input_id = session.upload(input_raw, "features.csv", project)
    proofs = []
    handles = []
    for task in ("classification", "regression"):
        lines = ["x,z,outcome"]
        for index in range(40):
            outcome = ("bad" if index % 2 else "good") if task == "classification" else str(index / 7 + index % 3)
            lines.append(f"{index / 40},{index % 7},{outcome}")
        dataset = session.upload(("\n".join(lines) + "\n").encode(), task + ".csv", project)
        base = f"/api/jobs/datasets/{dataset}/"
        options = {"data_role": "development_only", "features": ["x", "z"], "validation": {"strategy": "random", "n_splits": 2},
                   "business_understanding": {"problem_type": task, "objective": "Synthetic installed workflow", "population": "Synthetic rows",
                    "prediction_horizon": "12 months", "feature_availability": {"default": "available_at_prediction"},
                    "target_contract": {"target_column": "outcome", "positive_class": "bad" if task == "classification" else None,
                                        "event_definition": "Synthetic recorded outcome", "label_maturity": "Complete follow-up"},
                    "success_criteria": {"primary_metric": "roc_auc" if task == "classification" else "rmse"}}}
        preview = session.data("POST", base + "training-input/?project_id=" + project, options)
        submission = dict(options, **{key: preview[key] for key in ("kind", "input_sha256", "training_sha256")}, request_id=str(uuid.uuid4()))
        queued = session.data("POST", base + "?project_id=" + project, submission, 202)
        require(session.data("POST", base + "?project_id=" + project, submission)["id"] == queued["id"], "training_retry")
        trained = session.finished(queued["id"])
        require(all(trained["result"][flag] is False for flag in FLAGS), "training_approval")
        export, headers = session.request("GET", f'/api/jobs/{trained["id"]}/candidate/?sha256={trained["result_sha256"]}&project_id={project}')
        export_sha = headers["x-declarai-export-sha256"]
        require(hashlib.sha256(export).hexdigest() == export_sha, "export_digest")
        candidate = json.loads(export)
        require(candidate["result"]["prediction_contract"]["task"] == task, "task_semantics")
        expected = offline_score(value, prepared, export, export_sha, input_raw, command)
        preview = session.data("POST", f'/api/jobs/{trained["id"]}/scoring-input/?project_id={project}', {
            "input_file_id": input_id, "training_result_sha256": trained["result_sha256"]})
        submission = {key: preview[key] for key in ("kind", "training_job_id", "training_result_sha256", "input_file_id", "input_sha256", "scoring_sha256")}
        submission["request_id"] = str(uuid.uuid4())
        queued = session.data("POST", base + "?project_id=" + project, submission, 202)
        scored = session.finished(queued["id"])
        scores, headers = session.request("GET", f'/api/jobs/{scored["id"]}/scores/?sha256={scored["result_sha256"]}')
        require(hashlib.sha256(scores).hexdigest() == scored["result_sha256"] == headers["x-declarai-receipt-sha256"], "scoring_digest")
        result = json.loads(scores)
        require(result == scored["result"] and result["scores"] == expected["scores"] and result["n_scored"] == 3
                and result["training_result_sha256"] == trained["result_sha256"] and result["export_sha256"] == export_sha
                and all(result[flag] is False for flag in FLAGS), "scoring_parity_or_approval")
        require(session.data("POST", base + "?project_id=" + project, submission)["id"] == scored["id"], "scoring_retry")
        require(session.data("GET", f'/api/jobs/{trained["id"]}/')["result_sha256"] == trained["result_sha256"], "training_immutable")
        proofs.append({"task": task, "training_result_sha256": trained["result_sha256"], "export_sha256": export_sha,
                       "scoring_result_sha256": scored["result_sha256"], "rows": 3, "prediction_and_chunk_parity": "passed"})
        handles.append({"task": task, "dataset_id": dataset, "input_file_id": input_id, "training": trained,
                        "scoring": scored, "export": export, "scores": scores})
    if observer is not None:
        observer(session, handles)
    require(session.data("POST", "/api/auth/logout/", {})["authenticated"] is False, "logout")
    return {"schema": "private_installed_workflow_v1", "actual_installed_tls_api_worker_dispatcher": "passed", "workflows": proofs,
            "duplicate_submission_single_job": "passed", "model_adopted": False, "production_use_approved": False,
            "credential_or_session_values_retained": False, "operator_installation_modified": False}
