import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("execution_jobs", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="nativejob",
            name="source_dataset",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="scoring_jobs",
                to="declaration.declaration",
            ),
        )
    ]
