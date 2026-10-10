"""Only registered native tasks, JSON messages, durable state in Django."""

import os
from celery import Celery
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
if not settings.DECLARAI_JOBS_ENABLED:
    raise ImproperlyConfigured("Dedicated job broker is not configured; execution is blocked.")
app = Celery("declarai")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    result_backend=None,
    task_ignore_result=True,
    task_default_queue="declarai-native-v1",
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    worker_enable_remote_control=False,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={"socket_timeout": 3, "socket_connect_timeout": 3, "visibility_timeout": 300},
    task_publish_retry=False,
    imports=("execution_jobs.tasks",),
)
