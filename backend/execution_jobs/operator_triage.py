"""Fixed installation-operator probe. Never exposed through HTTP, MCP or Celery."""

import json
import os
import sys
from pathlib import Path

MAX_ROWS = 50
MAX_BYTES = 131072
SCHEMA = "native_queue_operator_snapshot_v1"
STATES = ("queued", "running", "cancel_requested", "succeeded", "blocked", "failed", "cancelled")
KINDS = ("package_integrity_v1", "native_csv_scoring_v1", "native_numeric_training_search_v1",
         "native_training_scoring_v1", "native_protected_assessment_v1")
GUIDANCE = {
    "failed": "Inspect the exact project job receipt and worker/dispatcher/database/broker availability with the project owner.",
    "blocked": "Ask the project owner to resolve changed authority, inputs or runtime before preparing any new explicit request.",
    "expired_request": "Retain this request identity; inspect dispatcher progress. Observation does not reconcile expiry.",
    "overdue_lease": "Inspect worker interruption and dispatcher progress. Only normal bounded recovery may retry the same request.",
    "missing_lease": "Investigate inconsistent active metadata with the installation owner; do not edit job state.",
    "attempt_limit": "Retain the receipt and inspect attempts. Do not increase limits or recreate a request from this report.",
}


def read_snapshot():
    from django.conf import settings
    from django.db import connection, transaction
    from django.db.models import Count, Q
    from django.utils import timezone
    from execution_jobs.service import LIMITS
    from execution_jobs.models import NativeJob

    if connection.vendor != "postgresql":
        raise ValueError("operator_postgresql_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '5000ms'")
        observed = timezone.now()
        unfinished = Q(state__in=["queued", "running", "cancel_requested"])
        active = Q(state__in=["running", "cancel_requested"])
        conditions = {
            "failed": Q(state="failed"), "blocked": Q(state="blocked"),
            "expired_request": unfinished & Q(expires_at__lte=observed),
            "overdue_lease": active & Q(lease_until__lte=observed),
            "missing_lease": active & Q(lease_until__isnull=True),
            "attempt_limit": unfinished & Q(attempts__gte=LIMITS["attempts"]),
        }
        selected = Q(pk__in=[])
        for condition in conditions.values():
            selected |= condition
        jobs = NativeJob.objects.all()
        states = jobs.aggregate(**{s: Count("pk", filter=Q(state=s)) for s in STATES}, unknown=Count("pk", filter=~Q(state__in=STATES)))
        signals = jobs.aggregate(**{s: Count("pk", filter=q) for s, q in conditions.items()})
        total = jobs.filter(selected).count()
        # Values only: no model construction, full specification, result, actor,
        # authority, events, inputs, names, predictions or sealed bytes fetched.
        rows = list(jobs.filter(selected).order_by("-created_at", "-pk").values(
            "id", "dataset_id", "project_id", "revision", "state", "attempts", "created_at",
            "expires_at", "lease_until", "specification__kind",
        )[:MAX_ROWS])
        incidents = []
        for row in rows:
            state = row["state"]
            flags = [state] if state in {"failed", "blocked"} else []
            if state in {"queued", "running", "cancel_requested"}:
                if row["expires_at"] <= observed:
                    flags.append("expired_request")
                if row["attempts"] >= LIMITS["attempts"]:
                    flags.append("attempt_limit")
                if state != "queued":
                    if row["lease_until"] is None:
                        flags.append("missing_lease")
                    elif row["lease_until"] <= observed:
                        flags.append("overdue_lease")
            incidents.append({
                "job_id": str(row["id"]), "dataset_id": row["dataset_id"], "project_id": str(row["project_id"]),
                "revision": row["revision"], "state": state, "attempts": row["attempts"],
                "kind": row["specification__kind"] if row["specification__kind"] in KINDS else "unsupported",
                **{k: row[k].isoformat() if row[k] else None for k in ("created_at", "expires_at", "lease_until")},
                "signals": flags,
            })
        return {"schema": SCHEMA, "status": "observed", "observed_at": observed.isoformat(),
                "scope": "trusted_installation_all_projects", "read_only_transaction": True,
                "repeatable_read": True, "statement_timeout_ms": 5000, "jobs_enabled": settings.DECLARAI_JOBS_ENABLED,
                "states": states, "signals": signals, "incident_total": total, "attempt_limit": LIMITS["attempts"],
                "rows": incidents, "row_limit": MAX_ROWS, "truncated": total > len(incidents),
                "selection": "Newest matching jobs by creation time and UUID; signals may overlap. Terminal failures are historical, not proof of a current outage.",
                "guidance": GUIDANCE, "live_service_health": "not_tested", "recovery_authorized": False}


def main():
    # The controller chooses the exact trusted image/container; this entrypoint
    # additionally checks packaged sources before importing Django applications.
    if sys.platform != "linux" or os.getuid() != 10001 or os.getgid() != 10001:
        raise ValueError("operator_probe_identity_invalid")
    if os.environ.get("DECLARAI_RUNTIME_PROFILE") != "private" or os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings") != "backend.settings":
        raise ValueError("operator_probe_profile_invalid")
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    from private_runtime_manifest import verify
    verify(root)
    os.environ["DJANGO_SETTINGS_MODULE"] = "backend.settings"
    import django
    django.setup()
    try:
        value = read_snapshot()
    except Exception:
        # Database/driver messages may contain credentials, hosts or SQL.
        value = {"schema": SCHEMA, "status": "unavailable", "reason": "queue_metadata_unavailable"}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("operator_probe_output_budget")
    sys.stdout.buffer.write(raw)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("operator_probe_unavailable", file=sys.stderr)
        sys.exit(1)
