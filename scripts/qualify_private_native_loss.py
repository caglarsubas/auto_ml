"""Kill an exact owned native Celery child at a real publication lock wait."""

import hashlib
import json
import time
import uuid
from pathlib import Path

from qualify_private_installation_workflow import require

LOSS = r"""
import json,os,signal,sys,time
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django;django.setup()
from django.db import connection,transaction
from access_control.models import ProjectMembership
from execution_jobs.models import NativeJob
from execution_jobs.tasks import run_native_job
from execution_jobs import service
v=json.load(sys.stdin);job=NativeJob.objects.get(pk=v['id'])
assert job.state=='queued' and job.attempts==0 and job.result is None
assert job.specification['kind'] in {service.training_search.KIND,service.training_scoring.KIND}
assert job.specification==v['specification']
pin_key='training_sha256' if job.specification['kind']==service.training_search.KIND else 'scoring_sha256'
execution_pin=job.specification[pin_key]
specification_pin=service.digest(job.specification)
assert service.LIMITS['lease_seconds']==180 and service.LIMITS['max_active']==2
with transaction.atomic():
    ProjectMembership.objects.select_for_update().get(project=job.project,actor_id=job.authority['actor_id'])
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_backend_pid()');holder=cursor.fetchone()[0]
    run_native_job.apply_async(args=[str(job.pk)],retry=False)
    deadline=time.monotonic()+10
    while True:
        # The worker has performed its real numerical work and now waits for
        # this exact role lock in the production publication transaction.
        with connection.cursor() as cursor:
            # PostgreSQL statistics snapshots are cached within a transaction;
            # keep the role lock while reading current activity, not its first
            # pre-delivery snapshot. This changes no job state or lease clock.
            cursor.execute('SELECT pg_stat_clear_snapshot()')
            cursor.execute("SELECT client_port FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid)) AND query LIKE %s",
                           [holder,'%access_control_projectmembership%'])
            waiting=cursor.fetchall()
        if waiting:
            assert len(waiting)==1
            port=waiting[0][0]
            break
        if time.monotonic()>=deadline:
            job.refresh_from_db()
            raise AssertionError({'reason':'native_publication_wait_not_observed','state':job.state,
                                  'attempts':job.attempts,'reason_code':job.reason_code,
                                  'events':list(job.events.values_list('event_type',flat=True))})
        time.sleep(.025)
    # Remote Celery control stays disabled. Bind the blocking database client's
    # exact TCP port to its socket inode and owning process inside this owned
    # worker's PID/network namespaces; never infer a PID from a name alone.
    inodes=set()
    for table in ('tcp','tcp6'):
        for line in (Path('/proc/net')/table).read_text().splitlines()[1:]:
            fields=line.split()
            if int(fields[1].rsplit(':',1)[1],16)==port and int(fields[2].rsplit(':',1)[1],16)==5432:
                inodes.add(fields[9])
    assert len(inodes)==1
    owners=[]
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)<=1 or int(process.name)==os.getpid():continue
        try:
            if any(os.readlink(fd)=='socket:['+next(iter(inodes))+']' for fd in (process/'fd').iterdir()):
                owners.append(int(process.name))
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    assert len(owners)==1
    pid=owners[0]
    assert b'celery' in (Path('/proc')/str(pid)/'cmdline').read_bytes()
    job.refresh_from_db();assert job.state=='running' and job.attempts==1 and job.result is None
    lease=job.lease_until;token=job.lease_token
    os.kill(pid,signal.SIGKILL)
    deadline=time.monotonic()+2
    while True:
        stat=Path('/proc')/str(pid)/'stat'
        if not stat.exists() or stat.read_text().split()[2]=='Z':break
        assert time.monotonic()<deadline,'native_worker_did_not_stop'
        time.sleep(.025)
job.refresh_from_db()
assert job.state=='running' and job.result is None and not job.result_sha256
assert job.lease_until==lease and job.lease_token==token
assert not job.events.filter(event_type='succeeded').exists()
print(json.dumps({'schema':'private_native_worker_loss_v1','job_id':str(job.pk),'actual_prefork_SIGKILL':True,
                  'publication_role_lock_wait_observed':True,'request_sha256':job.request_sha256,
                  'pid_binding':'blocked_database_client_port_socket_inode_owner','celery_remote_control_enabled':False,
                  'execution_kind':job.specification['kind'],'execution_pin_key':pin_key,'execution_sha256':execution_pin,
                  'specification_sha256':specification_pin,'job_state':job.state,'lease_until':job.lease_until.isoformat(),
                  'attempts':job.attempts,'lease_seconds':180,'lease_clock_modified':False,
                  'partial_publication':False,'synthetic_only':True}))
"""


class NativeLossProbe:
    def capture_existing(self, session, identifier, adopted, command):
        dispatcher = adopted["services"]["dispatcher"]["container_id"]
        paused = command(["container", "inspect", "--format", "{{json .State.Paused}}", dispatcher])
        require(json.loads(paused) is True, "native_loss_dispatcher_not_paused")
        self.queued = session.data("GET", f"/api/jobs/{identifier}/")
        require(self.queued["state"] == "queued" and self.queued["attempts"] == 0, "native_loss_not_queued")
        output = command(["exec", "-i", adopted["services"]["worker"]["container_id"], "python", "-c", LOSS],
                         data=json.dumps({"id": identifier, "specification": self.queued["specification"]}).encode())
        self.loss = json.loads(output)
        self.loss["controller_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        return {"state": self.loss["job_state"], "lease_until": self.loss["lease_until"],
                "attempts": self.loss["attempts"], "lease_seconds": self.loss["lease_seconds"]}

    def before_stop(self, session, accounts, adopted, command):
        from qualify_private_legacy_execution import upload

        file_id, options, _ = upload(session, accounts["project_id"], "classification", rows=300, features=8)
        self.file_id = file_id
        base = f"/api/jobs/datasets/{file_id}/"
        options = {"data_role": "development_only", "features": ["x" + str(i) for i in range(8)],
                   "validation": {"strategy": "random", "n_splits": 2},
                   "business_understanding": options["business_understanding"]}
        preview = session.data("POST", base + "training-input/", options)
        data = {**options, **{k: preview[k] for k in ("kind", "input_sha256", "training_sha256")},
                "request_id": str(uuid.uuid4())}
        dispatcher = adopted["services"]["dispatcher"]["container_id"]
        command(["container", "pause", dispatcher])
        try:
            queued = session.data("POST", base, data, 202)
            require(session.data("POST", base, data)["id"] == queued["id"], "native_loss_admission_replay")
            self.capture_existing(session, queued["id"], adopted, command)
        finally:
            command(["container", "unpause", dispatcher])

    def after_restore(self, session, api, boundary):
        identifier = self.queued["id"]
        deadline = time.monotonic() + 30
        while True:
            row = session.data("GET", f"/api/jobs/{identifier}/")
            if row["state"] in {"succeeded", "failed", "blocked", "cancelled"}:
                break
            require(time.monotonic() < deadline, "native_loss_restore_deadline")
            time.sleep(.2)
        require(row["state"] == "succeeded" and row["attempts"] == 2
                and row["result"][self.loss["execution_pin_key"]] == self.loss["execution_sha256"]
                and row["specification"] == self.queued["specification"]
                and len([e for e in row["events"] if e["event_type"] == "succeeded"]) == 1,
                "native_loss_recovery_binding")
        before = boundary(api, "evidence", ids=[identifier])
        boundary(api, "duplicates", ids=[identifier])
        deadline = time.monotonic() + 30
        while any(boundary(api, "broker").values()):
            require(time.monotonic() < deadline, "native_loss_duplicate_drain")
            time.sleep(.2)
        require(boundary(api, "evidence", ids=[identifier]) == before, "native_loss_duplicate_publication")
        return {**self.loss, "recovered_attempts": row["attempts"], "result_sha256": row["result_sha256"],
                "unchanged_request": True, "terminal_events": 1, "duplicate_delivery": "no_state_or_result_change",
                "review_approved": False, "production_use_approved": False, "customer_accepted": False}
