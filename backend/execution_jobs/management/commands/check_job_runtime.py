"""Operator preflight for the private worker/dispatcher, not a release gate."""

import json
from django.core.management.base import BaseCommand, CommandError
from execution_jobs.preflight import check_application_role, check_runtime, RuntimeUnavailable


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--require-application-role", action="store_true")

    def handle(self, *args, **options):
        try:
            result = check_runtime()
            if options["require_application_role"]:
                check_application_role()
                result["application_role"] = "non_elevated"
            self.stdout.write(json.dumps(result, sort_keys=True))
        except RuntimeUnavailable as exc:
            raise CommandError(str(exc)) from None
