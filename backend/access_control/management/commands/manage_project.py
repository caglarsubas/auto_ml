"""Record explicit installation-operator assertions without inventing human identity."""

import json
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from access_control.projects import operator_change, ProjectDenied
from access_control.storage import positive_file_id


class Command(BaseCommand):
    help = "Create projects, set roles, or explicitly adopt legacy datasets/pipelines. Activation is durable."

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=["create", "member", "dataset", "pipeline"])
        parser.add_argument("--request-id", required=True)
        parser.add_argument(
            "--operator-label", required=True, help="Asserted local operator label, not authenticated identity"
        )
        parser.add_argument("--project-id")
        parser.add_argument("--name")
        parser.add_argument("--user")
        parser.add_argument("--role", choices=["developer", "reviewer", "admin", "none"])
        parser.add_argument("--file-id")
        parser.add_argument("--pipeline-id")

    def handle(self, *args, **options):
        try:
            label = options["operator_label"].strip()
            if not label or len(label) > 100 or not label.isprintable():
                raise ValueError()
            identifier = uuid.UUID(options["request_id"])
            op = options["operation"]
            spec = {"operation": op}
            if op == "create":
                name, user = options["name"], options["user"]
                if not name or len(name.strip()) > 200 or not user or len(user) > 150:
                    raise ValueError()
                spec.update(name=name.strip(), user=user)
            else:
                spec["project_id"] = str(uuid.UUID(options["project_id"]))
                if op == "member":
                    if not options["user"] or len(options["user"]) > 150 or not options["role"]:
                        raise ValueError()
                    spec.update(user=options["user"], role=options["role"])
                elif op == "dataset":
                    spec["file_id"] = positive_file_id(options["file_id"])
                else:
                    spec["pipeline_id"] = positive_file_id(options["pipeline_id"])
            event, replayed = operator_change(spec, identifier, label)
        except (ValueError, TypeError, ObjectDoesNotExist, DatabaseError, ProjectDenied) as exc:
            raise CommandError(
                "Project change failed. Check identifiers, role, existing records and metadata service. No authority receipt was published."
            ) from exc
        self.stdout.write(
            json.dumps(
                {
                    "event_id": str(event.pk),
                    "project_id": str(event.project_id),
                    "resource": event.resource,
                    "authority_source": event.authority_source,
                    "replayed": replayed,
                }
            )
        )
