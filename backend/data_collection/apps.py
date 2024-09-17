from django.apps import AppConfig
import os
from django.conf import settings

class DataCollectionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'data_collection'

    def ready(self):
        data_files_dir = os.path.join(settings.MEDIA_ROOT, 'data_files')
        os.makedirs(data_files_dir, exist_ok=True)