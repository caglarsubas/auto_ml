"""Scoped membership administration; bootstrap/adoption remain operator actions."""

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from rest_framework.response import Response
from rest_framework.views import APIView

from access_control import projects
from access_control.models import Project, ProjectMembership


class ProjectListView(APIView):
    def get(self, request):
        members = (
            ProjectMembership.objects.filter(
                actor=request.user, active=True, role__in=["developer", "reviewer", "admin"]
            )
            .select_related("project")
            .order_by("project_id")
        )
        return Response(
            {
                "governed": projects.governed(),
                "projects": [
                    {
                        "id": str(m.project_id),
                        "name": m.project.name,
                        "role": m.role,
                        "membership_revision": str(m.revision),
                    }
                    for m in members
                ],
            }
        )


class ProjectMemberView(APIView):
    def post(self, request, project_id):
        data = request.data
        try:
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("username"), str)
                or not 0 < len(data["username"]) <= 150
            ):
                raise ValueError("Supply an existing username, role and request UUID.")
            event, replayed = projects.admin_change(
                request.user, project_id, data["username"], data.get("role"), uuid.UUID(str(data.get("request_id")))
            )
            return Response(
                {
                    "event_id": str(event.pk),
                    "project_id": str(event.project_id),
                    "resource": event.resource,
                    "replayed": replayed,
                }
            )
        except (ValueError, ObjectDoesNotExist):
            return Response(
                {
                    "error": "Supply an existing username, valid role and unused request UUID. Self-administration requires the operator command."
                },
                status=400,
            )
        except projects.ProjectDenied as exc:
            return Response({"error": str(exc), "error_code": exc.code}, status=403)
        except DatabaseError:
            return Response({"error_code": "project_authority_unavailable"}, status=503)
