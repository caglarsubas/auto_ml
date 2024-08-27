from django.core.management.base import BaseCommand
from eda.models import IrisData
from sklearn.datasets import load_iris
import pandas as pd

class Command(BaseCommand):
    help = 'Populates the database with Iris dataset'

    def handle(self, *args, **kwargs):
        iris = load_iris()
        df = pd.DataFrame(data=iris.data, columns=iris.feature_names)
        df['species'] = pd.Categorical.from_codes(iris.target, iris.target_names)
        
        # Remove any rows with NaN values
        df = df.dropna()

        for _, row in df.iterrows():
            IrisData.objects.create(
                sepal_length=row['sepal length (cm)'],
                sepal_width=row['sepal width (cm)'],
                petal_length=row['petal length (cm)'],
                petal_width=row['petal width (cm)'],
                species=row['species']
            )
        self.stdout.write(self.style.SUCCESS('Successfully populated the database'))