from django.db import models

# Create your models here.

class IrisData(models.Model):
    sepal_length = models.FloatField()
    sepal_width = models.FloatField()
    petal_length = models.FloatField()
    petal_width = models.FloatField()
    species = models.CharField(max_length=50)

    class Meta:
        db_table = 'api_iris_data'

    def __str__(self):
        return f'{self.species}: {self.sepal_length}, {self.sepal_width}, {self.petal_length}, {self.petal_width}'