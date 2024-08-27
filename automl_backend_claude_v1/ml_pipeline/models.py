from django.db import models

class Dataset(models.Model):
    name = models.CharField(max_length=100)
    file = models.FileField(upload_to='datasets/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

class Model(models.Model):
    name = models.CharField(max_length=100)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    algorithm = models.CharField(max_length=50)
    hyperparameters = models.JSONField()
    performance = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)