# api/management/commands/load_iris_data.py
from django.core.management.base import BaseCommand
from api.models import IrisData
import pandas as pd
from sklearn.datasets import load_iris

class Command(BaseCommand):
    help = 'Load Iris data into the database'

    def handle(self, *args, **kwargs):
        iris = load_iris()
        data = pd.DataFrame(data=iris.data, columns=iris.feature_names)
        data['species'] = iris.target
        for _, row in data.iterrows():
            IrisData.objects.create(
                sepal_length=row['sepal length (cm)'],
                sepal_width=row['sepal width (cm)'],
                petal_length=row['petal length (cm)'],
                petal_width=row['petal width (cm)'],
                species=str(row['species'])
            )
        self.stdout.write(self.style.SUCCESS('Successfully loaded Iris data'))
