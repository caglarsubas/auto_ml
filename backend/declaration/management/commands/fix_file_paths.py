import os
from django.core.management.base import BaseCommand
from django.conf import settings
from declaration.models import Declaration  # Replace 'your_app_name' with your actual app name

class Command(BaseCommand):
    help = 'Fix file paths in the database'

    def handle(self, *args, **options):
        data_files_dir = os.path.join(settings.MEDIA_ROOT, 'data_files')
        for data_file in Declaration.objects.all():
            original_name = data_file.original_name
            for filename in os.listdir(data_files_dir):
                if filename.startswith('processed_') and filename.endswith(original_name):
                    data_file.file.name = os.path.join('data_files', filename)
                    data_file.save()
                    self.stdout.write(self.style.SUCCESS(f'Fixed file path for {original_name}'))
                    break
            else:
                self.stdout.write(self.style.WARNING(f'Could not find processed file for {original_name}'))