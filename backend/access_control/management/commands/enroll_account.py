"""Enroll an ordinary private account with an exact project scope and audit UUID."""

import json
import os
import stat

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from access_control.enrollment import EnrollmentDenied, enroll, specification
from execution_jobs.preflight import RuntimeUnavailable, check_application_role, check_runtime


def credential(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) not in {0o400, 0o600}
                or not 0 < before.st_size <= 4096
            ):
                raise ValueError
            raw = stream.read(4097)
            after = os.fstat(stream.fileno())
            if len(raw) != before.st_size or (before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise ValueError
            return raw.decode("utf-8").rstrip("\r\n")
    except (OSError, ValueError, UnicodeError):
        raise EnrollmentDenied("enrollment_private_credential_file_required") from None


class Command(BaseCommand):
    help = "Enroll an ordinary private account and exact project role; does not reset credentials or grant model-use approval."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument("--request-id", required=True)
        parser.add_argument(
            "--operator-label",
            required=True,
            help="Asserted installation operator/ticket label; not authenticated human identity",
        )
        parser.add_argument(
            "--password-file",
            required=True,
            help="Private regular file owned by the calling runtime identity; no password argument",
        )
        parser.add_argument("--role", required=True, choices=["developer", "reviewer", "admin"])
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--project-id")
        scope.add_argument(
            "--new-project", help="Create a new project; requires admin role and activates durable project isolation"
        )

    def handle(self, *args, **options):
        try:
            if settings.DECLARAI_RUNTIME_PROFILE != "private":
                raise EnrollmentDenied("enrollment_private_profile_required")
            check_application_role()
            check_runtime()
            spec = specification(
                options["user"],
                options["operator_label"],
                options["role"],
                options.get("project_id"),
                options.get("new_project"),
            )
            password = credential(options["password_file"])
            event, replayed = enroll(spec, options["request_id"], password)
        except (EnrollmentDenied, RuntimeUnavailable) as error:
            raise CommandError(str(error)) from None
        except (DatabaseError, ValueError, KeyError, TypeError):
            raise CommandError("enrollment_transaction_unavailable") from None
        self.stdout.write(
            json.dumps(
                {
                    "event_id": str(event.pk),
                    "subject_user_id": event.subject_snapshot["id"],
                    "project_id": event.details["project_id"],
                    "role": event.details["scope"]["role"],
                    "authority_source": event.authority_source,
                    "replayed_receipt": replayed,
                    "global_privileges_granted": False,
                    "model_use_approved": False,
                }
            )
        )
