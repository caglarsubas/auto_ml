# data_collection/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Declaration, DataDictionary
from .serializers import DeclarationSerializer
import os, io
from django.db.models import Q
from django.conf import settings
from django.core.files.storage import default_storage, FileSystemStorage
from django.core.files.base import ContentFile
from django.core.exceptions import MultipleObjectsReturned
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
import logging
from openpyxl import load_workbook
from rest_framework.exceptions import ValidationError
import magic  # You'll need to install python-magic: pip install python-magic
from django.utils import timezone

logger = logging.getLogger(__name__)


def detect_has_header(raw_bytes: bytes, sep: str = ',', is_excel: bool = False,
                      sheet_name=0) -> bool:
    """
    Heuristic: decide whether the first row is a header or data.

    Strategy — read first 20 rows with header=None and compare the first row
    against subsequent rows column-by-column:
      • If a column's data is predominantly numeric but the first-row value is
        a non-numeric string longer than 1 char → header signal.
      • If a column's data AND first-row value are both numeric → data signal.
      • For text columns: if the first-row value never appears in the data
        rows and is a plausible label → header signal, else data signal.

    Returns True if the first row looks like a header.
    """
    try:
        sample_rows = 20
        buf = io.BytesIO(raw_bytes)
        if is_excel:
            df_raw = pd.read_excel(buf, header=None, nrows=sample_rows + 1,
                                   sheet_name=sheet_name, engine='openpyxl')
        else:
            df_raw = pd.read_csv(buf, header=None, nrows=sample_rows + 1, sep=sep)

        if len(df_raw) < 2:
            return True  # can't tell with only one row

        first_row = df_raw.iloc[0]
        data_rows = df_raw.iloc[1:]

        header_signals = 0
        data_signals = 0

        for col_idx in range(len(df_raw.columns)):
            first_val = str(first_row.iloc[col_idx]).strip()
            col_data = data_rows.iloc[:, col_idx].dropna()

            # Is the column data predominantly numeric?
            numeric_data = pd.to_numeric(col_data, errors='coerce')
            data_is_numeric = numeric_data.notna().mean() > 0.5

            # Is the first-row value numeric?
            first_is_numeric = False
            try:
                float(first_val)
                first_is_numeric = True
            except (ValueError, TypeError):
                pass

            if data_is_numeric and not first_is_numeric and len(first_val) > 1:
                header_signals += 1
            elif data_is_numeric and first_is_numeric:
                data_signals += 1
            elif not data_is_numeric:
                # Text column — check if first value is unique / label-like
                data_vals = set(str(v) for v in col_data.values)
                if first_val not in data_vals and len(first_val) > 1:
                    header_signals += 1
                elif first_val in data_vals:
                    data_signals += 1
                else:
                    # Single-char first value could be data (e.g. 'Y', 'N', 'A')
                    data_signals += 1

        return header_signals >= data_signals
    except Exception:
        return True  # default to has-header on error


class DeclarationViewSet(viewsets.ModelViewSet):
    queryset = Declaration.objects.all()
    serializer_class = DeclarationSerializer
    
    def create(self, request, *args, **kwargs):
        files = request.FILES
        first_line_is_not_header = request.POST.get('first_line_is_not_header') == 'true'
        first_sheet_has_not_dataset = request.POST.get('first_sheet_has_not_dataset') == 'true'
        column_separator = request.POST.get('column_separator', 'semicolon')
        merge_column_wise = request.POST.get('merge_column_wise') == 'true'

        if not files:
            return Response({"error": "No files provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dataframes = []
            auto_detected_no_header = False
            for file_key in files:
                file = files[file_key]
                file_content = file.read()

                is_csv = file.name.lower().endswith('.csv')
                is_excel = file.name.lower().endswith(('.xls', '.xlsx'))
                sep = self.get_separator(column_separator)

                # Auto-detect header if user didn't explicitly check the box
                if not first_line_is_not_header:
                    sheet = 0
                    if is_excel and first_sheet_has_not_dataset:
                        wb = load_workbook(filename=io.BytesIO(file_content), read_only=True)
                        sheet = wb.sheetnames[1] if len(wb.sheetnames) > 1 else 0
                    has_header = detect_has_header(
                        file_content, sep=sep, is_excel=is_excel, sheet_name=sheet
                    )
                    if not has_header:
                        first_line_is_not_header = True
                        auto_detected_no_header = True
                        logger.info("Auto-detected: first row is data, not header (%s)", file.name)

                if is_csv:
                    df = pd.read_csv(io.BytesIO(file_content), header=None if first_line_is_not_header else 0, sep=sep)
                elif is_excel:
                    if first_sheet_has_not_dataset:
                        wb = load_workbook(filename=io.BytesIO(file_content), read_only=True)
                        sheet_to_read = wb.sheetnames[1] if len(wb.sheetnames) > 1 else wb.sheetnames[0]
                        df = pd.read_excel(io.BytesIO(file_content), sheet_name=sheet_to_read, header=None if first_line_is_not_header else 0, engine='openpyxl')
                    else:
                        df = pd.read_excel(io.BytesIO(file_content), header=None if first_line_is_not_header else 0, engine='openpyxl')
                else:
                    return Response({"error": f"Unsupported file format: {file.name}"}, status=status.HTTP_400_BAD_REQUEST)

                if first_line_is_not_header:
                    df.columns = [f'Col_{i+1}' for i in range(len(df.columns))]

                dataframes.append(df)

            # Merge dataframes based on user choice
            if len(dataframes) > 1:
                if merge_column_wise:
                    # Merge column-wise (horizontally)
                    merged_df = pd.concat(dataframes, axis=1)
                    # Rename duplicate columns
                    merged_df.columns = self.rename_duplicate_columns(merged_df.columns)
                else:
                    # Merge row-wise (vertically)
                    merged_df = pd.concat(dataframes, axis=0, ignore_index=True)
            else:
                merged_df = dataframes[0]

            # Save merged DataFrame
            merged_file_name = f'merged_data_{timezone.now().strftime("%Y%m%d%H%M%S")}.csv'
            merged_file_path = os.path.join('data_files', merged_file_name)
            full_merged_path = os.path.join(settings.MEDIA_ROOT, merged_file_path)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(full_merged_path), exist_ok=True)
            
            merged_df.to_csv(full_merged_path, index=False)

            # Create Declaration instance
            declaration = Declaration.objects.create(
                file=merged_file_path,
                name=merged_file_name,
                original_name=merged_file_name,
                has_header=not first_line_is_not_header,
            )

            serializer = self.get_serializer(declaration)
            response_data = serializer.data
            if auto_detected_no_header:
                response_data['auto_detected_no_header'] = True
            headers = self.get_success_headers(serializer.data)
            return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

        except Exception as e:
            import traceback
            print(traceback.format_exc())  # This will print the full traceback
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def rename_duplicate_columns(self, columns):
        new_columns = []
        seen = set()
        for item in columns:
            counter = 1
            new_item = item
            while new_item in seen:
                new_item = f"{item}_{counter}"
                counter += 1
            new_columns.append(new_item)
            seen.add(new_item)
        return new_columns

    def get_separator(self, separator_name):
        separators = {
            'semicolon': ';',
            'comma': ',',
            'tab': '\t',
            'space': ' '
        }
        return separators.get(separator_name, ';')
        
    def perform_create(self, serializer):
        file = self.request.FILES['file']
        serializer.save(original_name=file.name)

    @action(detail=False, methods=['get'], url_path='by-name/(?P<file_name>.+)')
    def get_by_name(self, request, file_name=None):
        try:
            data_file = Declaration.objects.get(file__endswith=file_name)
            serializer = self.get_serializer(data_file)
            return Response(serializer.data)
        except Declaration.DoesNotExist:
            return Response({"error": f"File '{file_name}' not found."}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        data_file = self.get_object()
        file_path = data_file.file.path

        # Ensure the file exists
        if not os.path.exists(file_path):
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check file type
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)
        
        print(f"File path: {file_path}")
        print(f"Detected MIME type: {file_type}")

        try:
            if file_type == 'text/csv' or file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'] or file_path.lower().endswith(('.xls', '.xlsx')):
                # Try different engines
                try:
                    df = pd.read_excel(file_path, engine='openpyxl')
                except Exception as openpyxl_error:
                    print(f"Error with openpyxl: {str(openpyxl_error)}")
                    try:
                        df = pd.read_excel(file_path, engine='xlrd')
                    except Exception as xlrd_error:
                        print(f"Error with xlrd: {str(xlrd_error)}")
                        raise ValueError("Unable to read Excel file with available engines.")
            else:
                return Response({"error": f"Unsupported file format: {file_type}"}, status=status.HTTP_400_BAD_REQUEST)

            df = df.replace({np.nan: None})

            preview = {
                "file_name": data_file.name,
                "total_rows": len(df),
                "total_columns": len(df.columns),
                "columns": df.columns.tolist(),
                "top_rows": df.head(5).to_dict(orient='records'),
                "bottom_rows": df.tail(5).to_dict(orient='records'),
                "data_types": df.dtypes.apply(lambda x: x.name).to_dict(),
                "non_null_counts": df.count().to_dict(),
                "first_line_is_not_header": not data_file.has_header
            }

            return Response(preview)
        except Exception as e:
            # Log the full error for debugging
            import traceback
            print(f"Error in preview: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": f"Error reading file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def calculate_descriptive_stats(self, column_data, data_type, level_of_measurement):
        desc_stats = {}
        if level_of_measurement in ['continuous', 'cardinal']:
            numeric_data = pd.to_numeric(column_data, errors='coerce')
            desc_stats = {
                'Mean': round(numeric_data.mean(), 2),
                'Min': round(numeric_data.min(), 2),
                '1st_Quantile': round(numeric_data.quantile(0.01), 2),
                '5th_Quantile': round(numeric_data.quantile(0.05), 2),
                '25th_Q1': round(numeric_data.quantile(0.25), 2),
                '50th_Median': round(numeric_data.median(), 2),
                '75th_Q3': round(numeric_data.quantile(0.75), 2),
                '95th_Quantile': round(numeric_data.quantile(0.95), 2),
                '99th_Quantile': round(numeric_data.quantile(0.99), 2),
                'Max': round(numeric_data.max(), 2),
                'Std': round(numeric_data.std(), 2),
                'Skewness': round(scipy_stats.skew(numeric_data.dropna()), 2),
                'Kurtosis': round(scipy_stats.kurtosis(numeric_data.dropna()), 2)
            }
        elif level_of_measurement in ['nominal', 'ordinal']:
            value_counts = column_data.value_counts(dropna=False)
            total_count = len(column_data)
            desc_stats = {
                '#_of_Categories': len(value_counts),
                'Mode_Value': value_counts.index[0] if len(value_counts) > 0 else None,
                'Mode_Ratio': round((value_counts.iloc[0] / total_count) * 100, 2) if len(value_counts) > 0 else 0,
                'Missing_Ratio': round((column_data.isnull().sum() / total_count) * 100, 2),
                '#_of_Outlier_Categories': sum((value_counts / total_count) < 0.005)
            }
        return desc_stats

    # to json serialization of NaNs
    def replace_nan_with_none(self, obj):
        if isinstance(obj, dict):
            return {key: self.replace_nan_with_none(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.replace_nan_with_none(item) for item in obj]
        elif isinstance(obj, float) and np.isnan(obj):
            return None
        return obj
        
    @action(detail=True, methods=['get', 'post'])
    def data_dictionary(self, request, pk=None):
        data_file = self.get_object()
        file_path = data_file.file.path
        dictionary_file = request.FILES.get('dictionary')

        # Check file type
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)
        
        print(f"Data file path: {file_path}")
        print(f"Detected MIME type: {file_type}")

        try:
            if file_type == 'text/csv' or file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'] or file_path.lower().endswith(('.xls', '.xlsx')):
                # Try different engines
                try:
                    df = pd.read_excel(file_path, engine='openpyxl')
                except Exception as openpyxl_error:
                    print(f"Error with openpyxl: {str(openpyxl_error)}")
                    try:
                        df = pd.read_excel(file_path, engine='xlrd')
                    except Exception as xlrd_error:
                        print(f"Error with xlrd: {str(xlrd_error)}")
                        raise ValueError("Unable to read Excel file with available engines.")
            else:
                return Response({"error": f"Unsupported file format: {file_type}"}, status=status.HTTP_400_BAD_REQUEST)

            def determine_level_of_measurement(column_data, data_type, unique_count):
                if unique_count == len(column_data):
                    return 'id'
                elif (data_type in ('float64', 'float', 'float32'))&(unique_count>1000):
                    return 'continuous'
                elif (data_type in ('float64', 'float', 'float32'))&(unique_count<=1000):
                    return 'cardinal'
                elif data_type == 'integer':
                    if unique_count > 1000 or unique_count / len(column_data) > 0.1:
                        return 'continuous'
                    else:
                        if unique_count>5:
                            return 'cardinal'
                        else:
                            return 'nominal'
                elif data_type in ('object', 'str', 'string'):
                    try:
                        pd.to_datetime(column_data, errors='raise', format='%d/%m/%Y %I:%M:%S %p')
                        return 'datetime'
                    except:
                        return 'nominal'
                else:
                    return 'unknown'

            data_dict = []
            n_rows = len(df)
            for column in df.columns:
              try:
                column_data = df[column]
                numeric_data = pd.to_numeric(column_data, errors='coerce')
                
                if numeric_data.notna().all() and np.isfinite(numeric_data).all():
                    if all(numeric_data.astype(float) == numeric_data.astype(int)):
                        data_type = 'integer'
                    else:
                        data_type = 'float'
                else:
                    data_type = column_data.dtype.name

                unique_count = column_data.nunique(dropna=False)
                level_of_measurement = determine_level_of_measurement(column_data, data_type, unique_count)

                # Calculate Missing_Ratio and Mode_Ratio
                missing_ratio = (column_data.isnull().sum() / n_rows) * 100 if n_rows > 0 else 0
                vc = column_data.value_counts()
                mode_count = vc.iloc[0] if len(vc) > 0 else 0
                mode_ratio = (mode_count / n_rows) * 100 if n_rows > 0 else 0

                # Determine Model_Usage_YN
                model_usage_yn = ('No' if level_of_measurement in ['id', 'date', 'datetime', 'timestamp'] or 
                                column in ['Target'] or 'date' in data_type.lower() or 
                                (n_rows > 0 and unique_count/n_rows > 0.90) 
                                else 'Yes')

                # Calculate descriptive statistics
                descriptive_stats = self.calculate_descriptive_stats(column_data, data_type, level_of_measurement)

                data_dict.append({
                    'Feature_Name': column,
                    'Data_Type': data_type,
                    '#_of_Unique_Value': unique_count,
                    'Level_of_Measurement': level_of_measurement,
                    'Missing_Ratio': round(missing_ratio, 2),
                    'Mode_Ratio': round(mode_ratio, 2),
                    'Model_Usage_YN': model_usage_yn,
                    'Descriptive_Stats': descriptive_stats
                })
              except Exception as col_err:
                print(f"Warning: data_dictionary skipped column '{column}': {col_err}")
                data_dict.append({
                    'Feature_Name': column,
                    'Data_Type': str(df[column].dtype),
                    '#_of_Unique_Value': 0,
                    'Level_of_Measurement': 'unknown',
                    'Missing_Ratio': 0,
                    'Mode_Ratio': 0,
                    'Model_Usage_YN': 'Yes',
                    'Descriptive_Stats': {}
                })

            # Process dictionary file if provided
            if dictionary_file:
                dict_file_type = mime.from_buffer(dictionary_file.read())
                dictionary_file.seek(0)  # Reset file pointer
                print(f"Dictionary file type: {dict_file_type}")

                try:
                    if dict_file_type == 'text/csv' or dictionary_file.name.lower().endswith('.csv'):
                        dict_df = pd.read_csv(dictionary_file)
                    elif dict_file_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'] or dictionary_file.name.lower().endswith(('.xls', '.xlsx')):
                        dict_df = pd.read_excel(dictionary_file, engine='openpyxl')
                    else:
                        return Response({"error": "Unsupported dictionary file format"}, status=400)

                    dict_df = dict_df.set_index(dict_df.columns[0])
                    for item in data_dict:
                        if item['Feature_Name'] in dict_df.index:
                            description = dict_df.loc[item['Feature_Name'], dict_df.columns[0]]
                            item['Feature_Description'] = description
                            if 'Level_of_Measurement' in dict_df.columns:
                                item['Level_of_Measurement'] = dict_df.loc[item['Feature_Name'], 'Level_of_Measurement']
                            
                            # Save to DataDictionary model
                            DataDictionary.objects.update_or_create(
                                data_file=data_file,
                                column_name=item['Feature_Name'],
                                defaults={'description': description}
                            )

                except Exception as e:
                    print(f"Error processing dictionary file: {str(e)}")
                    return Response({"error": f"Error processing dictionary file: {str(e)}"}, status=400)
            else:
                # No dictionary file uploaded in this request; try to enrich from saved DataDictionary
                try:
                    for item in data_dict:
                        try:
                            desc = DataDictionary.get_description(data_file.id, item['Feature_Name'])
                            if desc:
                                item['Feature_Description'] = desc
                        except Exception:
                            pass
                except Exception:
                    # Non-fatal: continue without descriptions
                    pass

            data_dict = self.replace_nan_with_none(data_dict)
            return Response(data_dict)

        except Exception as e:
            import traceback
            print(f"Error in data_dictionary: {str(e)}")
            print(traceback.format_exc())
            return Response({"error": f"Error processing file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ─── Feature Engineering (AI-driven) ───────────────────────────────
    @action(detail=True, methods=['post'])
    def engineer_features(self, request, pk=None):
        """
        Create derived features on the uploaded dataset.
        Body: { "features": [ { "name": str, "formula": str, "description": str, "fillna": any|null } ] }

        Supported formula types:
        - Arithmetic on columns: "Var_19 / (Var_24 + 1)"  → evaluated via df.eval()
        - ISNA:ColName             → df['ColName'].isna().astype(int)
        - LOG1P:ColName            → np.log1p(df['ColName'].clip(lower=0).fillna(0))
        - ABS:ColName              → df['ColName'].abs()
        - FLAG:expression          → (df.eval(expression)).astype(int)
        - CLIP:ColName:lower:upper → df['ColName'].clip(lower, upper)
        """
        import re, traceback

        data_file = self.get_object()
        file_path = data_file.file.path
        if not os.path.exists(file_path):
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        features = request.data.get('features', [])
        if not features or not isinstance(features, list):
            return Response({"error": "No features provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Load dataset
            if file_path.lower().endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file_path, engine='openpyxl')
            else:
                df = pd.read_csv(file_path)

            existing_cols = set(df.columns.tolist())
            created = []
            errors = []

            for feat in features:
                name = str(feat.get('name', '')).strip()
                formula = str(feat.get('formula', '')).strip()
                desc = feat.get('description', '')
                fill = feat.get('fillna', None)

                if not name or not formula:
                    errors.append({"name": name, "error": "name and formula are required"})
                    continue
                # Sanitize name: replace spaces/special chars with underscore
                safe_name = re.sub(r'[^A-Za-z0-9_]', '_', name)

                try:
                    series = self._eval_feature_formula(df, formula)
                    if fill is not None:
                        series = series.fillna(fill)
                    df[safe_name] = series
                    created.append({"name": safe_name, "description": desc, "formula": formula})
                except Exception as fe:
                    errors.append({"name": name, "error": str(fe)})

            if not created:
                return Response({"error": "No features could be created", "details": errors},
                                status=status.HTTP_400_BAD_REQUEST)

            # Save updated dataset back (always as CSV for consistency)
            out_path = file_path
            if file_path.lower().endswith(('.xls', '.xlsx')):
                out_path = file_path.rsplit('.', 1)[0] + '.csv'
                # Update the model's file field to point to CSV
                from django.core.files.base import ContentFile
                csv_bytes = df.to_csv(index=False).encode('utf-8')
                data_file.file.save(os.path.basename(out_path), ContentFile(csv_bytes), save=True)
            else:
                df.to_csv(out_path, index=False)

            # Update DataDictionary entries for new features
            for feat_info in created:
                DataDictionary.objects.update_or_create(
                    data_file=data_file,
                    column_name=feat_info['name'],
                    defaults={'description': feat_info.get('description', '')}
                )

            df_clean = df.replace({np.nan: None})
            preview = {
                "total_rows": len(df),
                "total_columns": len(df.columns),
                "columns": df.columns.tolist(),
                "top_rows": df_clean.head(5).to_dict(orient='records'),
            }

            return Response({
                "status": "success",
                "created": created,
                "errors": errors,
                "preview": preview,
            })

        except Exception as e:
            traceback.print_exc()
            return Response({"error": f"Feature engineering failed: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _eval_feature_formula(self, df: pd.DataFrame, formula: str) -> pd.Series:
        """Safely evaluate a feature formula against the dataframe."""
        import re as _re

        # Special prefix handlers
        if formula.upper().startswith('ISNA:'):
            col = formula[5:].strip()
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found")
            return df[col].isna().astype(int)

        if formula.upper().startswith('LOG1P:'):
            col = formula[6:].strip()
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found")
            return np.log1p(pd.to_numeric(df[col], errors='coerce').clip(lower=0).fillna(0))

        if formula.upper().startswith('ABS:'):
            col = formula[4:].strip()
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found")
            return pd.to_numeric(df[col], errors='coerce').abs()

        if formula.upper().startswith('FLAG:'):
            expr = formula[5:].strip()
            self._validate_expression_columns(df, expr)
            return df.eval(expr).astype(int)

        if formula.upper().startswith('CLIP:'):
            parts = formula[5:].split(':')
            if len(parts) != 3:
                raise ValueError("CLIP format: CLIP:ColName:lower:upper")
            col, lo, hi = parts[0].strip(), float(parts[1]), float(parts[2])
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found")
            return pd.to_numeric(df[col], errors='coerce').clip(lower=lo, upper=hi)

        # Default: arithmetic expression via df.eval()
        self._validate_expression_columns(df, formula)
        return df.eval(formula)

    def _validate_expression_columns(self, df: pd.DataFrame, expr: str):
        """Check that column references in an expression exist in the dataframe."""
        import re as _re
        # Extract potential column names (word tokens that aren't Python keywords or numbers)
        tokens = set(_re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', expr))
        keywords = {'and', 'or', 'not', 'in', 'True', 'False', 'None', 'nan', 'inf'}
        col_refs = tokens - keywords
        missing = col_refs - set(df.columns.tolist())
        if missing:
            raise ValueError(f"Unknown columns: {', '.join(sorted(missing))}")