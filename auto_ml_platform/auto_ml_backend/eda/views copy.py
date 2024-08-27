from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import IrisData
import pandas as pd
import plotly.express as px
import json
import numpy as np
import plotly.express as px
import plotly.io as pio

class EDAView(APIView):
    def get(self, request):
        try:
            # Fetch data from the database
            iris_data = IrisData.objects.all().values()
            
            # Convert to pandas DataFrame
            df = pd.DataFrame(list(iris_data))
            
            if df.empty:
                return Response({"error": "No data available"}, status=status.HTTP_404_NOT_FOUND)

            # Calculate basic statistics
            basic_stats = df.describe(include='all').to_dict()

            # Helper function to convert numpy types to Python types
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
                            
            # Replace NaN values with None for JSON serialization
            for feature in basic_stats:
                for stat in basic_stats[feature]:
                    if pd.isna(basic_stats[feature][stat]):
                        basic_stats[feature][stat] = None
                    else:
                        basic_stats[feature][stat] = convert_to_python_type(basic_stats[feature][stat])

            # Add species count to basic_stats
            species_count = df['species'].value_counts().to_dict()
            basic_stats['species'] = {'count': species_count}
            
            # Get the list of features
            features = df.columns.tolist()
            features.remove('species')  # Remove target variable from feature list
            default_feature = features[0] if features else None
            
            # If a specific feature is requested, create its plot
            selected_feature = request.query_params.get('feature', default_feature)
            is_stacked = request.query_params.get('stacked', 'false').lower() == 'true'
            plot_data = None
            
            if selected_feature and selected_feature in features:
                if df[selected_feature].dtype in ['int64', 'float64']:
                    if is_stacked:
                        fig = px.histogram(df, x=selected_feature, color='species', barmode='stack')
                    else:
                        fig = px.histogram(df, x=selected_feature)
                    fig.update_layout(title=f'{"Stacked " if is_stacked else ""}Histogram of {selected_feature}')
                else:
                    if is_stacked:
                        fig = px.bar(df[selected_feature].value_counts().reset_index(), x='index', y=selected_feature, color='species')
                    else:
                        fig = px.bar(df[selected_feature].value_counts().reset_index(), x='index', y=selected_feature)
                    fig.update_layout(title=f'{"Stacked " if is_stacked else ""}Bar Plot of {selected_feature}')
                
                fig.update_layout(xaxis_title=selected_feature, yaxis_title='Count')
                plot_data = pio.to_json(fig)

            # Convert DataFrame to dict
            df_dict = df.to_dict(orient='records')
            
            return Response({
                'basic_stats': basic_stats,
                'features': features,
                'plot_data': plot_data,
                'data': df_dict  # If you need to return the actual data
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)