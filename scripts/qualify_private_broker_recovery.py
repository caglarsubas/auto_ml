#!/usr/bin/env python3
"""Bounded broker restart/replay inside the exclusively owned Linux fixture."""

RECOVERY_CODE = r'''
import json,sys,uuid
from pathlib import Path
sys.path.insert(0,'/app/scripts')
from private_runtime_manifest import verify
verify(Path('/app'))
sys.path.insert(0,'/app/backend')
from backend.celery import app
from execution_jobs.broker_transport import SelectedCAConnection,Transport
from kombu import Producer,Queue
import redis
with app.connection_for_write() as connection:
    assert connection.get_transport_cls() is Transport
    connection.ensure_connection(max_retries=0)
    channel=connection.default_channel
    client=channel.client;pool=client.connection_pool
    assert issubclass(pool.connection_class,SelectedCAConnection)
    ca=pool.connection_kwargs['ssl_ca_data']
    assert ca==app.conf.broker_use_ssl['ssl_ca_data'] and client.info('persistence')['aof_enabled']==1
    token=uuid.uuid4().hex
    queue=Queue('declarai-broker-recovery-'+token,durable=True,auto_delete=False)(connection)
    queue.declare()
    payload={'owned':token,'stage':'before-restart'}
    Producer(connection).publish(payload,exchange='',routing_key=queue.name,serializer='json',retry=False)
    print('broker_recovery_ready',flush=True)
    assert sys.stdin.readline().strip()=='broker_stopped'
    try:client.ping()
    except redis.exceptions.ConnectionError:pass
    else:raise AssertionError('stopped_broker_unexpectedly_connected')
    assert channel.client is client and client.connection_pool is pool
    print('broker_recovery_unavailable',flush=True)
    assert sys.stdin.readline().strip()=='broker_restarted'
    try:
        assert client.ping() is True
        assert channel.client is client and client.connection_pool is pool
        assert pool.connection_kwargs['ssl_ca_data']==ca
        assert issubclass(pool.connection_class,SelectedCAConnection)
        message=queue.get(no_ack=False)
        assert message is not None and message.payload==payload
        message.ack()
        assert queue.get(no_ack=False) is None
        print(json.dumps({'same_process_pool_reconnect':'passed','captured_ca_preserved':'passed','broker_unavailable_refused':'passed','aof_payload_replayed_once':'passed'}))
    finally:queue.delete()
'''


def recovery(value, adopted, dependency, parent, command):
    import json
    import os
    import re
    import selectors
    import subprocess
    import sys
    from pathlib import Path
    import private_dependency_start as startup
    import private_installation_adopt as adopter

    if (sys.platform != "linux" or os.geteuid() != 0 or parent.parent != Path("/srv")
            or not re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
            or value["request"]["root"] != str(parent / "installation")):
        raise startup.checker.planner.PlanError("broker_recovery_fixture_scope_required")
    expected = dependency["plan_manifest_sha256"]
    _, spec, initial, _, _, directory = startup.prepared(parent / "plan", expected)
    os.close(directory)
    broker_id = dependency["services"]["job-broker"]["container_id"]
    receipt = (parent / "installation/dependencies/started.json").read_bytes()
    profile, digest, binding = adopter.application_profile(value, expected, initial["initialization_id"])
    images = {role: startup.resources.inspect("image", image) for role, image in value["images"].items()}
    active = adopter.active_applications(profile, digest, binding, images)
    if {role: row["Id"] for role, row in active.items()} != {
            role: row["container_id"] for role, row in adopted["services"].items()}:
        raise startup.checker.planner.PlanError("broker_recovery_fixture_application_changed")

    def validate_broker():
        startup.validate(startup.resources.inspect("container", broker_id), "job-broker", spec,
                         startup.labels(value, initial), images["redis"], startup.names(value)["job-broker"], active=True)

    validate_broker()
    process = subprocess.Popen([
        *startup.resources.PREFIX, "exec", "-i", adopted["services"]["api"]["container_id"],
        "python", "-I", "-c", RECOVERY_CODE,
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def marker(wanted):
        with selectors.DefaultSelector() as selected:
            selected.register(process.stdout, selectors.EVENT_READ)
            if not selected.select(20) or process.stdout.readline().strip() != wanted:
                raise startup.checker.planner.PlanError("broker_recovery_fixture_handshake_failed")

    try:
        marker(b"broker_recovery_ready")
        validate_broker()
        command(["container", "stop", "--time", "10", broker_id])
        process.stdin.write(b"broker_stopped\n")
        process.stdin.flush()
        marker(b"broker_recovery_unavailable")
        command(["container", "start", broker_id])
        restarted = startup.start(parent / "plan", expected)
        if ({role: row["container_id"] for role, row in restarted["services"].items()}
                != {role: row["container_id"] for role, row in dependency["services"].items()}
                or (parent / "installation/dependencies/started.json").read_bytes() != receipt):
            raise startup.checker.planner.PlanError("broker_recovery_fixture_changed_identity_or_history")
        process.stdin.write(b"broker_restarted\n")
        process.stdin.flush()
        output, _ = process.communicate(timeout=20)
        if process.returncode:
            raise startup.checker.planner.PlanError("broker_recovery_fixture_client_failed")
        result = json.loads(output)
        result["same_dependency_ids_and_receipt"] = "passed"
        # Existing service containers retain their normal environment and ordinary
        # metadata authority; this neither starts nor replaces an application.
        for role in ("api", "worker", "dispatcher"):
            checked = json.loads(command([
                "exec", adopted["services"][role]["container_id"], "python", "manage.py", "check_job_runtime",
                "--require-application-role",
            ]))
            if any(checked.get(key) != wanted for key, wanted in {
                    "private_metadata_tls": "verified", "broker_connection": "verified", "migrations": "current",
                    "cache_connection": "authenticated_tls_verified", "application_role": "non_elevated",
            }.items()):
                raise startup.checker.planner.PlanError("broker_recovery_fixture_role_preflight_failed")
        repeated = adopter.adoption(parent / "plan", expected, parent / "server.crt")
        if {role: row["container_id"] for role, row in repeated["services"].items()} != {
                role: row["container_id"] for role, row in adopted["services"].items()}:
            raise startup.checker.planner.PlanError("broker_recovery_fixture_application_changed")
        result["three_role_preflight"] = "passed"
        result["same_application_ids_after_readmission"] = "passed"
        return result
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
