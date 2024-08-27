from django.shortcuts import render
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from .models import IrisData
from .serializers import IrisDataSerializer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
import pandas as pd
import numpy as np

# Create your views here.

class IrisDataViewSet(viewsets.ModelViewSet):
    queryset = IrisData.objects.all()
    serializer_class = IrisDataSerializer

    @action(detail=False, methods=['post'])
    def preprocess(self, request):
        data = pd.DataFrame(list(IrisData.objects.all().values()))
        data.fillna(data.mean(), inplace=True)
        data = data[(np.abs(data - data.mean()) <= (3 * data.std())).all(axis=1)]
        for column in ['sepal_length', 'sepal_width', 'petal_length', 'petal_width']:
            data[column] = (data[column] - data[column].mean()) / data[column].std()
        data['species'] = data['species'].astype('category').cat.codes
        return Response(data.to_dict(orient='records'))


@api_view(['POST', 'GET'])
def get_model_performance(request):
    try:
        # Load data from the IrisData model
        data = pd.DataFrame(list(IrisData.objects.all().values()))

        # Assuming 'species' is the target variable
        X = data.drop('species', axis=1)
        y = data['species']

        # Split the data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

        # Train the model
        model = LogisticRegression(max_iter=200)
        model.fit(X_train, y_train)

        # Make predictions
        y_pred = model.predict(X_test)

        # Calculate metrics
        f1 = f1_score(y_test, y_pred, average='weighted')
        precision = precision_score(y_test, y_pred, average='weighted')
        recall = recall_score(y_test, y_pred, average='weighted')
        roc_auc = roc_auc_score(y_test, model.predict_proba(X_test), multi_class='ovr')

        # Return the metrics
        metrics = {
            'f1_score': f1,
            'precision': precision,
            'recall': recall,
            'roc_auc': roc_auc
        }

        return Response(metrics, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)