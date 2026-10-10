"""Durable outbox pump/reconciliation; run separately from HTTP and workers."""

import time
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from execution_jobs.service import dispatch_once, JobConflict


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            try:
                result = dispatch_once()
                self.stdout.write(str(result))
            except JobConflict as exc:
                raise CommandError(exc.code) from None
            except DatabaseError:
                if options["once"]:
                    raise CommandError("job_storage_unavailable") from None
                self.stderr.write("job_storage_unavailable; retrying")
            if options["once"]:
                return
            time.sleep(5)
