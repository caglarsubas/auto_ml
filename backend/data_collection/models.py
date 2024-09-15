from django.db import models

class DataFile(models.Model):
    file = models.FileField(upload_to='data_files/')
    name = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class DataDictionary(models.Model):
    data_file = models.ForeignKey(DataFile, on_delete=models.CASCADE, related_name='data_dictionary')
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