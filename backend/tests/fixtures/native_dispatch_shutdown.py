"""Owned Linux signal proof; publication/storage are synthetic seams only."""
import contextlib
import io
import json
import os
import signal
import sys
import uuid
from unittest.mock import patch

import django
django.setup()
from django.conf import settings
settings.DECLARAI_JOBS_ENABLED = True
settings.CELERY_BROKER_URL = 'redis://127.0.0.1:9/15'
from execution_jobs import service
from execution_jobs.management.commands.dispatch_jobs import Command
from execution_jobs.tasks import run_native_job

original = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
selected = getattr(signal, sys.argv[1] if len(sys.argv) > 1 else 'SIGTERM')
identifiers = [uuid.UUID(int=i) for i in range(1,4)]
sent, scheduled = [], []

def publish(*, args, retry):
    assert retry is False
    sent.extend(args)
    if len(sent) == 1:
        os.kill(os.getpid(), selected)

def schedule(**kwargs):
    scheduled.append(kwargs)

with (patch.object(service, 'reconcile', return_value=identifiers),
      patch.object(service, 'locked', side_effect=contextlib.nullcontext),
      patch.object(service.NativeJob.objects, 'filter') as manager,
      patch.object(run_native_job, 'apply_async', side_effect=publish),
      patch('execution_jobs.management.commands.dispatch_jobs.close_old_connections')):
    manager.return_value.update.side_effect = schedule
    out = io.StringIO()
    Command(stdout=out).handle(once=False)
assert all(item == {'next_dispatch'} for item in (set(row) for row in scheduled))
print(json.dumps({'pid':os.getpid(),'signal':selected.name,'published':len(sent),
                  'finalized':len(scheduled),'ids':sent,'handlers_restored':all(signal.getsignal(s) is h for s,h in original.items()),'actual_broker_or_database_used':False}))
