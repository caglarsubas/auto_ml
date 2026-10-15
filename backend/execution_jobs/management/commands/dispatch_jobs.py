"""Durable outbox pump/reconciliation; run separately from HTTP and workers."""

import signal
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, InterfaceError, close_old_connections
from execution_jobs.service import dispatch_once, JobConflict


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        stop_requested = False
        previous = {}

        def stop(signum, frame):
            # Finish the current bounded outbox transaction, then return cleanly.
            # Explicit handling is required when this process is container PID 1.
            nonlocal stop_requested
            stop_requested = True

        if not options["once"]:
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, stop)
        try:
            while not stop_requested:
                # Management commands do not receive Django's request lifecycle
                # hooks. Retire broken/obsolete connections between cycles so
                # the next durable outbox read can reconnect after a DB outage.
                close_old_connections()
                try:
                    result = dispatch_once()
                    self.stdout.write(str(result))
                except JobConflict as exc:
                    raise CommandError(exc.code) from None
                except (DatabaseError, InterfaceError):
                    if options["once"]:
                        raise CommandError("job_storage_unavailable") from None
                    self.stderr.write("job_storage_unavailable; retrying")
                finally:
                    close_old_connections()
                if options["once"]:
                    return
                # The signal handler only assigns a flag: acquiring an Event's
                # lock in a reentrant Python signal handler can deadlock.
                until = time.monotonic() + 5
                while not stop_requested:
                    remaining = until - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.1, remaining))
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
