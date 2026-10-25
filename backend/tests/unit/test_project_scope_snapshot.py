"""One live scope statement preserves role policy, revisions and denial semantics."""

import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from access_control import projects
from access_control.models import Project, ProjectDataset, ProjectMembership
from declaration.models import Declaration

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def scope_world(django_user_model):
    actor = django_user_model.objects.create(username="scope-snapshot-actor")
    project = Project.objects.create(name="Scope snapshot")
    dataset = Declaration.objects.create(name="Scope fixture", original_name="scope.csv", file="data_files/scope.csv")
    binding = ProjectDataset.objects.create(dataset=dataset, project=project)
    member = ProjectMembership.objects.create(project=project, actor=actor, role="developer")
    return SimpleNamespace(actor=actor, project=project, dataset=dataset, binding=binding, member=member)


def reference_scope(actor_id, file_id, operation):
    # The unchanged membership policy is the existing behavior oracle.
    binding = ProjectDataset.objects.filter(dataset_id=file_id).first()
    if binding is None:
        raise projects.ProjectDenied("dataset_project_assignment_required")
    return {**projects.membership(actor_id, binding.project_id, operation),
            "file_id": binding.dataset_id, "binding_revision": str(binding.revision)}


@pytest.mark.parametrize("role", ["developer", "reviewer", "admin", "unsupported"])
@pytest.mark.parametrize("actor_active", [True, False])
@pytest.mark.parametrize("member_active", [True, False])
@pytest.mark.parametrize("operation", ["read", "write", "admin", "unsupported"])
def test_single_statement_scope_matches_live_membership_policy(scope_world, role, actor_active, member_active, operation):
    w = scope_world
    type(w.actor).objects.filter(pk=w.actor.pk).update(is_active=actor_active)
    ProjectMembership.objects.filter(pk=w.member.pk).update(role=role, active=member_active)
    try:
        expected = reference_scope(w.actor.pk, w.dataset.pk, operation)
        denied = None
    except projects.ProjectDenied as error:
        expected, denied = None, error.code
    with CaptureQueriesContext(connection) as queries:
        if denied:
            with pytest.raises(projects.ProjectDenied) as result:
                projects.dataset_authority(w.actor.pk, w.dataset.pk, operation)
            assert result.value.code == denied
        else:
            assert projects.dataset_authority(w.actor.pk, w.dataset.pk, operation) == expected
    assert len(queries) == 1


@pytest.mark.parametrize("resource", ["unbound", "unknown"])
def test_missing_binding_keeps_assignment_denial_in_one_statement(scope_world, resource):
    w = scope_world
    ProjectDataset.objects.filter(pk=w.dataset.pk).delete()
    file_id = w.dataset.pk if resource == "unbound" else w.dataset.pk + 1000
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied) as denied:
        projects.dataset_authority(w.actor.pk, file_id)
    assert denied.value.code == "dataset_project_assignment_required"
    assert len(queries) == 1


def test_missing_membership_keeps_access_denial_without_losing_the_binding(scope_world):
    w = scope_world
    w.member.delete()
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied) as denied:
        projects.dataset_authority(w.actor.pk, w.dataset.pk)
    assert denied.value.code == "project_access_denied"
    assert len(queries) == 1


@pytest.mark.parametrize("change,expected", [
    ("membership_revision", "project_authority_changed"),
    ("binding_revision", "project_authority_changed"),
    ("actor_disabled", "project_access_denied"),
    ("membership_disabled", "project_access_denied"),
    ("role_changed", "project_access_denied"),
])
def test_rechecks_query_current_state_without_reusing_an_earlier_scope(scope_world, change, expected):
    w = scope_world
    scope = projects.dataset_authority(w.actor.pk, w.dataset.pk, "write")
    if change == "membership_revision":
        ProjectMembership.objects.filter(pk=w.member.pk).update(revision=uuid.uuid4())
    elif change == "binding_revision":
        ProjectDataset.objects.filter(pk=w.dataset.pk).update(revision=uuid.uuid4())
    elif change == "actor_disabled":
        type(w.actor).objects.filter(pk=w.actor.pk).update(is_active=False)
    elif change == "membership_disabled":
        ProjectMembership.objects.filter(pk=w.member.pk).update(active=False)
    else:
        ProjectMembership.objects.filter(pk=w.member.pk).update(role="reviewer", revision=uuid.uuid4())
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied) as denied:
        projects.recheck(scope)
    assert denied.value.code == expected
    assert len(queries) == 1


def test_a_membership_in_another_project_cannot_authorize_this_binding(scope_world):
    w = scope_world
    w.member.delete()
    other = Project.objects.create(name="Unrelated project")
    ProjectMembership.objects.create(project=other, actor=w.actor, role="developer")
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied) as denied:
        projects.dataset_authority(w.actor.pk, w.dataset.pk)
    assert denied.value.code == "project_access_denied"
    assert len(queries) == 1


def test_a_changed_binding_uses_only_its_current_project_membership(scope_world):
    w = scope_world
    previous = projects.dataset_authority(w.actor.pk, w.dataset.pk)
    other = Project.objects.create(name="Changed binding fixture")
    member = ProjectMembership.objects.create(project=other, actor=w.actor, role="reviewer")
    revision = uuid.uuid4()
    ProjectDataset.objects.filter(pk=w.dataset.pk).update(project=other, revision=revision)
    with CaptureQueriesContext(connection) as queries:
        current = projects.dataset_authority(w.actor.pk, w.dataset.pk)
    assert len(queries) == 1
    assert current == {"project_id": str(other.pk), "actor_id": w.actor.pk,
                       "membership_revision": str(member.revision), "role": "reviewer",
                       "operation": "read", "file_id": w.dataset.pk, "binding_revision": str(revision)}
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied) as denied:
        projects.recheck(previous)
    assert denied.value.code == "project_authority_changed"
    assert len(queries) == 1
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied) as denied:
        projects.dataset_authority(w.actor.pk, w.dataset.pk, "write")
    assert denied.value.code == "project_access_denied"
    assert len(queries) == 1


def test_conflicting_project_and_dataset_resolution_is_refused_before_storage(scope_world):
    w = scope_world
    with CaptureQueriesContext(connection) as queries, pytest.raises(projects.ProjectDenied):
        projects.membership(w.actor.pk, w.project.pk, _dataset_id=w.dataset.pk)
    assert len(queries) == 0
