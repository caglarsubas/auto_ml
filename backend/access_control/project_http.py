"""Explicit native endpoint registry; absent policies fail closed in governed mode."""

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError as InvalidRequest
from rest_framework.permissions import BasePermission

from access_control import projects
from access_control.models import AssistantActionApproval, ProjectMembership, ProjectAuthorityEvent
from access_control.storage import positive_file_id

GLOBAL = {"api-root", "ai-assistant-models", "ai-assistant-feedback", "project-list", "preprocessing-options"}
DATASET = {
    "declaration-detail",
    "declaration-data-dictionary",
    "declaration-engineer-features",
    "declaration-preview",
    "feature-card-get-feature-info",
    "feature-card-get-stacked-feature-data",
    "get-stacked-feature-data",
    "preprocessing-apply",
    "preprocessing-run",
    "preprocessing-datq-detail",
    "preprocessing-datq-timeseries",
    "preprocessing-datq-summary-row",
    "preprocessing-status",
    "modeling-start",
    "modeling-status",
    "feature-explainability",
    "sfs-start",
    "sfs-status",
    "sfs-stop",
    "sfs-results",
    "hyperparam-start",
    "hyperparam-status",
    "hyperparam-stop",
    "hyperparam-results",
    "encoding-analyze",
    "encoding-apply",
    "vif-detail",
    "evaluation-run",
    "evaluation-status",
    "holdout-history",
    "evaluation-pack",
    "evaluation-governance",
    "deployment-bundle",
    "deployment-score",
    "deployment-receipt",
    "deployment-status",
    "deployment-pack",
    "package-review-list",
    "dataset-jobs",
    "job-input",
    "crisp-export",
    "crisp-monitoring",
    "crisp-sequential",
    "crisp-datq",
    "sfs-history",
    "champion-promote",
    "booster-compare",
    "ai-assistant-chat",
    "ai-assistant-execute-action",
    "assistant-prepare-action",
    "ai-assistant-cache",
}
SPECIAL = {
    "declaration-list",
    "declaration-get-by-name",
    "pipeline-list",
    "pipeline-create",
    "pipeline-detail",
    "pipeline-report",
    "crisp-iteration-clone",
    "assistant-approve-action",
    "assistant-cancel-action",
    "assistant-action-receipt",
    "project-member",
    "package-review-detail",
    "job-detail",
    "job-scores",
}
READ_POST = {"evaluation-pack", "deployment-pack", "crisp-export", "package-review-list", "package-review-detail", "dataset-jobs", "job-detail"}


class AuthorityUnavailable(APIException):
    status_code = 503
    default_detail = {
        "error": "Project authority cannot be verified. Retry after recovery.",
        "error_code": "project_authority_unavailable",
    }


def directory_snapshot(actor_id):
    return list(
        ProjectMembership.objects.filter(
            actor_id=actor_id, actor__is_active=True, active=True, role__in=["developer", "reviewer", "admin"]
        )
        .order_by("project_id")
        .values("project_id", "revision", "role")
    )


def authorize(request, view):
    from declaration.models import Declaration

    name = request.resolver_match.url_name if getattr(request, "resolver_match", None) else None
    # RequestFactory does not resolve URLs. Use its concrete route to apply the same registry.
    if name is None:
        from django.urls import resolve

        name = resolve(request.path).url_name
    if name not in GLOBAL | DATASET | SPECIAL:
        raise projects.ProjectDenied("endpoint_project_policy_unavailable")
    body = request.data if request.method not in {"GET", "HEAD", "OPTIONS"} else {}
    if not hasattr(body, "get"):
        raise projects.ProjectDenied("project_request_object_required")
    operation = "read" if request.method in {"GET", "HEAD", "OPTIONS"} or name in READ_POST else "write"
    scopes, file_id = [], None
    supplied = [
        v
        for v in [view.kwargs.get("file_id"), request.query_params.get("file_id"), body.get("file_id")]
        if v is not None
    ]
    if name in GLOBAL:
        if name == "project-list":
            request._request._project_directory = directory_snapshot(request.user.pk)
        if supplied:
            scopes.append(projects.dataset_authority(request.user.pk, supplied[0], operation))
    elif name in {"declaration-list", "pipeline-list"} and request.method in {"GET", "HEAD", "OPTIONS"}:
        request._request._project_directory = directory_snapshot(request.user.pk)
    elif name in {"declaration-list", "pipeline-create"}:
        scopes.append(projects.choose_project(request.user.pk, body.get("project_id")))
    elif name == "declaration-get-by-name":
        matches = list(
            Declaration.objects.filter(file__endswith=view.kwargs["file_name"]).values_list("pk", flat=True)[:2]
        )
        if len(matches) != 1:
            raise projects.ProjectDenied("dataset_name_resolution_unavailable")
        supplied.append(matches[0])
    elif name in {"pipeline-detail", "pipeline-report", "crisp-iteration-clone"}:
        identifier = view.kwargs.get("pk") if name != "crisp-iteration-clone" else body.get("pipeline_run_id")
        scopes.append(projects.pipeline_authority(request.user.pk, identifier, operation))
    elif name in {"assistant-approve-action", "assistant-cancel-action", "assistant-action-receipt"}:
        identifier = view.kwargs.get("approval_id") or body.get("approval_id")
        try:
            record = AssistantActionApproval.objects.get(pk=identifier, actor_id=request.user.pk)
        except (AssistantActionApproval.DoesNotExist, ValueError, TypeError, ValidationError):
            raise projects.ProjectDenied("action_approval_unavailable") from None
        supplied.append(record.file_id)
    elif name == "project-member":
        scopes.append(projects.membership(request.user.pk, view.kwargs["project_id"], "admin"))
    elif name == "package-review-detail":
        from deployment.models import PackageReview
        try:
            record = PackageReview.objects.get(pk=view.kwargs['review_id'])
        except PackageReview.DoesNotExist:
            raise projects.ProjectDenied('package_review_unavailable') from None
        supplied.append(record.dataset_id)
    elif name in {'job-detail', 'job-scores'}:
        from execution_jobs.models import NativeJob
        try:
            record = NativeJob.objects.get(pk=view.kwargs['job_id'])
        except NativeJob.DoesNotExist:
            raise projects.ProjectDenied('job_unavailable') from None
        supplied.append(record.dataset_id)
    # A browser workspace may narrow reads/writes to one already-authorized project.
    # Never use this selector as a resource assignment or substitute for its binding.
    if request.query_params.get("project_id") is not None:
        if len(request.query_params.getlist("project_id")) != 1:
            raise projects.ProjectDenied("project_reference_invalid")
        scopes.append(projects.membership(request.user.pk, request.query_params["project_id"], operation))
    for values in [request.query_params, body]:
        if values.get("pipeline_run_id") is not None and name != "crisp-iteration-clone":
            scopes.append(projects.pipeline_authority(request.user.pk, values["pipeline_run_id"], operation))
    if name in DATASET and view.kwargs.get("pk") is not None:
        supplied.append(view.kwargs["pk"])
    state = body.get("state")
    if isinstance(state, dict):
        supplied.extend(v for v in [state.get("file_id"), state.get("fileId")] if v is not None)
    normalized = list({positive_file_id(v) for v in supplied})
    if len(normalized) > 1:
        raise projects.ProjectDenied("dataset_identifiers_must_agree")
    if normalized:
        file_id = normalized[0]
        related = projects.dataset_authority(request.user.pk, file_id, operation)
        if scopes and any(s["project_id"] != related["project_id"] for s in scopes):
            raise projects.ProjectDenied("pipeline_dataset_project_mismatch")
        scopes.append(related)
    elif name in DATASET or name == "declaration-get-by-name":
        raise projects.ProjectDenied("dataset_identifier_required")
    for values in [request.query_params, body]:
        projects.validate_paths(request.user.pk, file_id, values, operation)
    if len({scope["project_id"] for scope in scopes}) > 1:
        raise projects.ProjectDenied("pipeline_dataset_project_mismatch")
    return name, scopes


class ProjectAccessPermission(BasePermission):
    def has_permission(self, request, view):
        try:
            if not projects.governed():
                return True
            try:
                name, scopes = authorize(request, view)
            except (ValueError, TypeError, ValidationError):
                raise projects.ProjectDenied("project_reference_invalid") from None
            event = projects.audit(
                request.user,
                "native_access",
                {"endpoint": name, "scopes": scopes},
                scopes[0]["project_id"] if scopes else None,
                outcome="started",
            )
        except projects.ProjectDenied as exc:
            try:
                projects.audit(request.user, "native_access", {}, outcome="denied", reason=exc.code)
            except DatabaseError:
                raise AuthorityUnavailable() from None
            if exc.code == "dataset_identifier_required":
                raise InvalidRequest(
                    {"error": "file_id is required for this operation.", "error_code": exc.code}
                ) from None
            raise PermissionDenied({"error": str(exc), "error_code": exc.code}) from None
        except DatabaseError:
            raise AuthorityUnavailable() from None
        raw = request._request
        raw._project_scopes, raw._project_event = scopes, event.pk
        if getattr(raw, "_project_context_managed", False):
            projects.current_actor.set(request.user.pk)
        request.user._declarai_project_scopes = scopes
        return True


class ProjectResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def checkpoint(request):
        for scope in getattr(request, "_project_scopes", []):
            projects.recheck(scope, allow_deleted=getattr(request, "_project_deleted", False))
        directory = getattr(request, "_project_directory", None)
        if directory is not None and directory != directory_snapshot(request.user.pk):
            raise projects.ProjectDenied("project_authority_changed")

    @staticmethod
    def finish(request, outcome, reason=""):
        if (
            ProjectAuthorityEvent.objects.filter(pk=request._project_event, outcome="started").update(
                outcome=outcome, reason_code=reason
            )
            != 1
        ):
            raise projects.ProjectDenied("project_access_audit_unavailable")

    @staticmethod
    def check_evidence(request, response):
        import io
        import json
        import zipfile

        files = {s["file_id"] for s in request._project_scopes if s.get("file_id")}
        if len(files) != 1 or response.streaming or response.status_code >= 400:
            return
        file_id = files.pop()
        content_type = response.get("Content-Type", "")
        if "application/json" in content_type:
            projects.assert_evidence_scope(json.loads(response.content), file_id)
        elif "application/zip" in content_type:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                for entry in archive.infolist():
                    if entry.filename.endswith(".json"):
                        projects.assert_evidence_scope(json.loads(archive.read(entry)), file_id)

    def process_view(self, request, view, args, kwargs):
        match = request.resolver_match
        if (
            match
            and match.namespace == "admin"
            and match.url_name not in {"login", "logout", "password_change", "password_change_done"}
        ):
            try:
                if projects.governed():
                    return JsonResponse(
                        {"error": "Use scoped project administration.", "error_code": "unscoped_admin_unavailable"},
                        status=403,
                    )
            except DatabaseError:
                return JsonResponse({"error_code": "project_authority_unavailable"}, status=503)
        return None

    def __call__(self, request):
        token = projects.current_actor.set(None)
        request._project_context_managed = True
        try:
            response = self.get_response(request)
            if not hasattr(request, "_project_event"):
                return response
            request._project_deleted = request.method == "DELETE" and 200 <= response.status_code < 300
            self.checkpoint(request)
            self.check_evidence(request, response)
            if response.status_code < 400 and response.get("X-Export-Path"):
                scope = next((s for s in request._project_scopes if s.get("file_id")), request._project_scopes[0])
                projects.register_artifact(
                    response["X-Export-Path"], file_id=scope.get("file_id"), project_id=scope["project_id"]
                )
            self.checkpoint(request)
            if response.streaming:
                source = response.streaming_content
                if response.is_async:
                    # Async native streams require a separately qualified lifecycle.
                    response.close()
                    raise projects.ProjectDenied("async_project_stream_unavailable")

                def stream():
                    stream_token = projects.current_actor.set(request.user.pk)
                    try:
                        iterator = iter(source)
                        while True:
                            self.checkpoint(request)
                            try:
                                chunk = next(iterator)
                            except StopIteration:
                                break
                            self.checkpoint(request)
                            yield chunk
                        self.finish(request, "completed" if response.status_code < 400 else "failed")
                    except (projects.ProjectDenied, DatabaseError):
                        try:
                            self.finish(request, "withheld", "project_authority_changed")
                        except (projects.ProjectDenied, DatabaseError):
                            pass
                    finally:
                        projects.current_actor.reset(stream_token)
                        close = getattr(source, "close", None)
                        if close:
                            close()

                response.streaming_content = stream()
            else:
                self.finish(request, "completed" if response.status_code < 400 else "failed")
            return response
        except (projects.ProjectDenied, DatabaseError) as exc:
            if "response" in locals():
                response.close()
            code = exc.code if isinstance(exc, projects.ProjectDenied) else "project_authority_unavailable"
            if hasattr(request, "_project_event"):
                try:
                    self.finish(request, "withheld", code)
                except (projects.ProjectDenied, DatabaseError):
                    pass
            result = JsonResponse(
                {
                    "error": "Project authority changed or cannot be verified. Review your access before retrying.",
                    "error_code": code,
                },
                status=403 if isinstance(exc, projects.ProjectDenied) else 503,
            )
            result["Cache-Control"] = "no-store"
            return result
        finally:
            projects.current_actor.reset(token)
