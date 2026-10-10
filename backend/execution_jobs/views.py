"""Real session/CSRF/project authority; no generic expert/task dispatch."""

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from rest_framework.response import Response
from rest_framework.views import APIView
from access_control import projects
from execution_jobs import service
from execution_jobs.models import NativeJob


def failure(exc):
    if isinstance(exc, projects.ProjectDenied):
        return Response({"error_code": exc.code}, status=403)
    if isinstance(exc, DatabaseError):
        return Response({"error_code": "job_storage_unavailable"}, status=503)
    if isinstance(exc, ObjectDoesNotExist):
        return Response({"error_code": "job_unavailable"}, status=404)
    if isinstance(exc, service.JobConflict):
        return Response({"error_code": exc.code}, status=503 if exc.code == "job_service_disabled" else 409)
    return Response({"error_code": "job_request_invalid"}, status=400)


ERRORS = (ObjectDoesNotExist, DatabaseError, ValueError, TypeError, OSError, projects.ProjectDenied)


class DatasetJobsView(APIView):
    def get(self, request, file_id):
        try:
            current = service.scope(request.user, file_id)
            offset = int(request.query_params.get("offset", "0"))
            if offset < 0:
                raise ValueError
            rows = NativeJob.objects.filter(dataset_id=file_id, project_id=current["project_id"]).order_by(
                "-created_at", "-pk"
            )
            total = rows.count()
            values = [
                {
                    "id": str(j.pk),
                    "state": j.state,
                    "bundle_id": j.specification["bundle_id"],
                    "created_at": j.created_at.isoformat(),
                }
                for j in rows[offset : offset + 50]
            ]
            projects.recheck(current)
            return Response(
                {
                    "jobs_enabled": settings_enabled(),
                    "jobs": values,
                    "total": total,
                    "next_offset": offset + 50 if offset + 50 < total else None,
                }
            )
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, file_id):
        try:
            result = service.submit(request.user, file_id, request.data)
            return Response(result, status=200 if result["replayed"] else 202)
        except ERRORS as exc:
            return failure(exc)


def settings_enabled():
    from django.conf import settings

    return settings.DECLARAI_JOBS_ENABLED


class JobDetailView(APIView):
    def get(self, request, job_id):
        try:
            return Response(service.read(request.user, job_id))
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, job_id):
        try:
            return Response(service.cancel(request.user, job_id, request.data))
        except ERRORS as exc:
            return failure(exc)
