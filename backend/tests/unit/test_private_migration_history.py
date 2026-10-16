"""A sealed private image must recognize the database's applied migration history."""

from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from execution_jobs import preflight

pytestmark = [pytest.mark.unit, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def private_history(settings, monkeypatch):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    # Transport-only seam: the real loader/recorder below reads this test's DB.
    # TLS connectivity is independently qualified by the private runtime suite.
    database = MagicMock(vendor="postgresql")
    database.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    broker = MagicMock()
    executors = []

    def executor(_):
        value = MigrationExecutor(connection)
        executors.append(value)
        return value

    monkeypatch.setattr(preflight, "connection", database)
    monkeypatch.setattr(preflight, "MigrationExecutor", executor)
    # Physical catalog behavior is independently exercised by schema-presence
    # tests. This fixture isolates real migration-history behavior from TLS.
    monkeypatch.setattr(preflight, "check_schema", lambda: None)
    monkeypatch.setattr(preflight, "check_schema_privileges", lambda: None)
    monkeypatch.setattr("backend.celery.app.connection_for_write", lambda: broker)
    # check_consistent_history must receive the real database as well.
    database.alias = connection.alias
    database.introspection = connection.introspection
    # MigrationRecorder only needs cursor/introspection; keep the TLS fake
    # confined to the initial TLS query and route history reads to the real DB.
    actual_cursor = connection.cursor
    calls = [0]

    def cursor():
        calls[0] += 1
        return MagicMock(__enter__=lambda _: MagicMock(fetchone=lambda: (True,)),
                         __exit__=lambda *args: False) if calls[0] == 1 else actual_cursor()

    database.cursor.side_effect = cursor
    yield broker.__enter__.return_value, executors


def run_preflight(command):
    if command:
        output = StringIO()
        call_command("check_job_runtime", stdout=output)
        return output.getvalue()
    return preflight.check_runtime()


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("unknown", [
    ("execution_jobs", "9999_unrecognized_future_schema"),
    ("retired_app", "0001_private_history_sentinel"),
])
def test_unknown_applied_migration_blocks_before_broker(private_history, command, unknown):
    recorder = MigrationRecorder(connection)
    recorder.record_applied(*unknown)
    try:
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_migration_history_invalid$") as caught:
            run_preflight(command)
        assert unknown[0] not in str(caught.value) and unknown[1] not in str(caught.value)
        private_history[0].ensure_connection.assert_not_called()
        assert unknown in recorder.applied_migrations(), "preflight must never repair history"
    finally:
        recorder.record_unapplied(*unknown)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("missing", [("declaration", "0001_initial"), ("access_control", "0002_assistantactionapproval")])
def test_applied_child_without_parent_is_invalid_history(private_history, command, missing):
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*missing)
    try:
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_migration_history_invalid$"):
            run_preflight(command)
        private_history[0].ensure_connection.assert_not_called()
        assert missing not in recorder.applied_migrations()
    finally:
        recorder.record_applied(*missing)


@pytest.mark.parametrize("command", [False, True])
def test_consistent_pending_leaf_keeps_pending_diagnostic(private_history, command):
    missing = ("deployment", "0002_packagereviewevent_evidence_and_more")
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*missing)
    try:
        expected = CommandError if command else preflight.RuntimeUnavailable
        with pytest.raises(expected, match="^job_migrations_required$"):
            run_preflight(command)
        private_history[0].ensure_connection.assert_not_called()
        assert missing not in recorder.applied_migrations()
    finally:
        recorder.record_applied(*missing)


@pytest.mark.parametrize("command", [False, True])
def test_current_exact_history_allows_connectivity_probe(private_history, command):
    before = set(MigrationRecorder(connection).applied_migrations())
    result = run_preflight(command)
    assert "current" in str(result)
    private_history[0].ensure_connection.assert_called_once_with(max_retries=0)
    assert len(private_history[1]) == 1
    assert before == set(MigrationRecorder(connection).applied_migrations())
