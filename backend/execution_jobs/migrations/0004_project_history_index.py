"""Reversible physical index for scoped, bounded native job history.

Keep the Python model/execution fingerprint stable: adding this operational
index neither changes row layout nor invalidates existing model evidence/jobs.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("execution_jobs", "0003_nativeadoption_nativeprotectedinput_and_more")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.AddIndex(
                model_name="nativejob",
                index=models.Index(fields=["project", "-created_at", "-id"], name="native_job_project_history_idx"),
            )],
            state_operations=[],
        ),
    ]
