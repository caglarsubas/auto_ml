"""Operator state classification stays exact under insensitive SQL collations."""

import json
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from execution_jobs import operator_triage
from execution_jobs.models import NativeJob
from tests.unit.test_native_job_pagination import listing  # noqa: F401
from tests.unit.test_native_operator_triage import snapshot  # noqa: F401
from tests.unit.test_native_queue_history import add
from tests.unit.test_private_queue_evidence import module as evidence

pytestmark = [pytest.mark.unit, pytest.mark.auth_boundary, pytest.mark.django_db(transaction=True)]
UNKNOWN = [s.upper() for s in operator_triage.STATES] + ["faíled", "blócked", "rúnning", "queued ", "legacy_state"]


@pytest.fixture
def insensitive_state(listing, snapshot):  # noqa: F811
    # Real PostgreSQL owns this temporary, deliberately inconsistent column
    # profile. SQLite runs the same receipt/compatibility assertions on its
    # ordinary exact comparisons; it does not claim to simulate ICU behavior.
    if connection.vendor != "postgresql":
        yield snapshot
        return
    quote = connection.ops.quote_name
    table = NativeJob._meta.db_table
    name = "p144_state_" + uuid.uuid4().hex
    catalog = (
        "SELECT a.attcollation, n.nspname, c.collname, format_type(a.atttypid, a.atttypmod) "
        "FROM pg_attribute a JOIN pg_collation c ON c.oid=a.attcollation "
        "JOIN pg_namespace n ON n.oid=c.collnamespace "
        "WHERE a.attrelid=%s::regclass AND a.attname='state'"
    )
    with connection.cursor() as cursor:
        cursor.execute(catalog, [table])
        original = cursor.fetchone()
        assert original[3] == "character varying(24)"
        cursor.execute(f"CREATE COLLATION {quote(name)} (provider=icu, locale='und-u-ks-level1', deterministic=false)")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE {quote(table)} ALTER COLUMN "state" TYPE varchar(24) COLLATE {quote(name)}')
            cursor.execute(f"SELECT 'failed' COLLATE {quote(name)} = 'FAILED', 'failed' COLLATE {quote(name)} = 'faíled'")
            assert cursor.fetchone() == (True, True)
        yield snapshot
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE {quote(table)} ALTER COLUMN "state" TYPE varchar(24) COLLATE {quote(original[1])}.{quote(original[2])}')
            cursor.execute(f"DROP COLLATION {quote(name)}")
            cursor.execute(catalog, [table])
            assert cursor.fetchone() == original


def risky(listing, state):
    now = timezone.now()
    return add(listing, state=state, attempts=3, lease_until=None,
               created_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1))


def check(value):
    evidence.queue(value)
    assert value["read_only_transaction"] and value["repeatable_read"]
    assert value["statement_timeout_ms"] == 5000
    assert value["live_service_health"] == "not_tested" and not value["recovery_authorized"]


@pytest.mark.parametrize("state", UNKNOWN)
def test_noncanonical_labels_remain_unknown_without_false_incidents(listing, insensitive_state, state):  # noqa: F811
    risky(listing, state)
    before = list(NativeJob.objects.order_by("pk").values())
    value = insensitive_state()
    assert value["states"] == {s: 53 if s == "queued" else 0 for s in operator_triage.STATES} | {"unknown": 1}
    assert not any(value["signals"].values()) and value["incident_total"] == 0 and value["rows"] == []
    check(value)
    assert list(NativeJob.objects.order_by("pk").values()) == before


@pytest.mark.parametrize("state", operator_triage.STATES)
def test_supported_states_preserve_overlapping_signals_and_receipt_validation(listing, insensitive_state, state):  # noqa: F811
    row = risky(listing, state)
    before = list(NativeJob.objects.order_by("pk").values())
    value = insensitive_state()
    assert value["states"] == {s: (53 if s == "queued" else 0) + int(s == state) for s in operator_triage.STATES} | {"unknown": 0}
    flags = [state] if state in {"failed", "blocked"} else []
    if state in {"queued", "running", "cancel_requested"}:
        flags += ["expired_request", "attempt_limit"]
        if state != "queued":
            flags.append("missing_lease")
    assert value["signals"] == {s: int(s in flags) for s in operator_triage.GUIDANCE}
    assert value["incident_total"] == int(bool(flags))
    assert [r["job_id"] for r in value["rows"]] == ([str(row.pk)] if flags else [])
    if flags:
        assert value["rows"][0]["signals"] == flags and value["rows"][0]["state"] == state
    check(value)
    assert list(NativeJob.objects.order_by("pk").values()) == before


def test_unknown_collisions_cannot_displace_bounded_canonical_incident_rows(listing, insensitive_state):  # noqa: F811
    for _ in range(53):
        add(listing, state="failed")
        add(listing, state="FAILED")
    # Compute the reference by exact Python labels, independently of SQL's
    # deliberately insensitive default column comparison.
    expected = [str(r["pk"]) for r in NativeJob.objects.order_by("-created_at", "-pk").values("pk", "state") if r["state"] == "failed"]
    before = list(NativeJob.objects.order_by("pk").values())
    value = insensitive_state()
    assert value["states"]["failed"] == value["states"]["unknown"] == value["incident_total"] == 53
    assert value["signals"]["failed"] == 53 and sum(value["signals"].values()) == 53
    assert value["row_limit"] == len(value["rows"]) == 50 and value["truncated"]
    assert [r["job_id"] for r in value["rows"]] == expected[:50]
    assert all(r["state"] == "failed" and r["signals"] == ["failed"] for r in value["rows"])
    check(value)
    assert list(NativeJob.objects.order_by("pk").values()) == before


def test_all_unknown_labels_stay_observable_without_a_health_or_recovery_claim(listing, insensitive_state):  # noqa: F811
    NativeJob.objects.all().update(state="QUEUED", attempts=3, expires_at=timezone.now() - timedelta(hours=1))
    value = insensitive_state()
    assert value["states"]["unknown"] == 53 and sum(value["states"].values()) == 53
    assert not any(value["states"][s] for s in operator_triage.STATES)
    assert not any(value["signals"].values()) and value["incident_total"] == 0 and not value["truncated"]
    check(value)


def test_exact_summary_keeps_metadata_projection_and_never_constructs_full_jobs(listing, insensitive_state, monkeypatch):  # noqa: F811
    hidden = add(listing, state="FAILED", other=True, result={"private-p144-fixture": True})
    visible = add(listing, state="failed", result={"private-p144-fixture": True})
    before = list(NativeJob.objects.order_by("pk").values())
    monkeypatch.setattr(NativeJob, "from_db", lambda *a, **k: pytest.fail("full job materialized"))
    with CaptureQueriesContext(connection) as queries:
        value = insensitive_state()
    assert value["states"]["unknown"] == value["states"]["failed"] == value["incident_total"] == 1
    assert [r["job_id"] for r in value["rows"]] == [str(visible.pk)]
    assert str(hidden.pk) not in json.dumps(value) and "private-p144-fixture" not in json.dumps(value)
    for q in queries:
        sql = q["sql"]
        assert not sql.lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
        assert '"execution_jobs_jobevent"' not in sql and '"modeling_holdoutaccess"' not in sql
        if sql.lstrip().startswith("SELECT") and '"execution_jobs_nativejob"' in sql:
            selected = sql.split(" FROM ", 1)[0]
            assert all(f'"{name}"' not in selected for name in ["result", "authority", "actor_snapshot", "reason_code"])
    check(value)
    assert list(NativeJob.objects.order_by("pk").values()) == before
