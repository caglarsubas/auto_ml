from django.db import migrations, models

def remove_duplicates(apps, schema_editor):
    DataFile = apps.get_model('data_collection', 'DataFile')
    seen = set()
    for datafile in DataFile.objects.all():
        if datafile.original_name in seen:
            datafile.delete()
        else:
            seen.add(datafile.original_name)

class Migration(migrations.Migration):

    dependencies = [
        ('data_collection', '0003_alter_datafile_original_name'),
        ('data_collection', '0004_handle_duplicate_original_names'),
    ]

    operations = [
        migrations.RunPython(remove_duplicates),
        migrations.AlterField(
            model_name='datafile',
            name='original_name',
            field=models.CharField(max_length=255, unique=True),
        ),
    ]