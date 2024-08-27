from django.urls import path
from .views import DatasetListView, DataCollectionView, EDAView

urlpatterns = [
    path('datasets/', DatasetListView.as_view(), name='dataset-list'),
    path('collect-dataset/', DataCollectionView.as_view(), name='collect-dataset'),
    path('eda/', EDAView.as_view(), name='eda'),
]