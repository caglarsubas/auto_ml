"""Checkpoint rows preserve ORM conversion and fresh data without generic readers."""
import time
import uuid
from unittest.mock import patch

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import DatabaseError, connection

from access_control import projects
from declaration.models import Declaration
from execution_jobs import service
from execution_jobs.models import JobEvent, NativeJob
from tests.unit.test_native_checkpoint_payloads import worker  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
FULL = ('id', 'state', 'lease_token', 'lease_until', 'expires_at', 'authority', 'specification', 'project', 'dataset', 'source_dataset')
GUARDS = ('id', 'state', 'lease_token', 'lease_until', 'expires_at')


@pytest.mark.parametrize('fields', [FULL, GUARDS], ids=['authority', 'guards'])
@pytest.mark.parametrize('string_id', [False, True])
@pytest.mark.parametrize('source', [False, True])
def test_converted_rows_match_the_independent_orm_projection(worker, fields, string_id, source):
    if source:
        dataset = Declaration.objects.create(name='Materialization source')
        projects.bind_dataset(dataset, worker.project.pk)
        NativeJob.objects.filter(pk=worker.job.pk).update(source_dataset=dataset)
    expected = NativeJob.objects.only(*fields).get(pk=worker.job.pk)
    before = NativeJob.objects.values().get(pk=worker.job.pk)
    identifier = str(worker.job.pk) if string_id else worker.job.pk
    with patch.object(NativeJob, 'refresh_from_db', side_effect=AssertionError('Deferred payload read')):
        actual = service._checkpoint_row(identifier, fields)
        assert actual.get_deferred_fields() == expected.get_deferred_fields()
        assert actual._state.db == expected._state.db and actual._state.adding is False
        for name in fields:
            key = NativeJob._meta.get_field(name).attname
            assert type(getattr(actual, key)) is type(getattr(expected, key))
            assert getattr(actual, key) == getattr(expected, key)
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()


@pytest.mark.parametrize('fields', [FULL, GUARDS])
def test_every_read_observes_committed_changes_and_still_materializes_the_model(worker, fields):
    first = service._checkpoint_row(worker.job.pk, fields)
    token = uuid.uuid4()
    NativeJob.objects.filter(pk=worker.job.pk).update(state='cancel_requested', lease_token=token)
    with patch.object(NativeJob, 'from_db', wraps=NativeJob.from_db) as loaded:
        second = service._checkpoint_row(worker.job.pk, fields)
    assert first.state == 'running' and second.state == 'cancel_requested' and second.lease_token == token
    assert loaded.call_count == 1
    assert loaded.call_args.args[0] == second._state.db
    expected_order = [f.attname for f in NativeJob._meta.concrete_fields if f.name in fields or f.attname in fields]
    assert loaded.call_args.args[1] == expected_order


@pytest.mark.parametrize('fields', [FULL, GUARDS])
def test_missing_rows_retain_the_model_missing_exception(worker, fields):
    with pytest.raises(NativeJob.DoesNotExist):
        service._checkpoint_row(uuid.uuid4(), fields)


@pytest.mark.parametrize('fields', [FULL, GUARDS])
def test_model_materialization_failures_propagate_without_writes(worker, monkeypatch, fields):
    failure = DatabaseError('Owned model conversion failure')
    before = NativeJob.objects.values().get(pk=worker.job.pk)

    def unavailable(*args):
        raise failure

    monkeypatch.setattr(NativeJob, 'from_db', unavailable)
    with pytest.raises(DatabaseError) as caught:
        service._checkpoint_row(worker.job.pk, fields)
    assert caught.value is failure
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before


@pytest.mark.parametrize('field', ['authority', 'specification'])
def test_live_field_conversion_failure_is_never_hidden(worker, monkeypatch, field):
    failure = DatabaseError('Owned JSON conversion failure')
    original = NativeJob._meta.get_field(field).from_db_value
    calls = []

    def convert(*args):
        calls.append(True)
        raise failure

    with monkeypatch.context() as scoped:
        scoped.setattr(NativeJob._meta.get_field(field), 'from_db_value', convert)
        with pytest.raises(DatabaseError) as caught:
            service._checkpoint_row(worker.job.pk, FULL)
    assert caught.value is failure and calls == [True]
    assert NativeJob._meta.get_field(field).from_db_value == original


@pytest.mark.parametrize('fields', [('state',), ('lease_token', 'expires_at')])
def test_missing_primary_key_cannot_create_a_partially_trusted_row(worker, fields):
    with pytest.raises(FieldDoesNotExist):
        service._checkpoint_row(worker.job.pk, fields)


@pytest.mark.parametrize('mode', ['duplicate', 'short', 'long', 'database'])
def test_cursor_failures_and_contradictory_rows_never_create_a_checkpoint(worker, monkeypatch, mode):
    original = connection.cursor
    before = NativeJob.objects.values().get(pk=worker.job.pk)
    closed = []

    class Cursor:
        def __enter__(self):
            self.cursor = original(); self.cursor.__enter__(); return self

        def __exit__(self, *args):
            closed.append(True)
            return self.cursor.__exit__(*args)

        def execute(self, *args):
            return self.cursor.execute(*args)

        def fetchall(self):
            rows = self.cursor.fetchall()
            if mode == 'database':
                raise DatabaseError('Owned row read failure')
            if mode == 'duplicate':
                return rows * 2
            return [row[:-1] if mode == 'short' else (*row, None) for row in rows]

    with monkeypatch.context() as scoped:
        scoped.setattr(connection, 'cursor', Cursor)
        with pytest.raises(NativeJob.MultipleObjectsReturned if mode == 'duplicate' else DatabaseError):
            service._checkpoint_row(worker.job.pk, FULL)
    assert closed == [True]
    assert NativeJob.objects.values().get(pk=worker.job.pk) == before
    assert not JobEvent.objects.filter(job=worker.job).exists()
