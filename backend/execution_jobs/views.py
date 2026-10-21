"""Real session/CSRF/project authority; no generic expert/task dispatch."""

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from access_control import projects
from execution_jobs import service
from execution_jobs import csv_scoring, training_search, training_scoring, native_assessment
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


ERRORS = (ObjectDoesNotExist, DatabaseError, ValueError, TypeError, OSError, projects.ProjectDenied, ValidationError)


class DatasetJobsView(APIView):
    def get(self, request, file_id):
        try:
            current = service.scope(request.user, file_id)
            offset = int(request.query_params.get("offset", "0"))
            if not 0 <= offset <= 2**63 - 1:
                raise ValueError
            rows = NativeJob.objects.filter(dataset_id=file_id, project_id=current["project_id"]).order_by(
                "-created_at", "-pk"
            )
            total = rows.count()
            values = [
                {
                    "id": str(j.pk),
                    "state": j.state,
                    "kind": j.specification["kind"],
                    "bundle_id": j.specification.get("bundle_id"),
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


class JobInputView(APIView):
    def get(self, request, file_id):
        try:
            return Response(csv_scoring.prepare(request.user, file_id))
        except ERRORS as exc:
            return failure(exc)


class JobTrainingInputView(APIView):
    def post(self, request, file_id):
        try:
            return Response(training_search.preview(request.user, file_id, request.data))
        except ERRORS as exc:
            return failure(exc)


class JobScoresView(APIView):
    def get(self, request, job_id):
        try:
            sha = request.query_params.get("sha256")
            raw = service.scoring_receipt(request.user, job_id, sha)
            response = HttpResponse(raw, content_type="application/json")
            response["Content-Disposition"] = f'attachment; filename="scoring-{job_id}.json"'
            response["X-DeclarAI-Receipt-SHA256"] = sha
            response["Cache-Control"] = "no-store"
            return response
        except ERRORS as exc:
            return failure(exc)


class JobCandidateExportView(APIView):
    def get(self, request, job_id):
        try:
            raw = training_scoring.export(request.user, job_id, request.query_params.get("sha256"))
            response = HttpResponse(raw, content_type="application/json")
            response["Content-Disposition"] = f'attachment; filename="candidate-{job_id}.json"'
            response["X-DeclarAI-Export-SHA256"] = training_scoring.native_candidate.sha(raw)
            response["Access-Control-Expose-Headers"] = "X-DeclarAI-Export-SHA256"
            response["Cache-Control"] = "no-store"
            return response
        except ERRORS as exc:
            return failure(exc)


class JobCandidateInputView(APIView):
    def post(self, request, job_id):
        try:
            return Response(training_scoring.preview(request.user, job_id, request.data))
        except ERRORS as exc:
            return failure(exc)


class NativeAdoptionListView(APIView):
    def get(self, request, job_id):
        try:
            job = NativeJob.objects.get(pk=job_id)
            for scope in service.read_authority(request.user, job):
                projects.recheck(scope)
            rows = native_assessment.NativeAdoption.objects.filter(training_job=job).order_by('-created_at')
            return Response({'adoptions': [native_assessment.serialize(request.user, a) for a in rows[:50]]})
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, job_id):
        try:
            result = native_assessment.propose(request.user, job_id, request.data)
            return Response(result, status=200 if result['replayed'] else 201)
        except ERRORS as exc:
            return failure(exc)


class NativeAdoptionView(APIView):
    def get(self, request, adoption_id):
        try:
            return Response(native_assessment.serialize(request.user, native_assessment.NativeAdoption.objects.select_related('training_job').get(pk=adoption_id)))
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, adoption_id):
        try:
            return Response(native_assessment.decide(request.user, adoption_id, request.data))
        except ERRORS as exc:
            return failure(exc)


class NativeProtectedInputView(APIView):
    def post(self, request, adoption_id):
        try:
            if set(request.FILES) != {'file'}:
                raise ValueError('Supply one protected CSV.')
            data = {k: request.data[k] for k in request.data if k != 'file'}
            return Response(native_assessment.seal(request.user, adoption_id, data, request.FILES['file']))
        except ERRORS as exc:
            return failure(exc)


class NativeAssessmentInputView(APIView):
    def post(self, request, protected_id):
        try:
            if request.data:
                raise ValueError('The sealed input determines the complete assessment plan.')
            return Response(native_assessment.preview(request.user, protected_id))
        except ERRORS as exc:
            return failure(exc)


class JobOperationalHandoffView(APIView):
    def get(self, request, job_id):
        try:
            from execution_jobs import operational_handoff

            value = operational_handoff.read(request.user, job_id, request.query_params.get("revision"), request.query_params.get("sha256"))
            response = Response(value)
            response["Cache-Control"] = "no-store"
            return response
        except ERRORS as exc:
            return failure(exc)


class DatasetJobHistoryView(APIView):
    def get(self, request, file_id):
        try:
            from execution_jobs import history

            response = Response(history.read(request.user, file_id, request.query_params))
        except ERRORS as exc:
            response = failure(exc)
        response["Cache-Control"] = "no-store"
        return response
