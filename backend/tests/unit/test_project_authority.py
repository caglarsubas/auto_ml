"""Real HTTP, path, MCP and approval scope regressions; no staff bypass."""

import io
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError
from django.db import DatabaseError
from django.http import StreamingHttpResponse
from django.test import Client, RequestFactory
from django.urls import URLResolver, get_resolver
from rest_framework.response import Response

from access_control import projects
from access_control.authority import authorized_access, AccessDenied
from access_control.models import (
    Project,
    ProjectPolicy,
    ProjectMembership,
    ProjectDataset,
    ProjectPipeline,
    ProjectAuthorityEvent,
    MCPDatasetGrant,
    MCPAccessEvent,
    AssistantActionApproval,
)
from access_control.project_http import GLOBAL, DATASET, SPECIAL, ProjectResponseMiddleware
from declaration.models import Declaration
from modeling.models import PipelineRun

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def world(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.DECLARAI_RUNTIME_PROFILE = "development"
    ProjectPolicy.objects.create()
    a, b = Project.objects.create(name="A"), Project.objects.create(name="B")
    users, clients = {}, {}
    for role in ["developer", "reviewer", "admin", "outsider"]:
        user = django_user_model.objects.create_user(username=role, password="synthetic-project-pass")
        if role != "outsider":
            ProjectMembership.objects.create(project=a, actor=user, role=role)
        client = Client()
        client.force_login(user)
        users[role], clients[role] = user, client
    files = []
    for index, project in enumerate([a, b]):
        relative = f"data_files/project{index}.csv"
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("x,target\n1,0\n2,1\n")
        dataset = Declaration.objects.create(name=project.name, original_name=path.name, file=relative)
        projects.bind_dataset(dataset, project.pk, source="synthetic_fixture")
        files.append(dataset)
    pipeline = PipelineRun.objects.create(name="A before upload", state={})
    projects.bind_pipeline(pipeline, a.pk)
    return a, b, users, clients, files, pipeline


def post(client, url, data):
    return client.post(url, json.dumps(data), content_type="application/json")


@pytest.mark.parametrize("role", ["developer", "reviewer", "admin"])
def test_scoped_lists_and_project_metadata(world, role):
    a, _, _, clients, files, pipeline = world
    rows = clients[role].get("/api/declaration/").json()
    assert [r["id"] for r in rows] == [files[0].pk]
    assert [r["id"] for r in clients[role].get("/api/pipeline/").json()] == [pipeline.pk]
    assert clients[role].get("/api/projects/").json()["projects"][0]["id"] == str(a.pk)
    assert clients[role].get(f"/api/declaration/{files[1].pk}/").status_code == 403
    assert clients[role].get("/media/" + files[1].file.name).status_code == 403
    response = clients[role].get("/media/" + files[0].file.name)
    assert response.status_code == 200 and b"x,target" in b"".join(response.streaming_content)
    response.close()
    assert not ProjectAuthorityEvent.objects.filter(operation="media_access", outcome="started").exists()


@pytest.mark.parametrize("role,expected", [("developer", 201), ("reviewer", 403), ("admin", 403), ("outsider", 403)])
def test_pipeline_creation_role_and_binding(world, role, expected):
    a, _, _, clients, _, _ = world
    response = post(clients[role], "/api/pipeline/create/", {"name": "New"})
    assert response.status_code == expected
    if expected == 201:
        assert ProjectPipeline.objects.get(pipeline_id=response.json()["id"]).project_id == a.pk
    else:
        assert not PipelineRun.objects.filter(name="New").exists()


def test_missing_role_and_staff_never_grant_access(world):
    _, _, users, clients, files, _ = world
    users["outsider"].is_staff = users["outsider"].is_superuser = True
    users["outsider"].save()
    assert clients["outsider"].get("/api/declaration/").json() == []
    assert clients["outsider"].get(f"/api/modeling/status/{files[0].pk}/").status_code == 403
    assert clients["outsider"].get("/admin/").status_code == 403


def test_unbound_legacy_needs_explicit_current_assignment_and_no_filename_fallback(world):
    a, _, _, clients, _, _ = world
    legacy = Declaration.objects.create(name="legacy", original_name="project0.csv", file="data_files/missing.csv")
    assert legacy.get_file_path() is None
    assert clients["developer"].get(f"/api/declaration/{legacy.pk}/").status_code == 403
    identifier = uuid.uuid4()
    spec = {"operation": "dataset", "project_id": str(a.pk), "file_id": legacy.pk}
    event, replay = projects.operator_change(spec, identifier, "synthetic-operator")
    assert not replay and event.actor is None and event.actor_snapshot == {}
    again, replay = projects.operator_change(spec, identifier, "synthetic-operator")
    assert replay and again.pk == event.pk
    assert clients["developer"].get(f"/api/declaration/{legacy.pk}/").status_code == 200
    with pytest.raises(ValueError):
        projects.operator_change({**spec, "file_id": 999999}, identifier, "synthetic-operator")


def test_override_and_pipeline_reference_cannot_select_another_project(world):
    a, b, _, clients, files, pipeline = world
    foreign = PipelineRun.objects.create(name="foreign", file_id=files[1].pk)
    projects.bind_pipeline(foreign, b.pk)
    for payload in [
        {"file_id": files[0].pk, "processed_file": files[1].file.name},
        {"file_id": files[0].pk, "pipeline_run_id": foreign.pk},
        {"file_id": files[0].pk, "model_path": "models/native.json"},
    ]:
        with patch("evaluation.views.reserve_holdout_access", side_effect=AssertionError("must not start")):
            assert post(clients["developer"], "/api/evaluation/run/", payload).status_code == 403
    assert post(clients["developer"], f"/api/pipeline/{pipeline.pk}/", {"file_id": files[1].pk}).status_code in [
        403,
        405,
    ]
    response = clients["developer"].put(
        f"/api/pipeline/{pipeline.pk}/", json.dumps({"file_id": files[1].pk}), content_type="application/json"
    )
    assert response.status_code == 403
    assert post(clients["developer"], "/api/crisp/iteration/clone/", {"pipeline_run_id": foreign.pk}).status_code == 403
    cloned = post(clients["developer"], "/api/crisp/iteration/clone/", {"pipeline_run_id": pipeline.pk})
    assert cloned.status_code == 201
    assert ProjectPipeline.objects.get(pipeline_id=cloned.json()["pipeline_run_id"]).project_id == a.pk


def test_native_upload_and_registered_artifact_require_correct_owner(world, settings):
    a, _, users, clients, files, _ = world
    upload = io.BytesIO(b"x,target\n1,0\n2,1\n")
    upload.name = "new.csv"
    response = clients["developer"].post("/api/declaration/", {"file": upload, "has_header": "true"})
    assert response.status_code == 201, response.content
    assert ProjectDataset.objects.get(dataset_id=response.json()["id"]).project_id == a.pk
    relative = "encoded_files/native.csv"
    path = Path(settings.MEDIA_ROOT) / relative
    path.parent.mkdir()
    path.write_text("x\n1\n")
    assert clients["developer"].get("/media/" + relative).status_code == 403
    projects.register_artifact(relative, file_id=files[0].pk)
    response = clients["reviewer"].get("/media/" + relative)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == path.read_bytes()
    response.close()
    with pytest.raises(projects.ProjectDenied):
        projects.register_artifact(relative, file_id=files[1].pk)
    with pytest.raises(projects.ProjectDenied):
        projects.path_authority(users["developer"].pk, relative, file_id=files[1].pk)


def test_explicit_project_choice_and_durable_activation(world):
    _, b, users, clients, _, _ = world
    ProjectMembership.objects.create(project=b, actor=users["developer"], role="developer")
    assert post(clients["developer"], "/api/pipeline/create/", {"name": "Ambiguous"}).status_code == 403
    chosen = post(clients["developer"], "/api/pipeline/create/", {"name": "Chosen", "project_id": str(b.pk)})
    assert chosen.status_code == 201
    assert ProjectPipeline.objects.get(pipeline_id=chosen.json()["id"]).project_id == b.pk
    assert projects.governed() is True


def test_admin_changes_are_attributable_idempotent_and_cancel_unused_actions(world):
    from access_control.assistant_approvals import prepare

    a, _, users, clients, files, _ = world
    proposal = prepare(
        users["developer"], {"file_id": files[0].pk, "action_type": "update_notes", "payload": {"content": "new"}}
    )
    data = {"username": "developer", "role": "reviewer", "request_id": str(uuid.uuid4())}
    assert post(clients["reviewer"], f"/api/projects/{a.pk}/members/", data).status_code == 403
    changed = post(clients["admin"], f"/api/projects/{a.pk}/members/", data)
    assert changed.status_code == 200, changed.content
    event = ProjectAuthorityEvent.objects.get(pk=changed.json()["event_id"])
    assert event.actor == users["admin"] and event.authority_source == "browser_session" and not event.operator_label
    assert post(clients["admin"], f"/api/projects/{a.pk}/members/", data).json()["replayed"] is True
    assert post(clients["admin"], f"/api/projects/{a.pk}/members/", {**data, "role": "developer"}).status_code == 400
    record = AssistantActionApproval.objects.get(pk=proposal["approval_id"])
    assert record.state == "cancelled" and record.reason_code == "project_membership_changed"
    assert record.actor_snapshot["project_authority"]["role"] == "developer"
    assert post(clients["developer"], "/api/ai-assistant/approve-action/", proposal).status_code == 403


def test_mcp_grant_is_additional_to_project_scope_and_rechecked(world, monkeypatch):
    a, _, users, _, files, _ = world
    user = users["developer"]
    monkeypatch.setenv("DECLARAI_MCP_ACTOR_USER_ID", str(user.pk))
    monkeypatch.setenv("DECLARAI_MCP_SCOPES", "pipeline:read,action:prepare")
    grant = MCPDatasetGrant.objects.create(actor=user, dataset=files[0], role="prepare")
    MCPDatasetGrant.objects.create(actor=user, dataset=files[1], role="prepare")
    from ai_assistant.mcp_server.auth import SCOPE_PIPELINE_READ, SCOPE_ACTION_PREPARE

    monkeypatch.setenv("DECLARAI_MCP_SCOPES", ",".join([SCOPE_PIPELINE_READ, SCOPE_ACTION_PREPARE]))
    with authorized_access(files[0].pk, "read", "synthetic", SCOPE_PIPELINE_READ) as receipt:
        assert receipt["project_authority"]["project_id"] == str(a.pk)
    with pytest.raises(AccessDenied):
        with authorized_access(files[1].pk, "read", "synthetic", SCOPE_PIPELINE_READ):
            pytest.fail("foreign dataset reached")
    with pytest.raises(AccessDenied, match="changed"):
        with authorized_access(files[0].pk, "read", "synthetic", SCOPE_PIPELINE_READ):
            member = ProjectMembership.objects.get(actor=user, project=a)
            member.active = False
            member.save()
    assert MCPAccessEvent.objects.filter(outcome="withheld").exists()
    assert projects.current_actor.get() is None


def test_revoked_stream_withholds_later_chunks_and_records_outcome(world):
    a, _, users, _, files, _ = world
    request = RequestFactory().get("/synthetic-stream/")
    request.user = users["reviewer"]
    scope = projects.dataset_authority(request.user.pk, files[0].pk)
    event = projects.audit(request.user, "synthetic", {}, a.pk, outcome="started")

    def handler(raw):
        raw._project_scopes, raw._project_event = [scope], event.pk
        return StreamingHttpResponse(iter([b"first", b"secret-after-revocation"]))

    response = ProjectResponseMiddleware(handler)(request)
    iterator = iter(response.streaming_content)
    assert next(iterator) == b"first"
    member = ProjectMembership.objects.get(actor=request.user, project=a)
    member.active = False
    member.save()
    assert list(iterator) == []
    event.refresh_from_db()
    assert event.outcome == "withheld"
    response.close()
    assert projects.current_actor.get() is None


def test_database_or_audit_failure_never_returns_data(world):
    _, _, _, clients, files, _ = world
    with patch("access_control.projects.membership", side_effect=DatabaseError("not a public error")):
        response = clients["developer"].get(f"/api/modeling/status/{files[0].pk}/")
        assert response.status_code == 503 and b"not a public error" not in response.content
    with patch("access_control.projects.audit", side_effect=DatabaseError("not a public error")):
        assert clients["developer"].get("/api/declaration/").status_code == 503


def test_holdout_reuse_counts_survive_cross_project_redaction(world):
    from modeling.holdout_evidence import holdout_history, holdout_spec, reserve_holdout_access

    _, _, users, _, files, _ = world
    spec = holdout_spec("a" * 64, "target", [1, 2, 3], "raw_snapshot")
    reserve_holdout_access(spec, files[1].pk, uuid.uuid4(), users["outsider"], {"private": "foreign-parameter"})
    history = holdout_history(spec, files[0].pk)
    assert history["same_final_rows_accesses"] == 1 and history["total_related_accesses"] == 1
    record = history["records"][0]
    assert record["visibility"] == "outside_project" and record["overlap_rows"] == 3
    assert not {"file_id", "actor", "access_id", "execution_id", "parameters", "accessed_at"} & record.keys()


def test_every_native_route_has_an_explicit_policy():
    def names(resolver):
        for item in resolver.url_patterns:
            if isinstance(item, URLResolver):
                if item.namespace != "admin":
                    yield from names(item)
            elif item.name:
                yield item.name

    native = set(names(get_resolver())) - {"auth-session", "auth-login", "auth-logout", "protected-media"}
    assert native <= GLOBAL | DATASET | SPECIAL


def test_operator_bootstrap_receipt_and_invalid_command_are_atomic(world, django_user_model):
    user = django_user_model.objects.create_user(username="bootstrap-admin")
    out = io.StringIO()
    request_id = str(uuid.uuid4())
    args = [
        "create",
        "--request-id",
        request_id,
        "--operator-label",
        "synthetic-operator",
        "--name",
        "New project",
        "--user",
        user.username,
    ]
    call_command("manage_project", *args, stdout=out)
    receipt = json.loads(out.getvalue())
    assert receipt["authority_source"] == "installation_operator"
    assert ProjectMembership.objects.get(project_id=receipt["project_id"], actor=user).role == "admin"
    out = io.StringIO()
    call_command("manage_project", *args, stdout=out)
    assert json.loads(out.getvalue())["replayed"] is True
    count = Project.objects.count()
    with pytest.raises(CommandError):
        call_command("manage_project", *args[:-1], "missing-user")
    assert Project.objects.count() == count


def test_legacy_frozen_cross_project_history_is_withheld_without_rewriting(world, settings):
    _, _, _, clients, files, _ = world
    foreign = {"relation": "same_final_rows", "file_id": files[1].pk, "parameters": {"foreign": "secret"}}
    payload = {"evaluation": {"holdout_history": {"records": [foreign]}}}
    directory = Path(settings.MEDIA_ROOT) / "evaluation"
    directory.mkdir()
    path = directory / f"{files[0].pk}_evaluation.json"
    path.write_text(json.dumps(payload))
    original = path.read_bytes()
    response = clients["reviewer"].get(f"/api/evaluation/status/{files[0].pk}/")
    assert response.status_code == 403 and b"secret" not in response.content
    assert response.json()["error_code"] == "cross_project_evidence_requires_new_assessment"
    assert path.read_bytes() == original
    response = post(clients["reviewer"], "/api/evaluation/pack/", {"file_id": files[0].pk})
    assert response.status_code == 403 and b"secret" not in response.content


def test_reviewer_cannot_mutate_governance_and_csrf_remains_required(world):
    _, _, users, clients, files, _ = world
    assert (
        post(clients["reviewer"], "/api/evaluation/governance/", {"file_id": files[0].pk, "checks": {}}).status_code
        == 403
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(users["developer"])
    assert post(client, "/api/pipeline/create/", {"name": "Without CSRF"}).status_code == 403
    assert client.get("/api/auth/session/").json()["authenticated"] is True


def test_regrant_cannot_reuse_previous_prepared_approval(world):
    from access_control.assistant_approvals import prepare, approve, ApprovalError

    a, _, users, _, files, _ = world
    proposal = prepare(
        users["developer"], {"file_id": files[0].pk, "action_type": "update_notes", "payload": {"content": "new"}}
    )
    member = ProjectMembership.objects.get(actor=users["developer"], project=a)
    member.active = False
    member.save()
    member.active = True
    member.save()
    with pytest.raises(ApprovalError, match="recorded inputs changed"):
        approve(users["developer"], proposal)
    record = AssistantActionApproval.objects.get(pk=proposal["approval_id"])
    assert record.state == "stale" and record.reason_code == "project_authority_changed"


def test_mid_prepare_role_change_does_not_publish_approval(world, monkeypatch):
    from access_control import assistant_approvals as authority

    a, _, users, _, files, _ = world
    original = authority.recorded_context

    def changed(*args):
        result = original(*args)
        member = ProjectMembership.objects.get(actor=users["developer"], project=a)
        member.active = False
        member.save()
        return result

    monkeypatch.setattr(authority, "recorded_context", changed)
    with pytest.raises(authority.ApprovalError):
        authority.prepare(
            users["developer"], {"file_id": files[0].pk, "action_type": "update_notes", "payload": {"content": "new"}}
        )
    assert not AssistantActionApproval.objects.exists()


def test_project_listing_revocation_during_response_withholds_names(world, monkeypatch):
    from access_control.project_views import ProjectListView

    a, _, users, clients, _, _ = world
    original = ProjectListView.get

    def changed(view, request):
        response = original(view, request)
        member = ProjectMembership.objects.get(actor=users["developer"], project=a)
        member.active = False
        member.save()
        return response

    monkeypatch.setattr(ProjectListView, "get", changed)
    response = clients["developer"].get("/api/projects/")
    assert response.status_code == 403 and b'"name"' not in response.content


@pytest.mark.parametrize("operation", ["read", "prepare_action"])
def test_reviewer_mcp_reads_but_cannot_prepare_even_with_prepare_grant(world, monkeypatch, operation):
    _, _, users, _, files, _ = world
    from ai_assistant.mcp_server.auth import SCOPE_PIPELINE_READ, SCOPE_ACTION_PREPARE

    monkeypatch.setenv("DECLARAI_MCP_ACTOR_USER_ID", str(users["reviewer"].pk))
    monkeypatch.setenv("DECLARAI_MCP_SCOPES", ",".join([SCOPE_PIPELINE_READ, SCOPE_ACTION_PREPARE]))
    MCPDatasetGrant.objects.create(actor=users["reviewer"], dataset=files[0], role="prepare")
    scope = SCOPE_PIPELINE_READ if operation == "read" else SCOPE_ACTION_PREPARE
    if operation == "read":
        with authorized_access(files[0].pk, operation, "synthetic", scope):
            pass
    else:
        with pytest.raises(AccessDenied, match="project_access_denied"):
            with authorized_access(files[0].pk, operation, "synthetic", scope):
                pytest.fail("reviewer preparation started")


def test_authorized_deletion_returns_success_and_absence_never_grants_access(world):
    _, _, _, clients, files, pipeline = world
    assert clients["reviewer"].delete(f"/api/pipeline/{pipeline.pk}/").status_code == 403
    assert clients["developer"].delete(f"/api/pipeline/{pipeline.pk}/").status_code == 200
    assert clients["developer"].get(f"/api/pipeline/{pipeline.pk}/").status_code == 403
    assert clients["developer"].delete(f"/api/declaration/{files[0].pk}/").status_code == 204
    assert clients["developer"].get(f"/api/declaration/{files[0].pk}/").status_code == 403
    assert not ProjectAuthorityEvent.objects.filter(outcome="started").exists()


def test_published_native_execution_artifacts_have_explicit_project_owners(world):
    from modeling.execution_artifacts import begin_execution, publish_execution
    from access_control.models import ProjectArtifact

    a, _, _, clients, files, _ = world
    identifier, root, _ = begin_execution(files[0].get_file_path())
    (root / "tuning_selection.json").write_text('{"status": "completed"}')
    publish_execution(identifier, {"file_id": files[0].pk, "model": {}})
    relative = f"execution_runs/{identifier}/modeling_status.json"
    assert ProjectArtifact.objects.get(relative_path=relative).project_id == a.pk
    response = clients["reviewer"].get("/media/" + relative)
    assert response.status_code == 200
    assert json.loads(b"".join(response.streaming_content))["file_id"] == files[0].pk
    response.close()
    assert clients["outsider"].get("/media/" + relative).status_code == 403


def test_revocation_during_export_inspection_withholds_the_final_response(world, monkeypatch):
    a, _, users, clients, _, _ = world

    def changed(request, response):
        member = ProjectMembership.objects.get(actor=users["developer"], project=a)
        member.active = False
        member.save()

    monkeypatch.setattr(ProjectResponseMiddleware, "check_evidence", staticmethod(changed))
    response = clients["developer"].get("/api/projects/")
    assert response.status_code == 403 and b'"name"' not in response.content


@pytest.mark.parametrize('role', ['developer', 'reviewer', 'admin'])
def test_workspace_filter_only_returns_selected_project(world, role):
    a, b, users, clients, files, pipeline = world
    ProjectMembership.objects.create(project=b, actor=users[role], role=role)
    other = PipelineRun.objects.create(name='B record', state={})
    projects.bind_pipeline(other, b.pk)
    for project, dataset, run in [(a, files[0], pipeline), (b, files[1], other)]:
        response = clients[role].get('/api/declaration/', {'project_id': str(project.pk)})
        assert response.status_code == 200
        assert [(row['id'], row['project_id']) for row in response.json()] == [(dataset.pk, str(project.pk))]
        response = clients[role].get('/api/pipeline/', {'project_id': str(project.pk)})
        assert response.status_code == 200
        assert [(row['id'], row['project_id']) for row in response.json()] == [(run.pk, str(project.pk))]
    assert len(clients[role].get('/api/declaration/').json()) == 2


@pytest.mark.parametrize('route', ['/api/declaration/', '/api/pipeline/'])
@pytest.mark.parametrize('selector', ['unavailable', 'invalid', 'empty', 'duplicate'])
def test_workspace_filter_does_not_fall_back_to_all_records(world, route, selector):
    a, b, _, clients, _, _ = world
    query = {
        'unavailable': f'project_id={b.pk}', 'invalid': 'project_id=malformed',
        'empty': 'project_id=', 'duplicate': f'project_id={a.pk}&project_id={b.pk}',
    }[selector]
    response = clients['developer'].get(route + '?' + query)
    assert response.status_code == 403
    assert response.json()['error_code'] in ['project_access_denied', 'project_reference_invalid']


@pytest.mark.parametrize('method,route', [
    ('get', '/api/pipeline/{pipeline}/'), ('get', '/api/pipeline/{pipeline}/report/'),
    ('get', '/api/declaration/{dataset}/'), ('put', '/api/pipeline/{pipeline}/'),
    ('delete', '/api/pipeline/{pipeline}/'),
])
def test_workspace_filter_cannot_relabel_a_resource(world, method, route):
    _, b, users, clients, files, pipeline = world
    ProjectMembership.objects.create(project=b, actor=users['developer'], role='developer')
    url = route.format(pipeline=pipeline.pk, dataset=files[0].pk) + f'?project_id={b.pk}'
    response = (getattr(clients['developer'], method)(url, '{}', content_type='application/json')
                if method in {'put', 'delete'} else clients['developer'].get(url))
    assert response.status_code == 403
    assert PipelineRun.objects.filter(pk=pipeline.pk).exists()
    assert Declaration.objects.filter(pk=files[0].pk).exists()


def test_workspace_explicit_creation_with_multiple_developer_projects(world):
    a, b, users, clients, _, _ = world
    ProjectMembership.objects.create(project=b, actor=users['developer'], role='developer')
    missing = post(clients['developer'], '/api/pipeline/create/', {'name': 'ambiguous'})
    assert missing.status_code == 403
    assert missing.json()['error_code'] == 'project_selection_required'
    for project in [a, b]:
        response = post(clients['developer'], '/api/pipeline/create/', {'name': 'explicit', 'project_id': str(project.pk)})
        assert response.status_code == 201
        assert ProjectPipeline.objects.get(pipeline_id=response.json()['id']).project_id == project.pk
    conflict = post(clients['developer'], f'/api/pipeline/create/?project_id={b.pk}', {'project_id': str(a.pk)})
    assert conflict.status_code == 403
