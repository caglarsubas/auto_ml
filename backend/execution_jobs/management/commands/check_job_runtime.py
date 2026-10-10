"""Operator preflight for the private worker/dispatcher, not a release gate."""

import json
from django.core.management.base import BaseCommand, CommandError
from execution_jobs.preflight import check_runtime, RuntimeUnavailable


class Command(BaseCommand):
    def handle(self, *args, **options):
        try:
            self.stdout.write(json.dumps(check_runtime(), sort_keys=True))
        except RuntimeUnavailable as exc:
            raise CommandError(str(exc)) from None
