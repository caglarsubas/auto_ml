from django.db import models

class Dataset(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name

class DataPoint(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='datapoints')
    feature_values = models.JSONField()
    target_value = models.FloatField()

    def __str__(self):
        return f"DataPoint for {self.dataset.name}"