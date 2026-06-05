from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from declaration.views import DeclarationViewSet
from feature_card.views import FeatureCardViewSet
from preprocessing.views import PreprocessingApplyView, PreprocessingOptionsView, PreprocessingRunView, PreprocessingDatqDetailView, PreprocessingDatqTimeseriesView, PreprocessingDatqSummaryRowView, PreprocessingStatusView
from modeling.views import ModelingStartView, ModelingStatusView, FeatureExplainabilityView, SFSResultsView, SFSStartView, SFSStatusView, SFSStopView, VifDetailView, PipelineRunListView, PipelineRunCreateView, PipelineRunDetailView, PipelineReportView, HyperparamStartView, HyperparamStatusView, HyperparamStopView, HyperparamResultsView
from encoding.views import EncodingAnalyzeView, EncodingApplyView
from ai_assistant.feedback import AIFeedbackView
from ai_assistant.views import AIAssistantView, AIActionExecuteView, AICachePushView, AIModelListView
from django.conf import settings
from django.conf.urls.static import static

router = DefaultRouter()
router.register(r'declaration', DeclarationViewSet)
router.register(r'feature-card', FeatureCardViewSet, basename='feature-card')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/feature-card/<int:pk>/get_stacked_feature_data/', FeatureCardViewSet.as_view({'get': 'get_stacked_feature_data'}), name='get-stacked-feature-data'),
    path('api/preprocessing/apply/', PreprocessingApplyView.as_view(), name='preprocessing-apply'),
    path('api/preprocessing/options/', PreprocessingOptionsView.as_view(), name='preprocessing-options'),
    path('api/preprocessing/run/', PreprocessingRunView.as_view(), name='preprocessing-run'),
    path('api/preprocessing/datq_detail/', PreprocessingDatqDetailView.as_view(), name='preprocessing-datq-detail'),
    path('api/preprocessing/datq_timeseries/', PreprocessingDatqTimeseriesView.as_view(), name='preprocessing-datq-timeseries'),
    path('api/preprocessing/datq_summary_row/<int:file_id>/', PreprocessingDatqSummaryRowView.as_view(), name='preprocessing-datq-summary-row'),
    path('api/preprocessing/status/<int:file_id>/', PreprocessingStatusView.as_view(), name='preprocessing-status'),
    path('api/modeling/start/', ModelingStartView.as_view(), name='modeling-start'),
    path('api/modeling/status/<int:file_id>/', ModelingStatusView.as_view(), name='modeling-status'),
    path('api/modeling/feature-explainability/', FeatureExplainabilityView.as_view(), name='feature-explainability'),
    path('api/modeling/sfs/start/', SFSStartView.as_view(), name='sfs-start'),
    path('api/modeling/sfs/status/<int:file_id>/', SFSStatusView.as_view(), name='sfs-status'),
    path('api/modeling/sfs/stop/<int:file_id>/', SFSStopView.as_view(), name='sfs-stop'),
    path('api/modeling/sfs/<int:file_id>/', SFSResultsView.as_view(), name='sfs-results'),
    path('api/modeling/hyperparam/start/', HyperparamStartView.as_view(), name='hyperparam-start'),
    path('api/modeling/hyperparam/status/<int:file_id>/', HyperparamStatusView.as_view(), name='hyperparam-status'),
    path('api/modeling/hyperparam/stop/<int:file_id>/', HyperparamStopView.as_view(), name='hyperparam-stop'),
    path('api/modeling/hyperparam/<int:file_id>/', HyperparamResultsView.as_view(), name='hyperparam-results'),
    path('api/encoding/analyze/', EncodingAnalyzeView.as_view(), name='encoding-analyze'),
    path('api/encoding/apply/', EncodingApplyView.as_view(), name='encoding-apply'),
    path('api/modeling/vif-detail/', VifDetailView.as_view(), name='vif-detail'),
    path('api/pipeline/', PipelineRunListView.as_view(), name='pipeline-list'),
    path('api/pipeline/create/', PipelineRunCreateView.as_view(), name='pipeline-create'),
    path('api/pipeline/<int:pk>/', PipelineRunDetailView.as_view(), name='pipeline-detail'),
    path('api/pipeline/<int:pk>/report/', PipelineReportView.as_view(), name='pipeline-report'),
    path('api/ai-assistant/chat/', AIAssistantView.as_view(), name='ai-assistant-chat'),
    path('api/ai-assistant/execute-action/', AIActionExecuteView.as_view(), name='ai-assistant-execute-action'),
    path('api/ai-assistant/feedback/', AIFeedbackView.as_view(), name='ai-assistant-feedback'),
    path('api/ai-assistant/cache/', AICachePushView.as_view(), name='ai-assistant-cache'),
    path('api/ai-assistant/models/', AIModelListView.as_view(), name='ai-assistant-models'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
