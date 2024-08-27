from django.urls import path
from .views import iris_data

urlpatterns = [
    path('api/iris_data', iris_data, name='iris_data'),
]
