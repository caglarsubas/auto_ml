#!/bin/sh
set -eu
# Invoke in /app/backend in an installed, fixed native runtime image.
# Never migrate automatically or downgrade to the development profile.
if [ "${DECLARAI_RUNTIME_PROFILE:-}" != private ] || [ "$#" != 1 ]; then
  echo 'Private job launch requires private configuration and one role.' >&2
  exit 1
fi
case "$1" in
  worker|dispatcher) ;;
  *) echo 'Select worker or dispatcher.' >&2; exit 1 ;;
esac
python manage.py check_job_runtime
if [ "$1" = worker ]; then
  exec python -m celery -A backend.celery:app worker --pool=prefork --concurrency=2 --without-gossip --without-mingle --without-heartbeat --loglevel=WARNING
fi
exec python manage.py dispatch_jobs
