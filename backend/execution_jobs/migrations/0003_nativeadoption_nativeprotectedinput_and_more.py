import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('execution_jobs', '0002_nativejob_source_dataset'),
    ]

    operations = [
        migrations.CreateModel(
            name='NativeAdoption',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('proposal', models.JSONField()),
                ('proposal_sha256', models.CharField(max_length=64)),
                ('request_sha256', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('training_job', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='adoptions', to='execution_jobs.nativejob')),
            ],
        ),
        migrations.CreateModel(
            name='NativeProtectedInput',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('specification', models.JSONField()),
                ('specification_sha256', models.CharField(max_length=64)),
                ('request_sha256', models.CharField(max_length=64)),
                ('payload', models.BinaryField()),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('adoption', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='protected_inputs', to='execution_jobs.nativeadoption')),
            ],
        ),
        migrations.CreateModel(
            name='NativeAdoptionEvent',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('revision', models.PositiveIntegerField()),
                ('kind', models.CharField(max_length=16)),
                ('payload', models.JSONField()),
                ('payload_sha256', models.CharField(max_length=64)),
                ('request_sha256', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('adoption', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='execution_jobs.nativeadoption')),
            ],
            options={
                'ordering': ['revision'],
                'constraints': [models.UniqueConstraint(fields=('adoption', 'revision'), name='native_adoption_event_revision')],
            },
        ),
    ]
