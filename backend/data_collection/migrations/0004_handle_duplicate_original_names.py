from django.db import migrations

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
        ('data_collection', '0002_alter_datadictionary_data_file_and_more'),
    ]

    operations = [
        migrations.RunPython(remove_duplicates),
    ]