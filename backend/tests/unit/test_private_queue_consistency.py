"""Digest integrity must not substitute for coherent incident observations."""

import datetime as dt
from collections import Counter

import pytest

from tests.unit.test_private_queue_evidence import NOW, module, sample, verify

pytestmark = pytest.mark.unit


def populated():
    value = sample()
    value.update(observation_started_at=(NOW - dt.timedelta(seconds=1)).isoformat(),
                 observation_finished_at=(NOW + dt.timedelta(seconds=1)).isoformat())
    q = value["queue"]
    rows = []
    for i, (state, flags, attempts, expiry, lease) in enumerate([
        ("failed", ["failed"], 1, 60, None),
        ("blocked", ["blocked"], 0, 60, None),
        ("running", ["expired_request", "attempt_limit", "overdue_lease"], 3, -1, -1),
        ("cancel_requested", ["missing_lease"], 1, 60, None),
        ("queued", ["attempt_limit"], 3, 60, None),
    ]):
        rows.append(dict(job_id=f"00000000-0000-0000-0000-{100-i:012x}",
                         project_id="11111111-1111-1111-1111-111111111111", dataset_id=1,
                         revision=i, state=state, attempts=attempts, kind="unsupported",
                         created_at=(NOW - dt.timedelta(days=1)).isoformat(),
                         expires_at=(NOW + dt.timedelta(seconds=expiry)).isoformat(),
                         lease_until=(NOW + dt.timedelta(seconds=lease)).isoformat() if lease is not None else None,
                         signals=flags))
    q.update(rows=rows, incident_total=len(rows))
    q["states"].update(Counter(row["state"] for row in rows))
    q["states"]["queued"] += 1  # Routine work need not match any incident.
    q["states"]["succeeded"] = 2
    q["states"]["unknown"] = 1
    q["signals"].update(Counter(flag for row in rows for flag in row["signals"]))
    return value


@pytest.mark.parametrize("mutation", [
    lambda q: q["states"].update(failed=2),
    lambda q: q["states"].update(blocked=2),
    lambda q: q["signals"].update(failed=2),
    lambda q: q["signals"].update(blocked=2),
    lambda q: q["signals"].update(expired_request=4),
    lambda q: q["signals"].update(attempt_limit=5),
    lambda q: q["signals"].update(overdue_lease=3),
    lambda q: q["signals"].update(missing_lease=2),
    lambda q: q["states"].update(running=0),
    lambda q: q["signals"].update(attempt_limit=1),
    lambda q: q["signals"].update(expired_request=0),
    lambda q: q["signals"].update(missing_lease=0),
    lambda q: q["rows"][0].update(signals=["failed", "attempt_limit"]),
    lambda q: q["rows"][0].update(state="succeeded"),
    lambda q: q["rows"][4].update(attempts=0),
    lambda q: q["rows"][2].update(expires_at=(NOW + dt.timedelta(seconds=30)).isoformat()),
    lambda q: q["rows"][2].update(lease_until=None),
    lambda q: q["rows"][2].update(lease_until=(NOW + dt.timedelta(seconds=30)).isoformat()),
    lambda q: q["rows"][3].update(lease_until=(NOW + dt.timedelta(seconds=30)).isoformat()),
    lambda q: q["rows"][4].update(signals=["attempt_limit", "missing_lease"]),
    lambda q: q.update(observed_at=(NOW + dt.timedelta(seconds=2)).isoformat()),
    lambda q: q.update(observed_at=(NOW - dt.timedelta(seconds=2)).isoformat()),
])
def test_recomputed_trusted_digest_cannot_bless_contradictory_snapshot(mutation):
    value = populated()
    mutation(value["queue"])
    # The helper recomputes both wrapper and externally supplied digests. These
    # cases exercise consistency, not the already-qualified tamper detector.
    with pytest.raises(ValueError):
        verify(value)


def truncated():
    value = populated()
    q = value["queue"]
    template = q["rows"][2]
    q["rows"] = [dict(template, job_id=f"00000000-0000-0000-0000-{100-i:012x}") for i in range(50)]
    q.update(incident_total=51, truncated=True)
    q["states"] = {s: 51 if s == "running" else 0 for s in q["states"]}
    q["signals"] = {s: 51 if s in template["signals"] else 0 for s in q["signals"]}
    return value


@pytest.mark.parametrize("mutation", [
    lambda q: q["states"].update(running=49),
    lambda q: q["signals"].update(expired_request=49),
    lambda q: q["signals"].update(expired_request=52),
    lambda q: q["rows"][0].update(state="blocked", signals=["blocked"]),
])
def test_truncated_sample_cannot_exceed_global_counts_or_hide_impossible_remainder(mutation):
    value = truncated()
    mutation(value["queue"])
    with pytest.raises(ValueError):
        verify(value)


@pytest.mark.parametrize("shape", ["no_remaining_signals", "no_remaining_active_jobs"])
def test_omitted_incidents_must_have_possible_signals_and_active_lease_population(shape):
    value = truncated()
    q = value["queue"]
    if shape == "no_remaining_signals":
        q["signals"] = {s: 50 if count else 0 for s, count in q["signals"].items()}
    else:
        q["states"].update(running=50, queued=1)
        q["signals"] = {s: 51 if s == "attempt_limit" else 1 if s == "missing_lease" else 0 for s in q["signals"]}
        for row in q["rows"]:
            row.update(expires_at=(NOW + dt.timedelta(seconds=60)).isoformat(),
                       lease_until=(NOW + dt.timedelta(seconds=30)).isoformat(), signals=["attempt_limit"])
    with pytest.raises(ValueError):
        verify(value)


@pytest.mark.parametrize("shape", ["empty", "overlapping", "truncated", "disabled", "reordered_flags"])
def test_valid_observations_keep_overlap_truncation_unknown_and_disabled_limits(shape):
    value = sample() if shape == "empty" else truncated() if shape == "truncated" else populated()
    if shape == "disabled":
        value["queue"]["jobs_enabled"] = False
    if shape == "reordered_flags":
        value["queue"]["rows"][2]["signals"].reverse()
    observed, verification = verify(value)
    assert observed == value and verification["queue_consistency"] == "cross_checked_metadata"
    result = module.handoff(observed, verification, "a" * 64)["evidence"]
    assert not result["current_health_qualified"] and not result["recovery_authorized"]
    assert result["truncated"] == value["queue"]["truncated"]


def test_unavailable_observation_is_not_cross_checked_or_converted_to_zero():
    value = sample()
    value["queue"] = dict(status="unavailable", reason="probe_transport_unavailable")
    observed, verification = verify(value)
    result = module.handoff(observed, verification, "a" * 64)["evidence"]
    assert verification["queue_consistency"] == "unavailable"
    assert result["incident_total"] is result["signals"] is result["truncated"] is None


def test_out_of_order_sample_is_disclosed_and_preserved_for_investigation():
    value = populated()
    value["queue"]["states"]["unknown"] = 0
    value["queue"]["rows"].reverse()
    observed, verification = verify(value)
    assert observed == value and verification["sample_order"] == "not_newest_first"
    result = module.handoff(observed, verification, "a" * 64)["evidence"]
    assert [r["job_id"] for r in result["job_references"]] == [r["job_id"] for r in value["queue"]["rows"]]
    assert any(s["id"] == "incomplete" and "out of declared order" in s["instruction"] for s in result["investigation_steps"])


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("shape", ["overlap", "truncated"])
def test_actual_orm_snapshot_passes_consistency_without_job_or_service_mutation(shape, listing, snapshot):
    from django.utils import timezone
    from execution_jobs.models import NativeJob
    from tests.unit.test_native_queue_history import add

    started = timezone.now()
    if shape == "overlap":
        job = add(listing, state="running", attempts=3, expires_at=started - dt.timedelta(seconds=1), lease_until=None)
        NativeJob.objects.filter(pk=job.pk).update(created_at=started - dt.timedelta(days=1))
    else:
        NativeJob.objects.update(state="failed")
    before = list(NativeJob.objects.values())
    value = sample()
    value["queue"] = snapshot()
    finished = timezone.now()
    value.update(observation_started_at=started.isoformat(), observation_finished_at=finished.isoformat())
    observed, verification = verify(value, now=finished)
    assert verification["queue_consistency"] == "cross_checked_metadata"
    assert observed["queue"]["incident_total"] == (1 if shape == "overlap" else 53)
    assert observed["queue"]["truncated"] == (shape == "truncated")
    assert list(NativeJob.objects.values()) == before


# Existing fixture performs real PostgreSQL transaction settings in the native
# suite; SQLite adapts only its unsupported SET statements, exactly as before.
from tests.unit.test_native_operator_triage import snapshot  # noqa: E402,F401
from tests.unit.test_native_job_pagination import listing  # noqa: E402,F401
