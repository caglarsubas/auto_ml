"""Native adoption reads keep authority/evidence contracts under scoped SQL bounds."""
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction

from execution_jobs import history, native_assessment as assessment, service
from execution_jobs.models import JobEvent, NativeAdoption, NativeAdoptionEvent, NativeJob, NativeProtectedInput, QueueLock
from modeling.models import HoldoutAccess
from tests.unit.test_durable_training_search import world  # noqa: F401
from tests.unit.test_native_protected_assessment import candidate, proposal, approve, seal  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def reviewed(candidate):  # noqa: F811
    value = approve(candidate, proposal(candidate))
    seal(candidate, value)
    candidate.adoption_id = value['id']
    return candidate


def url(w, route):
    return f'/api/jobs/{w.trained.pk}/adoptions/' if route == 'list' else f'/api/native-adoptions/{w.adoption_id}/'


def snapshot():
    return [list(model.objects.order_by('pk').values()) for model in
            [NativeJob, JobEvent, NativeAdoption, NativeAdoptionEvent, NativeProtectedInput, HoldoutAccess, QueueLock]]


def milliseconds():
    with connection.cursor() as cursor:
        cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout'")
        return cursor.fetchone()[0]


def configure(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f'{value}ms'])


def is_entry(sql, route):
    table, column = ('execution_jobs_nativejob', 'result') if route == 'list' else ('execution_jobs_nativeadoption', 'proposal')
    return sql.startswith('SELECT') and f'FROM "{table}"' in sql and f'"{column}"' in sql


@pytest.mark.parametrize('route', ['list', 'detail'])
def test_record_materialization_receipts_and_final_checks_share_bound_with_audits_outside(reviewed, route, monkeypatch):
    w = reviewed
    baseline = w.clients['reviewer'].get(url(w, route)).json()
    before, entered, reads, checked, writes = snapshot(), [], [], [], []
    active = False
    original, recheck = history._bounded_read, assessment.projects.recheck

    @contextmanager
    def bound():
        nonlocal active
        entered.append(True)
        with original():
            active = True
            try:
                yield
            finally:
                active = False

    def inspect(execute, sql, params, many, context):
        if is_entry(sql, route) or sql.startswith('SELECT') and any(f'FROM "{name}"' in sql for name in
                ['execution_jobs_nativeadoptionevent', 'execution_jobs_nativeprotectedinput']):
            reads.append(active)
        if sql.startswith('SELECT') and 'FROM "execution_jobs_nativeprotectedinput"' in sql:
            assert '"payload"' not in sql.split('FROM', 1)[0], 'read fetched protected outcome bytes'
        if sql.lstrip().startswith(('INSERT', 'UPDATE', 'DELETE')):
            writes.append((sql.split()[0], '"access_control_projectauthorityevent"' in sql, active))
        return execute(sql, params, many, context)

    def check(*args, **kwargs):
        checked.append(active)
        return recheck(*args, **kwargs)

    monkeypatch.setattr(history, '_bounded_read', bound)
    monkeypatch.setattr(assessment.projects, 'recheck', check)
    monkeypatch.setattr(service, 'locked', lambda: pytest.fail('adoption read acquired queue execution lock'))
    with connection.execute_wrapper(inspect):
        response = w.clients['reviewer'].get(url(w, route))
    assert response.status_code == 200 and response.json() == baseline
    assert entered == [True] and reads and all(reads) and True in checked
    assert writes == [('INSERT', True, False), ('UPDATE', True, False)]
    assert response['Cache-Control'] == 'no-store' and snapshot() == before


@pytest.mark.parametrize('route', ['list', 'detail'])
@pytest.mark.parametrize('initial', [0, 17000, 2000, 1000])
def test_effective_postgresql_ceiling_and_exact_caller_restoration(reviewed, route, initial):
    w, postgres = reviewed, connection.vendor == 'postgresql'
    before, seen = snapshot(), []
    original = milliseconds() if postgres else None
    def inspect(execute, sql, params, many, context):
        if is_entry(sql, route):
            seen.append(milliseconds() if postgres else 'sqlite')
        return execute(sql, params, many, context)
    with transaction.atomic():
        if postgres:
            configure(initial)
        with connection.execute_wrapper(inspect):
            response = w.clients['reviewer'].get(url(w, route))
        assert response.status_code == 200, response.content
        assert seen and set(seen) == {min(initial or 5000, 5000) if postgres else 'sqlite'}
        if postgres:
            assert milliseconds() == initial
        assert not connection.needs_rollback
    if postgres:
        assert milliseconds() == original
    assert snapshot() == before


@pytest.mark.parametrize('method', ['get', 'head'])
@pytest.mark.parametrize('stage', ['list_entry', 'detail_entry', 'events', 'protected_metadata'])
def test_real_cancellation_preserves_private_errors_and_connection_reuse(reviewed, method, stage):
    w, postgres, injected = reviewed, connection.vendor == 'postgresql', []
    route = 'detail' if stage == 'detail_entry' else 'list'
    before = snapshot()
    def slow(execute, sql, params, many, context):
        matches = is_entry(sql, route) if stage.endswith('entry') else (sql.startswith('SELECT') and
            f'FROM "execution_jobs_{"nativeadoptionevent" if stage == "events" else "nativeprotectedinput"}"' in sql)
        if matches and not injected:
            injected.append(True)
            if postgres:
                execute('SELECT pg_sleep(1)', None, False, context)
            else:
                raise DatabaseError('private SQL, parameters and driver credentials')
        return execute(sql, params, many, context)
    with transaction.atomic():
        if postgres:
            configure(100)
        with connection.execute_wrapper(slow):
            response = getattr(w.clients['reviewer'], method)(url(w, route))
        assert injected == [True] and response.status_code == 503
        assert response['Cache-Control'] == 'no-store'
        if method == 'head':
            assert response.content == b''
        else:
            assert response.json()['error_code'] == ('project_authority_unavailable' if stage.endswith('entry') else 'job_storage_unavailable')
            assert b'parameters' not in response.content and b'credentials' not in response.content
            assert b'proposal_sha256' not in response.content and b'protected_inputs' not in response.content
        assert not connection.needs_rollback
        if postgres:
            assert milliseconds() == 100
        assert snapshot() == before


@pytest.mark.parametrize('route', ['list', 'detail'])
def test_default_ceiling_cancels_previously_unlimited_record_query(reviewed, route):
    w, before, injected = reviewed, snapshot(), []
    if connection.vendor != 'postgresql':
        assert w.clients['reviewer'].get(url(w, route)).status_code == 200
        assert snapshot() == before
        return
    def slow(execute, sql, params, many, context):
        if is_entry(sql, route) and not injected:
            injected.append(True)
            execute('SELECT pg_sleep(6)', None, False, context)
        return execute(sql, params, many, context)
    with transaction.atomic():
        configure(0)
        with connection.execute_wrapper(slow):
            response = w.clients['reviewer'].get(url(w, route))
        assert response.status_code == 503 and injected == [True]
        assert response.json()['error_code'] == 'project_authority_unavailable'
        assert milliseconds() == 0 and not connection.needs_rollback
    assert snapshot() == before


@pytest.mark.parametrize('route', ['list', 'detail'])
def test_initial_unauthorized_actor_is_denied_before_the_bound(reviewed, route, monkeypatch):
    monkeypatch.setattr(history, '_bounded_read', lambda: pytest.fail('bound entered before initial authority'))
    response = reviewed.clients['outsider'].get(url(reviewed, route))
    assert response.status_code == 403 and response['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('route', ['list', 'detail'])
def test_bound_configuration_outage_returns_existing_private_storage_error(reviewed, route, monkeypatch):
    before = snapshot()
    @contextmanager
    def unavailable():
        raise DatabaseError('private timeout configuration details')
        yield
    monkeypatch.setattr(history, '_bounded_read', unavailable)
    response = reviewed.clients['reviewer'].get(url(reviewed, route))
    assert response.status_code == 503 and response.json() == {'error_code': 'job_storage_unavailable'}
    assert response['Cache-Control'] == 'no-store' and snapshot() == before


@pytest.mark.parametrize('route', ['list', 'detail'])
def test_repeated_nested_reads_restore_enclosing_history_timeout(reviewed, route):
    before, postgres = snapshot(), connection.vendor == 'postgresql'
    with transaction.atomic():
        if postgres:
            configure(17000)
        with history._bounded_read():
            for _ in range(2):
                response = reviewed.clients['reviewer'].get(url(reviewed, route))
                assert response.status_code == 200
                if postgres:
                    assert milliseconds() == 5000
        if postgres:
            assert milliseconds() == 17000
    assert snapshot() == before
