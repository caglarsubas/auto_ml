from django.core.management.base import BaseCommand
from eda.models import Dataset

class Command(BaseCommand):
    help = 'Populates the database with initial datasets'

    def handle(self, *args, **kwargs):
        datasets = [
            {'name': 'Iris', 'description': 'Iris flower dataset'},
            {'name': 'Boston Housing', 'description': 'Boston Housing dataset'},
            {'name': 'Breast Cancer', 'description': 'Breast Cancer Wisconsin dataset'},
            {'name': 'Wine', 'description': 'Wine recognition dataset'},
        ]

        for data in datasets:
            Dataset.objects.get_or_create(name=data['name'], defaults={'description': data['description']})

        self.stdout.write(self.style.SUCCESS('Successfully populated datasets'))