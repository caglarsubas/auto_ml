from django.db import models
import os
from django.conf import settings
from access_control.storage import managed_path

class Declaration(models.Model):
    file = models.FileField(upload_to='data_files/')
    name = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)#, unique=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    has_header = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def get_file_path(self):
        file_path = managed_path(self.file.name, table=True)
        if os.path.isfile(file_path):
            return file_path
        # Legacy fallback must be unique; never choose another dataset arbitrarily.
        data_files_dir = os.path.join(settings.MEDIA_ROOT, 'data_files')
        if not os.path.isdir(data_files_dir):
            return None
        matches = [managed_path(os.path.join('data_files', name), table=True)
            for name in os.listdir(data_files_dir)
            if name.startswith('processed_') and name.endswith(self.original_name) and name.endswith('.csv')]
        return matches[0] if len(matches) == 1 and os.path.isfile(matches[0]) else None

class DataDictionary(models.Model):
    data_file = models.ForeignKey(Declaration, on_delete=models.CASCADE, related_name='data_dictionary')
    column_name = models.CharField(max_length=255)
    description = models.TextField()

    class Meta:
        unique_together = ('data_file', 'column_name')

    @classmethod
    def get_description(cls, file_id, column_name):
        try:
            data_dict = cls.objects.get(data_file_id=file_id, column_name=column_name)
            return data_dict.description
        except cls.DoesNotExist:
            return None

    def __str__(self):
        return f"{self.data_file.name} - {self.column_name}"