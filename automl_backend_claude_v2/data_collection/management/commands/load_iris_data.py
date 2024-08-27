import sys
import os
directory_path = "/home/caglarsubas/projects/automl_backend/data_collection"
sys.path.append(directory_path)
import django
# Add the project root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'automl_backend.settings')
# Setup Django
django.setup()
from django.core.management.base import BaseCommand
from sklearn.datasets import load_iris
from data_collection.models import IrisData

class Command(BaseCommand):
    help = 'Load Iris dataset into the database'

    def handle(self, *args, **kwargs):
        iris = load_iris()
        for i in range(len(iris.data)):
            IrisData.objects.create(
                sepal_length=iris.data[i][0],
                sepal_width=iris.data[i][1],
                petal_length=iris.data[i][2],
                petal_width=iris.data[i][3],
                species=iris.target_names[iris.target[i]]
            )
        self.stdout.write(self.style.SUCCESS('Successfully loaded Iris data'))