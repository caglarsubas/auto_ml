"""Owned native task qualification of the sealed private worker/dispatcher.

The API fixture owns credentials/artifacts; a separate private volume contains
synthetic observer state. Only the observer receives harness code through stdin.
Service containers run the unchanged image entrypoint, with no source mounts.
"""

import json
import re
import subprocess
import uuid

from qualify_private_api_image import PrivateCheckFailed, command


PROBE = r'''
import hashlib,json,os,secrets,sys,time,uuid
from pathlib import Path
os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
import django;django.setup()
import numpy as np
import pandas as pd
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from access_control import projects
from access_control.models import Project,ProjectMembership,ProjectPolicy
from declaration.models import Declaration
from deployment.deploy_utils import score_frame
from execution_jobs import service,csv_scoring
from execution_jobs.models import NativeJob
from execution_jobs.tasks import run_native_job
from execution_jobs.preflight import check_runtime
value=json.load(sys.stdin)
assert settings.DECLARAI_RUNTIME_PROFILE=='private' and os.environ.get('DECLARAI_TEST_INSTALLATION')=='1'
assert connection.vendor=='postgresql' and connection.settings_dict['NAME']=='declarai_fixture'
with connection.cursor() as cursor:
    cursor.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()');assert cursor.fetchone()[0]
check_runtime()
state_file=Path('/fixture/state.json');request={'secure':True,'HTTP_HOST':settings.ALLOWED_HOSTS[0]}
def post(client,path,data,status=200):
    csrf=client.get('/api/auth/session/',**request).json()['csrf_token']
    response=client.post(path,json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=csrf,
                         HTTP_ORIGIN=settings.CSRF_TRUSTED_ORIGINS[0],**request)
    assert response.status_code==status, (path,response.status_code)
    return response.json()
def input_file(token,label,project,frame):
    relative='data_files/fixed-job-'+token+'-'+label+'.csv';path=Path(settings.MEDIA_ROOT)/relative
    path.parent.mkdir(parents=True,exist_ok=True);frame.to_csv(path,index=False)
    dataset=Declaration.objects.create(name=label,original_name=path.name,file=relative)
    projects.bind_dataset(dataset,project.pk,source='disposable_fixed_job_fixture');return dataset
def snapshot(ids):
    return {label:{'receipt':service.serialize(job),'full_result':job.result,'authority':job.authority,
                   'request_sha256':job.request_sha256,'specification':job.specification}
            for label,job in ((label,NativeJob.objects.get(pk=identifier)) for label,identifier in ids.items())}
def artifact_hashes():
    return {p.relative_to(settings.MEDIA_ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file()}
if value['phase']=='seed':
    assert not state_file.exists()
    token=uuid.uuid4().hex;ProjectPolicy.objects.get_or_create(pk=1)
    project=Project.objects.create(name='Synthetic sealed-image execution '+token)
    users,clients={},{}
    for role in ['developer','reviewer','revoked','outsider']:
        actor=get_user_model().objects.create_user(username='fixed-job-'+role+'-'+token,password=secrets.token_urlsafe(32))
        if role!='outsider':
            ProjectMembership.objects.create(project=project,actor=actor,role='developer' if role=='revoked' else role)
        # Real cookie/CSRF login with a fresh password; state stays in the private observer volume.
        password=secrets.token_urlsafe(32);actor.set_password(password);actor.save()
        client=Client(enforce_csrf_checks=True)
        post(client,'/api/auth/login/',{'username':actor.username,'password':password})
        users[role],clients[role]=actor,client
    rng=np.random.default_rng(25);x,other=rng.normal(size=160),rng.normal(size=160)
    fixtures,ids={},{}
    for task in ['classification','regression']:
        outcomes=np.where(x+0.4*other>0,'bad','good') if task=='classification' else 2*x-other
        model=input_file(token,task+'-model',project,pd.DataFrame({'x':x,'other':other,'outcome':outcomes}))
        declared={'problem_type':task,'objective':'Predict the synthetic outcome','population':'Synthetic applicants',
                  'prediction_horizon':'12 months','feature_availability':{'default':'available_at_prediction'},
                  'target_contract':{'target_column':'outcome','positive_class':'bad','event_definition':'Synthetic outcome',
                                     'label_maturity':'Complete follow-up'},
                  'success_criteria':{'primary_metric':'roc_auc' if task=='classification' else 'rmse',
                                      'cost_matrix':{'fn_cost':4,'fp_cost':1}}}
        trained=post(clients['developer'],'/api/modeling/start/',{'file_id':model.pk,'processed_file':model.file.name,
                     'algorithm':'logistic_regression' if task=='classification' else 'xgboost','business_understanding':declared})
        assessed=post(clients['developer'],'/api/evaluation/run/',{'file_id':model.pk,'execution_id':trained['execution_id']})
        bundle=post(clients['developer'],'/api/deployment/bundle/',{'file_id':model.pk,'execution_id':trained['execution_id'],
                    'assessment_id':assessed['evaluation']['holdout_access_id']})
        frame=pd.DataFrame({'other':np.linspace(2,-2,650),'x':np.linspace(-3,3,650)})
        source=input_file(token,task+'-input',project,frame)
        expected=score_frame(model.pk,pd.read_csv(source.get_file_path()),bundle['bundle_id'])
        if task=='classification':assert expected['scores_calibrated'] is True
        fixtures[task]={'expected':expected,'source_id':source.pk}
        for label in ['queued','cancelled','changed','missing']+(['revoked'] if task=='classification' else []):
            selected=input_file(token,task+'-'+label,project,frame) if label in {'changed','missing'} else source
            role='revoked' if label=='revoked' else 'developer'
            metadata=clients[role].get(f'/api/jobs/datasets/{selected.pk}/input/',**request);assert metadata.status_code==200
            payload={'request_id':str(uuid.uuid4()),'kind':csv_scoring.KIND,'bundle_id':bundle['bundle_id'],
                     'manifest_sha256':bundle['manifest_sha256'],'input_file_id':selected.pk,'input_sha256':metadata.json()['sha256']}
            receipt=post(clients[role],f'/api/jobs/datasets/{model.pk}/',payload,202);ids[task+'-'+label]=receipt['id']
            replay=post(clients[role],f'/api/jobs/datasets/{model.pk}/',payload,200)
            assert replay['id']==receipt['id'] and replay['replayed'] is True
            if label=='cancelled':post(clients[role],f"/api/jobs/{receipt['id']}/",{'action':'cancel'})
            if label=='changed':Path(selected.get_file_path()).write_text('other,x\n999,999\n')
            if label=='missing':Path(selected.get_file_path()).unlink()
        if task=='classification':
            receipt=service.submit(users['reviewer'],model.pk,{'request_id':str(uuid.uuid4()),'kind':service.KIND,
                                   'bundle_id':bundle['bundle_id'],'manifest_sha256':bundle['manifest_sha256']})
            ids['integrity-queued']=receipt['id']
    projects.operator_change({'operation':'member','project_id':str(project.pk),'user':users['revoked'].username,'role':'none'},
                             uuid.uuid4(),'disposable-fixed-image')
    state={'ids':ids,'fixtures':fixtures,'jobs':snapshot(ids),'project_id':str(project.pk),'artifacts':artifact_hashes(),
           'sessions':{role:client.cookies[settings.SESSION_COOKIE_NAME].value for role,client in clients.items()}}
    state_file.write_text(json.dumps(state));state_file.chmod(0o600)
    print(json.dumps({'phase':'seed','jobs':len(ids),'rows_per_task':650,'trusted_native_fit':'passed'}));sys.exit(0)
state=json.loads(state_file.read_text());ids=state['ids']
if value['phase']=='verify':
    until=time.monotonic()+45
    while time.monotonic()<until:
        if all(NativeJob.objects.get(pk=identifier).state in service.TERMINAL for identifier in ids.values()):break
        time.sleep(0.1)
    else:raise RuntimeError('Fixed-image tasks did not complete.')
    clients={}
    for role,session in state['sessions'].items():
        client=Client(enforce_csrf_checks=True);client.cookies[settings.SESSION_COOKIE_NAME]=session;clients[role]=client
    for label,identifier in ids.items():
        task,scenario=label.split('-',1);job=NativeJob.objects.get(pk=identifier);original=state['jobs'][label]
        assert job.authority==original['authority'] and job.request_sha256==original['request_sha256']
        assert job.specification==original['specification']
        assert service.serialize(job)['events'][:len(original['receipt']['events'])]==original['receipt']['events']
        if scenario=='cancelled':assert snapshot({label:identifier})[label]==original
        elif scenario in {'changed','missing','revoked'}:
            assert job.state=='blocked' and job.result is None and not job.result_sha256
            assert job.reason_code=={'changed':'job_input_changed','missing':'job_package_or_budget_invalid','revoked':'job_authority_changed'}[scenario]
        else:
            assert job.state=='succeeded' and job.attempts==1 and job.events.filter(event_type='succeeded').count()==1
            assert job.result_sha256==service.digest(job.result)
            if task!='integrity':
                np.testing.assert_allclose(job.result['scores'],state['fixtures'][task]['expected']['scores'],atol=1e-12,rtol=1e-12)
                url=f"/api/jobs/{job.pk}/scores/?sha256={job.result_sha256}&project_id={state['project_id']}"
                response=clients['reviewer'].get(url,**request)
                assert response.status_code==200 and response.content==csv_scoring.canonical_bytes(job.result)
                assert len(response.json()['scores'])==650 and response['Cache-Control']=='no-store'
                assert clients['outsider'].get(url,**request).status_code==403
                assert clients['revoked'].get(url,**request).status_code==403
    assert artifact_hashes()==state['artifacts']
    state['terminal']=snapshot(ids);state_file.write_text(json.dumps(state))
    print(json.dumps({'phase':'verify','sealed_worker_dispatcher_completion':'passed','native_scoring_parity':'passed',
                      'calibrated_classification':True,'rows_per_task':650,'jobs':len(ids),'queued_cancellation':'passed',
                      'changed_missing_inputs_revocation':'blocked','authorized_full_receipts':'passed'}));sys.exit(0)
assert value['phase'] in {'duplicates','settled'} and snapshot(ids)==state['terminal']
# The owning controller has stopped its dispatcher. This dedicated synthetic
# broker DB has no other producers/consumers. Observe ACK drain, not a timed sleep.
from backend.celery import app
with app.connection_for_write() as broker:
    channel=broker.channel();client=channel.client
    queues=[channel._q_for_pri(app.conf.task_default_queue,priority) for priority in channel.priority_steps]
    def pending():return sum(client.llen(q) for q in queues)+client.hlen(channel.unacked_key)+client.zcard(channel.unacked_index_key)
    assert pending()==0
    if value['phase']=='duplicates':
        deliveries=[run_native_job.apply_async(args=[identifier],retry=False).id for identifier in ids.values() for _ in range(2)]
        assert len(deliveries)==20 and len(set(deliveries))==20
    until=time.monotonic()+45
    while time.monotonic()<until:
        if pending()==0:break
        time.sleep(0.1)
    else:raise RuntimeError('Fixed-image duplicate deliveries were not acknowledged.')
assert snapshot(ids)==state['terminal'] and artifact_hashes()==state['artifacts']
print(json.dumps({'phase':value['phase'],'duplicate_broker_drained':'passed',
                  'terminal_history_artifacts_unchanged':'passed','deployment_qualified':False,'expert_isolation_qualified':False}))
'''


def qualify_jobs(image_id, network, installation, artifacts, env_file, reports):
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
        or not network.startswith("declarai-fixture-")
        or not all(name.startswith("declarai-fixed-api-") for name in (installation, artifacts))
    ):
        raise RuntimeError("Requires exact image and owning disposable API fixture.")
    prefix = "declarai-fixed-jobs-" + uuid.uuid4().hex[:12]
    state = prefix + "-observer-state"
    containers = []
    volumes = []
    common = [
        "--pull", "never", "--network", network, "--read-only", "--cpus", "2", "--memory", "2g",
        "--pids-limit", "256", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001",
        "--env-file", str(env_file), "-v", installation + ":/installation:ro", "-v", artifacts + ":/artifacts",
    ]
    roles = {}
    summaries = []

    def probe(phase):
        output = command(
            ["docker", "run", "--rm", "-i", *common, "-v", state + ":/fixture", "--entrypoint", "python",
             image_id, "-c", PROBE], data=json.dumps({"phase": phase}).encode(), timeout=180,
        )
        # Django/native model diagnostics precede the one safe receipt line.
        receipt = json.loads(output.decode().splitlines()[-1])
        if receipt.get("phase") != phase:
            raise RuntimeError("Fixed-image observer receipt mismatch.")
        summaries.append(receipt)

    try:
        command(["docker", "volume", "create", state])
        volumes.append(state)
        command(
            ["docker", "run", "--rm", "--pull", "never", "--network", "none", "--read-only", "--user", "0:0",
             "--cap-drop", "ALL", "--cap-add", "CHOWN", "--security-opt", "no-new-privileges",
             "-v", state + ":/fixture", "--entrypoint", "python", image_id, "-c",
             "import os;os.chmod('/fixture',0o700);os.chown('/fixture',10001,10001)"],
        )
        probe("seed")
        for role in ("worker", "dispatcher"):
            name = prefix + "-" + role
            command(["docker", "create", "--name", name, *common, image_id, role])
            containers.append(name)
            command(["docker", "start", name])
            info = json.loads(command(["docker", "inspect", name]))[0]
            verify_role(info, image_id, role, network)
            roles[role] = name
        probe("verify")
        command(["docker", "stop", "--time", "20", roles["dispatcher"]])
        stopped = json.loads(command(["docker", "inspect", roles["dispatcher"]]))[0]
        if stopped["State"]["Running"] or stopped["State"]["OOMKilled"] or stopped["State"]["ExitCode"] not in (0, 143):
            raise RuntimeError("Fixed dispatcher did not stop cleanly.")
        probe("duplicates")
        # Warm shutdown closes the consumer before the final empty-broker check,
        # removing the BRPOP-to-unacked visibility race from acknowledgement proof.
        command(["docker", "stop", "--time", "20", roles["worker"]])
        for role, name in roles.items():
            info = json.loads(command(["docker", "inspect", name]))[0]
            verify_role(info, image_id, role, network)
            if info["State"]["OOMKilled"] or info["State"]["Running"] or info["State"]["ExitCode"] not in ((0,) if role == "worker" else (0, 143)):
                raise RuntimeError("Fixed job service exited unexpectedly.")
        probe("settled")
        result = {
            "image_id": image_id, "roles": list(roles), "source_mounts": False, "public_ports": False,
            "read_only_root": True, "uid": 10001, "fixed_entrypoint": True,
            "resource_limits": {"cpus": 2, "memory_bytes": 2 * 1024**3, "pids": 256},
            "observer_state_visible_to_services": False, "receipts": summaries,
            "twenty_acknowledged_duplicate_deliveries": "passed", "warm_worker_shutdown": "passed",
            "production_recovery_qualified": False, "expert_isolation_qualified": False,
        }
        (reports / "fixed-jobs.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    except BaseException as error:
        diagnostic = getattr(error, "diagnostic", b"") + str(error).encode()
        for name in containers:
            log = subprocess.run(["docker", "logs", name], capture_output=True, check=False)
            diagnostic += getattr(log, "stdout", b"") + getattr(log, "stderr", b"")
        # The outer API fixture redacts all installation secrets before retaining
        # diagnostics. Never retain observer state, cookies or a full inspect.
        raise PrivateCheckFailed(diagnostic) from error
    finally:
        for name in reversed(containers):
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, check=False)
        for name in volumes:
            subprocess.run(["docker", "volume", "rm", name], capture_output=True, check=False)


def verify_role(info, image_id, role, network):
    """Check actual daemon configuration, not just the requested flags."""
    config, host = info["Config"], info["HostConfig"]
    if not (
        info["Image"] == image_id and config["User"] == "10001:10001" and config["Cmd"] == [role]
        and config["Entrypoint"] == ["python", "/app/scripts/private_service.py"]
        and host["ReadonlyRootfs"] and not host["Privileged"] and not host["PortBindings"]
        and set(host["CapDrop"]) == {"ALL"} and not host["CapAdd"]
        and "no-new-privileges" in host["SecurityOpt"] and host["NanoCpus"] == 2_000_000_000
        and host["Memory"] == 2 * 1024**3 and host["PidsLimit"] == 256
        and host["NetworkMode"] == network and not info["NetworkSettings"]["Ports"]
        and set(host["Tmpfs"]) == {"/tmp"}
    ):
        raise RuntimeError("Fixed job role configuration rejected.")
    mounts = {m["Destination"]: m for m in info["Mounts"]}
    if (
        len(mounts) != len(info["Mounts"]) or set(mounts) != {"/installation", "/artifacts"}
        or any(m["Type"] != "volume" for m in mounts.values())
        or mounts["/installation"]["RW"] or not mounts["/artifacts"]["RW"]
    ):
        raise RuntimeError("Fixed job role mounts rejected.")
