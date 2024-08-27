from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets
from .models import Dataset, Model
from .serializers import DatasetSerializer, ModelSerializer
from .ml_utils import preprocess_data, train_model, evaluate_model

class DatasetViewSet(viewsets.ModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer

class ModelViewSet(viewsets.ModelViewSet):
    queryset = Model.objects.all()
    serializer_class = ModelSerializer

    def list(self, request):
        models = Model.objects.all()
        return render(request, 'model_results.html', {'models': models})
    
    def perform_create(self, serializer):
        model = serializer.save()
        dataset = model.dataset
        preprocessed_data = preprocess_data(dataset.file.path)
        trained_model = train_model(preprocessed_data, model.algorithm, model.hyperparameters)
        performance = evaluate_model(trained_model, preprocessed_data)
        model.performance = performance
        model.save()