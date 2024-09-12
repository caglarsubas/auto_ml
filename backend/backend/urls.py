from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from data_collection.views import DataFileViewSet
from feature_card.views import FeatureCardViewSet

router = DefaultRouter()
router.register(r'data-files', DataFileViewSet)
router.register(r'feature-card', FeatureCardViewSet, basename='feature-card')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
]

print(router.urls)  # Add this line to print out all registered URLs
