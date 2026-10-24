"""Installation metadata triage is bounded and cannot cause execution or reads of outcomes."""

import json
from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from execution_jobs import operator_triage, service
from execution_jobs.models import NativeJob
from tests.unit.test_native_queue_history import add
from tests.unit.test_native_job_pagination import listing  # noqa: F401

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def snapshot(monkeypatch):
    # The native suite and private Linux qualifier exercise real PostgreSQL
    # read-only/repeatable-read settings. SQLite adapts PostgreSQL control
    # statements only; real model queries still execute.
    if connection.vendor != "postgresql":
        import django.db
        original = connection.cursor

        @contextmanager
        def cursor():
            with original() as current:
                class SettingsCursor:
                    def execute(self, sql, params=None):
                        self.last = sql
                        if sql in {"SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY", "SET LOCAL statement_timeout = '5000ms'",
                                   "SELECT current_setting('statement_timeout'), setting::bigint FROM pg_settings WHERE name = 'statement_timeout'"}:
                            assert params is None
                        else:
                            assert sql == "SELECT set_config('statement_timeout', %s, true)" and params == ["5000ms"]

                    def fetchone(self):
                        assert self.last == "SELECT current_setting('statement_timeout'), setting::bigint FROM pg_settings WHERE name = 'statement_timeout'"
                        return "0", 0
                yield SettingsCursor()

        class SettingsConnection:
            vendor = "postgresql"

            @property
            def in_atomic_block(self):
                return connection.in_atomic_block

            def cursor(self):
                return cursor()

        monkeypatch.setattr(django.db, "connection", SettingsConnection())
    return operator_triage.read_snapshot


def test_metadata_has_explicit_installation_scope_without_fetching_jobs_or_outcomes(listing, snapshot, monkeypatch):
    row = add(listing, state="failed", other=True, result={"never": "sensitive-model"})
    NativeJob.objects.filter(pk=row.pk).update(specification={"kind": "sensitive-name"}, reason_code="sensitive-name", actor_snapshot={"never": "sensitive-name"})
    monkeypatch.setattr(NativeJob, "from_db", lambda *a, **k: pytest.fail("full job fetched"))
    value = snapshot()
    assert value["scope"] == "trusted_installation_all_projects" and value["read_only_transaction"]
    assert value["rows"][0]["job_id"] == str(row.pk) and value["rows"][0]["kind"] == "unsupported"
    assert "sensitive" not in json.dumps(value) and "actor" not in json.dumps(value)
    assert value["live_service_health"] == "not_tested" and not value["recovery_authorized"]


@pytest.mark.parametrize("state,fields,flags", [
    ("failed", {}, ["failed"]), ("blocked", {}, ["blocked"]),
    ("running", {"lease_until": None}, ["missing_lease"]),
    ("cancel_requested", {"lease_until": None, "attempts": 3}, ["attempt_limit", "missing_lease"]),
    ("queued", {"attempts": 3}, ["attempt_limit"]),
    ("running", {"lease_until": "past", "expires_at": "past", "attempts": 3}, ["expired_request", "attempt_limit", "overdue_lease"]),
])
def test_incident_signals_and_guidance_are_nonexclusive(listing, snapshot, state, fields, flags):
    fields = {k: timezone.now() - timedelta(seconds=1) if v == "past" else v for k, v in fields.items()}
    row = add(listing, state=state, **fields)
    value = snapshot()
    assert value["incident_total"] == 1 and value["rows"][0]["job_id"] == str(row.pk)
    assert value["rows"][0]["signals"] == flags
    assert all(value["signals"][flag] == 1 and value["guidance"][flag] for flag in flags)


def test_no_incident_is_not_a_health_claim_and_reading_cannot_mutate_jobs(listing, snapshot, monkeypatch):
    for name in ["claim", "execute", "reconcile", "dispatch", "cancel"]:
        if hasattr(service, name):
            monkeypatch.setattr(service, name, lambda *a, **k: pytest.fail("observation executed work"))
    before = list(NativeJob.objects.values())
    value = snapshot()
    assert value["incident_total"] == 0 and value["rows"] == [] and not value["truncated"]
    assert value["states"]["queued"] == 53 and value["live_service_health"] == "not_tested"
    assert list(NativeJob.objects.values()) == before


def test_bounded_incident_rows_do_not_hide_total_or_overlapping_counts(listing, snapshot):
    NativeJob.objects.update(state="failed")
    value = snapshot()
    assert len(value["rows"]) == value["row_limit"] == 50 and value["incident_total"] == 53 and value["truncated"]
    assert [v["job_id"] for v in value["rows"]] == [str(pk) for pk in NativeJob.objects.order_by("-created_at", "-pk").values_list("pk", flat=True)[:50]]


def test_unsupported_database_blocks_before_queue_query(listing, monkeypatch):
    import django.db
    monkeypatch.setattr(django.db, "connection", type("Unsupported", (), {"vendor": "unsupported"})())
    monkeypatch.setattr(NativeJob.objects, "all", lambda: pytest.fail("unsupported storage queried"))
    with pytest.raises(ValueError, match="operator_postgresql_required"):
        operator_triage.read_snapshot()
