from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('data_collection.urls')),
    path('admin/', admin.site.urls),
]
