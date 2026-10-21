"""Read-only, dataset-scoped metadata observations and bounded keyset navigation."""

import uuid
from datetime import datetime

from django.conf import settings
from django.core import signing
from django.db.models import Count, Min, Q
from django.utils import timezone

from access_control import projects
from execution_jobs import service
from execution_jobs.models import NativeJob

PAGE_SIZE = 50
CURSOR_SECONDS = 3600
SALT = "native-job-history-v1"
STATES = ("queued", "running", "cancel_requested", "succeeded", "blocked", "failed", "cancelled")
KINDS = (service.KIND, service.csv_scoring.KIND, service.training_search.KIND,
         service.training_scoring.KIND, service.native_assessment.KIND)


def key_filter(key, newer=False):
    stamp, identifier = key
    operator = "gt" if newer else "lt"
    return Q(**{f"created_at__{operator}": stamp}) | Q(created_at=stamp, **{f"pk__{operator}": identifier})


def read(actor, file_id, params):
    current = service.scope(actor, file_id)
    # Validate bounded inputs before querying job storage. Authority is always first.
    if set(params) - {"project_id", "state", "kind", "cursor"} or any(len(params.getlist(k)) != 1 for k in params):
        raise ValueError("Unsupported history parameters.")
    state, kind, token = (params.get(k, "") for k in ["state", "kind", "cursor"])
    if state not in ("", *STATES) or kind not in ("", *KINDS) or len(token) > 2048:
        raise ValueError("Unsupported history filter or cursor.")
    observed = timezone.now()
    binding = [actor.pk, file_id, current["project_id"], state, kind]
    cutoff, anchor, newer = observed, None, False
    if token:
        try:
            value = signing.loads(token, salt=SALT, max_age=CURSOR_SECONDS)
            if set(value) != {"binding", "cutoff", "anchor", "newer"} or value["binding"] != binding or type(value["newer"]) is not bool:
                raise ValueError
            cutoff = datetime.fromisoformat(value["cutoff"])
            stamp, identifier = value["anchor"]
            anchor = (datetime.fromisoformat(stamp), uuid.UUID(identifier))
            if timezone.is_naive(cutoff) or timezone.is_naive(anchor[0]) or cutoff > observed or anchor[0] > cutoff:
                raise ValueError
            newer = value["newer"]
        except (signing.BadSignature, ValueError, TypeError, KeyError) as exc:
            raise service.JobConflict("job_history_cursor_invalid_or_expired") from exc

    scope = NativeJob.objects.filter(dataset_id=file_id, project_id=current["project_id"])
    # No result, specification body, actor, event, protected input or model is fetched.
    counts = scope.aggregate(**{s: Count("pk", filter=Q(state=s)) for s in STATES})
    unfinished = scope.filter(state__in=["queued", *service.ACTIVE])
    signals = unfinished.aggregate(
        queued_due=Count("pk", filter=Q(state="queued", next_dispatch__lte=observed, expires_at__gt=observed)),
        expired_requests=Count("pk", filter=Q(expires_at__lte=observed)),
        overdue_leases=Count("pk", filter=Q(state__in=service.ACTIVE, lease_until__lte=observed)),
        missing_active_leases=Count("pk", filter=Q(state__in=service.ACTIVE, lease_until__isnull=True)),
        attempts_at_limit=Count("pk", filter=Q(attempts__gte=service.LIMITS["attempts"])),
        oldest_queued=Min("created_at", filter=Q(state="queued")),
    )
    oldest = signals.pop("oldest_queued")
    signals["oldest_queued_seconds"] = max(0, int((observed - oldest).total_seconds())) if oldest else None
    rows = scope.filter(created_at__lte=cutoff)
    if state:
        rows = rows.filter(state=state)
    if kind:
        rows = rows.filter(specification__kind=kind)
    page = rows.filter(key_filter(anchor, newer)) if anchor else rows
    order = ("created_at", "pk") if newer else ("-created_at", "-pk")
    values = list(page.order_by(*order).values("id", "created_at", "state", "specification__kind", "attempts", "reason_code")[:PAGE_SIZE])
    if newer:
        values.reverse()

    def cursor(row, direction):
        key = (row["created_at"], row["id"])
        if not rows.filter(key_filter(key, direction)).exists():
            return None
        return signing.dumps(dict(binding=binding, cutoff=cutoff.isoformat(),
                                  anchor=[key[0].isoformat(), str(key[1])], newer=direction), salt=SALT)

    previous = cursor(values[0], True) if values else None
    following = cursor(values[-1], False) if values else None
    projects.recheck(current)
    return {
        "schema": "native_job_history_v1", "read_only": True,
        "observed_at": observed.isoformat(), "history_cutoff": cutoff.isoformat(),
        "jobs_enabled": settings.DECLARAI_JOBS_ENABLED, "page_size": PAGE_SIZE,
        "cursor_seconds": CURSOR_SECONDS, "filters": {"state": state, "kind": kind},
        "jobs": [{"id": str(j["id"]), "created_at": j["created_at"].isoformat(), "state": j["state"],
                  "kind": j["specification__kind"], "attempts": j["attempts"], "reason_code": j["reason_code"]} for j in values],
        "previous_cursor": previous, "next_cursor": following,
        "restart_required": bool(token and not values),
        "queue": {"scope": "current_dataset", "states": counts, "signals": signals,
                  "installation_limits": {k: service.LIMITS[k] for k in ["max_active", "max_pending", "attempts", "lease_seconds"]},
                  "live_service_health": "not_observed", "recovery_authorized": False},
        "limitation": "Stored metadata only; counts cover this dataset, not installation capacity use or queue position. "
                      "Worker/broker health is not tested. Due dispatch and overdue leases are signals, not confirmed failures. "
                      "History excludes newer submissions after its cutoff; states remain live and filtered rows may move. "
                      "Refresh restarts navigation. Observation never dispatches, reconciles, retries or approves a job.",
    }
