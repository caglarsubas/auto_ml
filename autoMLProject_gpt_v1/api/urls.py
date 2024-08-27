from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IrisDataViewSet, get_model_performance

router = DefaultRouter()
router.register(r'iris-data', IrisDataViewSet, basename='iris-data')

urlpatterns = [
    path('', include(router.urls)),
    #path('iris-data/', IrisDataViewSet.as_view({'get': 'list'}), name='iris-data'),
    path('iris-data/model-performance/', get_model_performance, name='model-performance')
]
