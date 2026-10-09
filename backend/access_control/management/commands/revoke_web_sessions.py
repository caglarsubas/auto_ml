"""Explicit, retry-safe installation-operator browser-session revocation."""

import json
import re
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from access_control.session_authority import revoke_sessions


class Command(BaseCommand):
    help = "Revoke one account's browser sessions and unused typed approvals; optionally deactivate the account."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Exact existing username")
        parser.add_argument("--request-id", required=True, help="UUID reused for retries of the same operation")
        parser.add_argument(
            "--operator-label", required=True, help="Installation operator/ticket assertion, not authenticated identity"
        )
        parser.add_argument(
            "--deactivate", action="store_true", help="Also block future sign-in and the configured local MCP actor"
        )

    def handle(self, *args, **options):
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}", options["operator_label"]):
            raise CommandError("Use an operator label of 1–100 letters, digits, dots, underscores, @ or hyphens.")
        try:
            identifier = uuid.UUID(options["request_id"])
        except ValueError:
            raise CommandError("Use a valid request UUID.") from None
        try:
            user = get_user_model().objects.get(username=options["user"])
            event, replayed = revoke_sessions(
                user, request_id=identifier, operator_label=options["operator_label"], deactivate=options["deactivate"]
            )
        except get_user_model().DoesNotExist:
            raise CommandError("The account does not exist.") from None
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        except DatabaseError:
            raise CommandError(
                "Revocation authority could not be committed. Retry with the same request UUID."
            ) from None
        self.stdout.write(
            json.dumps(
                {
                    "event_id": str(event.pk),
                    "subject_user_id": event.subject_snapshot["id"],
                    **event.details,
                    "replayed_receipt": replayed,
                }
            )
        )
