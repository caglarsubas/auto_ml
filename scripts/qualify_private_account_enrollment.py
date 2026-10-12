#!/usr/bin/env python3
"""Account qualification only inside the caller's exclusively owned fresh root."""

import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import private_schema_init as schema_init

ACCOUNT_CODE = r"""
import io,json,os,sys,uuid
from pathlib import Path
try:
    sys.path.insert(0,'/app/scripts')
    from private_runtime_manifest import verify
    verify(Path('/app'))
    Path('/tmp/enrollment-media').mkdir(mode=0o700)
    sys.path.insert(0,'/app/backend');os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
    import django;django.setup()
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from django.contrib.auth import get_user_model
    from access_control.models import AuthenticationEvent,ProjectAuthorityEvent,ProjectMembership,ProjectPolicy,SessionAuthority
    token=os.environ['ENROLLMENT_FIXTURE'];assert len(token)==32
    users={r:'fixture-'+r+'-'+token for r in ['admin','developer','reviewer']}
    ids={r:str(uuid.uuid5(uuid.UUID(token),r)) for r in users}
    def run(account_role,**overrides):
        args=dict(user=users[account_role],request_id=ids[account_role],operator_label='disposable-installation',password_file='/credentials/'+account_role,role=account_role)
        if account_role=='admin':args['new_project']='Disposable installation project'
        else:args['project_id']=project
        args.update(overrides);args={k:v for k,v in args.items() if v is not None};out=io.StringIO();call_command('enroll_account',stdout=out,**args);return json.loads(out.getvalue())
    assert not get_user_model().objects.exists() and not ProjectPolicy.objects.exists()
    try:run('admin',password_file='/credentials/weak')
    except CommandError as e:assert str(e)=='enrollment_password_policy_failed'
    else:raise AssertionError('weak_password_admitted')
    assert not get_user_model().objects.exists() and not ProjectPolicy.objects.exists()
    try:run('admin',role='developer',new_project=None,project_id=str(uuid.uuid4()))
    except CommandError as e:assert str(e)=='enrollment_project_unavailable'
    else:raise AssertionError('foreign_project_admitted')
    assert not get_user_model().objects.exists() and not ProjectPolicy.objects.exists() and not AuthenticationEvent.objects.exists()
    first=run('admin');project=first['project_id']
    a=get_user_model().objects.get(username=users['admin']);before=(a.pk,a.password,SessionAuthority.objects.get(user=a).revision,ProjectMembership.objects.get(actor=a).revision)
    again=run('admin');a.refresh_from_db()
    assert again['replayed_receipt'] and again['event_id']==first['event_id'] and before==(a.pk,a.password,SessionAuthority.objects.get(user=a).revision,ProjectMembership.objects.get(actor=a).revision)
    try:run('admin',operator_label='changed-assertion')
    except CommandError as e:assert str(e)=='enrollment_request_changed'
    else:raise AssertionError('stale_request_admitted')
    a.is_staff=True;a.save(update_fields=['is_staff'])
    try:
        try:run('admin')
        except CommandError as e:assert str(e)=='enrollment_account_state_changed'
        else:raise AssertionError('altered_privilege_admitted')
        a.refresh_from_db();assert a.is_staff is True
    finally:a.is_staff=False;a.save(update_fields=['is_staff'])
    receipts={'admin':first}
    for role in ['developer','reviewer']:
        receipts[role]=run(role);u=get_user_model().objects.get(username=users[role])
        assert u.is_active and not u.is_staff and not u.is_superuser and not u.groups.exists() and not u.user_permissions.exists()
        assert ProjectMembership.objects.get(actor=u).role==role
        assert run(role)['replayed_receipt'] is True
    assert AuthenticationEvent.objects.filter(event_type='account_enrolled').count()==3 and ProjectAuthorityEvent.objects.count()==3
    print(json.dumps({'schema':'private_account_fixture_v1','project_id':project,'accounts':receipts,'atomic_failed_project_and_password':'passed','exact_retry_preserves_credentials_revisions_history':'passed','changed_assertion_and_privilege':'blocked_without_repair','ordinary_exact_project_roles':'passed','password_values_or_hashes_emitted':False,'model_use_approved':False},sort_keys=True))
except Exception:
    print('private_account_fixture_failed');raise SystemExit(1)
"""


def qualify(value, receipt, parent):
    m = schema_init.resources
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or parent.parent != Path("/srv")
        or not m.re.fullmatch(r"declarai-p37-[0-9a-f]{32}", parent.name)
        or value["request"]["root"] != str(parent / "installation")
    ):
        raise schema_init.checker.planner.PlanError("account_fixture_scope_required")
    token = parent.name.removeprefix("declarai-p37-")
    delivery = parent / "account-delivery"
    delivery.mkdir(mode=0o750)
    os.chown(delivery, 0, 10001)
    passwords = {r: secrets.token_urlsafe(48) for r in ["admin", "developer", "reviewer"]}
    passwords["weak"] = "short"
    for role, password in passwords.items():
        path = delivery / role
        path.write_text(password)
        path.chmod(0o400)
        os.chown(path, 10001, 10001)
    env = {
        **schema_init.checker.planner.composition(value["request"], value["images"])["services"]["api"]["environment"],
        "DECLARAI_MEDIA_ROOT": "/tmp/enrollment-media",
        "ENROLLMENT_FIXTURE": token,
    }
    binding = schema_init.startup.labels(value, receipt)
    mounts = {"/installation": value["request"]["root"] + "/secrets/app", "/credentials": str(delivery)}
    args = [
        "container",
        "create",
        "--name",
        "declarai-account-qualification-" + token,
        "--pull",
        "never",
        "--network",
        value["prerequisites"]["networks"][0]["name"],
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--cpus",
        "1",
        "--memory",
        "1g",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=134217728,uid=10001,gid=10001,mode=700",
        "--entrypoint",
        "python",
    ]
    for k, v in {**binding, m.LABEL + "role": "account-qualification"}.items():
        args += ["--label", k + "=" + v]
    for k, v in env.items():
        args += ["--env", k + "=" + v]
    for target, source in mounts.items():
        args += ["--mount", "type=bind,src=" + source + ",dst=" + target + ",readonly"]
    identifier = None
    try:
        identifier = m.command([*args, value["images"]["api"], "-I", "-c", ACCOUNT_CODE]).decode().strip()
        if not m.re.fullmatch(r"[0-9a-f]{64}", identifier):
            identifier = None
            raise schema_init.checker.planner.PlanError("account_fixture_identity_invalid")
        schema_init.adopter.validate_preflight(
            m.inspect("container", identifier),
            value,
            env,
            binding,
            m.inspect("image", value["images"]["api"]),
            role="account-qualification",
            entrypoint=["python"],
            command=["-I", "-c", ACCOUNT_CODE],
            mount_sources=mounts,
        )
        output = m.command(["container", "start", "--attach", identifier], allow_failure=True)
        state = m.inspect("container", identifier)["State"]
        if state.get("Running") is not False or state.get("ExitCode") != 0 or len(output) > 16384:
            raise schema_init.checker.planner.PlanError("account_fixture_failed")
        result = schema_init.checker.planner.decode(output)
        if result["password_values_or_hashes_emitted"] is not False or any(
            p.encode() in output for p in passwords.values()
        ):
            raise schema_init.checker.planner.PlanError("account_fixture_output_invalid")
        return result, passwords
    finally:
        if identifier:
            m.command(["container", "rm", "--force", identifier])


def https_roles(value, accounts, passwords, parent):
    """Actual CA/hostname-verified sessions; never retain cookies or passwords."""
    from http.cookies import SimpleCookie

    m = schema_init.adopter
    host, port = schema_init.checker.planner.authority(value["request"]["authority"])
    context = m.client_context(parent / "server.crt")
    for role in ["admin", "developer", "reviewer"]:
        cookies = SimpleCookie()

        def request(method, path, body=None, csrf=None):
            connection = m.DeclaredHTTPS(value["request"]["bind_ip"], port, host, context)
            headers = {"Host": value["request"]["authority"], "Origin": "https://" + value["request"]["authority"]}
            if cookies:
                headers["Cookie"] = "; ".join(k + "=" + v.value for k, v in cookies.items())
            if csrf:
                headers["X-CSRFToken"] = csrf
            if body is not None:
                headers["Content-Type"] = "application/json"
                body = json.dumps(body)
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read(16385)
                if len(data) > 16384:
                    raise schema_init.checker.planner.PlanError("account_fixture_https_failed")
                for key, value_ in response.getheaders():
                    if key.lower() == "set-cookie":
                        cookies.load(value_)
                return response.status, json.loads(data)
            finally:
                connection.close()

        status, anonymous = request("GET", "/api/auth/session/")
        if status != 200 or anonymous["authenticated"] is not False:
            raise schema_init.checker.planner.PlanError("account_fixture_https_failed")
        username = "fixture-" + role + "-" + parent.name.removeprefix("declarai-p37-")
        status, session = request(
            "POST", "/api/auth/login/", {"username": username, "password": passwords[role]}, anonymous["csrf_token"]
        )
        if (
            status != 200
            or session["authenticated"] is not True
            or session["user"]["id"] != accounts["accounts"][role]["subject_user_id"]
        ):
            raise schema_init.checker.planner.PlanError("account_fixture_https_failed")
        status, projects = request("GET", "/api/projects/")
        if (
            status != 200
            or projects["governed"] is not True
            or len(projects["projects"]) != 1
            or projects["projects"][0]["id"] != accounts["project_id"]
            or projects["projects"][0]["role"] != role
        ):
            raise schema_init.checker.planner.PlanError("account_fixture_https_role_failed")
        if role != "admin":
            status, _ = request(
                "POST",
                "/api/projects/" + accounts["project_id"] + "/members/",
                {"username": username, "role": "admin", "request_id": uuid.uuid4().hex},
                session["csrf_token"],
            )
            if status != 403:
                raise schema_init.checker.planner.PlanError("account_fixture_https_escalation_not_blocked")
        status, logged_out = request("POST", "/api/auth/logout/", {}, session["csrf_token"])
        if status != 200 or logged_out["authenticated"] is not False:
            raise schema_init.checker.planner.PlanError("account_fixture_https_failed")
    return {
        "actual_tls_session_csrf_signin_roles_logout": "passed",
        "developer_reviewer_admin_escalation": "blocked",
        "credential_or_session_values_retained": False,
    }
