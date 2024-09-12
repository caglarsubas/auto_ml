from django.db import migrations, models

def set_original_name(apps, schema_editor):
    DataFile = apps.get_model('data_collection', 'DataFile')
    for data_file in DataFile.objects.all():
        data_file.original_name = data_file.name
        data_file.save()

class Migration(migrations.Migration):

    dependencies = [
        ('data_collection', '0001_initial'),  # Replace with the actual previous migration name
    ]

    operations = [
        migrations.AddField(
            model_name='datafile',
            name='original_name',
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.RunPython(set_original_name),
        migrations.AlterField(
            model_name='datafile',
            name='original_name',
            field=models.CharField(max_length=255),
        ),
    ]