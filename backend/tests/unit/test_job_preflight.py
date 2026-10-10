"""Preflight uses real connection attempts, blocks unsafe startup, hides secrets."""

from io import StringIO
from pathlib import Path
import os
import subprocess
from unittest.mock import MagicMock, patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from execution_jobs import preflight

pytestmark = pytest.mark.unit


@pytest.fixture
def checks(settings):
    settings.DECLARAI_RUNTIME_PROFILE = "private"
    settings.DECLARAI_JOBS_ENABLED = True
    database = MagicMock(vendor="postgresql")
    database.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    executor = MagicMock()
    executor.migration_plan.return_value = []
    broker = MagicMock()
    with (
        patch.object(preflight, "connection", database),
        patch.object(preflight, "MigrationExecutor", return_value=executor),
        patch("backend.celery.app.connection_for_write", return_value=broker),
    ):
        yield database, executor, broker.__enter__.return_value


def test_private_preflight_connects_without_task_publication(checks):
    result = preflight.check_runtime()
    database, executor, broker = checks
    database.ensure_connection.assert_called_once()
    executor.migration_plan.assert_called_once()
    broker.ensure_connection.assert_called_once_with(max_retries=0)
    assert result["broker_connection"] == "verified"


@pytest.mark.parametrize("failure,code", [
    ("profile", "job_private_configuration_required"),
    ("disabled", "job_private_configuration_required"),
    ("engine", "job_private_postgresql_required"),
    ("tls", "job_metadata_tls_required"),
    ("migrations", "job_migrations_required"),
    ("database", "job_storage_unavailable"),
    ("broker", "job_broker_unavailable"),
])
def test_failed_preflight_blocks_launch_and_never_exposes_secrets(checks, settings, failure, code):
    database, executor, broker = checks
    secret_error = RuntimeError("rediss://private:DO_NOT_DISCLOSE@secret-host/1")
    if failure == "profile":
        settings.DECLARAI_RUNTIME_PROFILE = "development"
    elif failure == "disabled":
        settings.DECLARAI_JOBS_ENABLED = False
    elif failure == "engine":
        database.vendor = "sqlite"
    elif failure == "tls":
        database.cursor.return_value.__enter__.return_value.fetchone.return_value = (False,)
    elif failure == "migrations":
        executor.migration_plan.return_value = [object()]
    elif failure == "database":
        database.ensure_connection.side_effect = secret_error
    else:
        broker.ensure_connection.side_effect = secret_error
    with pytest.raises(CommandError, match="^" + code + "$"):
        call_command("check_job_runtime", stdout=StringIO())
    if failure != "broker":
        broker.ensure_connection.assert_not_called()


@pytest.mark.parametrize("profile,args", [
    ("development", ["worker"]),
    ("private", []),
    ("private", ["worker", "--concurrency=999"]),
    ("private", ["arbitrary-code"]),
])
def test_private_launcher_rejects_downgrades_and_arbitrary_commands(profile, args):
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["sh", str(root / "docker/private-job-entrypoint.sh"), *args],
        env={**os.environ, "DECLARAI_RUNTIME_PROFILE": profile},
        capture_output=True, text=True, timeout=5, check=False,
    )
    assert result.returncode == 1
    assert not result.stdout
    assert "Private job launch requires" in result.stderr or "Select worker or dispatcher" in result.stderr
