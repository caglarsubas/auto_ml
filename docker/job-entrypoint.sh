#!/bin/sh
set -eu
# Development composition must never silently downgrade a private deployment.
if [ "${DECLARAI_RUNTIME_PROFILE:-development}" != development ]; then
  echo 'Use a qualified private job deployment; live-reload jobs refuse private mode.' >&2
  exit 1
fi
python manage.py migrate --check
exec "$@"
