"""Authenticated, project-scoped review discussion endpoints."""
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from access_control import projects
from deployment import reviews
from deployment.models import PackageReview
from modeling.execution_artifacts import projection_lock


def failure(exc):
    if isinstance(exc, projects.ProjectDenied):
        return Response({'error_code': exc.code, 'error': str(exc)}, status=403)
    if isinstance(exc, DatabaseError):
        return Response({'error_code': 'review_storage_unavailable'}, status=503)
    if isinstance(exc, reviews.ReviewConflict):
        return Response({'error_code': exc.code, 'error': 'The package or discussion changed. Refresh before retrying.'}, status=409)
    if isinstance(exc, (ObjectDoesNotExist, FileNotFoundError)):
        return Response({'error_code': 'review_evidence_unavailable'}, status=404)
    return Response({'error': str(exc)}, status=400)


ERRORS = (ValueError, TypeError, ObjectDoesNotExist, OSError, DatabaseError, projects.ProjectDenied)


class PackageReviewListView(APIView):
    def get(self, request, file_id):
        try:
            scope = reviews.actor_scope(request.user, file_id)
            offset = int(request.query_params.get('offset', '0'))
            if offset < 0:
                raise ValueError('Offset must be nonnegative.')
            cases = PackageReview.objects.filter(dataset_id=file_id, project_id=scope['project_id']).order_by('-created_at', '-pk')
            total = cases.count()
            selected = list(cases[offset:offset + 50])
            rows = [{'id': str(c.pk), 'bundle_id': str(c.bundle_id), 'revision': c.revision,
                     'freshness': reviews.freshness(c), 'created_at': c.created_at.isoformat()} for c in selected]
            projects.recheck(scope)
            return Response({'file_id': file_id, 'current_package': reviews.current_identity(file_id),
                             'reviews': rows, 'total': total, 'next_offset': offset + 50 if offset + 50 < total else None})
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, file_id):
        try:
            return Response(reviews.start(request.user, file_id, request.data))
        except ERRORS as exc:
            return failure(exc)


class PackageReviewDetailView(APIView):
    def get(self, request, review_id):
        try:
            case = PackageReview.objects.get(pk=review_id)
            scope = reviews.actor_scope(request.user, case.dataset_id)
            if str(case.project_id) != scope['project_id']:
                raise projects.ProjectDenied('review_project_mismatch')
            with projection_lock(case.dataset_id), transaction.atomic():
                case = PackageReview.objects.select_for_update().get(pk=review_id)
                result = reviews.serialize(case)
                projects.recheck(scope)
                return Response(result)
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, review_id):
        try:
            return Response(reviews.append(request.user, review_id, request.data))
        except ERRORS as exc:
            return failure(exc)
