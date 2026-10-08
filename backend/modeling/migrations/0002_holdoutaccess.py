import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('modeling', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='HoldoutAccess',
        fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('execution_id', models.UUIDField(null=True)),
            ('file_id', models.IntegerField()),
            ('dataset_sha256', models.CharField(blank=True, max_length=64)),
            ('parameters', models.JSONField(default=dict)),
            ('accessed_at', models.DateTimeField(default=django.utils.timezone.now)),
            ('evidence_status', models.CharField(default='exploratory', max_length=24)),
            ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ],
        options={'ordering': ['accessed_at'], 'indexes': [models.Index(fields=['file_id', 'dataset_sha256'], name='holdout_dataset_idx')]},
    )]
