from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from data_collection.views import DataFileViewSet
from feature_card.views import FeatureCardViewSet
from django.conf import settings
from django.conf.urls.static import static

router = DefaultRouter()
router.register(r'data-files', DataFileViewSet)
router.register(r'feature-card', FeatureCardViewSet, basename='feature-card')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/feature-card/<int:pk>/get_stacked_feature_data/', FeatureCardViewSet.as_view({'get': 'get_stacked_feature_data'}), name='get-stacked-feature-data'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
print(router.urls)  # Add this line to print out all registered URLs
