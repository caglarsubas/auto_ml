from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Dataset, DataPoint
from .data_collection import collect_dataset
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.io as pio

class DatasetListView(APIView):
    def get(self, request):
        datasets = Dataset.objects.all().values('name', 'description')
        return Response(list(datasets))  # Convert to list for serialization

class DataCollectionView(APIView):
    def post(self, request):
        dataset_name = request.data.get('dataset_name')
        print(f"Received request to collect dataset: {dataset_name}")
        print(f"Request data: {request.data}")
        try:
            dataset_info = collect_dataset(dataset_name)
            
            # Save to database
            dataset, created = Dataset.objects.get_or_create(
                name=dataset_name,
                defaults={'description': dataset_info['DESCR']}
            )

            if not created:
                # If the dataset already exists, clear old data points
                DataPoint.objects.filter(dataset=dataset).delete()

            # Create new data points
            data_points = []
            for features, target in zip(dataset_info['data'], dataset_info['target']):
                data_point = DataPoint(
                    dataset=dataset,
                    feature_values=dict(zip(dataset_info['feature_names'], features)),
                    target_value=target
                )
                data_points.append(data_point)
            
            DataPoint.objects.bulk_create(data_points)

            return Response({'message': f'Dataset {dataset_name} collected successfully'})
        except Exception as e:
            print(f"Error collecting dataset: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


import logging
logger = logging.getLogger(__name__)
class EDAView(APIView):
    def get(self, request):
        try:
            dataset_name = request.query_params.get('dataset')
            if not dataset_name:
                return Response({'error': 'Dataset name is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"Fetching dataset: {dataset_name}")
            
            dataset = Dataset.objects.get(name=dataset_name)
            datapoints = DataPoint.objects.filter(dataset=dataset)
            
            logger.info(f"Number of datapoints: {datapoints.count()}")
            
            df = pd.DataFrame([dp.feature_values for dp in datapoints])
            df['target'] = [dp.target_value for dp in datapoints]
            
            if df.empty:
                logger.warning("DataFrame is empty")
                return Response({"error": "No data available"}, status=status.HTTP_404_NOT_FOUND)

            logger.info(f"DataFrame shape: {df.shape}")

            basic_stats = df.describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).to_dict()

            def convert_to_python_type(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, pd.Series):
                    return obj.tolist()
                else:
                    return obj
            
            for feature in basic_stats:
                for stat in basic_stats[feature]:
                    if pd.isna(basic_stats[feature][stat]):
                        basic_stats[feature][stat] = None
                    else:
                        basic_stats[feature][stat] = convert_to_python_type(basic_stats[feature][stat])

            features = df.columns.tolist()
            features.remove('target')
            features = ['target'] + features

            selected_feature = request.query_params.get('feature', 'target')
            is_stacked = request.query_params.get('stacked', 'false').lower() == 'true'
            
            if selected_feature == 'target':
                target_counts = df['target'].value_counts().reset_index()
                target_counts.columns = ['target', 'count']
                fig = px.bar(target_counts, x='target', y='count')
                fig.update_layout(title='Distribution of Target', xaxis_title='Target', yaxis_title='Count')
            elif selected_feature in features:
                if df[selected_feature].dtype in ['int64', 'float64']:
                    if is_stacked:
                        fig = px.histogram(df, x=selected_feature, color='target', barmode='stack')
                    else:
                        fig = px.histogram(df, x=selected_feature)
                    fig.update_layout(title=f'{"Stacked " if is_stacked else ""}Histogram of {selected_feature}')
                else:
                    feature_counts = df[selected_feature].value_counts().reset_index()
                    feature_counts.columns = [selected_feature, 'count']
                    if is_stacked:
                        fig = px.bar(feature_counts, x=selected_feature, y='count', color='target')
                    else:
                        fig = px.bar(feature_counts, x=selected_feature, y='count')
                    fig.update_layout(title=f'{"Stacked " if is_stacked else ""}Bar Plot of {selected_feature}')
                
                fig.update_layout(xaxis_title=selected_feature, yaxis_title='Count')
            else:
                return Response({'error': 'Invalid feature selected'}, status=status.HTTP_400_BAD_REQUEST)
            
            plot_data = pio.to_json(fig)

            logger.info("EDA data prepared successfully")
            return Response({
                'basic_stats': basic_stats,
                'features': features,
                'plot_data': plot_data
            })
        except Dataset.DoesNotExist:
            logger.error(f"Dataset not found: {dataset_name}")
            return Response({'error': 'Dataset not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("Error in EDA view")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)