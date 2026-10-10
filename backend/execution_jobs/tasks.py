from backend.celery import app
from execution_jobs.service import execute


@app.task(
    name="declarai.package_integrity",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
    soft_time_limit=130,
    time_limit=150,
)
def run_native_job(identifier):
    import uuid
    from execution_jobs.models import NativeJob

    try:
        execute(uuid.UUID(str(identifier)))
    except (ValueError, NativeJob.DoesNotExist):
        return
