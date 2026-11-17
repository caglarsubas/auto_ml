"""Authenticated, project-scoped review discussion endpoints."""
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, transaction
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from access_control import projects
from deployment import reviews
from deployment.models import PackageReview, PackageReviewEvent
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


class ReviewView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response


class PackageReviewListView(ReviewView):
    def get(self, request, file_id):
        try:
            scope = reviews.actor_scope(request.user, file_id)
            offset = int(request.query_params.get('offset', '0'))
            if offset < 0:
                raise ValueError('Offset must be nonnegative.')
            cases = PackageReview.objects.filter(dataset_id=file_id, project_id=scope['project_id']).order_by('-created_at', '-pk')
            total = cases.count()
            selected = list(cases[offset:offset + 50])
            rows = []
            for case in selected:
                if case.native_assessment_id is not None:
                    with reviews.review_transaction(file_id, native=True):
                        freshness = reviews.freshness(case)
                else:
                    freshness = reviews.freshness(case)
                rows.append({'id': str(case.pk), **reviews.subject_identity(case), 'revision': case.revision,
                             'freshness': freshness, 'created_at': case.created_at.isoformat()})
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


class PackageReviewDetailView(ReviewView):
    def get(self, request, review_id):
        try:
            case = PackageReview.objects.get(pk=review_id)
            scope = reviews.actor_scope(request.user, case.dataset_id)
            if str(case.project_id) != scope['project_id']:
                raise projects.ProjectDenied('review_project_mismatch')
            with reviews.review_transaction(case.dataset_id, native=case.native_assessment_id is not None):
                case = PackageReview.objects.select_for_update().get(pk=review_id)
                result = reviews.serialize(case, request.user)
                projects.recheck(scope)
                return Response(result)
        except ERRORS as exc:
            return failure(exc)

    def post(self, request, review_id):
        try:
            return Response(reviews.append(request.user, review_id, request.data))
        except ERRORS as exc:
            return failure(exc)


class PackageReviewReceiptView(ReviewView):
    def get(self, request, review_id, event_id):
        from deployment.review_evidence import receipt
        from execution_jobs.csv_scoring import canonical_bytes
        try:
            case = PackageReview.objects.get(pk=review_id)
            scope = reviews.actor_scope(request.user, case.dataset_id)
            if str(case.project_id) != scope['project_id']:
                raise projects.ProjectDenied('review_project_mismatch')
            with projection_lock(case.dataset_id), transaction.atomic():
                event = PackageReviewEvent.objects.get(pk=event_id, review=case)
                raw = canonical_bytes(receipt(request.user, case, event))
                projects.recheck(scope)
                response = HttpResponse(raw, content_type='application/json')
                response['Content-Disposition'] = f'attachment; filename="review-{review_id}-event-{event_id}.json"'
                return response
        except ERRORS as exc:
            return failure(exc)
