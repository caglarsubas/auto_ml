from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from declaration.models import Declaration
import os
from django.conf import settings
import json
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import accuracy_score, r2_score
from joblib import dump as joblib_dump


@method_decorator(csrf_exempt, name='dispatch')
class ModelingStartView(APIView):
    """Accepts processed file info and signals modeling can start.

    Payload: { file_id: number, processed_file: string }
    Returns 200 with echo of inputs. Real training can be hooked here later.
    """

    def post(self, request, *args, **kwargs):
        file_id = request.data.get('file_id')
        processed_file = request.data.get('processed_file')
        algorithm = request.data.get('algorithm')  # optional, e.g., 'xgboost', 'lightgbm', 'catboost'

        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not processed_file:
            return Response({'error': 'processed_file is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate declaration exists
        try:
            Declaration.objects.get(pk=file_id)
        except Declaration.DoesNotExist:
            return Response({'error': f'Declaration with id {file_id} not found'}, status=status.HTTP_404_NOT_FOUND)

        # Validate processed file exists under MEDIA_ROOT
        full_path = os.path.join(settings.MEDIA_ROOT, processed_file) if not os.path.isabs(processed_file) else processed_file
        if not os.path.exists(full_path):
            return Response({'error': f'processed file not found: {processed_file}'}, status=status.HTTP_404_NOT_FOUND)

        # Minimal synchronous "training" stub: compute simple metrics and write a status file
        modeling_dir = os.path.join(settings.MEDIA_ROOT, 'modeling')
        os.makedirs(modeling_dir, exist_ok=True)
        status_path = os.path.join(modeling_dir, f'{file_id}_status.json')

        # mark running
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump({'status': 'running', 'file_id': file_id, 'processed_file': processed_file, 'algorithm': algorithm}, f)

        # do quick metrics and a minimal training pass (best-effort)
        model_info = {}
        try:
            df = pd.read_csv(full_path) if full_path.lower().endswith('.csv') else pd.read_excel(full_path)
            metrics = {
                'rows': int(df.shape[0]),
                'features': int(df.shape[1]),
                'columns': list(map(str, df.columns[:50]))  # cap to 50 to keep response light
            }

            # Heuristically choose target
            target_col = None
            for candidate in ['Target', 'target', 'label', 'Label', 'y']:
                if candidate in df.columns:
                    target_col = candidate
                    break
            if target_col is None and len(df.columns) >= 2:
                target_col = df.columns[-1]

            if target_col is not None:
                # Prepare features/target
                y = df[target_col]
                X = df.drop(columns=[target_col])
                # Use only numeric features for simplicity
                X = X.select_dtypes(include=['number']).copy()
                # Drop columns with all NaNs
                X = X.dropna(axis=1, how='all')
                # Fill remaining NaNs with column means (numeric)
                X = X.fillna(X.mean(numeric_only=True))

                # If no features remain, skip training
                if X.shape[1] >= 1 and len(y) >= 5:
                    # Determine problem type: classification if few unique classes
                    is_classification = False
                    try:
                        n_unique = y.nunique(dropna=True)
                        is_classification = 2 <= n_unique <= 10
                    except Exception:
                        is_classification = False

                    # Coerce target
                    if is_classification:
                        # Encode categories to integers
                        y_encoded, _ = pd.factorize(y)
                        X_train, X_test, y_train, y_test = train_test_split(X, y_encoded, test_size=0.2, random_state=42)
                        clf = LogisticRegression(max_iter=1000)
                        clf.fit(X_train, y_train)
                        y_pred = clf.predict(X_test)
                        score = float(accuracy_score(y_test, y_pred))
                        model_type = 'logistic_regression'
                        # Save model
                        models_dir = os.path.join(settings.MEDIA_ROOT, 'models')
                        os.makedirs(models_dir, exist_ok=True)
                        model_path = os.path.join(models_dir, f'{file_id}_logreg.joblib')
                        joblib_dump(clf, model_path)
                    else:
                        # Regression path
                        y_num = pd.to_numeric(y, errors='coerce')
                        # If target all NaN after coercion, skip
                        if y_num.notna().sum() >= 5:
                            y_num = y_num.fillna(y_num.mean())
                            X_train, X_test, y_train, y_test = train_test_split(X, y_num, test_size=0.2, random_state=42)
                            reg = LinearRegression()
                            reg.fit(X_train, y_train)
                            y_pred = reg.predict(X_test)
                            score = float(r2_score(y_test, y_pred))
                            model_type = 'linear_regression'
                            models_dir = os.path.join(settings.MEDIA_ROOT, 'models')
                            os.makedirs(models_dir, exist_ok=True)
                            model_path = os.path.join(models_dir, f'{file_id}_linreg.joblib')
                            joblib_dump(reg, model_path)
                        else:
                            score = None
                            model_type = 'linear_regression'
                            model_path = None

                    model_info = {
                        'model_type': model_type,
                        'score': score,
                        'model_path': os.path.relpath(model_path, settings.MEDIA_ROOT) if model_path else None,
                        'feature_count': int(X.shape[1])
                    }
                else:
                    model_info = {'warning': 'Insufficient features or rows to train'}
            else:
                model_info = {'warning': 'No target column detected'}
        except Exception as e:
            metrics = {'error': str(e)}
            model_info = {'error': str(e)}

        # mark completed
        # attach algorithm to model info if provided
        if algorithm:
            model_info['requested_algorithm'] = algorithm

        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump({'status': 'completed', 'file_id': file_id, 'processed_file': processed_file, 'metrics': metrics, 'model': model_info, 'algorithm': algorithm}, f)

        return Response({'status': 'ok', 'job_status': 'completed', 'file_id': file_id, 'processed_file': processed_file, 'metrics': metrics, 'model': model_info, 'algorithm': algorithm}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class ModelingStatusView(APIView):
    """Returns current modeling status and metrics for a file id."""

    def get(self, request, file_id: int, *args, **kwargs):
        modeling_dir = os.path.join(settings.MEDIA_ROOT, 'modeling')
        status_path = os.path.join(modeling_dir, f'{file_id}_status.json')
        if not os.path.exists(status_path):
            return Response({'status': 'unknown', 'file_id': file_id}, status=status.HTTP_200_OK)
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
