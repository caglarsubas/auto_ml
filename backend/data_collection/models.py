# data_collection/models.py
from django.db import models

class DataFile(models.Model):
    file = models.FileField(upload_to='data_files/')
    name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name