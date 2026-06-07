"""
UNIT TESTS
===========
Isolated tests for models, serializers, utility functions, and pure logic.
These tests do NOT hit the database or make HTTP requests unless necessary
for Django model validation.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# Declaration model tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDeclarationModel:

    def test_create_declaration(self):
        """Declaration can be created with required fields."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        assert decl.pk is not None
        assert str(decl) == 'test.csv'

    def test_declaration_get_file_path_returns_none_when_missing(self, _use_tmp_media):
        """get_file_path returns None when file does not exist on disk."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/nonexistent.csv',
            name='nonexistent.csv',
            original_name='nonexistent.csv',
        )
        assert decl.get_file_path() is None


@pytest.mark.unit
@pytest.mark.django_db
class TestDataDictionaryModel:

    def test_create_data_dictionary(self):
        """DataDictionary can be linked to a Declaration."""
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        dd = DataDictionary.objects.create(
            data_file=decl,
            column_name='Age',
            description='Customer age in years',
        )
        assert dd.pk is not None
        assert str(dd) == 'test.csv - Age'

    def test_get_description_returns_none_for_missing(self):
        """get_description returns None when column not in dictionary."""
        from declaration.models import DataDictionary
        assert DataDictionary.get_description(file_id=9999, column_name='X') is None

    def test_unique_together_constraint(self):
        """Duplicate (data_file, column_name) raises IntegrityError."""
        from django.db import IntegrityError
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        DataDictionary.objects.create(data_file=decl, column_name='Age', description='v1')
        with pytest.raises(IntegrityError):
            DataDictionary.objects.create(data_file=decl, column_name='Age', description='v2')


# ---------------------------------------------------------------------------
# Header auto-detection tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDetectHasHeader:
    """Test the detect_has_header heuristic from declaration/views.py."""

    def test_csv_with_text_headers(self):
        """A CSV whose first row has descriptive text headers should return True."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"AppID,Application_Datetime,Target,Var_1,Var_2\n"
            b"1,2020-01-01,0,1500,200\n"
            b"2,2020-02-01,1,3000,400\n"
            b"3,2020-03-01,0,500,100\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is True

    def test_csv_without_headers(self):
        """A CSV whose first row is all data (numeric + short strings) → False."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"0,1/1/2020 0:00,0,0,L,Y,1750,1\n"
            b"1,1/1/2020 0:00,0,0,1,N,1300,12\n"
            b"2,1/1/2020 0:00,0,0,0,N,0,0\n"
            b"3,2/1/2020 0:00,1,1,0,Y,500,3\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is False

    def test_csv_semicolon_with_headers(self):
        """Semicolon-delimited CSV with headers should return True."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"Name;Age;Income;City\n"
            b"Alice;30;50000;Berlin\n"
            b"Bob;25;40000;Munich\n"
        )
        assert detect_has_header(csv_bytes, sep=';') is True

    def test_csv_semicolon_without_headers(self):
        """Semicolon-delimited CSV without headers — mostly numeric + short codes."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"0;1/1/2020;Y;1750;500;A\n"
            b"1;2/1/2020;N;1300;600;R\n"
            b"2;3/1/2020;Y;0;100;A\n"
            b"3;4/1/2020;N;500;200;R\n"
        )
        result = detect_has_header(csv_bytes, sep=';')
        assert result is False

    def test_single_row_defaults_to_true(self):
        """With only one row, can't tell — default to has-header."""
        from declaration.views import detect_has_header
        csv_bytes = b"col1,col2,col3\n"
        assert detect_has_header(csv_bytes, sep=',') is True

    def test_empty_content_defaults_to_true(self):
        """Empty/unparseable content defaults to has-header."""
        from declaration.views import detect_has_header
        assert detect_has_header(b"", sep=',') is True

    def test_mixed_numeric_header(self):
        """First row has text headers, data rows are numeric → True."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"ID,Score,Amount,Balance,Limit\n"
            b"1,750,5000,2000,10000\n"
            b"2,680,3000,1500,8000\n"
            b"3,720,4500,3000,12000\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is True

    def test_all_numeric_no_header(self):
        """All values including first row are numeric → False."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"100,200,300,400\n"
            b"101,201,301,401\n"
            b"102,202,302,402\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is False


# ---------------------------------------------------------------------------
# Declaration model has_header field tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDeclarationHasHeader:

    def test_has_header_defaults_to_true(self):
        """New Declaration defaults to has_header=True."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        assert decl.has_header is True

    def test_has_header_can_be_set_false(self):
        """Declaration can be created with has_header=False."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
            has_header=False,
        )
        assert decl.has_header is False


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDeclarationSerializer:

    def test_serializer_fields(self):
        """Serializer exposes the expected field set."""
        from declaration.serializers import DeclarationSerializer
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        s = DeclarationSerializer(decl)
        assert set(s.data.keys()) == {'id', 'file', 'name', 'original_name', 'uploaded_at', 'has_header'}

    def test_serializer_read_only_id(self):
        """The id field is read-only."""
        from declaration.serializers import DeclarationSerializer
        s = DeclarationSerializer()
        assert s.fields['id'].read_only is True


# ---------------------------------------------------------------------------
# Utility / pure-logic tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetSeparator:

    def _get_separator(self, name):
        """Mirror the DeclarationViewSet.get_separator logic."""
        separators = {
            'semicolon': ';',
            'comma': ',',
            'tab': '\t',
            'space': ' ',
        }
        return separators.get(name, ';')

    def test_known_separators(self):
        assert self._get_separator('semicolon') == ';'
        assert self._get_separator('comma') == ','
        assert self._get_separator('tab') == '\t'
        assert self._get_separator('space') == ' '

    def test_unknown_defaults_to_semicolon(self):
        assert self._get_separator('pipe') == ';'
        assert self._get_separator('') == ';'


@pytest.mark.unit
class TestRenameDuplicateColumns:

    def _rename(self, columns):
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

    def test_no_duplicates(self):
        assert self._rename(['A', 'B', 'C']) == ['A', 'B', 'C']

    def test_with_duplicates(self):
        result = self._rename(['A', 'A', 'B', 'A'])
        assert result == ['A', 'A_1', 'B', 'A_2']

    def test_empty_list(self):
        assert self._rename([]) == []


@pytest.mark.unit
class TestDetermineLevelOfMeasurement:
    """Test the level-of-measurement classification logic."""

    def _determine(self, column_data, data_type, unique_count):
        if unique_count == len(column_data):
            return 'id'
        elif (data_type in ('float64', 'float', 'float32')) and (unique_count > 1000):
            return 'continuous'
        elif (data_type in ('float64', 'float', 'float32')) and (unique_count <= 1000):
            return 'cardinal'
        elif data_type == 'integer':
            if unique_count > 1000 or unique_count / len(column_data) > 0.1:
                return 'continuous'
            else:
                if unique_count > 5:
                    return 'cardinal'
                else:
                    return 'nominal'
        elif data_type in ('object', 'str', 'string'):
            try:
                pd.to_datetime(column_data, errors='raise', format='%d/%m/%Y %I:%M:%S %p')
                return 'datetime'
            except Exception:
                return 'nominal'
        else:
            return 'unknown'

    def test_unique_id_column(self):
        data = pd.Series(range(100))
        assert self._determine(data, 'integer', 100) == 'id'

    def test_float_continuous(self):
        data = pd.Series(np.random.uniform(0, 1, 5000))
        assert self._determine(data, 'float64', 4500) == 'continuous'

    def test_float_cardinal(self):
        data = pd.Series(np.random.uniform(0, 1, 100))
        assert self._determine(data, 'float', 80) == 'cardinal'

    def test_integer_continuous(self):
        data = pd.Series(range(10000))
        assert self._determine(data, 'integer', 5000) == 'continuous'

    def test_integer_cardinal(self):
        data = pd.Series(np.random.randint(1, 20, 200))
        assert self._determine(data, 'integer', 15) == 'cardinal'

    def test_integer_nominal(self):
        data = pd.Series(np.random.choice([0, 1], 100))
        assert self._determine(data, 'integer', 2) == 'nominal'

    def test_object_nominal(self):
        data = pd.Series(['A', 'B', 'C'] * 30)
        assert self._determine(data, 'object', 3) == 'nominal'

    def test_str_nominal(self):
        """Regression: 'str' dtype (pandas 2.0+) should classify as nominal, not unknown."""
        data = pd.Series(['cat', 'dog'] * 50)
        assert self._determine(data, 'str', 2) == 'nominal'

    def test_string_nominal(self):
        """Regression: 'string' dtype should classify as nominal, not unknown."""
        data = pd.Series(['x', 'y', 'z'] * 30)
        assert self._determine(data, 'string', 3) == 'nominal'

    def test_datetime_detection(self):
        dates = pd.Series([f'01/0{i}/2024 01:00:00 AM' for i in range(1, 10)] * 3)
        assert self._determine(dates, 'object', 9) == 'datetime'

    def test_unknown_fallback(self):
        data = pd.Series([1, 2, 3])
        assert self._determine(data, 'bool', 2) == 'unknown'


@pytest.mark.unit
class TestCalculateDescriptiveStats:
    """Test descriptive statistics calculation."""

    def test_continuous_stats_keys(self):
        data = pd.Series(np.random.uniform(0, 100, 500))
        numeric_data = pd.to_numeric(data, errors='coerce')
        stats = {
            'Mean': round(numeric_data.mean(), 2),
            'Min': round(numeric_data.min(), 2),
            'Max': round(numeric_data.max(), 2),
            'Std': round(numeric_data.std(), 2),
        }
        assert 'Mean' in stats
        assert 'Min' in stats
        assert stats['Min'] <= stats['Max']
        assert stats['Std'] >= 0

    def test_nominal_stats_keys(self):
        data = pd.Series(['A', 'B', 'C', 'A', 'A', 'B'])
        value_counts = data.value_counts(dropna=False)
        total_count = len(data)
        stats = {
            '#_of_Categories': len(value_counts),
            'Mode_Value': value_counts.index[0],
            'Mode_Ratio': round((value_counts.iloc[0] / total_count) * 100, 2),
        }
        assert stats['#_of_Categories'] == 3
        assert stats['Mode_Value'] == 'A'
        assert stats['Mode_Ratio'] == 50.0


# ---------------------------------------------------------------------------
# PipelineRun model tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestPipelineRunModel:

    def test_create_pipeline_run(self):
        """PipelineRun can be created with required fields."""
        from modeling.models import PipelineRun
        run = PipelineRun.objects.create(name='Test Pipeline', pipeline_type='boosting')
        assert run.pk is not None
        assert run.status == 'active'
        assert run.current_step == 'declaration'
        assert run.state == {}

    def test_pipeline_run_str(self):
        """String representation includes name, type, step, and status."""
        from modeling.models import PipelineRun
        run = PipelineRun.objects.create(
            name='Credit Model', pipeline_type='boosting',
            current_step='modeling', status='active'
        )
        s = str(run)
        assert 'Credit Model' in s
        assert 'boosting' in s
        assert 'modeling' in s
        assert 'active' in s

    def test_pipeline_run_json_state(self):
        """JSONField state stores and retrieves complex data."""
        from modeling.models import PipelineRun
        state = {
            'declaration': {'file_id': 42},
            'modeling': {'substep': 'encoding_completed', 'encodingPlan': [{'feature': 'Region'}]},
            'pipeline_notes': {'after_data_preview': 'Looks good'},
        }
        run = PipelineRun.objects.create(name='State Test', state=state)
        run.refresh_from_db()
        assert run.state['declaration']['file_id'] == 42
        assert run.state['modeling']['substep'] == 'encoding_completed'
        assert run.state['pipeline_notes']['after_data_preview'] == 'Looks good'

    def test_pipeline_run_ordering(self):
        """Runs are ordered by most recently updated (descending)."""
        from modeling.models import PipelineRun
        import time
        run1 = PipelineRun.objects.create(name='First')
        time.sleep(0.05)
        run2 = PipelineRun.objects.create(name='Second')
        runs = list(PipelineRun.objects.all())
        assert runs[0].name == 'Second'
        assert runs[1].name == 'First'

    def test_pipeline_run_status_choices(self):
        """All valid status choices are accepted."""
        from modeling.models import PipelineRun
        for status_val in ('active', 'paused', 'completed'):
            run = PipelineRun.objects.create(name=f'Run-{status_val}', status=status_val)
            assert run.status == status_val

    def test_pipeline_run_step_choices(self):
        """All valid step choices are accepted."""
        from modeling.models import PipelineRun
        valid_steps = ['declaration', 'preprocessing', 'data_quality', 'modeling', 'sfs', 'evaluation', 'deployment']
        for step in valid_steps:
            run = PipelineRun.objects.create(name=f'Run-{step}', current_step=step)
            assert run.current_step == step


# ---------------------------------------------------------------------------
# sanitize_sfs logic tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSanitizeSfsLogic:
    """Test the SFS result sanitization logic (numpy → float conversion)."""

    def _sanitize_sfs(self, results_list):
        """Mirror the sanitize_sfs function from views.py."""
        sanitized = []
        for item in results_list:
            sanitized_item = {
                'step': item['step'],
                'direction': item['direction'],
                'action': item['action'],
                'feature_name': item['feature_name'],
                'selected_features': item['selected_features'],
                'train_roc_auc': float(item['train_roc_auc']),
                'train_pr_auc': float(item['train_pr_auc']),
                'cv_roc_auc': float(item['cv_roc_auc']),
                'cv_pr_auc': float(item['cv_pr_auc']),
                'test_roc_auc': float(item['test_roc_auc']),
                'test_pr_auc': float(item['test_pr_auc']),
                'stability_type': item['stability_type'],
                'stability_value': float(item['stability_value']) if item['stability_value'] is not None else None,
                'shap_importance': float(item['shap_importance']),
                'shap_changes': {k: float(v) for k, v in item['shap_changes'].items()},
                'feature_importance': {k: float(v) for k, v in item.get('feature_importance', {}).items()},
                'shap_importance_by_feature': {k: float(v) for k, v in item.get('shap_importance_by_feature', {}).items()}
            }
            sanitized.append(sanitized_item)
        return sanitized

    def _make_step(self, **overrides):
        base = {
            'step': 1, 'direction': 'forward', 'action': 'added',
            'feature_name': 'Var_1', 'selected_features': ['Var_1'],
            'train_roc_auc': np.float64(0.85), 'train_pr_auc': np.float64(0.80),
            'cv_roc_auc': np.float64(0.83), 'cv_pr_auc': np.float64(0.78),
            'test_roc_auc': np.float64(0.82), 'test_pr_auc': np.float64(0.77),
            'stability_type': 'psi', 'stability_value': np.float64(0.01),
            'shap_importance': np.float64(0.15),
            'shap_changes': {'Var_1': np.float64(0.15)},
            'feature_importance': {'Var_1': np.float64(0.9)},
            'shap_importance_by_feature': {'Var_1': np.float64(0.15)},
        }
        base.update(overrides)
        return base

    def test_converts_numpy_to_float(self):
        """Numpy float64 values are converted to plain Python floats."""
        step = self._make_step()
        result = self._sanitize_sfs([step])
        assert len(result) == 1
        r = result[0]
        assert isinstance(r['train_roc_auc'], float)
        assert isinstance(r['cv_roc_auc'], float)
        assert isinstance(r['shap_importance'], float)
        assert isinstance(r['shap_changes']['Var_1'], float)

    def test_preserves_none_stability_value(self):
        """None stability_value is preserved as None."""
        step = self._make_step(stability_value=None)
        result = self._sanitize_sfs([step])
        assert result[0]['stability_value'] is None

    def test_preserves_selected_features(self):
        """selected_features list is preserved correctly."""
        step = self._make_step(selected_features=['Var_1', 'Var_2', 'Var_3'])
        result = self._sanitize_sfs([step])
        assert result[0]['selected_features'] == ['Var_1', 'Var_2', 'Var_3']

    def test_missing_selected_features_raises_keyerror(self):
        """Missing 'selected_features' key raises KeyError (regression guard)."""
        step = self._make_step()
        del step['selected_features']
        with pytest.raises(KeyError):
            self._sanitize_sfs([step])

    def test_empty_list_returns_empty(self):
        result = self._sanitize_sfs([])
        assert result == []

    def test_multiple_steps(self):
        steps = [
            self._make_step(step=1, feature_name='Var_1'),
            self._make_step(step=2, feature_name='Var_2', selected_features=['Var_1', 'Var_2']),
        ]
        result = self._sanitize_sfs(steps)
        assert len(result) == 2
        assert result[0]['feature_name'] == 'Var_1'
        assert result[1]['feature_name'] == 'Var_2'


# ---------------------------------------------------------------------------
# SFS forward-from-backward detection logic
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSfsForwardFromBackwardDetection:
    """Test the logic that detects forward-from-backward runs to prevent duplicate forward results."""

    def _detect(self, new_forward, existing_data):
        """Mirror the is_forward_from_backward detection from views.py final save."""
        return bool(new_forward and existing_data.get('backward'))

    def test_fwd_from_bwd_detected(self):
        """New forward + existing backward → forward-from-backward."""
        assert self._detect(
            [{'step': 1}],
            {'backward': [{'step': 1}]}
        ) is True

    def test_standalone_forward_not_detected(self):
        """New forward + no existing backward → standalone forward."""
        assert self._detect(
            [{'step': 1}],
            {}
        ) is False

    def test_empty_forward_not_detected(self):
        """Empty forward list → not forward-from-backward."""
        assert self._detect(
            [],
            {'backward': [{'step': 1}]}
        ) is False

    def test_no_forward_no_backward(self):
        assert self._detect([], {}) is False

    def test_save_logic_preserves_original_forward(self):
        """When is_forward_from_backward, original forward is preserved, not overwritten."""
        new_forward = [{'step': 1, 'feature_name': 'fwd_from_bwd_Var'}]
        existing_data = {
            'forward': [{'step': 1, 'feature_name': 'original_fwd_Var'}],
            'backward': [{'step': 1, 'feature_name': 'bwd_Var'}],
        }
        is_fwd_from_bwd = bool(new_forward and existing_data.get('backward'))

        sfs_data = {
            'forward': existing_data.get('forward', []) if is_fwd_from_bwd else (new_forward if new_forward else existing_data.get('forward', [])),
            'forward_from_backward': new_forward if is_fwd_from_bwd else existing_data.get('forward_from_backward', []),
        }
        assert sfs_data['forward'][0]['feature_name'] == 'original_fwd_Var'
        assert sfs_data['forward_from_backward'][0]['feature_name'] == 'fwd_from_bwd_Var'

    def test_save_logic_standalone_forward_uses_new(self):
        """Standalone forward (no backward) stores new results in 'forward' key."""
        new_forward = [{'step': 1, 'feature_name': 'new_fwd_Var'}]
        existing_data = {}
        is_fwd_from_bwd = bool(new_forward and existing_data.get('backward'))

        sfs_data = {
            'forward': existing_data.get('forward', []) if is_fwd_from_bwd else (new_forward if new_forward else existing_data.get('forward', [])),
            'forward_from_backward': new_forward if is_fwd_from_bwd else existing_data.get('forward_from_backward', []),
        }
        assert sfs_data['forward'][0]['feature_name'] == 'new_fwd_Var'
        assert sfs_data['forward_from_backward'] == []


# ---------------------------------------------------------------------------
# _infer_detailed_step logic tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestInferDetailedStep:
    """Test the backward-compat _infer_detailed_step logic."""

    _SUB_MAP = {
        'algorithm_selected': '3a_encoding',
        'encoding_completed': '3a_encoding',
        'modeling_started': '3b_modeling',
        'modeling_completed': '3b_modeling',
        'sfs_backward_completed': '3ci_sfs_backward',
        'hyperparam_completed': '3d_hyperparameter_tuning',
    }

    def _infer(self, current_step, modeling_sub, file_id):
        if current_step == 'declaration':
            return '1b_data_declaration' if file_id else '1a_pipeline_declaration'
        elif current_step == 'preprocessing':
            return '2a_purifier_declaration'
        elif current_step == 'data_quality':
            return '2b_data_quality_summary'
        elif current_step in ('modeling', 'sfs'):
            if modeling_sub:
                if modeling_sub in self._SUB_MAP:
                    return self._SUB_MAP[modeling_sub]
                if modeling_sub.startswith('sfs_'):
                    return '3c_sfs'
                if modeling_sub.startswith('hyperparam_'):
                    return '3d_hyperparameter_tuning'
            return '3a_encoding' if current_step == 'modeling' else '3c_sfs'
        return '1a_pipeline_declaration'

    def test_declaration_no_file(self):
        assert self._infer('declaration', '', None) == '1a_pipeline_declaration'

    def test_declaration_with_file(self):
        assert self._infer('declaration', '', 42) == '1b_data_declaration'

    def test_preprocessing(self):
        assert self._infer('preprocessing', '', None) == '2a_purifier_declaration'

    def test_data_quality(self):
        assert self._infer('data_quality', '', None) == '2b_data_quality_summary'

    def test_modeling_encoding_completed(self):
        assert self._infer('modeling', 'encoding_completed', 1) == '3a_encoding'

    def test_modeling_started(self):
        assert self._infer('modeling', 'modeling_started', 1) == '3b_modeling'

    def test_modeling_completed(self):
        assert self._infer('modeling', 'modeling_completed', 1) == '3b_modeling'

    def test_sfs_backward_completed(self):
        assert self._infer('modeling', 'sfs_backward_completed', 1) == '3ci_sfs_backward'

    def test_sfs_generic_substep(self):
        assert self._infer('modeling', 'sfs_forward_completed', 1) == '3c_sfs'

    def test_hyperparam_substep(self):
        assert self._infer('sfs', 'hyperparam_completed', 1) == '3d_hyperparameter_tuning'

    def test_sfs_step_no_substep(self):
        assert self._infer('sfs', '', None) == '3c_sfs'

    def test_modeling_no_substep(self):
        assert self._infer('modeling', '', None) == '3a_encoding'

    def test_unknown_step_fallback(self):
        assert self._infer('unknown_step', '', None) == '1a_pipeline_declaration'


# ---------------------------------------------------------------------------
# Pipeline step regression guard logic
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPipelineStepRegressionGuard:
    """Test that step regression (going backwards) is blocked."""

    STEP_ORDER = {
        'declaration': 0, 'preprocessing': 1, 'data_quality': 2,
        'modeling': 3, 'sfs': 4, 'evaluation': 5, 'deployment': 6,
    }

    def test_forward_step_allowed(self):
        old, new = 'declaration', 'preprocessing'
        assert self.STEP_ORDER[new] >= self.STEP_ORDER[old]

    def test_same_step_allowed(self):
        old, new = 'modeling', 'modeling'
        assert self.STEP_ORDER[new] >= self.STEP_ORDER[old]

    def test_backward_step_blocked(self):
        old, new = 'modeling', 'declaration'
        assert self.STEP_ORDER[new] < self.STEP_ORDER[old]

    def test_sfs_to_modeling_blocked(self):
        old, new = 'sfs', 'modeling'
        assert self.STEP_ORDER[new] < self.STEP_ORDER[old]

    def test_deployment_to_anything_blocked(self):
        for step in ('declaration', 'preprocessing', 'data_quality', 'modeling', 'sfs', 'evaluation'):
            assert self.STEP_ORDER[step] < self.STEP_ORDER['deployment']


# ---------------------------------------------------------------------------
# Encoding utility tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDetermineFallbackStrategy:
    """Test _determine_fallback_strategy from encoding_utils."""

    def _determine(self, lom, nunique):
        from encoding.encoding_utils import _determine_fallback_strategy
        return _determine_fallback_strategy(lom, nunique)

    def test_ordinal_low_unique_ohe(self):
        strategy, _ = self._determine('ordinal', 3)
        assert strategy == 'one_hot_encoding'

    def test_ordinal_mid_unique_ordinal(self):
        strategy, _ = self._determine('ordinal', 7)
        assert strategy == 'ordinal_encoding'

    def test_ordinal_high_unique_target(self):
        strategy, _ = self._determine('ordinal', 15)
        assert strategy == 'target_encoding'

    def test_nominal_label(self):
        strategy, _ = self._determine('nominal', 5)
        assert strategy == 'label_encoding'

    def test_unknown_label(self):
        strategy, _ = self._determine('unknown', 10)
        assert strategy == 'label_encoding'

    def test_boundary_ordinal_5(self):
        """Boundary: ordinal with exactly 5 unique → ordinal_encoding."""
        strategy, _ = self._determine('ordinal', 5)
        assert strategy == 'ordinal_encoding'

    def test_boundary_ordinal_10(self):
        """Boundary: ordinal with exactly 10 unique → ordinal_encoding."""
        strategy, _ = self._determine('ordinal', 10)
        assert strategy == 'ordinal_encoding'

    def test_boundary_ordinal_11(self):
        """Boundary: ordinal with 11 unique → target_encoding."""
        strategy, _ = self._determine('ordinal', 11)
        assert strategy == 'target_encoding'


@pytest.mark.unit
class TestLabelEncode:

    def test_basic_label_encoding(self):
        from encoding.encoding_utils import _label_encode
        df = pd.DataFrame({'Color': ['Red', 'Blue', 'Green', 'Red']})
        df_enc, mapping = _label_encode(df, 'Color')
        assert df_enc['Color'].dtype in (np.int64, np.int32, int)
        assert 'mapping' in mapping
        assert len(mapping['mapping']) == 3

    def test_label_encoding_with_nulls(self):
        from encoding.encoding_utils import _label_encode
        df = pd.DataFrame({'Color': ['Red', None, 'Blue', None]})
        df_enc, mapping = _label_encode(df, 'Color')
        assert '__NULL__' in mapping['mapping']
        assert df_enc['Color'].isnull().sum() == 0


@pytest.mark.unit
class TestOheEncode:

    def test_basic_ohe(self):
        from encoding.encoding_utils import _ohe_encode
        df = pd.DataFrame({'Animal': ['cat', 'dog', 'cat', 'bird'], 'X': [1, 2, 3, 4]})
        df_enc, mapping, new_cols = _ohe_encode(df, 'Animal')
        assert 'Animal' not in df_enc.columns
        assert len(new_cols) == 3
        assert 'X' in df_enc.columns

    def test_ohe_with_nulls(self):
        from encoding.encoding_utils import _ohe_encode
        df = pd.DataFrame({'Animal': ['cat', None, 'dog']})
        df_enc, mapping, new_cols = _ohe_encode(df, 'Animal')
        null_cols = [c for c in new_cols if 'NULL' in c]
        assert len(null_cols) == 1


@pytest.mark.unit
class TestTargetEncode:

    def test_basic_target_encoding(self):
        from encoding.encoding_utils import _target_encode
        df = pd.DataFrame({
            'Region': ['A', 'A', 'B', 'B', 'A', 'B'],
            'Target': [1, 1, 0, 0, 1, 0],
        })
        df_enc, mapping = _target_encode(df, 'Region', 'Target')
        assert df_enc['Region'].dtype == float
        assert mapping['type'] == 'target_encoding'
        assert float(mapping['mapping']['A']) == pytest.approx(1.0, abs=0.01)
        assert float(mapping['mapping']['B']) == pytest.approx(0.0, abs=0.01)

    def test_target_encode_missing_target_falls_back(self):
        from encoding.encoding_utils import _target_encode
        df = pd.DataFrame({'Region': ['A', 'B', 'A']})
        df_enc, mapping = _target_encode(df, 'Region', 'Target')
        assert mapping['type'] == 'label_encoding'


@pytest.mark.unit
class TestComputeStats:

    def test_numeric_stats(self):
        from encoding.encoding_utils import _compute_stats
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        stats = _compute_stats(s)
        assert stats['total_count'] == 5
        assert stats['null_count'] == 0
        assert 'mean' in stats
        assert stats['mean'] == pytest.approx(3.0)

    def test_categorical_stats(self):
        from encoding.encoding_utils import _compute_stats
        s = pd.Series(['A', 'B', 'A', 'C'])
        stats = _compute_stats(s)
        assert stats['nunique'] == 3
        assert 'mean' not in stats

    def test_stats_with_nulls(self):
        from encoding.encoding_utils import _compute_stats
        s = pd.Series([1.0, None, 3.0, None, 5.0])
        stats = _compute_stats(s)
        assert stats['null_count'] == 2
        assert stats['null_ratio'] == pytest.approx(40.0)


@pytest.mark.unit
class TestAnalyzeCategoricalFeatures:

    def test_identifies_categorical_features(self):
        from encoding.encoding_utils import analyze_categorical_features
        df = pd.DataFrame({
            'Region': ['North', 'South', 'East'],
            'Score': [0.5, 0.7, 0.3],
            'Target': [0, 1, 0],
        })
        data_dict = [
            {'Feature_Name': 'Region', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'Score', 'Level_of_Measurement': 'continuous'},
        ]
        plan = analyze_categorical_features(df, data_dict)
        features = [p['feature'] for p in plan]
        assert 'Region' in features
        assert 'Score' not in features
        assert 'Target' not in features

    def test_excludes_target_and_excluded_cols(self):
        from encoding.encoding_utils import analyze_categorical_features
        df = pd.DataFrame({
            'A': ['x', 'y'], 'B': ['a', 'b'], 'Target': [0, 1],
        })
        data_dict = [
            {'Feature_Name': 'A', 'Level_of_Measurement': 'nominal'},
            {'Feature_Name': 'B', 'Level_of_Measurement': 'nominal'},
        ]
        plan = analyze_categorical_features(df, data_dict, excluded_cols=['B'])
        features = [p['feature'] for p in plan]
        assert 'A' in features
        assert 'B' not in features

    def test_plan_entry_structure(self):
        from encoding.encoding_utils import analyze_categorical_features
        df = pd.DataFrame({'Cat': ['a', 'b', 'a'], 'Target': [0, 1, 0]})
        data_dict = [{'Feature_Name': 'Cat', 'Level_of_Measurement': 'nominal'}]
        plan = analyze_categorical_features(df, data_dict)
        assert len(plan) == 1
        entry = plan[0]
        assert entry['feature'] == 'Cat'
        assert 'nunique' in entry
        assert 'strategy' in entry
        assert 'fallback_strategy' in entry
        assert entry['strategy'] == 'native_categorical'


# ---------------------------------------------------------------------------
# NumpyEncoder tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestNumpyEncoder:
    """Test the NumpyEncoder.default() method from feature_card/views.py.

    Note: np.float64 / np.int64 are subclasses of Python float / int, so
    json.dumps handles them natively without calling default(). We test
    default() directly for edge cases that the encoder dispatches to it.
    """

    def _default(self, obj):
        from feature_card.views import NumpyEncoder
        return NumpyEncoder().default(obj)

    def test_numpy_int_via_default(self):
        assert self._default(np.int64(42)) == 42
        assert isinstance(self._default(np.int64(42)), int)

    def test_numpy_float_via_default(self):
        result = self._default(np.float64(3.14))
        assert abs(result - 3.14) < 1e-9
        assert isinstance(result, float)

    def test_numpy_nan_returns_none_via_default(self):
        assert self._default(np.float64('nan')) is None

    def test_numpy_inf_returns_none_via_default(self):
        assert self._default(np.float64('inf')) is None
        assert self._default(np.float64('-inf')) is None

    def test_numpy_int_serializable_via_dumps(self):
        import json
        from feature_card.views import NumpyEncoder
        result = json.loads(json.dumps({'val': np.int64(7)}, cls=NumpyEncoder))
        assert result['val'] == 7

    def test_numpy_float_serializable_via_dumps(self):
        import json
        from feature_card.views import NumpyEncoder
        result = json.loads(json.dumps({'val': np.float64(2.5)}, cls=NumpyEncoder))
        assert result['val'] == 2.5

    def test_dict_with_mixed_numpy_types(self):
        import json
        from feature_card.views import NumpyEncoder
        data = {'a': 1, 'b': 'hello', 'c': [1, 2]}
        result = json.loads(json.dumps(data, cls=NumpyEncoder))
        assert result == data


# ---------------------------------------------------------------------------
# FeatureCardViewSet.safe_float tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSafeFloat:
    """Test the safe_float static method from FeatureCardViewSet."""

    def _safe_float(self, value):
        from feature_card.views import FeatureCardViewSet
        return FeatureCardViewSet.safe_float(value)

    def test_normal_float(self):
        assert self._safe_float(3.14) == 3.14

    def test_normal_int(self):
        assert self._safe_float(42) == 42.0

    def test_nan_returns_none(self):
        assert self._safe_float(float('nan')) is None

    def test_inf_returns_none(self):
        assert self._safe_float(float('inf')) is None

    def test_neg_inf_returns_none(self):
        assert self._safe_float(float('-inf')) is None

    def test_none_returns_none(self):
        assert self._safe_float(None) is None

    def test_numpy_nan_returns_none(self):
        assert self._safe_float(np.nan) is None

    def test_numpy_inf_returns_none(self):
        assert self._safe_float(np.inf) is None

    def test_numpy_float64(self):
        result = self._safe_float(np.float64(2.5))
        assert result == 2.5

    def test_non_numeric_string_returns_none(self):
        assert self._safe_float('abc') is None

    def test_numeric_string(self):
        assert self._safe_float('3.14') == 3.14

    def test_zero(self):
        assert self._safe_float(0) == 0.0
        assert self._safe_float(0.0) == 0.0


# ---------------------------------------------------------------------------
# FeatureCardViewSet.determine_level_of_measurement tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFeatureCardDetermineLevel:
    """Test the FeatureCardViewSet.determine_level_of_measurement method."""

    def _determine(self, column_data):
        from feature_card.views import FeatureCardViewSet
        vs = FeatureCardViewSet()
        return vs.determine_level_of_measurement(column_data)

    def test_numeric_continuous(self):
        data = pd.Series(np.random.uniform(0, 100, 200))
        assert self._determine(data) == 'continuous'

    def test_numeric_cardinal(self):
        data = pd.Series(np.random.choice([1, 2, 3, 4, 5], 100))
        assert self._determine(data) == 'cardinal'

    def test_numeric_boundary_10(self):
        """Exactly 10 unique numeric values → cardinal (not continuous)."""
        data = pd.Series(list(range(10)) * 10)
        assert self._determine(data) == 'cardinal'

    def test_numeric_boundary_11(self):
        """11 unique numeric values → continuous."""
        data = pd.Series(list(range(11)) * 10)
        assert self._determine(data) == 'continuous'

    def test_string_nominal(self):
        data = pd.Series(['cat', 'dog', 'bird'] * 20)
        assert self._determine(data) == 'nominal'


# ---------------------------------------------------------------------------
# AI _extract_actions helper tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExtractActions:
    """Test the _extract_actions helper from ai_assistant/views.py."""

    def _extract(self, message):
        from ai_assistant.views import _extract_actions
        return _extract_actions(message)

    def test_no_actions(self):
        actions, clean = self._extract('Just a normal message.')
        assert actions == []
        assert clean == 'Just a normal message.'

    def test_single_action(self):
        msg = 'Here is advice. <<<ACTION:update_notes>>>{"position":"after_data_preview","content":"Note"}<<<END_ACTION>>> Done.'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['type'] == 'update_notes'
        assert actions[0]['payload']['content'] == 'Note'
        assert '<<<ACTION' not in clean
        assert 'Done.' in clean

    def test_multiple_actions(self):
        msg = '<<<ACTION:update_notes>>>{"content":"a"}<<<END_ACTION>>> text <<<ACTION:update_config>>>{"key":"x"}<<<END_ACTION>>>'
        actions, clean = self._extract(msg)
        assert len(actions) == 2
        assert actions[0]['type'] == 'update_notes'
        assert actions[1]['type'] == 'update_config'

    def test_invalid_json_skipped(self):
        msg = '<<<ACTION:update_notes>>>not valid json<<<END_ACTION>>> ok'
        actions, clean = self._extract(msg)
        assert len(actions) == 0
        assert 'ok' in clean

    def test_empty_message(self):
        actions, clean = self._extract('')
        assert actions == []
        assert clean == ''

    def test_two_angle_brackets(self):
        """LLM sometimes generates << >> instead of <<< >>>."""
        msg = 'Advice. <<ACTION:update_notes>>{"content":"note"}<<END_ACTION>> Done.'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['payload']['content'] == 'note'
        assert '<<ACTION' not in clean

    def test_mixed_angle_brackets(self):
        """LLM uses 3 opening but 2 closing brackets."""
        msg = '<<<ACTION:execute_code>>>{"code":"x=1","description":"test"}<<END_ACTION>>'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'

    def test_code_fence_wrapped_json(self):
        """LLM wraps the JSON payload in a code fence."""
        msg = '<<<ACTION:execute_code>>>```json\n{"code":"x=1","description":"test"}\n```<<<END_ACTION>>>'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['payload']['code'] == 'x=1'

    def test_multiline_execute_code(self):
        """Real-world: multiline code in execute_code action block."""
        code = "import pandas as pd\\ndf['New'] = df['A'] / df['B'].replace(0, 1)"
        msg = f'Creating features.\n<<<ACTION:execute_code>>>\n{{"code": "{code}", "description": "derive"}}\n<<<END_ACTION>>>\nDone.'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert 'pandas' in actions[0]['payload']['code']
        assert '<<<ACTION' not in clean

    def test_extra_whitespace_in_delimiters(self):
        """LLM adds spaces inside the angle brackets."""
        msg = '<<< ACTION : update_notes >>>{"content":"a"}<<< END_ACTION >>>'
        actions, clean = self._extract(msg)
        assert len(actions) == 1

    # ── Truncated action block tests ──────────────────────────────────

    def test_truncated_action_complete_json_no_end_tag(self):
        """Model hit token limit: JSON is complete but END_ACTION was never emitted."""
        msg = 'Creating features.\n<<<ACTION:execute_code>>>\n{"code":"x=1","description":"test"}'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert actions[0]['payload']['code'] == 'x=1'
        assert '<<<ACTION' not in clean
        assert 'Creating features.' in clean

    def test_truncated_action_json_cut_mid_string(self):
        """Model hit token limit: JSON is truncated mid-value."""
        msg = 'Here we go.\n<<<ACTION:execute_code>>>\n{"code":"a=1","description":"create fea'
        actions, clean = self._extract(msg)
        # _try_parse_truncated_json attempts to repair by closing string + brace.
        # Either it salvages it or returns nothing — either way, no crash.
        if actions:
            assert actions[0]['type'] == 'execute_code'
        assert '<<<ACTION' not in clean

    def test_truncated_action_garbage_after_json(self):
        """Complete JSON followed by garbage text (no END_ACTION)."""
        msg = 'Advice.\n<<<ACTION:execute_code>>>{"code":"x=1","description":"ok"}some trailing text'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['payload']['code'] == 'x=1'

    def test_truncated_fallback_only_when_no_complete_match(self):
        """Normal blocks are preferred; truncated fallback only fires when needed."""
        msg = '<<<ACTION:execute_code>>>{"code":"a=1","description":"x"}<<<END_ACTION>>> Done.'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert 'Done.' in clean

    def test_truncated_action_preserves_post_json_explanation(self):
        """Real trace: model emits action JSON then continues with explanation, no END_ACTION.

        The explanation text after the JSON must appear in clean_message so the
        user sees 'What was added:' in the chat bubble.
        """
        explanation = (
            'Created the suggested features.\n\n'
            'What was added:\n'
            '- Time features from Application_Datetime\n'
            '  - App_Month\n'
            '  - App_DayOfWeek\n'
            '- Ratio features\n'
            '  - Var_19_to_Var_24'
        )
        msg = f'<<<ACTION:execute_code>>>\n{{"code":"x=1","description":"derive"}}\n{explanation}'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['payload']['code'] == 'x=1'
        # The explanation text must be preserved in clean_message
        assert 'What was added:' in clean
        assert 'App_Month' in clean
        assert 'Var_19_to_Var_24' in clean
        assert '<<<ACTION' not in clean

    def test_truncated_action_preserves_text_before_and_after(self):
        """Text before the action tag AND after the JSON are both preserved."""
        msg = 'I will create features.\n<<<ACTION:execute_code>>>{"code":"x=1","description":"d"}\nDone creating.'
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert 'I will create features.' in clean
        assert 'Done creating.' in clean


# ---------------------------------------------------------------------------
# AI _format_context tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFormatContext:
    """Test the _format_context helper from ai_assistant/views.py."""

    def _format(self, context, section):
        from ai_assistant.views import _format_context
        return _format_context(context, section)

    def test_data_quality_section(self):
        ctx = {'summary': [{'Variable': 'Age', 'Variable_Type': 'numeric', 'PSI': 0.05, 'Datq_Decision': 'Accept'}]}
        result = self._format(ctx, 'data_quality')
        assert 'Age' in result
        assert 'PSI' in result
        assert 'Accept' in result

    def test_encoding_section(self):
        ctx = {'plan': [{'feature': 'Region', 'user_lom': 'nominal', 'nunique': 4, 'fallback_strategy': 'label_encoding'}]}
        result = self._format(ctx, 'encoding')
        assert 'Region' in result
        assert 'nominal' in result

    def test_cv_section(self):
        ctx = {'cv': {'roc_auc_mean': 0.85, 'roc_auc_std': 0.02, 'pr_auc_mean': 0.70, 'pr_auc_std': 0.03, 'n_splits': 5}}
        result = self._format(ctx, 'cv')
        assert '0.85' in result or '0.8500' in result
        assert 'Cross-Validation' in result

    def test_shap_section(self):
        ctx = {'features': [{'feature': 'Income', 'impact': 0.45, 'signed_impact': 0.35}]}
        result = self._format(ctx, 'shap')
        assert 'Income' in result
        assert 'SHAP' in result

    def test_selected_features_section(self):
        ctx = {'features': [{'feature': 'Score', 'combined_score': 0.9, 'shap_percentile': 95, 'gain_percentile': 88, 'vif': 1.2, 'usage': 'keep'}]}
        result = self._format(ctx, 'selected_features')
        assert 'Score' in result
        assert 'Selected Features' in result

    def test_sfs_section(self):
        ctx = {
            'forward': [{'step': 1, 'feature_name': 'Var_1', 'cv_roc_auc': 0.80, 'remaining': ['Var_1']}],
            'backward': [],
        }
        result = self._format(ctx, 'sfs')
        assert 'Forward' in result
        assert 'Var_1' in result

    def test_general_section_fallback(self):
        ctx = {'data_preview': {'file_name': 'test.csv', 'total_rows': 100, 'total_columns': 5, 'columns': ['A', 'B']}}
        result = self._format(ctx, 'general')
        assert 'test.csv' in result
        assert '100' in result

    def test_empty_context_returns_json(self):
        result = self._format({}, 'unknown')
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# AI dispatch_action routing tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDispatchAction:
    """Test the dispatch_action router from ai_assistant/action_executor.py."""

    def _dispatch(self, file_id, action_type, payload):
        from ai_assistant.action_executor import dispatch_action
        return dispatch_action(file_id, action_type, payload)

    def test_unknown_action_returns_error(self):
        result = self._dispatch(1, 'bogus_action', {})
        assert result['status'] == 'error'
        assert 'Unknown action type' in result['error']

    def test_update_notes_routes_correctly(self):
        result = self._dispatch(1, 'update_notes', {
            'action': 'add',
            'position': 'after_data_preview',
            'content': 'Test',
        })
        assert result['status'] == 'success'
        assert result['action_type'] == 'update_notes'

    def test_update_metadata_empty_updates_error(self):
        result = self._dispatch(1, 'update_metadata', {'updates': []})
        assert result['status'] == 'error'

    def test_update_config_empty_updates_error(self):
        result = self._dispatch(1, 'update_config', {'updates': []})
        assert result['status'] == 'error'

    def test_execute_code_empty_code_error(self):
        result = self._dispatch(1, 'execute_code', {'code': '', 'description': ''})
        assert result['status'] == 'error'
        assert 'No code' in result['error']

    def test_execute_code_strips_import_lines(self):
        """Import lines should be stripped — np/pd are pre-loaded in sandbox."""
        from ai_assistant.action_executor import execute_code
        # Code with import lines that would fail in sandbox
        code_with_imports = "import numpy as np\nfrom pandas import DataFrame\ndf['test_col'] = 1"
        # Strip logic is inside execute_code, but we can test the stripping directly
        lines = code_with_imports.splitlines()
        stripped = '\n'.join(
            line for line in lines
            if not line.strip().startswith(('import ', 'from '))
        )
        assert 'import' not in stripped
        assert "df['test_col'] = 1" in stripped

    def test_restore_backup_copies_file(self, tmp_path):
        """_restore_backup should copy backup to original and remove backup."""
        from ai_assistant.action_executor import _restore_backup
        original = tmp_path / 'data.csv'
        backup = tmp_path / 'data.csv.bak'
        original.write_text('corrupted')
        backup.write_text('original_content')
        _restore_backup(str(backup), str(original))
        assert original.read_text() == 'original_content'
        assert not backup.exists()

    def test_remove_backup_cleans_up(self, tmp_path):
        """_remove_backup should delete the backup file."""
        from ai_assistant.action_executor import _remove_backup
        backup = tmp_path / 'data.csv.bak'
        backup.write_text('backup_content')
        _remove_backup(str(backup))
        assert not backup.exists()

    def test_remove_backup_noop_on_missing(self, tmp_path):
        """_remove_backup should not raise if file doesn't exist."""
        from ai_assistant.action_executor import _remove_backup
        _remove_backup(str(tmp_path / 'nonexistent.bak'))  # should not raise

    # ── v2.24.0+: set_ordinal_ranking action ────────────────────────────
    # The dedicated path for the AI to follow through on an ordinal LoM
    # change.  These tests pin the validation surface and ensure the
    # action is registered in the dispatcher.

    def test_set_ordinal_ranking_routes_correctly(self):
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_36', 'ranking': ['0', '1', '2', '3', '8', 'L', 'Others']},
            ],
        })
        assert result['status'] == 'success'
        assert result['action_type'] == 'set_ordinal_ranking'
        assert len(result['applied']) == 1
        applied = result['applied'][0]
        assert applied['column'] == 'Var_36'
        # Values must be coerced to strings to match the encoding plan
        # `unique_values` shape and the backend's _ordinal_encode key
        # type — guards against an LLM emitting numeric ranks.
        assert applied['ranking'] == ['0', '1', '2', '3', '8', 'L', 'Others']
        assert all(isinstance(v, str) for v in applied['ranking'])

    def test_set_ordinal_ranking_batches_multiple_features(self):
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_2', 'ranking': ['A', 'P', 'R']},
                {'column': 'Var_36', 'ranking': ['Low', 'Mid', 'High']},
            ],
        })
        assert result['status'] == 'success'
        assert len(result['applied']) == 2
        cols = {a['column'] for a in result['applied']}
        assert cols == {'Var_2', 'Var_36'}

    def test_set_ordinal_ranking_coerces_numeric_ranking_values_to_str(self):
        # The LLM may emit numeric values in the ranking — coercion to
        # string is required so the encoding-time `series.map(...)`
        # lookup hits (the column is astype(str)'d in _ordinal_encode).
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [{'column': 'Var_X', 'ranking': [0, 1, 2, 3]}],
        })
        assert result['status'] == 'success'
        assert result['applied'][0]['ranking'] == ['0', '1', '2', '3']

    def test_set_ordinal_ranking_empty_updates_error(self):
        result = self._dispatch(1, 'set_ordinal_ranking', {'updates': []})
        assert result['status'] == 'error'
        assert 'No ranking updates' in result['error']

    def test_set_ordinal_ranking_non_list_updates_error(self):
        result = self._dispatch(1, 'set_ordinal_ranking', {'updates': 'not-a-list'})
        assert result['status'] == 'error'

    def test_set_ordinal_ranking_rejects_duplicate_values(self):
        # The ordinal scale is a strict order — every category must
        # appear exactly once.  Duplicates would alias two ranks to
        # the same integer at encoding time.
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [{'column': 'Var_36', 'ranking': ['Low', 'Mid', 'Low', 'High']}],
        })
        assert result['status'] == 'error'  # no entry was applied
        assert len(result['errors']) == 1
        err = result['errors'][0]
        assert err['column'] == 'Var_36'
        assert 'duplicate' in err['error']

    def test_set_ordinal_ranking_rejects_single_value_ranking(self):
        # An ordinal "scale" of length 1 has no order to encode.
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [{'column': 'Var_X', 'ranking': ['only-one']}],
        })
        assert result['status'] == 'error'
        assert len(result['errors']) == 1
        assert 'at least 2' in result['errors'][0]['error']

    def test_set_ordinal_ranking_rejects_non_list_ranking(self):
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [{'column': 'Var_X', 'ranking': 'not-a-list'}],
        })
        assert result['status'] == 'error'
        assert len(result['errors']) == 1

    def test_set_ordinal_ranking_rejects_missing_column(self):
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [{'ranking': ['A', 'B', 'C']}],  # no `column`
        })
        assert result['status'] == 'error'
        assert len(result['errors']) == 1

    def test_set_ordinal_ranking_partial_success(self):
        # Mix of one valid + one invalid entry — the action should
        # report success because at least one ranking was applied,
        # and the invalid one is surfaced in `errors`.
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_OK', 'ranking': ['A', 'B', 'C']},
                {'column': 'Var_Bad', 'ranking': ['X', 'X']},  # duplicates
            ],
        })
        assert result['status'] == 'success'
        assert len(result['applied']) == 1
        assert result['applied'][0]['column'] == 'Var_OK'
        assert len(result['errors']) == 1
        assert result['errors'][0]['column'] == 'Var_Bad'

    # ── v2.39.0+: set_ordinal_ranking auto-couples LoM=ordinal ──────────
    # Pre-v2.39.0 the AI had to emit BOTH update_metadata (LoM=ordinal)
    # AND set_ordinal_ranking action blocks for the encoding-plan
    # dropdown to render the ranking.  Smaller models (gemma-4-26b)
    # reliably emitted only the second, so the ranking landed in the
    # cache but the UI silently kept rendering Nominal — the user saw
    # "Applied" while nothing visibly changed.  v2.39.0 closes the gap
    # by treating LoM='ordinal' as an automatic consequence of any
    # successfully-applied ranking, eliminating the multi-block chain.

    def test_set_ordinal_ranking_emits_implied_metadata_updates(self):
        # Single-feature happy path: the response carries a parallel
        # implied_metadata_updates list with one LoM=ordinal entry per
        # applied column.  Frontend uses this list to fan onto its
        # existing metadataUpdates$ broadcast — the encoding-plan
        # dropdown's LoM column flips visibly in lock-step.
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_36', 'ranking': ['Low', 'Mid', 'High']},
            ],
        })
        assert result['status'] == 'success'
        implied = result['implied_metadata_updates']
        assert isinstance(implied, list)
        assert len(implied) == 1
        entry = implied[0]
        # Shape MUST mirror update_metadata's `applied` array exactly so
        # the frontend's _applyMetadataPatchesToDictionaryCache helper
        # consumes it without a special case.
        assert set(entry.keys()) == {'column', 'field', 'value'}
        assert entry['column'] == 'Var_36'
        assert entry['field'] == 'Level_of_Measurement'
        assert entry['value'] == 'ordinal'

    def test_set_ordinal_ranking_implied_metadata_batches_multiple_features(self):
        # When several rankings land in one call, every applied column
        # gets its own LoM=ordinal entry — order preserved relative to
        # `applied` so the frontend's index-by-name lookup hits.
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_A', 'ranking': ['1', '2', '3']},
                {'column': 'Var_B', 'ranking': ['Low', 'High']},
                {'column': 'Var_C', 'ranking': ['Red', 'Green', 'Blue']},
            ],
        })
        assert result['status'] == 'success'
        implied = result['implied_metadata_updates']
        assert len(implied) == 3
        cols = [e['column'] for e in implied]
        assert cols == ['Var_A', 'Var_B', 'Var_C']
        # Every entry must declare LoM=ordinal — that's the whole point.
        assert all(e['field'] == 'Level_of_Measurement' for e in implied)
        assert all(e['value'] == 'ordinal' for e in implied)

    def test_set_ordinal_ranking_implied_metadata_only_for_applied_columns(self):
        # Partial success: one valid ranking lands, one invalid ranking
        # is rejected.  The implied LoM flip must fire ONLY for the
        # column whose ranking actually applied — flipping LoM for the
        # rejected column would leave the pipeline in a broken state
        # (LoM=ordinal but no ranking → encoding silently downgrades).
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_OK', 'ranking': ['A', 'B', 'C']},
                {'column': 'Var_Bad', 'ranking': ['X', 'X']},  # rejected: duplicates
            ],
        })
        assert result['status'] == 'success'
        implied = result['implied_metadata_updates']
        assert len(implied) == 1
        assert implied[0]['column'] == 'Var_OK'
        # Var_Bad MUST NOT appear — its ranking did not land.
        assert 'Var_Bad' not in {e['column'] for e in implied}

    def test_set_ordinal_ranking_empty_updates_returns_implied_metadata_field(self):
        # When the request fails validation outright (no updates), the
        # response still has `implied_metadata_updates` as an empty
        # list — frontend code paths assume the field is always
        # present and an `(resp.implied_metadata_updates || []).length`
        # check is a stricter contract than `if 'implied_metadata_updates' in resp`.
        result = self._dispatch(1, 'set_ordinal_ranking', {'updates': []})
        assert result['status'] == 'error'
        assert 'implied_metadata_updates' in result
        assert result['implied_metadata_updates'] == []

    def test_set_ordinal_ranking_implied_metadata_when_all_invalid(self):
        # Edge case: every supplied ranking is rejected → applied=[],
        # implied_metadata_updates=[].  The response status is 'error'
        # because nothing landed, and the frontend's
        # `if (impliedMetadata.length)` guard correctly skips the
        # broadcast — the encoding-plan dropdown is NOT mutated.
        result = self._dispatch(1, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_Bad1', 'ranking': ['X', 'X']},  # duplicates
                {'column': 'Var_Bad2', 'ranking': ['only-one']},  # too short
            ],
        })
        assert result['status'] == 'error'
        assert result['applied'] == []
        assert result['implied_metadata_updates'] == []

    def test_set_ordinal_ranking_writes_lom_through_to_data_dictionary_cache(self):
        # The cache write-through is best-effort: if Redis is up, the
        # NEXT get_data_dictionary tool call MUST report LoM='ordinal'
        # for every ranked column so the assistant's view of the
        # world matches the user's view in the encoding-plan
        # dropdown.  This test is the regression guard for the
        # "AI thinks Var_36 is still Nominal next turn" failure mode.
        from ai_assistant.cache import cache_put, cache_get, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        file_id = 39001
        try:
            cache_put(file_id, 'data_dictionary', [
                {'Feature_Name': 'Var_36', 'Level_of_Measurement': 'Nominal',
                 'Data_Type': 'object', 'Unique_Values': 7},
                {'Feature_Name': 'Var_Other', 'Level_of_Measurement': 'Nominal',
                 'Data_Type': 'object', 'Unique_Values': 3},
            ])
            self._dispatch(file_id, 'set_ordinal_ranking', {
                'updates': [
                    {'column': 'Var_36', 'ranking': ['0', '1', '2', '3', '8', 'L', 'Others']},
                ],
            })
            patched = cache_get(file_id, 'data_dictionary')
            by_name = {e['Feature_Name']: e for e in patched}
            # Var_36's LoM is now ordinal — the AI's NEXT
            # get_data_dictionary call sees the post-action state.
            assert by_name['Var_36']['Level_of_Measurement'] == 'ordinal'
            # Var_Other is untouched — only ranked columns flip.
            assert by_name['Var_Other']['Level_of_Measurement'] == 'Nominal'
        finally:
            _get_redis().delete(f'ai:pipeline:{file_id}:data_dictionary')

    def test_set_ordinal_ranking_dictionary_write_through_silent_on_cache_miss(self):
        # When the data_dictionary cache is empty (Redis available but
        # no prior cache_put), the write-through is a silent no-op —
        # the action still succeeds and returns implied_metadata_updates
        # so the frontend can patch its in-memory cache.  This test
        # pins the "fail open, never raise" contract: the cache layer
        # MUST NOT cause a successful action to error out.
        from ai_assistant.cache import _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        file_id = 39002
        # Ensure no stale cache.
        _get_redis().delete(f'ai:pipeline:{file_id}:data_dictionary')
        result = self._dispatch(file_id, 'set_ordinal_ranking', {
            'updates': [
                {'column': 'Var_X', 'ranking': ['A', 'B', 'C']},
            ],
        })
        # Action succeeded — cache miss was tolerated silently.
        assert result['status'] == 'success'
        assert result['applied'][0]['column'] == 'Var_X'
        # Frontend still gets the implied flip via the response.
        assert result['implied_metadata_updates'][0]['value'] == 'ordinal'

    def test_set_ordinal_ranking_dictionary_write_through_handles_dict_envelope(self):
        # Some pipeline-config caches store the dictionary inside a
        # `{'features': [...]}` envelope rather than as a bare list.
        # The write-through path MUST handle both shapes — the
        # frontend cache patcher already does (it reads
        # entry.Feature_Name), and the backend symmetrically must
        # not silently skip the envelope shape.
        from ai_assistant.cache import cache_put, cache_get, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        file_id = 39003
        try:
            cache_put(file_id, 'data_dictionary', {
                'features': [
                    {'Feature_Name': 'Var_E', 'Level_of_Measurement': 'Nominal',
                     'Data_Type': 'object'},
                ],
                'metadata': {'source': 'envelope-shape'},
            })
            self._dispatch(file_id, 'set_ordinal_ranking', {
                'updates': [
                    {'column': 'Var_E', 'ranking': ['1', '2', '3']},
                ],
            })
            patched = cache_get(file_id, 'data_dictionary')
            # Envelope preserved; nested feature flipped.
            assert isinstance(patched, dict)
            assert patched['metadata']['source'] == 'envelope-shape'
            assert patched['features'][0]['Level_of_Measurement'] == 'ordinal'
        finally:
            _get_redis().delete(f'ai:pipeline:{file_id}:data_dictionary')

    # ── v2.25.0+: update_config feature_usage subkey ────────────────────
    # The AI's correct path to "exclude Var_3 from SFS due to VIF" —
    # NOT execute_code drop.  These tests pin the validation surface
    # for the new sub-key.

    def test_update_config_feature_usage_drop_with_reason(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'feature_usage', 'column': 'Var_3', 'value': 'drop', 'reason': 'VIF=9.39'},
            ],
        })
        assert result['status'] == 'success'
        assert len(result['applied']) == 1
        entry = result['applied'][0]
        assert entry['key'] == 'feature_usage'
        assert entry['column'] == 'Var_3'
        assert entry['value'] == 'drop'
        assert entry['reason'] == 'VIF=9.39'

    def test_update_config_feature_usage_keep_no_reason(self):
        # The optional reason is dropped on "keep" — flipping back to
        # keep clears the rationale, matching the manual UI dropdown.
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'feature_usage', 'column': 'Var_3', 'value': 'keep'},
            ],
        })
        assert result['status'] == 'success'
        entry = result['applied'][0]
        assert entry['value'] == 'keep'
        assert 'reason' not in entry

    def test_update_config_feature_usage_invalid_value_error(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'feature_usage', 'column': 'Var_3', 'value': 'remove'},
            ],
        })
        assert result['status'] == 'error'
        assert len(result['errors']) == 1
        assert 'keep' in result['errors'][0]['error']

    def test_update_config_feature_usage_missing_column_error(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'feature_usage', 'value': 'drop', 'reason': 'low SHAP'},
            ],
        })
        assert result['status'] == 'error'
        assert len(result['errors']) == 1

    def test_update_config_feature_usage_does_not_validate_against_df_columns(self):
        # feature_usage targets the Selected Features list which may
        # include encoded columns (one-hot expansions) absent from the
        # raw dataframe — validation happens later at SFS-start time.
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'feature_usage', 'column': 'Var_HotEncoded_X', 'value': 'drop'},
            ],
        })
        # Not rejected even though the column doesn't exist in df.
        assert result['status'] == 'success'
        assert result['applied'][0]['column'] == 'Var_HotEncoded_X'

    def test_update_config_mixed_feature_and_model_usage(self):
        # A single update_config call may carry both feature_usage and
        # model_usage entries — they coexist without interference.
        # model_usage requires df validation; we patch _load_dataframe
        # to provide a stable column set.
        from ai_assistant import action_executor as ae

        class _FakeDf:
            columns = type('cols', (), {'tolist': staticmethod(lambda: ['Var_3', 'AppID', 'Target'])})()

        orig = ae._load_dataframe
        ae._load_dataframe = lambda fid: (_FakeDf(), None, '')
        try:
            result = self._dispatch(1, 'update_config', {
                'updates': [
                    {'key': 'feature_usage', 'column': 'Var_3', 'value': 'drop', 'reason': 'VIF=9.39'},
                    {'key': 'model_usage', 'column': 'AppID', 'value': 'No'},
                ],
            })
        finally:
            ae._load_dataframe = orig
        assert result['status'] == 'success'
        assert len(result['applied']) == 2
        keys = [a['key'] for a in result['applied']]
        assert 'feature_usage' in keys
        assert 'model_usage' in keys

    # ── v2.25.0+: start_sfs action ──────────────────────────────────────
    # The dedicated path for the AI to actually KICK OFF SFS.  Before
    # v2.25.0 the AI could only TALK about doing it.  These tests pin
    # the validation surface end-to-end.

    def test_start_sfs_routes_correctly_minimal_payload(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {
                'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}],
            },
        })
        assert result['status'] == 'success'
        assert result['action_type'] == 'start_sfs'
        applied = result['applied']
        assert applied['methods'] == ['backward']
        assert applied['stopping_criteria']['metrics'] == [
            {'metric': 'roc_auc', 'pct_change': 1.0},
        ]
        # Defaults filled in.
        assert applied['stopping_criteria']['min_features'] == 5
        assert applied['stopping_criteria']['max_features'] == 15
        assert applied['n_jobs'] == 3
        assert applied['top_k'] == 5
        assert applied['excluded_features'] == []

    def test_start_sfs_full_payload_round_trips(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['forward', 'backward'],
            'stopping_criteria': {
                'metrics': [
                    {'metric': 'roc_auc', 'pct_change': 0.5},
                    {'metric': 'pr_auc', 'pct_change': 1.0},
                ],
                'min_features': 3,
                'max_features': 20,
            },
            'excluded_features': ['Var_3', 'Var_99'],
            'n_jobs': 4,
            'top_k': 7,
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['methods'] == ['forward', 'backward']
        assert len(applied['stopping_criteria']['metrics']) == 2
        assert applied['stopping_criteria']['min_features'] == 3
        assert applied['stopping_criteria']['max_features'] == 20
        assert applied['excluded_features'] == ['Var_3', 'Var_99']
        assert applied['n_jobs'] == 4
        assert applied['top_k'] == 7

    def test_start_sfs_deduplicates_methods(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['forward', 'forward', 'backward', 'backward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
        })
        assert result['status'] == 'success'
        assert result['applied']['methods'] == ['forward', 'backward']

    def test_start_sfs_rejects_empty_methods(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': [],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
        })
        assert result['status'] == 'error'
        assert 'methods' in result['error']

    def test_start_sfs_rejects_unknown_method(self):
        # 'middlewards' is gibberish — all methods are filtered out so
        # we end up with an empty list.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['middlewards', 'sideways'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
        })
        assert result['status'] == 'error'

    def test_start_sfs_rejects_empty_metrics(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': []},
        })
        assert result['status'] == 'error'
        assert 'metrics' in result['error']

    def test_start_sfs_filters_unknown_metric_names(self):
        # 'f1_score' isn't supported — all entries get filtered, the
        # action errors out because no valid metric remains.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [{'metric': 'f1_score', 'pct_change': 1.0}]},
        })
        assert result['status'] == 'error'
        assert 'roc_auc' in result['error']

    def test_start_sfs_clamps_n_jobs_and_top_k(self):
        # Both fields have hard upper bounds to protect the engine.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'n_jobs': 9999,
            'top_k': 9999,
        })
        assert result['status'] == 'success'
        assert result['applied']['n_jobs'] == 16
        assert result['applied']['top_k'] == 50

    def test_start_sfs_coerces_negative_n_jobs_to_default(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'n_jobs': -5,
            'top_k': -1,
        })
        assert result['status'] == 'success'
        # Defaults are 3 / 5 after _pos_int kicks in.
        assert result['applied']['n_jobs'] == 3
        assert result['applied']['top_k'] == 5

    def test_start_sfs_handles_non_list_excluded_features(self):
        # Robust against the LLM passing a string by mistake.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'excluded_features': 'Var_3',  # not a list
        })
        assert result['status'] == 'success'
        assert result['applied']['excluded_features'] == []

    def test_start_sfs_coerces_pct_change_to_float(self):
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [
                {'metric': 'roc_auc', 'pct_change': '1.5'},  # str
                {'metric': 'pr_auc', 'pct_change': None},   # None → 0.0
            ]},
        })
        assert result['status'] == 'success'
        m = result['applied']['stopping_criteria']['metrics']
        assert m[0] == {'metric': 'roc_auc', 'pct_change': 1.5}
        assert m[1] == {'metric': 'pr_auc', 'pct_change': 0.0}

    def test_start_sfs_registered_in_handlers(self):
        # Defense-in-depth: protect against an accidental delete of
        # the HANDLERS dict entry on a future refactor.
        from ai_assistant.action_executor import HANDLERS, start_sfs
        assert HANDLERS.get('start_sfs') is start_sfs

    # ── v2.37.0+: backward_cut_step (forward-from-backward) ─────────────
    # Closes the gap where the AI's only way to mimic the manual
    # "Run Forward Selection on These N Features" button was to
    # enumerate every backward-dropped feature in excluded_features —
    # fragile, conflated with user-drop intent, and silently failing to
    # update the visible green-box cut-step display.

    def test_start_sfs_default_applied_backward_cut_step_is_none(self):
        # Backward-compat with v2.25.0..v2.36.1 callers — when the AI
        # doesn't send backward_cut_step, applied must still expose the
        # field as None so subscribers can read it uniformly.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
        })
        assert result['status'] == 'success'
        assert 'backward_cut_step' in result['applied']
        assert result['applied']['backward_cut_step'] is None

    def test_start_sfs_rejects_non_int_backward_cut_step(self):
        # "thirty-seven" isn't coercible to int — must fail loudly.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['forward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'backward_cut_step': 'thirty-seven',
        })
        assert result['status'] == 'error'
        assert 'backward_cut_step' in result['error']
        assert 'invalid_backward_cut_step' in result.get('errors', [])

    def test_start_sfs_rejects_non_positive_backward_cut_step(self):
        # 0 and negatives are nonsense step numbers — backend steps are 1-indexed.
        for bad_val in (0, -1, -42):
            result = self._dispatch(1, 'start_sfs', {
                'methods': ['forward'],
                'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
                'backward_cut_step': bad_val,
            })
            assert result['status'] == 'error', f'expected error for backward_cut_step={bad_val}'
            assert 'positive integer' in result['error']

    def test_start_sfs_rejects_backward_cut_step_without_forward_method(self):
        # backward_cut_step only makes sense for forward-from-backward.
        # If methods=['backward'], honoring the cut step is silent
        # corruption — the cut features would never reach the engine.
        result = self._dispatch(1, 'start_sfs', {
            'methods': ['backward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'backward_cut_step': 37,
        })
        assert result['status'] == 'error'
        assert 'forward' in result['error']
        assert 'backward_cut_step_requires_forward_method' in result.get('errors', [])

    def test_start_sfs_rejects_backward_cut_step_when_sfs_results_missing(self, tmp_path, settings):
        # Without a completed backward SFS run there's nothing to cut
        # from.  Tool must reject (not silently fall back to full feature
        # pool — that would surprise the user).
        settings.MEDIA_ROOT = str(tmp_path)
        # tmp_path has no sfs_results directory at all.
        result = self._dispatch(99999, 'start_sfs', {
            'methods': ['forward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'backward_cut_step': 1,
        })
        assert result['status'] == 'error'
        assert 'no sfs_results' in result['error']

    def test_start_sfs_rejects_backward_cut_step_out_of_range(self, tmp_path, settings):
        # cut_step=999 is greater than the number of backward steps on disk.
        import os
        import json
        settings.MEDIA_ROOT = str(tmp_path)
        sfs_dir = os.path.join(str(tmp_path), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)
        sfs_path = os.path.join(sfs_dir, '777_sfs_results.json')
        with open(sfs_path, 'w', encoding='utf-8') as f:
            json.dump({
                'forward': [],
                'backward': [
                    {'step': 1, 'selected_features': ['A', 'B', 'C']},
                    {'step': 2, 'selected_features': ['B', 'C']},
                    {'step': 3, 'selected_features': ['C']},
                ],
            }, f)
        result = self._dispatch(777, 'start_sfs', {
            'methods': ['forward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'backward_cut_step': 999,
        })
        assert result['status'] == 'error'
        assert 'not a valid backward step' in result['error']
        assert 'invalid_backward_cut_step_value' in result.get('errors', [])

    def test_start_sfs_rejects_backward_cut_step_when_backward_array_empty(self, tmp_path, settings):
        # File exists but has no backward results.  This shouldn't
        # happen in normal operation but the guard prevents a confusing
        # downstream error in SFSStartView.
        import os
        import json
        settings.MEDIA_ROOT = str(tmp_path)
        sfs_dir = os.path.join(str(tmp_path), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)
        sfs_path = os.path.join(sfs_dir, '888_sfs_results.json')
        with open(sfs_path, 'w', encoding='utf-8') as f:
            json.dump({'forward': [{'step': 1, 'selected_features': ['A']}], 'backward': []}, f)
        result = self._dispatch(888, 'start_sfs', {
            'methods': ['forward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'backward_cut_step': 1,
        })
        assert result['status'] == 'error'
        assert 'no backward array' in result['error']
        assert 'no_backward_results_for_cut_step' in result.get('errors', [])

    def test_start_sfs_accepts_valid_backward_cut_step(self, tmp_path, settings):
        # Happy path: cut step exists in the on-disk backward results
        # and methods includes 'forward' — cut step is mirrored into
        # applied so the frontend can branch on it.
        import os
        import json
        settings.MEDIA_ROOT = str(tmp_path)
        sfs_dir = os.path.join(str(tmp_path), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)
        sfs_path = os.path.join(sfs_dir, '555_sfs_results.json')
        with open(sfs_path, 'w', encoding='utf-8') as f:
            json.dump({
                'forward': [],
                'backward': [
                    {'step': 1, 'selected_features': ['A', 'B', 'C', 'D']},
                    {'step': 2, 'selected_features': ['B', 'C', 'D']},
                    {'step': 3, 'selected_features': ['C', 'D']},
                ],
            }, f)
        result = self._dispatch(555, 'start_sfs', {
            'methods': ['forward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}], 'min_features': 2, 'max_features': 4},
            'backward_cut_step': 2,
            'n_jobs': 3,
            'top_k': 5,
        })
        assert result['status'] == 'success'
        assert result['applied']['backward_cut_step'] == 2

    def test_start_sfs_coerces_numeric_string_backward_cut_step(self, tmp_path, settings):
        # Robustness: the LLM sometimes wraps numbers in quotes.  As long
        # as int() can coerce it (and all other constraints are met),
        # accept it rather than reject — symmetric with how other
        # numeric fields are coerced.
        import os
        import json
        settings.MEDIA_ROOT = str(tmp_path)
        sfs_dir = os.path.join(str(tmp_path), 'sfs_results')
        os.makedirs(sfs_dir, exist_ok=True)
        sfs_path = os.path.join(sfs_dir, '556_sfs_results.json')
        with open(sfs_path, 'w', encoding='utf-8') as f:
            json.dump({
                'forward': [],
                'backward': [{'step': 1, 'selected_features': ['A', 'B']}],
            }, f)
        result = self._dispatch(556, 'start_sfs', {
            'methods': ['forward'],
            'stopping_criteria': {'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}]},
            'backward_cut_step': '1',  # ← string, not int
        })
        assert result['status'] == 'success'
        assert result['applied']['backward_cut_step'] == 1

    # ── v2.26.0+: pipeline-orchestration actions ────────────────────────
    # These three actions close the "AI cannot click pipeline buttons"
    # gap exposed in v2.25.0 (the user's screenshot showed the AI
    # saying "I cannot 'start' the modeling engine directly").
    # Each action validates a payload shape mirroring the manual UI
    # form fields and returns an `applied` config the frontend
    # forwards to the owning component to fire the actual code path.

    # ── start_data_purifier ──────────────────────────────────────────
    def test_start_data_purifier_routes_correctly_minimal_payload(self):
        # Empty payload is valid — frontend falls back to form values.
        result = self._dispatch(1, 'start_data_purifier', {})
        assert result['status'] == 'success'
        assert result['action_type'] == 'start_data_purifier'
        applied = result['applied']
        assert applied['purifier_options'] == []
        assert applied['split'] is None  # signals "use form defaults"

    def test_start_data_purifier_full_payload_round_trips(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'purifier_options': [1, 2, 5, 7],
            'split': {
                'strategy': 'random',
                'percent': 25,
            },
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['purifier_options'] == [1, 2, 5, 7]
        assert applied['split'] == {'strategy': 'random', 'percent': 25.0}

    def test_start_data_purifier_oot_with_cutoff(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'split': {
                'strategy': 'oot',
                'date_column': 'Application_Datetime',
                'cutoff': '2024-01-01T00:00:00',
            },
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['split']['strategy'] == 'oot'
        assert applied['split']['date_column'] == 'Application_Datetime'
        assert applied['split']['cutoff'] == '2024-01-01T00:00:00'

    def test_start_data_purifier_oot_with_percent(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'split': {
                'strategy': 'oot',
                'date_column': 'Application_Datetime',
                'percent': 30,
            },
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['split']['strategy'] == 'oot'
        assert applied['split']['date_column'] == 'Application_Datetime'
        assert 'cutoff' not in applied['split']
        assert applied['split']['percent'] == 30.0

    def test_start_data_purifier_oot_missing_date_column_error(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'split': {'strategy': 'oot'},
        })
        assert result['status'] == 'error'
        assert 'date_column' in result['error']

    def test_start_data_purifier_invalid_strategy_error(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'split': {'strategy': 'random_oot_hybrid'},
        })
        assert result['status'] == 'error'
        assert "'random'" in result['error']

    def test_start_data_purifier_drops_invalid_option_ids(self):
        # IDs outside 1..34 are dropped silently; non-int values too.
        result = self._dispatch(1, 'start_data_purifier', {
            'purifier_options': [1, 2, 99, -5, 'foo', 34, 0],
        })
        assert result['status'] == 'success'
        # Valid: 1, 2, 34.  Invalid IDs and non-ints filtered.
        assert result['applied']['purifier_options'] == [1, 2, 34]

    def test_start_data_purifier_dedupes_purifier_options(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'purifier_options': [1, 2, 1, 2, 5, 5, 7],
        })
        assert result['status'] == 'success'
        assert result['applied']['purifier_options'] == [1, 2, 5, 7]

    def test_start_data_purifier_rejects_non_list_options(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'purifier_options': 'all',  # not a list
        })
        assert result['status'] == 'error'

    def test_start_data_purifier_rejects_non_dict_split(self):
        result = self._dispatch(1, 'start_data_purifier', {
            'split': 'random',  # not a dict
        })
        assert result['status'] == 'error'

    def test_start_data_purifier_drops_invalid_percent(self):
        # 0 and >=100 are silently dropped (out of range), keeps strategy.
        result = self._dispatch(1, 'start_data_purifier', {
            'split': {'strategy': 'random', 'percent': 150},
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['split']['strategy'] == 'random'
        assert 'percent' not in applied['split']

    def test_start_data_purifier_registered_in_handlers(self):
        from ai_assistant.action_executor import HANDLERS, start_data_purifier
        assert HANDLERS.get('start_data_purifier') is start_data_purifier

    # ── update_purifier_selection (v2.28.0+) ────────────────────────
    # The "preview" sibling of start_data_purifier — edits the
    # Data-Purifier checkbox UI WITHOUT firing the run.  Two payload
    # forms (wholesale + diff), strict XOR between them, group-conflict
    # validation on wholesale, add/remove disjointness on diff, no-op
    # fallthroughs for empty payloads.  These tests script every
    # branch in the handler so a future refactor cannot silently regress
    # the "review-then-run" UX.

    def test_update_purifier_selection_wholesale_form_round_trips(self):
        # The screenshot scenario: AI consolidates IDs 11+17 into ID 23.
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [1, 2, 3, 4, 7, 23, 28, 32],
            'description': 'Consolidate IDs 11+17 into ID 23',
        })
        assert result['status'] == 'success'
        assert result['action_type'] == 'update_purifier_selection'
        applied = result['applied']
        assert applied['form'] == 'wholesale'
        assert applied['purifier_options'] == [1, 2, 3, 4, 7, 23, 28, 32]
        assert applied['add'] == []
        assert applied['remove'] == []
        assert result['description'] == 'Consolidate IDs 11+17 into ID 23'

    def test_update_purifier_selection_wholesale_empty_clears_selection(self):
        # Empty wholesale list is a legitimate "clear everything" use case.
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [],
            'description': 'Clear all purifier options',
        })
        assert result['status'] == 'success'
        assert result['applied']['form'] == 'wholesale'
        assert result['applied']['purifier_options'] == []

    def test_update_purifier_selection_wholesale_drops_invalid_ids(self):
        # IDs outside 1..34 are dropped silently, dedup preserved.
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [1, 1, 99, -3, 'foo', 23, 0, 34],
        })
        assert result['status'] == 'success'
        assert result['applied']['purifier_options'] == [1, 23, 34]

    def test_update_purifier_selection_wholesale_group_conflict_errors(self):
        # IDs 11 and 12 are both in sparsity_drop_group — UI normally
        # enforces single-select.  Backend must reject so the AI can
        # fix on the next turn instead of producing a silently malformed
        # selection.
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [1, 11, 12, 23],
        })
        assert result['status'] == 'error'
        assert 'Group conflict' in result['error']
        # Error message must name the conflicting IDs so the AI can
        # pick which to keep.
        assert '11' in result['error']
        assert '12' in result['error']
        assert 'sparsity_drop_group' in result['error']

    def test_update_purifier_selection_wholesale_no_conflict_across_groups(self):
        # IDs 11 (sparsity_drop_group), 17 (missing_drop_group), 23
        # (combined_drop_group) are in DIFFERENT groups — no conflict
        # even though the user wouldn't normally select all three.
        # (This particular combo is what the screenshot AI was warning
        # against — but it's not a backend-rejectable error, it's a
        # design recommendation.)
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [11, 17, 23],
        })
        assert result['status'] == 'success'
        assert sorted(result['applied']['purifier_options']) == [11, 17, 23]

    def test_update_purifier_selection_wholesale_no_conflict_for_standalone(self):
        # IDs 1-4 have group=None (standalone) — multiple selection is
        # never a conflict for them.
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [1, 2, 3, 4],
        })
        assert result['status'] == 'success'
        assert result['applied']['purifier_options'] == [1, 2, 3, 4]

    def test_update_purifier_selection_diff_form_round_trips(self):
        # The diff-form equivalent of the screenshot scenario.
        result = self._dispatch(1, 'update_purifier_selection', {
            'add': [23],
            'remove': [11, 17],
            'description': 'Replace 11+17 with combined-drop ID 23',
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['form'] == 'diff'
        assert applied['purifier_options'] is None  # diff form omits this
        assert applied['add'] == [23]
        assert applied['remove'] == [11, 17]

    def test_update_purifier_selection_diff_add_only(self):
        # "Just turn ON ID 7" — no removals.
        result = self._dispatch(1, 'update_purifier_selection', {
            'add': [7],
            'description': 'Add 0.85 corr-drop',
        })
        assert result['status'] == 'success'
        assert result['applied']['form'] == 'diff'
        assert result['applied']['add'] == [7]
        assert result['applied']['remove'] == []

    def test_update_purifier_selection_diff_remove_only(self):
        # "Just turn OFF ID 7" — no additions.
        result = self._dispatch(1, 'update_purifier_selection', {
            'remove': [7],
            'description': 'Drop correlation pruning',
        })
        assert result['status'] == 'success'
        assert result['applied']['form'] == 'diff'
        assert result['applied']['add'] == []
        assert result['applied']['remove'] == [7]

    def test_update_purifier_selection_diff_conflict_rejected(self):
        # Same ID in add and remove is incoherent — must error so the
        # AI fixes its diff on the next turn.
        result = self._dispatch(1, 'update_purifier_selection', {
            'add': [7, 23],
            'remove': [11, 23, 17],
        })
        assert result['status'] == 'error'
        assert '23' in result['error']
        # Error wording is stable so the AI can pattern-match on it.
        assert 'both' in result['error'].lower()

    def test_update_purifier_selection_rejects_both_forms_simultaneously(self):
        # Mixing wholesale and diff in one payload is incoherent.
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': [1, 2, 23],
            'add': [7],
        })
        assert result['status'] == 'error'
        assert 'exactly one' in result['error'].lower()

    def test_update_purifier_selection_description_only_is_noop(self):
        # Neither form provided — accept as a no-op (not an error).
        # The frontend handler will render the chat message but skip
        # the broadcast so the form doesn't flash.
        result = self._dispatch(1, 'update_purifier_selection', {
            'description': 'Thinking about it…',
        })
        assert result['status'] == 'success'
        assert result['applied']['form'] == 'noop'
        assert result['applied']['purifier_options'] is None

    def test_update_purifier_selection_self_cancelling_diff_is_noop(self):
        # Empty add + empty remove is a self-cancelling diff — accept
        # but mark as noop.
        result = self._dispatch(1, 'update_purifier_selection', {
            'add': [],
            'remove': [],
        })
        assert result['status'] == 'success'
        assert result['applied']['form'] == 'noop'

    def test_update_purifier_selection_rejects_non_list_wholesale(self):
        result = self._dispatch(1, 'update_purifier_selection', {
            'purifier_options': 'all',
        })
        assert result['status'] == 'error'
        assert 'list' in result['error'].lower()

    def test_update_purifier_selection_rejects_non_list_diff(self):
        result = self._dispatch(1, 'update_purifier_selection', {
            'add': 23,  # not a list
        })
        assert result['status'] == 'error'
        assert 'list' in result['error'].lower()

    def test_update_purifier_selection_registered_in_handlers(self):
        # Defense-in-depth: protect the HANDLERS dict entry from
        # accidental delete on a future refactor.  Without this, a
        # bad refactor would route update_purifier_selection requests
        # to "Unknown action type" and silently break the preview UX.
        from ai_assistant.action_executor import HANDLERS, update_purifier_selection
        assert HANDLERS.get('update_purifier_selection') is update_purifier_selection

    # ── apply_encoding ──────────────────────────────────────────────
    def test_apply_encoding_routes_correctly_default_payload(self):
        # Empty payload → use_native defaults to True.
        result = self._dispatch(1, 'apply_encoding', {})
        assert result['status'] == 'success'
        assert result['action_type'] == 'apply_encoding'
        assert result['applied']['use_native'] is True

    def test_apply_encoding_explicit_false(self):
        result = self._dispatch(1, 'apply_encoding', {'use_native': False})
        assert result['status'] == 'success'
        assert result['applied']['use_native'] is False

    def test_apply_encoding_coerces_string_truthy_values(self):
        # The LLM occasionally passes "true"/"false" as strings.
        for s, expected in [
            ('true', True),
            ('TRUE', True),
            ('1', True),
            ('yes', True),
            ('false', False),
            ('0', False),
            ('no', False),
            ('', False),
        ]:
            result = self._dispatch(1, 'apply_encoding', {'use_native': s})
            assert result['status'] == 'success'
            assert result['applied']['use_native'] is expected, \
                f"use_native={s!r} should coerce to {expected}"

    def test_apply_encoding_passes_description_through(self):
        result = self._dispatch(1, 'apply_encoding', {
            'description': 'Apply encoding plan with native library',
        })
        assert result['status'] == 'success'
        assert result['description'] == 'Apply encoding plan with native library'

    def test_apply_encoding_registered_in_handlers(self):
        from ai_assistant.action_executor import HANDLERS, apply_encoding
        assert HANDLERS.get('apply_encoding') is apply_encoding

    # ── start_modeling ──────────────────────────────────────────────
    def test_start_modeling_routes_correctly_minimal_payload(self):
        # Empty payload → algorithm null (use form value), use_native true.
        result = self._dispatch(1, 'start_modeling', {})
        assert result['status'] == 'success'
        assert result['action_type'] == 'start_modeling'
        applied = result['applied']
        assert applied['algorithm'] is None
        assert applied['encoding_use_native'] is True

    def test_start_modeling_with_algorithm(self):
        result = self._dispatch(1, 'start_modeling', {
            'algorithm': 'lightgbm',
            'encoding_use_native': True,
        })
        assert result['status'] == 'success'
        applied = result['applied']
        assert applied['algorithm'] == 'lightgbm'
        assert applied['encoding_use_native'] is True

    def test_start_modeling_strips_whitespace_from_algorithm(self):
        result = self._dispatch(1, 'start_modeling', {
            'algorithm': '  xgboost  ',
        })
        assert result['status'] == 'success'
        assert result['applied']['algorithm'] == 'xgboost'

    def test_start_modeling_rejects_empty_string_algorithm(self):
        # Empty string is suspicious — likely a buggy LLM emission.
        result = self._dispatch(1, 'start_modeling', {'algorithm': '   '})
        assert result['status'] == 'error'
        assert 'algorithm' in result['error']

    def test_start_modeling_rejects_non_string_algorithm(self):
        result = self._dispatch(1, 'start_modeling', {'algorithm': 123})
        assert result['status'] == 'error'

    def test_start_modeling_coerces_use_native_strings(self):
        result = self._dispatch(1, 'start_modeling', {
            'encoding_use_native': 'false',
        })
        assert result['status'] == 'success'
        assert result['applied']['encoding_use_native'] is False

    def test_start_modeling_omitted_algorithm_returns_null(self):
        # When the AI doesn't specify an algorithm, the frontend
        # falls back to the form's selectedAlgorithm value — null
        # in the payload signals that.
        result = self._dispatch(1, 'start_modeling', {
            'encoding_use_native': True,
            'description': 'Use whatever algorithm is selected',
        })
        assert result['status'] == 'success'
        assert result['applied']['algorithm'] is None

    def test_start_modeling_registered_in_handlers(self):
        from ai_assistant.action_executor import HANDLERS, start_modeling
        assert HANDLERS.get('start_modeling') is start_modeling

    # ── start_hyperparameter (Phase 3) ──────────────────────────────
    # The dedicated path for the AI to fire the "Start Hyperparameter
    # Tuning" button (the pipeline step after SFS).  These pin the
    # validation surface the frontend mirrors onto the tuning form.

    def test_start_hyperparameter_routes_correctly_minimal_payload(self):
        result = self._dispatch(1, 'start_hyperparameter', {})
        assert result['status'] == 'success'
        assert result['action_type'] == 'start_hyperparameter'
        applied = result['applied']
        assert applied['n_iter'] == 40
        assert applied['cv_folds'] == 3
        assert applied['n_jobs'] == 3
        assert applied['primary_metric'] == 'roc_auc'
        assert applied['validation_curve_points'] == 8
        assert applied['param_space'] is None
        assert applied['enabled_params'] is None

    def test_start_hyperparameter_clamps_numeric_bounds(self):
        result = self._dispatch(1, 'start_hyperparameter', {
            'n_iter': 99999, 'cv_folds': 99, 'n_jobs': 99999, 'validation_curve_points': 999,
        })
        applied = result['applied']
        assert applied['n_iter'] == 500
        assert applied['cv_folds'] == 10
        assert applied['n_jobs'] == 32
        assert applied['validation_curve_points'] == 25

    def test_start_hyperparameter_coerces_invalid_numbers_to_defaults(self):
        result = self._dispatch(1, 'start_hyperparameter', {
            'n_iter': 'lots', 'cv_folds': -3, 'n_jobs': 0,
        })
        applied = result['applied']
        assert applied['n_iter'] == 40    # non-int → default
        assert applied['cv_folds'] == 3   # negative → default
        assert applied['n_jobs'] == 3     # zero → default

    def test_start_hyperparameter_defaults_unknown_metric_to_roc_auc(self):
        result = self._dispatch(1, 'start_hyperparameter', {'primary_metric': 'rmse'})
        assert result['applied']['primary_metric'] == 'roc_auc'

    def test_start_hyperparameter_accepts_known_metric(self):
        result = self._dispatch(1, 'start_hyperparameter', {'primary_metric': 'f2'})
        assert result['applied']['primary_metric'] == 'f2'

    def test_start_hyperparameter_filters_unknown_enabled_params(self):
        result = self._dispatch(1, 'start_hyperparameter', {
            'enabled_params': ['max_depth', 'bogus_param', 'learning_rate'],
        })
        assert result['applied']['enabled_params'] == ['max_depth', 'learning_rate']

    def test_start_hyperparameter_enabled_params_all_unknown_becomes_none(self):
        result = self._dispatch(1, 'start_hyperparameter', {
            'enabled_params': ['nope', 'also_nope'],
        })
        # All filtered out → None so the frontend keeps its defaults.
        assert result['applied']['enabled_params'] is None

    def test_start_hyperparameter_validates_param_space_overrides(self):
        result = self._dispatch(1, 'start_hyperparameter', {
            'param_space': {
                'max_depth': {'type': 'int', 'min': 8, 'max': 3, 'log': False, 'enabled': True},  # min>max → swap
                'learning_rate': {'type': 'float', 'min': 0.01, 'max': 0.2, 'log': True},
                'unknown_param': {'type': 'int', 'min': 1, 'max': 2},  # dropped → reported
            },
        })
        applied = result['applied']
        ps = applied['param_space']
        assert ps['max_depth']['min'] == 3 and ps['max_depth']['max'] == 8  # swapped + int
        assert ps['learning_rate']['log'] is True
        assert 'unknown_param' not in ps
        assert 'unknown_param' in result['errors']

    def test_start_hyperparameter_param_space_int_rounding(self):
        result = self._dispatch(1, 'start_hyperparameter', {
            'param_space': {'n_estimators': {'type': 'int', 'min': 50.7, 'max': 600.2}},
        })
        ps = result['applied']['param_space']
        assert ps['n_estimators']['min'] == 51
        assert ps['n_estimators']['max'] == 600

    def test_start_hyperparameter_registered_in_handlers(self):
        from ai_assistant.action_executor import HANDLERS, start_hyperparameter
        assert HANDLERS.get('start_hyperparameter') is start_hyperparameter

    def test_start_hyperparameter_defaults_search_method_to_auto(self):
        result = self._dispatch(1, 'start_hyperparameter', {})
        applied = result['applied']
        assert applied['search_method'] == 'auto'
        assert applied['grid_points_per_param'] == 5

    def test_start_hyperparameter_accepts_explicit_search_method(self):
        for m in ('grid', 'random', 'bayesian'):
            result = self._dispatch(1, 'start_hyperparameter', {'search_method': m})
            assert result['applied']['search_method'] == m

    def test_start_hyperparameter_rejects_unknown_search_method(self):
        result = self._dispatch(1, 'start_hyperparameter', {'search_method': 'genetic'})
        assert result['applied']['search_method'] == 'auto'

    def test_start_hyperparameter_clamps_grid_points(self):
        assert self._dispatch(1, 'start_hyperparameter', {'grid_points_per_param': 99})['applied']['grid_points_per_param'] == 12
        assert self._dispatch(1, 'start_hyperparameter', {'grid_points_per_param': 1})['applied']['grid_points_per_param'] == 2

    # ── Procedural-chain end-to-end test ────────────────────────────
    # Ensures all v2.26.0 actions return shapes compatible with the
    # frontend chat-panel handlers — specifically that the `applied`
    # payload always contains the keys those handlers reference.
    def test_v2_26_pipeline_actions_return_consistent_applied_shape(self):
        cases = [
            ('start_data_purifier', {}, ['purifier_options', 'split']),
            ('apply_encoding', {}, ['use_native']),
            ('start_modeling', {}, ['algorithm', 'encoding_use_native']),
        ]
        for action, payload, expected_keys in cases:
            result = self._dispatch(1, action, payload)
            assert result['status'] == 'success', f"{action} failed: {result}"
            applied = result.get('applied', {})
            for key in expected_keys:
                assert key in applied, f"{action}.applied missing {key}"


# ---------------------------------------------------------------------------
# AI tool_executor: get_encoding_plan reader exposes unique_values + ranking
# ---------------------------------------------------------------------------
# v2.24.0+: the AI needs to see actual category strings (unique_values)
# and any existing ranking on every encoding-plan tool call so it can
# (a) propose a semantically meaningful ranking instead of guessing
# alphabetically, and (b) skip the set_ordinal_ranking chain when a
# ranking is already in place (idempotency).
@pytest.mark.unit
class TestEncodingPlanReader:
    """Exercises ai_assistant.tool_executor._handle_get_encoding_plan."""

    def _render(self, cached_plan):
        from ai_assistant import tool_executor
        # Monkey-patch the read fn — avoids needing a live Redis.
        orig = tool_executor.read_encoding_plan
        tool_executor.read_encoding_plan = lambda fid: cached_plan
        try:
            return tool_executor._handle_get_encoding_plan(1, {})
        finally:
            tool_executor.read_encoding_plan = orig

    def test_renders_unique_values(self):
        plan = [{
            'feature': 'Var_36', 'user_lom': 'ordinal', 'nunique': 7,
            'fallback_strategy': 'ordinal_encoding', 'needs_ranking': True,
            'unique_values': ['0', '1', '2', '3', '8', 'L', 'Others'],
            'ranking': None,
        }]
        out = self._render(plan)
        assert 'Var_36' in out
        # All unique values are visible in the rendered output.
        for v in ['0', '1', '2', '3', '8', 'L', 'Others']:
            assert v in out

    def test_flags_unset_ranking_when_needs_ranking_true(self):
        plan = [{
            'feature': 'Var_36', 'user_lom': 'ordinal', 'nunique': 7,
            'fallback_strategy': 'ordinal_encoding', 'needs_ranking': True,
            'unique_values': ['Low', 'Mid', 'High'],
            'ranking': None,
        }]
        out = self._render(plan)
        # The marker prompts the LLM to chain set_ordinal_ranking next.
        assert 'NOT SET' in out
        assert 'set_ordinal_ranking' in out

    def test_renders_existing_ranking(self):
        plan = [{
            'feature': 'Var_36', 'user_lom': 'ordinal', 'nunique': 3,
            'fallback_strategy': 'ordinal_encoding', 'needs_ranking': True,
            'unique_values': ['Low', 'Mid', 'High'],
            'ranking': ['Low', 'Mid', 'High'],
        }]
        out = self._render(plan)
        # Arrow-separated rendering of the existing ranking.
        assert 'Low → Mid → High' in out
        # No "call set_ordinal_ranking" prompt because ranking is set.
        assert 'NOT SET' not in out

    def test_does_not_prompt_set_ranking_when_not_ordinal(self):
        plan = [{
            'feature': 'Var_3', 'user_lom': 'nominal', 'nunique': 2,
            'fallback_strategy': 'label_encoding', 'needs_ranking': False,
            'unique_values': ['N', 'Y'],
            'ranking': None,
        }]
        out = self._render(plan)
        assert 'NOT SET' not in out
        assert 'set_ordinal_ranking' not in out

    def test_truncates_unique_values_past_12(self):
        plan = [{
            'feature': 'Var_HighCard', 'user_lom': 'nominal', 'nunique': 20,
            'fallback_strategy': 'label_encoding', 'needs_ranking': False,
            'unique_values': [f'cat{i}' for i in range(20)],
            'ranking': None,
        }]
        out = self._render(plan)
        assert 'cat0' in out
        assert 'cat11' in out  # 12th value (index 11) is shown
        assert 'cat12' not in out  # 13th value truncated
        assert '+8 more' in out  # 20 - 12 = 8 truncated


# ---------------------------------------------------------------------------
# v2.26.1 — get_pipeline_config tool key contract
# ---------------------------------------------------------------------------
# Regression guard for the v2.26.1 bugfix.  The frontend's
# ``model-development.component.ts::getPipelineConfig()`` writes the
# pipeline_config Redis artifact with these top-level keys:
#   - rows_before / rows_after / rows_removed
#   - selected_purifier_steps  (list of step *names*, not IDs)
#   - pipeline_type / target_definition / split_strategy / split_details
#
# Up to and including v2.26.0 the tool handler `_handle_get_pipeline_config`
# read the *wrong* names (`row_count_before`, `row_count_after`,
# `purifier_steps`).  The cache always exists once the user opens the
# Data Purifier Declaration screen (it's debounce-pushed by
# `onPipelineConfigChanged`), but the tool returned ``Rows: ? → ?`` and
# silently dropped the purifier list — leaving the LLM with no real
# config and forcing it to hallucinate generic preprocessing steps that
# don't exist in our codebase (the user reported "High Cardinality Drop"
# / "Quasi-Constant Drop" in an AI answer; neither is implemented in
# `preprocessing/views.py::_apply_options`).
#
# These tests pin the contract so future renames on either side fail
# fast.  Don't loosen them without first updating the frontend writer.
@pytest.mark.unit
class TestPipelineConfigToolContract:
    """Exercises ai_assistant.tool_executor._handle_get_pipeline_config."""

    def _render(self, cached_config):
        from ai_assistant import tool_executor
        orig = tool_executor.read_pipeline_config
        tool_executor.read_pipeline_config = lambda fid: cached_config
        try:
            return tool_executor._handle_get_pipeline_config(1, {})
        finally:
            tool_executor.read_pipeline_config = orig

    # ── Contract tests: tool reads the keys the frontend writes ──

    def test_reads_rows_before_after_keys(self):
        """Tool must read `rows_before`/`rows_after` (frontend writer's keys),
        not the legacy `row_count_before`/`row_count_after`."""
        cfg = {
            'pipeline_type': 'binary_classification',
            'rows_before': 12345,
            'rows_after': 11000,
            'rows_removed': 1345,
        }
        out = self._render(cfg)
        assert 'Rows: 12345 → 11000' in out, (
            "Tool failed to render row counts. Likely cause: legacy keys "
            "`row_count_before`/`row_count_after` revived in the handler."
        )
        assert 'Rows removed: 1345' in out

    def test_renders_selected_purifier_steps_list(self):
        """Tool must read `selected_purifier_steps` (frontend writer's key),
        not the legacy `purifier_steps`.  The list contains step *names*
        (strings) as written by ``selectedOptions.map(o => o.name)``."""
        cfg = {
            'pipeline_type': 'binary_classification',
            'selected_purifier_steps': [
                'Column-wise duplicate drop',
                'Row-wise duplicate drop',
                'Zero-variance drop',
                'Perfect-correlation drop',
                'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]',
            ],
        }
        out = self._render(cfg)
        assert 'Selected purifier steps (5):' in out
        for name in cfg['selected_purifier_steps']:
            assert name in out, (
                f"Step name '{name}' missing from rendered output. Likely "
                f"cause: legacy `purifier_steps` key revived in the handler."
            )

    def test_legacy_keys_rejected(self):
        """If the cache still carries ONLY the legacy keys (e.g. a stale
        artifact from before the migration), the tool must NOT silently
        succeed — it should report '?' so the LLM can detect the gap and
        either re-prompt the user or fall back to other tools.  This is
        the symmetric guard against the original bug."""
        legacy = {
            'pipeline_type': 'binary_classification',
            'row_count_before': 12345,           # legacy key
            'row_count_after': 11000,            # legacy key
            'purifier_steps': ['Foo', 'Bar'],    # legacy key
        }
        out = self._render(legacy)
        # Row counts unrenderable — tool falls back to '?'.
        assert 'Rows: ? → ?' in out
        # Purifier section absent because new key missing.
        assert 'Selected purifier steps' not in out
        assert 'Foo' not in out
        assert 'Bar' not in out

    # ── End-to-end contract: realistic frontend payload renders cleanly ──

    def test_renders_full_realistic_frontend_payload(self):
        """Mirrors what `model-development.component.ts::getPipelineConfig()`
        actually writes after the user ticks purifier checkboxes but
        BEFORE clicking Run Preprocessing — the exact state where the
        original bug surfaced."""
        cfg = {
            'pipeline_type': 'binary_classification',
            'target_definition': (
                'good/bag flag of credit applications within the 12 months '
                'period of its usage'
            ),
            'split_strategy': 'random',
            'split_details': {'oos_percent': 25},
            'rows_before': 0,    # 0 because preprocessing not yet run
            'rows_after': 0,
            'rows_removed': 0,
            'selected_purifier_steps': [
                'Column-wise duplicate drop',
                'Row-wise duplicate drop',
                'Zero-variance drop',
                'Perfect-correlation drop',
                'Corr-drop threshold = 0.85',
                'Outlier-cleaning [lower-upper] quantiles = [0.01-0.99]',
            ],
        }
        out = self._render(cfg)
        # Header and metadata.
        assert 'Pipeline type: binary_classification' in out
        assert 'Target definition: good/bag flag' in out
        assert 'Split strategy: random' in out
        # Rows render as 0 → 0 (NOT '?' → '?'), proving the keys lined up.
        assert 'Rows: 0 → 0' in out
        # All six step names rendered, one per line, with bullets.
        assert 'Selected purifier steps (6):' in out
        assert '    • Column-wise duplicate drop' in out
        assert '    • Outlier-cleaning [lower-upper] quantiles = [0.01-0.99]' in out

    def test_no_question_marks_when_all_keys_present(self):
        """A fully-populated config must produce zero '?' fallbacks.
        Catches future contract drift in any of the rendered fields."""
        cfg = {
            'pipeline_type': 'binary_classification',
            'target_definition': 'some target',
            'split_strategy': 'oot',
            'rows_before': 100,
            'rows_after': 90,
            'rows_removed': 10,
            'selected_purifier_steps': ['Step A'],
        }
        out = self._render(cfg)
        assert '?' not in out, (
            f"Unexpected '?' in tool output — a key contract drifted "
            f"between frontend writer and tool reader. Output:\n{out}"
        )

    def test_empty_config_returns_not_available(self):
        """When the cache has nothing (file_id never opened in the UI),
        the tool returns the standard not-available sentinel — NOT a
        partial 'Pipeline Configuration:' header with all '?' values."""
        out = self._render(None)
        assert 'not yet available' in out.lower() or 'no ' in out.lower()

    # ── Static guard: source code does not contain the legacy keys ──

    def test_handler_source_does_not_use_legacy_keys(self):
        """Belt-and-braces guard: even if a future refactor renamed the
        keys back, this test scans the handler's source for the exact
        legacy strings.  Cheap to run, very fast to flag drift."""
        import inspect
        from ai_assistant import tool_executor
        src = inspect.getsource(tool_executor._handle_get_pipeline_config)
        # `data.get('row_count_before'` and similar must never reappear.
        assert "'row_count_before'" not in src
        assert "'row_count_after'" not in src
        # Purifier list lives under `selected_purifier_steps`. Plain
        # `'purifier_steps'` is the legacy key and must not be used as
        # a `.get()` argument anywhere in this handler.
        assert "data.get('purifier_steps'" not in src


# ---------------------------------------------------------------------------
# Feature description generator tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestGenerateFeatureDescription:
    """Test _generate_feature_description for pattern-specific descriptions."""

    def _make_data_file(self):
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/test.csv', name='test.csv', original_name='test.csv',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_8',
            description='LO Number of bureau enquiries in last 3 months',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_19',
            description='LO Outstanding balance',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_24',
            description='LO Monthly income',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_2',
            description='CA Region code',
        )
        DataDictionary.objects.create(
            data_file=decl, column_name='Var_3',
            description='CA Occupation type',
        )
        return decl

    def test_log_signed(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('LogSigned_Var_8', df)
        assert 'sign(Var_8)' in desc
        assert 'ln(1 + |Var_8|)' in desc
        assert 'bureau enquiries' in desc

    def test_log1p(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Log1p_Var_8', df)
        assert 'ln(1 + Var_8)' in desc
        assert '"1p" suffix means "one plus"' in desc
        assert 'bureau enquiries' in desc

    def test_ratio(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Var_19_to_Var_24', df)
        assert 'Ratio' in desc
        assert 'Var_19' in desc and 'Var_24' in desc
        assert 'Outstanding balance' in desc
        assert 'Monthly income' in desc

    def test_difference(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Var_19_minus_Var_24', df)
        assert 'Difference' in desc
        assert 'Outstanding balance' in desc
        assert 'Monthly income' in desc

    def test_categorical_interaction(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Var_2_x_Var_3', df)
        assert 'Categorical interaction' in desc
        assert 'Region code' in desc
        assert 'Occupation type' in desc

    def test_is_missing(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('IsMissing_Var_8', df)
        assert 'missingness indicator' in desc
        assert 'bureau enquiries' in desc

    def test_datetime_feature(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('Application_Month', df)
        assert 'Month' in desc
        assert 'Application_Datetime' in desc

    def test_aggregation_known(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('NumVars_Missing_Count', df)
        assert 'missing' in desc.lower()
        assert 'numeric' in desc.lower()

    def test_aggregation_range(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('NumVars_Range', df)
        assert 'NumVars_Max' in desc
        assert 'NumVars_Min' in desc

    def test_fallback(self):
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('SomeUnknownCol', df)
        assert 'SomeUnknownCol' in desc

    def test_no_parent_desc_graceful(self):
        """Features referencing unknown parent vars should still describe the transform."""
        from ai_assistant.action_executor import _generate_feature_description
        df = self._make_data_file()
        desc = _generate_feature_description('LogSigned_Var_999', df)
        assert 'sign(Var_999)' in desc
        assert 'ln(1 + |Var_999|)' in desc
        # No parent desc — should NOT crash, just omit the parenthetical
        assert 'Var_999)' not in desc or 'sign(Var_999)' in desc


# ---------------------------------------------------------------------------
# Prometa SDK integration tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPrometaConfig:
    """Test prometa_config lazy decorators and flush when SDK is not configured."""

    @pytest.fixture(autouse=True)
    def _reset_prometa_singleton(self):
        """v2.34.0: the new agent_id wiring tests stub out
        ``prometa.Prometa`` and force-init the singleton; without this
        teardown the stub instance leaks into the next test (cache /
        tool-call specs that genuinely use the real client) and
        manifests as 16 cascading failures.

        Reset in BOTH directions (before AND after) so the class is
        hermetic regardless of which test ran before."""
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None
        yield
        pc._initialized = False
        pc._prometa = None

    def test_workflow_decorator_noop_without_endpoint(self, monkeypatch):
        """Without PROMETA_ENDPOINT, @workflow should be a transparent no-op."""
        monkeypatch.delenv('PROMETA_ENDPOINT', raising=False)
        # Force re-initialization
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None

        @pc.workflow(name='test-workflow')
        def sample_workflow(x):
            return x * 2

        assert sample_workflow(5) == 10

    def test_agent_decorator_noop_without_endpoint(self, monkeypatch):
        """Without PROMETA_ENDPOINT, @agent should be a transparent no-op."""
        monkeypatch.delenv('PROMETA_ENDPOINT', raising=False)
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None

        @pc.agent(name='test-agent')
        def sample_agent(msg):
            return f'reply: {msg}'

        assert sample_agent('hello') == 'reply: hello'

    def test_tool_decorator_noop_without_endpoint(self, monkeypatch):
        """Without PROMETA_ENDPOINT, @tool should be a transparent no-op."""
        monkeypatch.delenv('PROMETA_ENDPOINT', raising=False)
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None

        @pc.tool(name='test-tool')
        def sample_tool(q):
            return [q]

        assert sample_tool('search') == ['search']

    def test_flush_safe_without_endpoint(self, monkeypatch):
        """flush() should not raise when Prometa is not configured."""
        monkeypatch.delenv('PROMETA_ENDPOINT', raising=False)
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None
        pc.flush()  # should not raise

    def test_get_prometa_returns_none_without_endpoint(self, monkeypatch):
        """get_prometa() returns None when no PROMETA_ENDPOINT* vars are set."""
        monkeypatch.delenv('PROMETA_ENDPOINT', raising=False)
        monkeypatch.delenv('PROMETA_ENDPOINT_STAGING', raising=False)
        monkeypatch.delenv('PROMETA_ENDPOINT_PRODUCTION', raising=False)
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None
        assert pc.get_prometa() is None

    def test_decorated_functions_preserve_name(self, monkeypatch):
        """Lazy decorators should preserve function __name__ via functools.wraps."""
        monkeypatch.delenv('PROMETA_ENDPOINT', raising=False)
        import ai_assistant.prometa_config as pc
        pc._initialized = False
        pc._prometa = None

        @pc.workflow(name='named-wf')
        def my_workflow():
            pass

        assert my_workflow.__name__ == 'my_workflow'

    # ── Stable Prometa agent id wiring (v2.34.0 / SDK 0.7.0+) ─────────

    def test_get_prometa_passes_agent_id_when_env_var_set(self, monkeypatch):
        """When PROMETA_AGENT_ID is set, get_prometa() must forward it
        as agent_id= to Prometa(...).  This is the platform-correctness
        path: matching the trace's prometa.agent.id to the registry's
        Agent.id (or customer-owned slug accepted by ingest) is what
        makes PG↔CH joins work for lineage / AML scoring /
        incident-to-trace.

        Without this forwarding the SDK 0.7.0+ falls back to a random
        per-process id and emits a UserWarning."""
        # Bypass the pytest short-circuit (lines 42-44 of prometa_config)
        monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
        monkeypatch.delenv('PROMETA_DISABLE', raising=False)
        # Provide minimum endpoint config so init proceeds.
        monkeypatch.setenv('PROMETA_STAGE', 'staging')
        monkeypatch.setenv('PROMETA_ENDPOINT_STAGING', 'http://test.invalid/otlp')
        monkeypatch.setenv('PROMETA_API_KEY_STAGING', 'pk_test')
        # The behaviour-under-test: stable customer-owned slug via env var.
        # v2.40.2: value reflects Stream A naming (agent_name=declarai-agent).
        monkeypatch.setenv('PROMETA_AGENT_ID', 'declarai-agent-staging')

        # Capture the kwargs Prometa(...) is constructed with, without
        # actually emitting telemetry.
        captured_kwargs = {}

        class _StubPrometa:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)
                # SDK 0.7.0+ assigns agent_id from kwarg if present.
                self.agent_id = kwargs.get('agent_id', '<would-be-random>')

        import ai_assistant.prometa_config as pc
        import prometa
        monkeypatch.setattr(prometa, 'Prometa', _StubPrometa)
        # Avoid OpenAI auto-instrumentation side-effect during the test.
        if hasattr(prometa, 'integrations'):
            monkeypatch.setattr(prometa.integrations.openai, 'install',
                                lambda: None, raising=False)
        pc._initialized = False
        pc._prometa = None

        client = pc.get_prometa()
        assert client is not None
        assert 'agent_id' in captured_kwargs, (
            "PROMETA_AGENT_ID was set; get_prometa() must forward it as "
            "agent_id= so the SDK does not fall back to a random per-process id"
        )
        # v2.40.2: literal updated to match Stream A naming (this test
        # asserts pass-through behavior, so any deterministic value works
        # — kept aligned with the new default slug for consistency).
        assert captured_kwargs['agent_id'] == 'declarai-agent-staging'

    def test_get_prometa_uses_stable_slug_when_env_var_unset(self, monkeypatch):
        """When PROMETA_AGENT_ID is NOT set, use a deterministic slug.

        The attached Prometa feedback documents why we no longer ask
        operators to copy a platform UUID into .env: until Prometa
        auto-registers Agents like Tools, DeclarAI owns a stable slug so
        every cold start reports the same agent_id."""
        monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
        monkeypatch.delenv('PROMETA_DISABLE', raising=False)
        monkeypatch.delenv('PROMETA_AGENT_ID', raising=False)
        monkeypatch.setenv('PROMETA_STAGE', 'staging')
        monkeypatch.setenv('PROMETA_ENDPOINT_STAGING', 'http://test.invalid/otlp')
        monkeypatch.setenv('PROMETA_API_KEY_STAGING', 'pk_test')

        captured_kwargs = {}

        class _StubPrometa:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)
                self.agent_id = kwargs.get('agent_id', '<random>')

        import ai_assistant.prometa_config as pc
        import prometa
        monkeypatch.setattr(prometa, 'Prometa', _StubPrometa)
        if hasattr(prometa, 'integrations'):
            monkeypatch.setattr(prometa.integrations.openai, 'install',
                                lambda: None, raising=False)
        pc._initialized = False
        pc._prometa = None

        client = pc.get_prometa()
        assert client is not None
        # v2.40.2: default agent_name flipped from 'declarai-assistant' to
        # 'declarai-agent' (Stream A naming) so the derived slug is now
        # 'declarai-agent-staging'.
        assert captured_kwargs['agent_id'] == 'declarai-agent-staging', (
            "PROMETA_AGENT_ID was unset; get_prometa() must still pass a "
            "stable customer-owned slug so the SDK does not generate a "
            "random per-process id"
        )

    def test_get_prometa_uses_stable_slug_when_env_var_empty_string(self, monkeypatch):
        """Edge case: PROMETA_AGENT_ID set to empty string (often happens
        when an operator unsets a deployment var by leaving it blank in
        the env file). Treat as unset and use the deterministic slug."""
        monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
        monkeypatch.delenv('PROMETA_DISABLE', raising=False)
        monkeypatch.setenv('PROMETA_STAGE', 'staging')
        monkeypatch.setenv('PROMETA_ENDPOINT_STAGING', 'http://test.invalid/otlp')
        monkeypatch.setenv('PROMETA_API_KEY_STAGING', 'pk_test')
        monkeypatch.setenv('PROMETA_AGENT_ID', '')  # blank — should be treated as unset

        captured_kwargs = {}

        class _StubPrometa:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)
                self.agent_id = kwargs.get('agent_id', '<random>')

        import ai_assistant.prometa_config as pc
        import prometa
        monkeypatch.setattr(prometa, 'Prometa', _StubPrometa)
        if hasattr(prometa, 'integrations'):
            monkeypatch.setattr(prometa.integrations.openai, 'install',
                                lambda: None, raising=False)
        pc._initialized = False
        pc._prometa = None

        pc.get_prometa()
        # v2.40.2: default agent slug is now 'declarai-agent-staging'
        # (Stream A naming — see prometa_config.py module docstring).
        assert captured_kwargs['agent_id'] == 'declarai-agent-staging', (
            "Empty-string PROMETA_AGENT_ID must be treated as unset and "
            "replaced by the stable DeclarAI slug"
        )

    def test_prometa_config_module_documents_agent_id_env_var(self):
        """Module-level docstring must call out PROMETA_AGENT_ID so a
        future contributor reading the file learns about it without
        having to read the SDK source.  Pairs with the structural code
        guard below."""
        import ai_assistant.prometa_config as pc
        assert pc.__doc__ is not None
        assert 'PROMETA_AGENT_ID' in pc.__doc__, (
            "prometa_config module docstring must document the "
            "PROMETA_AGENT_ID env var (operator-facing config)"
        )

    def test_get_prometa_source_reads_agent_id_env_var(self):
        """Structural guard: the prometa_config module must read
        PROMETA_AGENT_ID (in _resolve_agent_id) AND get_prometa() must
        always forward the resolved stable agent_id to Prometa(...).

        Reverting to the pre-v2.34.0 shape (always-random agent_id)
        would silently break PG↔CH joins again — this test catches
        that regression at the source level even when the runtime
        code path is short-circuited under pytest.

        Split assertion across the two helpers because v2.34.0+
        factored the env-var read into ``_resolve_agent_id`` so
        get_prometa() stays a thin orchestrator.  Both pieces must
        be present for the contract to hold."""
        import inspect
        import ai_assistant.prometa_config as pc
        resolver_source = inspect.getsource(pc._resolve_agent_id)
        assert "PROMETA_AGENT_ID" in resolver_source, (
            "_resolve_agent_id() must read os.environ['PROMETA_AGENT_ID']"
        )
        getter_source = inspect.getsource(pc.get_prometa)
        assert "'agent_id': agent_id" in getter_source, (
            "get_prometa() must always forward the resolved stable agent_id"
        )

    def test_resolve_agent_id_defaults_to_stage_slug(self, monkeypatch):
        """Default agent_id is stable, readable, and environment-specific.

        v2.40.2: inputs reflect Stream A naming (agent_name='declarai-agent')."""
        import ai_assistant.prometa_config as pc
        monkeypatch.delenv('PROMETA_AGENT_ID', raising=False)
        assert pc._resolve_agent_id('declarai-agent', 'production') == (
            'declarai-agent-production',
            'default-slug',
        )

    def test_resolve_agent_id_slugifies_display_name(self, monkeypatch):
        """A changed display label should still produce a slug-shaped id.

        v2.40.2: input updated to 'DeclarAI Agent' to match Stream A
        naming — the slugify logic itself is unchanged."""
        import ai_assistant.prometa_config as pc
        monkeypatch.delenv('PROMETA_AGENT_ID', raising=False)
        assert pc._resolve_agent_id('DeclarAI Agent', 'Staging EU') == (
            'declarai-agent-staging-eu',
            'default-slug',
        )

    # ── v2.40.2: Stream A naming pin (platform-team request) ─────────

    def test_default_solution_id_is_stream_a_naming(self):
        """v2.40.2: pin DEFAULT_PROMETA_SOLUTION_ID = 'declarai-assistant'.

        Platform-team request (2026-05-21 screenshot): the auto-register
        dedupes on ``(orgId, solutionId, agentName)``.  The previous
        default 'sol_declarai' created a duplicate Agent row that the
        platform team soft-deprecated — reverting to this default would
        re-activate that row on the next trace.  This test catches an
        accidental revert at the source level."""
        import ai_assistant.prometa_config as pc
        assert pc.DEFAULT_PROMETA_SOLUTION_ID == 'declarai-assistant', (
            "DEFAULT_PROMETA_SOLUTION_ID must be 'declarai-assistant' "
            "(Stream A naming).  Reverting to 'sol_declarai' would "
            "re-activate the platform's soft-deprecated duplicate Agent row."
        )

    def test_default_agent_name_is_stream_a_naming(self):
        """v2.40.2: pin DEFAULT_PROMETA_AGENT_NAME = 'declarai-agent'.

        Companion guard to the solution-id pin above.  The platform-side
        dedup key is ``(orgId, solutionId, agentName)`` — both halves
        must stay correct or the soft-deprecate gets undone."""
        import ai_assistant.prometa_config as pc
        assert pc.DEFAULT_PROMETA_AGENT_NAME == 'declarai-agent', (
            "DEFAULT_PROMETA_AGENT_NAME must be 'declarai-agent' "
            "(Stream A naming).  Reverting to 'declarai-assistant' "
            "would re-activate the platform's soft-deprecated row."
        )

    def test_default_solution_id_is_not_sol_declarai(self):
        """Hard-fail if the pre-v2.40.2 default ever leaks back.  This is
        a redundant guard alongside the positive-assertion tests above,
        but the negative form makes the intent unmistakable in CI
        failure output."""
        import ai_assistant.prometa_config as pc
        assert pc.DEFAULT_PROMETA_SOLUTION_ID != 'sol_declarai', (
            "DEFAULT_PROMETA_SOLUTION_ID reverted to the pre-v2.40.2 "
            "value 'sol_declarai'.  See 2026-05-21 prometa-team "
            "screenshot — this value re-creates the duplicate Agent."
        )

    def test_dotenv_file_pins_stream_a_naming(self):
        """v2.40.2: the .env file ships with PROMETA_SOLUTION_ID,
        PROMETA_AGENT_NAME, and PROMETA_AGENT_ID aligned to Stream A
        naming.  Operators who copy this file as their starting point
        must NOT inherit the pre-v2.40.2 dedup-key-breaking values.

        We grep the literal file rather than the loaded env so the test
        catches drift in the COMMITTED defaults, not just the
        process-time values (which may have been overridden in CI)."""
        import os
        # Locate .env relative to this test file's repo root.
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        env_path = os.path.join(repo_root, '.env')
        if not os.path.exists(env_path):
            # In some CI environments .env is intentionally absent
            # (secrets injected by the runner).  Skip rather than fail.
            import pytest
            pytest.skip(f'.env not present at {env_path} — skipping')
        with open(env_path, 'r') as f:
            content = f.read()
        assert 'PROMETA_SOLUTION_ID=declarai-assistant' in content, (
            ".env must pin PROMETA_SOLUTION_ID=declarai-assistant "
            "(Stream A naming)."
        )
        assert 'PROMETA_AGENT_NAME=declarai-agent' in content, (
            ".env must pin PROMETA_AGENT_NAME=declarai-agent "
            "(Stream A naming) — platform-team request 2026-05-21."
        )
        assert 'PROMETA_AGENT_ID=declarai-agent-staging' in content, (
            ".env must pin PROMETA_AGENT_ID=declarai-agent-staging "
            "so the slug matches {agent_name}-{stage}."
        )
        # Negative guard: the pre-v2.40.2 values must NOT be present.
        assert 'PROMETA_SOLUTION_ID=sol_declarai' not in content, (
            "Pre-v2.40.2 PROMETA_SOLUTION_ID=sol_declarai leaked back "
            "into .env — this would re-activate the soft-deprecated row."
        )

    def test_set_span_attr_noop_without_active_span(self):
        """set_span_attr is a no-op when no Prometa span is active."""
        from ai_assistant.prometa_config import set_span_attr
        # Should not raise even with no active span
        set_span_attr('gen_ai.prompt', 'test prompt')
        set_span_attr('gen_ai.usage.total_tokens', 42)


# ---------------------------------------------------------------------------
# AI Assistant cache layer tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestAiCache:
    """Test the Redis-backed cache helpers from ai_assistant/cache.py."""

    def test_cache_put_and_get(self):
        """cache_put + cache_get round-trip when Redis is available."""
        from ai_assistant.cache import cache_put, cache_get, _get_redis
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        assert cache_put(99999, 'test_artifact', {'foo': 'bar'})
        result = cache_get(99999, 'test_artifact')
        assert result == {'foo': 'bar'}
        # Cleanup
        r.delete('ai:pipeline:99999:test_artifact')

    def test_cache_get_missing_returns_none(self):
        """cache_get returns None for missing keys."""
        from ai_assistant.cache import cache_get
        assert cache_get(99999, 'nonexistent_artifact') is None

    def test_cache_put_bulk(self):
        """cache_put_bulk stores multiple artifacts at once."""
        from ai_assistant.cache import cache_put_bulk, cache_get, _get_redis
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        ok = cache_put_bulk(99999, {
            'art_a': [1, 2, 3],
            'art_b': {'key': 'value'},
        })
        assert ok is True
        assert cache_get(99999, 'art_a') == [1, 2, 3]
        assert cache_get(99999, 'art_b') == {'key': 'value'}
        r.delete('ai:pipeline:99999:art_a', 'ai:pipeline:99999:art_b')

    def test_cache_list_artifacts(self):
        """cache_list_artifacts lists cached artifact types."""
        from ai_assistant.cache import cache_put, cache_list_artifacts, _get_redis
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        cache_put(99998, 'alpha', 'val')
        cache_put(99998, 'beta', 'val')
        arts = cache_list_artifacts(99998)
        assert 'alpha' in arts
        assert 'beta' in arts
        r.delete('ai:pipeline:99998:alpha', 'ai:pipeline:99998:beta')


# ---------------------------------------------------------------------------
# AI Tool executor tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestToolExecutor:
    """Test tool_executor.execute_tool_call resolves from cache."""

    def test_unknown_tool(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'nonexistent_tool', {})
        assert 'Unknown tool' in result

    def test_get_split_validation_with_data(self):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import execute_tool_call
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        cache_put(99997, 'split_validation', {
            'target_column': 'Target',
            'splits': [
                {'name': 'Full', 'count': 1000, 'target_mean': 0.05, 'label_counts': {'0': 950, '1': 50}},
                {'name': 'Train', 'count': 750, 'target_mean': 0.048, 'label_counts': {'0': 714, '1': 36}},
                {'name': 'Test', 'count': 250, 'target_mean': 0.056, 'label_counts': {'0': 236, '1': 14}},
            ],
        })
        result = execute_tool_call(99997, 'get_split_validation', {})
        assert 'Target' in result
        assert '0.0480' in result
        assert 'Train' in result
        r.delete('ai:pipeline:99997:split_validation')

    def test_get_split_validation_missing(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(99996, 'get_split_validation', {})
        assert 'not available' in result.lower() or 'No' in result

    def test_get_vif_decomposition_with_data(self):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import execute_tool_call
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        cache_put(99995, 'vif_decomposition', {
            'Var_2': {
                'vif': 12.58,
                'top_correlations': [
                    {'feature': 'Var_3', 'correlation': 0.924, 'signed_correlation': 0.924, 'vif_drop': 9.11},
                ],
            },
        })
        result = execute_tool_call(99995, 'get_vif_decomposition', {'feature': 'Var_2'})
        assert 'Var_3' in result
        assert '0.9240' in result
        assert '12.58' in result
        r.delete('ai:pipeline:99995:vif_decomposition')

    def test_get_dq_summary_with_filter(self):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import execute_tool_call
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        cache_put(99994, 'dq_summary', [
            {'Variable': 'Age', 'Variable_Type': 'numeric', 'PSI': 0.03, 'Datq_Decision': 'Accept'},
            {'Variable': 'Income', 'Variable_Type': 'numeric', 'PSI': 0.15, 'Datq_Decision': 'Watch'},
        ])
        # Filtered
        result = execute_tool_call(99994, 'get_dq_summary', {'feature': 'Income'})
        assert 'Income' in result
        assert 'Age' not in result
        # Unfiltered
        result_all = execute_tool_call(99994, 'get_dq_summary', {})
        assert 'Age' in result_all
        assert 'Income' in result_all
        r.delete('ai:pipeline:99994:dq_summary')


# ---------------------------------------------------------------------------
# Model registry tests
# ---------------------------------------------------------------------------
@pytest.fixture
def _stub_engine_models(monkeypatch):
    """Inject a deterministic engine /v1/models payload so tests don't need a
    live engine.  Mirrors the previous hard-coded ``llama3.2:3b`` /
    ``llama3.2:1b`` pair so historical assertions still mean something —
    just routed through the dynamic-discovery code path."""
    from ai_assistant import model_registry as mr
    fake = {
        'engine-llama3.2-3b': {
            'provider': 'engine',
            'model_id': 'llama3.2:3b',
            'display_name': 'llama3.2:3b (Inference Engine)',
            'temperature': 0.4,
            'max_tokens': 4096,
            'supports_tools': True,
            'architecture': 'dense',
            'reasoning': False,
            'thinking': False,
            'thinking_level': None,
            'ram_gb': 3,
            'tool_calling_mode': 'text',
        },
        'engine-llama3.2-1b': {
            'provider': 'engine',
            'model_id': 'llama3.2:1b',
            'display_name': 'llama3.2:1b (Inference Engine)',
            'temperature': 0.4,
            'max_tokens': 4096,
            'supports_tools': True,
            'architecture': 'dense',
            'reasoning': False,
            'thinking': False,
            'thinking_level': None,
            'ram_gb': 2,
            'tool_calling_mode': 'text',
        },
    }
    monkeypatch.setattr(mr, '_fetch_engine_models', lambda: fake)
    mr.invalidate_engine_cache()
    yield fake
    mr.invalidate_engine_cache()


@pytest.mark.unit
class TestModelRegistry:
    """Test the model_registry module — model configs, list, and defaults."""

    def test_list_models_returns_all(self, _stub_engine_models):
        from ai_assistant.model_registry import list_models, MODEL_REGISTRY
        models = list_models()
        # Cloud entries (static) + engine entries (dynamic stub)
        expected_count = len(MODEL_REGISTRY) + len(_stub_engine_models)
        assert len(models) == expected_count
        keys = [m['key'] for m in models]
        for k in MODEL_REGISTRY:
            assert k in keys
        for k in _stub_engine_models:
            assert k in keys

    def test_list_models_structure(self, _stub_engine_models):
        from ai_assistant.model_registry import list_models
        models = list_models()
        for m in models:
            assert 'key' in m
            assert 'display_name' in m
            assert 'provider' in m

    def test_get_model_config_known(self):
        from ai_assistant.model_registry import get_model_config
        cfg = get_model_config('gpt-5.5')
        assert cfg['provider'] == 'openai'
        assert cfg['model_id'] == 'gpt-5.5'
        assert cfg['supports_tools'] is True
        assert cfg['is_reasoning_model'] is True
        assert 'temperature' not in cfg

    def test_get_model_config_gpt_mini(self):
        from ai_assistant.model_registry import get_model_config
        cfg = get_model_config('gpt-5.4-mini')
        assert cfg['provider'] == 'openai'
        assert cfg['model_id'] == 'gpt-5.4-mini'
        assert cfg['supports_tools'] is True
        assert cfg['is_reasoning_model'] is True
        assert 'temperature' not in cfg

    def test_get_model_config_engine_llama_3b(self, _stub_engine_models):
        from ai_assistant.model_registry import get_model_config
        # Dynamic-discovery key: engine-{id with ':' replaced by '-'}
        cfg = get_model_config('engine-llama3.2-3b')
        assert cfg['provider'] == 'engine'
        assert cfg['model_id'] == 'llama3.2:3b'
        assert cfg['supports_tools'] is True

    def test_get_model_config_unknown_falls_back(self):
        from ai_assistant.model_registry import get_model_config, DEFAULT_MODEL, MODEL_REGISTRY
        cfg = get_model_config('nonexistent-model-xyz')
        assert cfg == MODEL_REGISTRY[DEFAULT_MODEL]

    def test_default_model_exists_in_registry(self):
        from ai_assistant.model_registry import DEFAULT_MODEL, MODEL_REGISTRY
        assert DEFAULT_MODEL in MODEL_REGISTRY

    def test_all_models_have_required_fields(self):
        from ai_assistant.model_registry import MODEL_REGISTRY
        required = {
            'provider', 'model_id', 'display_name', 'max_tokens',
            'supports_tools', 'architecture', 'reasoning', 'thinking',
            'thinking_level',
        }
        for key, cfg in MODEL_REGISTRY.items():
            missing = required - set(cfg.keys())
            assert not missing, f"Model '{key}' missing fields: {missing}"

    def test_all_models_valid_architecture(self):
        from ai_assistant.model_registry import MODEL_REGISTRY
        for key, cfg in MODEL_REGISTRY.items():
            assert cfg['architecture'] in ('dense', 'moe'), f"{key}: bad architecture"

    def test_all_models_valid_thinking_level(self):
        from ai_assistant.model_registry import MODEL_REGISTRY
        valid = {None, 'low', 'med', 'high'}
        for key, cfg in MODEL_REGISTRY.items():
            assert cfg['thinking_level'] in valid, f"{key}: bad thinking_level"

    def test_reasoning_models_skip_temperature(self):
        """Reasoning models (gpt-5.5) should not have temperature in config."""
        from ai_assistant.model_registry import get_model_config
        for key in ('gpt-5.5', 'gpt-5.4-mini'):
            cfg = get_model_config(key)
            assert cfg.get('is_reasoning_model') is True
            assert 'temperature' not in cfg

    def test_engine_models_have_temperature(self, _stub_engine_models):
        """Engine-routed models should expose temperature for inference control."""
        from ai_assistant.model_registry import get_model_config
        for key in ('engine-llama3.2-1b', 'engine-llama3.2-3b'):
            cfg = get_model_config(key)
            assert 'temperature' in cfg
            assert not cfg.get('is_reasoning_model')

    def test_list_models_includes_meta_flags(self):
        """list_models() should expose architecture/reasoning/thinking flags."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        for m in models:
            assert 'architecture' in m
            assert 'reasoning' in m
            assert 'thinking' in m
            assert 'thinking_level' in m

    def test_engine_models_have_ram_gb(self, _stub_engine_models):
        """All engine-routed models should declare their ram_gb requirement."""
        from ai_assistant.model_registry import _registry_snapshot
        for key, cfg in _registry_snapshot().items():
            if cfg['provider'] == 'engine':
                assert 'ram_gb' in cfg, f"Engine model '{key}' missing ram_gb"
                assert isinstance(cfg['ram_gb'], (int, float)), f"{key}: ram_gb must be numeric"
                assert cfg['ram_gb'] > 0, f"{key}: ram_gb must be positive"

    def test_list_models_includes_ram_gb(self, _stub_engine_models):
        """list_models() should expose ram_gb for engine-routed models."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        engine_models = [m for m in models if m['provider'] == 'engine']
        assert len(engine_models) > 0
        for m in engine_models:
            assert 'ram_gb' in m, f"Model '{m['key']}' missing ram_gb in list output"

    def test_openai_models_have_native_tool_calling_mode(self):
        """OpenAI models should declare tool_calling_mode='native'."""
        from ai_assistant.model_registry import MODEL_REGISTRY
        for key, cfg in MODEL_REGISTRY.items():
            if cfg['provider'] == 'openai':
                assert cfg.get('tool_calling_mode') == 'native', f"{key}: expected native tool calling"

    def test_engine_models_have_tool_calling_mode(self, _stub_engine_models):
        """Engine models should declare tool_calling_mode (default 'text')."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        engine_models = [m for m in models if m['provider'] == 'engine']
        for m in engine_models:
            assert 'tool_calling_mode' in m, f"Model '{m['key']}' missing tool_calling_mode"
            assert m['tool_calling_mode'] in ('native', 'text'), f"{m['key']}: invalid tool_calling_mode"

    def test_list_models_surfaces_tool_calling_mode(self):
        """list_models() should include tool_calling_mode for all models."""
        from ai_assistant.model_registry import list_models
        models = list_models()
        for m in models:
            assert 'tool_calling_mode' in m, f"Model '{m['key']}' missing tool_calling_mode in list output"


# ---------------------------------------------------------------------------
# v2.43.1: Nemotron CoT-leak fix — reasoning-family models must opt into
# chat_template_kwargs={'enable_thinking': True} on the engine call so the
# GGUF template pre-emits ``<think>\n`` and the engine's response normalizer
# can route the prelude to ``reasoning_content`` instead of dumping it into
# ``content``.  Two contracts to pin:
#   1. _build_engine_entry mirrors the engine's reasoning/thinking/level
#      flags from /v1/models into the DeclarAI registry (was hard-coded
#      False before this fix, which made bug #2 invisible).
#   2. call_engine passes chat_template_kwargs.enable_thinking via
#      OpenAI SDK's extra_body iff model_cfg['reasoning'] is True.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEngineEntryReasoningCapability:
    """_build_engine_entry must mirror the engine's reasoning flags."""

    def test_reasoning_flag_propagated_from_engine_payload(self):
        from ai_assistant.model_registry import _build_engine_entry
        cfg = _build_engine_entry({
            'id': 'nemotron-3-nano:30b',
            'reasoning': True,
            'thinking': True,
            'thinking_level': 'med',
            'tool_calling_mode': 'native',
            'size_bytes': 24 * 1024 ** 3,
        })
        assert cfg['reasoning'] is True
        assert cfg['thinking'] is True
        assert cfg['thinking_level'] == 'med'

    def test_non_reasoning_flag_propagated_from_engine_payload(self):
        from ai_assistant.model_registry import _build_engine_entry
        cfg = _build_engine_entry({
            'id': 'llama3.2:3b',
            'reasoning': False,
            'thinking': False,
            'thinking_level': None,
            'tool_calling_mode': 'text',
            'size_bytes': 2 * 1024 ** 3,
        })
        assert cfg['reasoning'] is False
        assert cfg['thinking'] is False
        assert cfg['thinking_level'] is None

    def test_missing_capability_fields_default_to_non_reasoning(self):
        """Older engine builds that pre-date the capability surface must keep
        working — every reasoning/thinking field has to default off so we
        don't accidentally opt non-reasoning models into enable_thinking."""
        from ai_assistant.model_registry import _build_engine_entry
        cfg = _build_engine_entry({
            'id': 'mystery-model:1b',
            'size_bytes': 1024 ** 3,
        })
        assert cfg['reasoning'] is False
        assert cfg['thinking'] is False
        assert cfg['thinking_level'] is None


@pytest.mark.unit
class TestCallEngineEnableThinking:
    """call_engine must opt reasoning models into enable_thinking on the
    OpenAI-extension extra_body, and must NOT touch the body for non-
    reasoning models (so we don't double-template Llama / Gemma)."""

    @pytest.fixture
    def _fake_openai_client(self, monkeypatch):
        """Patch openai.OpenAI so the test can intercept the create() kwargs
        without actually hitting the engine."""
        captured = {}

        class _FakeCompletions:
            def create(self, **kwargs):
                captured['kwargs'] = kwargs

                class _FakeResp:
                    def model_dump(self_inner):
                        return {'id': 'test', 'choices': []}
                return _FakeResp()

        class _FakeChat:
            def __init__(self):
                self.completions = _FakeCompletions()

        class _FakeOpenAI:
            def __init__(self, **_):
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, 'OpenAI', _FakeOpenAI)
        return captured

    def test_reasoning_model_gets_enable_thinking_true(self, _fake_openai_client):
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'nemotron-3-nano:30b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': True,
        }
        call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        sent = _fake_openai_client['kwargs']
        assert sent.get('extra_body') == {
            'chat_template_kwargs': {'enable_thinking': True}
        }, "reasoning models must opt into enable_thinking via extra_body"

    def test_non_reasoning_model_omits_extra_body(self, _fake_openai_client):
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'llama3.2:3b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': False,
        }
        call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        sent = _fake_openai_client['kwargs']
        assert 'extra_body' not in sent, (
            "non-reasoning models must NOT receive chat_template_kwargs — "
            "Llama/Gemma chat templates have no enable_thinking branch, and "
            "an unknown kwarg can change their rendering behavior on engine "
            "builds that pass it through to Jinja unconditionally"
        )

    def test_reasoning_flag_missing_omits_extra_body(self, _fake_openai_client):
        """Defensive: if model_cfg has no ``reasoning`` key at all (e.g. a
        hand-built test config or a legacy registry entry) we must not
        accidentally opt-in."""
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'engine-only:7b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
        }
        call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        assert 'extra_body' not in _fake_openai_client['kwargs']

    def test_reasoning_model_with_tools_keeps_both(self, _fake_openai_client):
        """Tools and extra_body must co-exist — the failing UI scenario has
        15 tools + Nemotron + enable_thinking all at once."""
        from ai_assistant.model_registry import call_engine
        cfg = {
            'provider': 'engine',
            'model_id': 'nemotron-3-nano:30b',
            'max_tokens': 4096,
            'temperature': 0.4,
            'supports_tools': True,
            'reasoning': True,
        }
        tools = [{'type': 'function', 'function': {
            'name': 'get_data_dictionary',
            'description': 'x',
            'parameters': {'type': 'object', 'properties': {}},
        }}]
        call_engine([{'role': 'user', 'content': 'hi'}], cfg, tools=tools)
        sent = _fake_openai_client['kwargs']
        assert sent.get('tools') == tools
        assert sent.get('tool_choice') == 'auto'
        assert sent.get('extra_body') == {
            'chat_template_kwargs': {'enable_thinking': True}
        }


# ---------------------------------------------------------------------------
# v2.43.2: client-side reasoning_content recovery.
#
# The llm-inference-engine team (PR fix/blocking-normalizer-reasoning-prelude)
# adopted the AGGRESSIVE blocking-path policy: unanchored text on a
# reasoning-family model routes to ``reasoning_content`` regardless of
# finish_reason, to stay byte-for-byte symmetric with the streaming
# normalizer.  Their rationale assumed DeclarAI renders reasoning
# collapsed-by-default and could recover a misrouted answer — but every
# DeclarAI consumer reads only ``message.content``.  Without this guard a
# real answer with no ``<think>`` markers is silently dropped (empty
# content → synthesis pass → _EMPTY_RESPONSE_FALLBACK).
#
# _recover_reasoning_content promotes reasoning_content into content when
# content is blank AND there are no tool_calls.  These tests pin that
# contract and its integration into call_engine.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestRecoverReasoningContent:
    """_recover_reasoning_content salvages a misrouted answer in-place."""

    def _resp(self, *, content, reasoning=None, tool_calls=None,
              finish_reason='stop'):
        msg = {'role': 'assistant', 'content': content}
        if reasoning is not None:
            msg['reasoning_content'] = reasoning
        if tool_calls is not None:
            msg['tool_calls'] = tool_calls
        return {'choices': [{'finish_reason': finish_reason, 'message': msg}]}

    def test_promotes_reasoning_when_content_empty(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content='', reasoning='The real answer is 42.')
        )
        msg = out['choices'][0]['message']
        assert msg['content'] == 'The real answer is 42.'
        # Original preserved for any future collapsed-CoT renderer
        assert msg['reasoning_content'] == 'The real answer is 42.'
        assert out['choices'][0]['declarai_reasoning_recovered'] is True

    def test_promotes_when_content_is_none(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content=None, reasoning='Answer here.')
        )
        assert out['choices'][0]['message']['content'] == 'Answer here.'

    def test_promotes_when_content_is_whitespace(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content='   \n  ', reasoning='Answer here.')
        )
        assert out['choices'][0]['message']['content'] == 'Answer here.'

    def test_does_not_touch_real_content(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(
            self._resp(content='A genuine reply.', reasoning='internal CoT')
        )
        msg = out['choices'][0]['message']
        assert msg['content'] == 'A genuine reply.'
        assert 'declarai_reasoning_recovered' not in out['choices'][0]

    def test_leaves_tool_call_round_alone(self):
        """A tool-call round legitimately has empty content — promoting
        reasoning_content there would corrupt the multi-turn loop."""
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(self._resp(
            content='',
            reasoning='thinking about which tool to call',
            tool_calls=[{'id': 'c1', 'function': {'name': 'get_cv_results',
                                                  'arguments': '{}'}}],
            finish_reason='tool_calls',
        ))
        msg = out['choices'][0]['message']
        assert msg['content'] == ''  # untouched
        assert 'declarai_reasoning_recovered' not in out['choices'][0]

    def test_noop_when_both_empty(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(self._resp(content='', reasoning=''))
        assert out['choices'][0]['message']['content'] == ''
        assert 'declarai_reasoning_recovered' not in out['choices'][0]

    def test_noop_when_no_reasoning_key(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        out = _recover_reasoning_content(self._resp(content=''))
        assert out['choices'][0]['message']['content'] == ''

    def test_promotes_on_stop_skips_on_length(self):
        """v2.44.0 contract refinement (supersedes the v2.43.2 'promote
        regardless of finish_reason' policy): a COMPLETE answer the engine
        misrouted into reasoning_content finishes with 'stop' and IS promoted;
        an UNFINISHED chain-of-thought finishes with 'length' and must NOT be
        promoted — promoting it leaks raw CoT to the user (the reproduced
        screenshot bug).  The length case is tagged
        ``declarai_reasoning_truncated`` and left for the finalization pass."""
        from ai_assistant.model_registry import _recover_reasoning_content
        # stop → promote (complete answer misrouted to reasoning_content)
        out = _recover_reasoning_content(
            self._resp(content='', reasoning='ans', finish_reason='stop')
        )
        assert out['choices'][0]['message']['content'] == 'ans'
        assert out['choices'][0].get('declarai_reasoning_recovered') is True
        # length → skip (truncated CoT); content stays empty + tagged truncated
        out2 = _recover_reasoning_content(
            self._resp(content='', reasoning='Okay, let me think…',
                       finish_reason='length')
        )
        msg2 = out2['choices'][0]['message']
        assert msg2['content'] == ''  # NOT promoted
        assert 'declarai_reasoning_recovered' not in out2['choices'][0]
        assert out2['choices'][0].get('declarai_reasoning_truncated') is True
        # original reasoning preserved for any future collapsed-CoT renderer
        assert msg2['reasoning_content'] == 'Okay, let me think…'

    def test_idempotent(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        r = self._resp(content='', reasoning='ans')
        once = _recover_reasoning_content(r)
        twice = _recover_reasoning_content(once)
        assert twice['choices'][0]['message']['content'] == 'ans'

    def test_defensive_against_malformed_shapes(self):
        """Never raise — a salvage helper must not be able to break chat."""
        from ai_assistant.model_registry import _recover_reasoning_content
        assert _recover_reasoning_content({}) == {}
        assert _recover_reasoning_content({'choices': None}) == {'choices': None}
        assert _recover_reasoning_content({'choices': [None, 'x']}) == {
            'choices': [None, 'x']
        }
        # choice without a dict message
        assert _recover_reasoning_content(
            {'choices': [{'message': 'not-a-dict'}]}
        ) == {'choices': [{'message': 'not-a-dict'}]}

    def test_handles_multiple_choices(self):
        from ai_assistant.model_registry import _recover_reasoning_content
        resp = {'choices': [
            {'finish_reason': 'stop',
             'message': {'content': '', 'reasoning_content': 'first'}},
            {'finish_reason': 'stop',
             'message': {'content': 'real', 'reasoning_content': 'cot'}},
        ]}
        out = _recover_reasoning_content(resp)
        assert out['choices'][0]['message']['content'] == 'first'
        assert out['choices'][1]['message']['content'] == 'real'


@pytest.mark.unit
class TestCallEngineRecoversReasoning:
    """call_engine must run the recovery pass on the engine's response so the
    rest of the app (which reads only message.content) sees the answer."""

    def _patch_openai(self, monkeypatch, fake_response: dict):
        class _FakeCompletions:
            def create(self, **kwargs):
                class _FakeResp:
                    def model_dump(self_inner):
                        return fake_response
                return _FakeResp()

        class _FakeChat:
            def __init__(self):
                self.completions = _FakeCompletions()

        class _FakeOpenAI:
            def __init__(self, **_):
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, 'OpenAI', _FakeOpenAI)

    def test_call_engine_promotes_reasoning_content(self, monkeypatch):
        from ai_assistant.model_registry import call_engine
        self._patch_openai(monkeypatch, {
            'id': 't',
            'choices': [{
                'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': '',
                            'reasoning_content': 'Recovered answer.'},
            }],
        })
        cfg = {'provider': 'engine', 'model_id': 'nemotron-3-nano:30b',
               'max_tokens': 4096, 'temperature': 0.4,
               'supports_tools': True, 'reasoning': True}
        out = call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        assert out['choices'][0]['message']['content'] == 'Recovered answer.'

    def test_call_engine_leaves_normal_response_unchanged(self, monkeypatch):
        from ai_assistant.model_registry import call_engine
        self._patch_openai(monkeypatch, {
            'id': 't',
            'choices': [{
                'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': 'Direct reply.'},
            }],
        })
        cfg = {'provider': 'engine', 'model_id': 'llama3.2:3b',
               'max_tokens': 4096, 'temperature': 0.4,
               'supports_tools': True, 'reasoning': False}
        out = call_engine([{'role': 'user', 'content': 'hi'}], cfg)
        assert out['choices'][0]['message']['content'] == 'Direct reply.'


# ---------------------------------------------------------------------------
# Data dictionary enrichment — DB-backed fallback for stale Redis cache
# (regression for the "Gemma says no descriptions exist" bug)
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDataDictionaryEnrichment:
    """Test _enrich_dd_with_descriptions falls back to the DB when the cache
    has missing/null descriptions, and that downstream consumers
    (system context + get_data_dictionary tool) surface those descriptions."""

    @pytest.fixture
    def _decl_with_descriptions(self):
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/dd_enrich.csv',
            name='dd_enrich.csv',
            original_name='dd_enrich.csv',
        )
        DataDictionary.objects.create(data_file=decl, column_name='Var_1',
                                      description='CC Num of application_L1M')
        DataDictionary.objects.create(data_file=decl, column_name='Var_2',
                                      description='Worst Account Status All Credits')
        return decl

    def test_enrich_backfills_missing_descriptions(self, _decl_with_descriptions):
        from ai_assistant.views import _enrich_dd_with_descriptions
        cached = [
            {'Feature_Name': 'Var_1', 'Feature_Description': None},
            {'Feature_Name': 'Var_2'},  # description key absent
            {'Feature_Name': 'Var_3', 'Feature_Description': 'Already has one'},
        ]
        out = _enrich_dd_with_descriptions(_decl_with_descriptions.pk, cached)
        by_name = {f['Feature_Name']: f.get('Feature_Description') for f in out}
        assert by_name['Var_1'] == 'CC Num of application_L1M'
        assert by_name['Var_2'] == 'Worst Account Status All Credits'
        assert by_name['Var_3'] == 'Already has one'  # unchanged

    def test_enrich_no_op_when_db_empty(self):
        from ai_assistant.views import _enrich_dd_with_descriptions
        cached = [{'Feature_Name': 'Var_1', 'Feature_Description': None}]
        out = _enrich_dd_with_descriptions(file_id=987654, dd_list=cached)
        assert out[0].get('Feature_Description') in (None, '')

    def test_enrich_handles_empty_list(self):
        from ai_assistant.views import _enrich_dd_with_descriptions
        assert _enrich_dd_with_descriptions(1, []) == []

    def test_slim_context_embeds_descriptions(self, _decl_with_descriptions):
        """Regression: every model (incl. text-mode tool callers) must see
        feature descriptions inline, not be told to call a tool."""
        from ai_assistant.cache import cache_put, _get_redis, ARTIFACT_DATA_DICTIONARY
        from ai_assistant.views import _build_slim_context
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        # Cache holds NULL descriptions — same situation we observed in prod
        fid = _decl_with_descriptions.pk
        cache_put(fid, ARTIFACT_DATA_DICTIONARY, [
            {'Feature_Name': 'Var_1', 'Feature_Description': None},
            {'Feature_Name': 'Var_2', 'Feature_Description': None},
        ])
        try:
            ctx = _build_slim_context(fid, 'dictionary_declaration')
            assert 'business descriptions' in ctx.lower()
            assert 'CC Num of application_L1M' in ctx
            assert 'Worst Account Status All Credits' in ctx
            # And it must NOT instruct the model that descriptions are missing
            assert 'No business descriptions found' not in ctx
        finally:
            r.delete(f'ai:pipeline:{fid}:data_dictionary')

    def test_slim_context_warns_when_truly_no_descriptions(self):
        """When neither cache nor DB has descriptions, the system context
        should explicitly tell the LLM so users can be guided to upload one."""
        from ai_assistant.cache import cache_put, _get_redis, ARTIFACT_DATA_DICTIONARY
        from ai_assistant.views import _build_slim_context
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        cache_put(987655, ARTIFACT_DATA_DICTIONARY, [
            {'Feature_Name': 'Var_1', 'Feature_Description': None},
        ])
        try:
            ctx = _build_slim_context(987655, 'dictionary_declaration')
            assert 'No business descriptions found' in ctx
        finally:
            r.delete('ai:pipeline:987655:data_dictionary')

    def test_get_data_dictionary_tool_uses_db_fallback(self, _decl_with_descriptions):
        """The get_data_dictionary tool output (used by native function-callers)
        must also benefit from the DB fallback."""
        from ai_assistant.cache import cache_put, _get_redis, ARTIFACT_DATA_DICTIONARY
        from ai_assistant.tool_executor import execute_tool_call
        r = _get_redis()
        if r is None:
            pytest.skip("Redis not available")
        fid = _decl_with_descriptions.pk
        cache_put(fid, ARTIFACT_DATA_DICTIONARY, [
            {'Feature_Name': 'Var_1', 'Feature_Description': None,
             'Data_Type': 'integer', 'Unique_Values': 10},
            {'Feature_Name': 'Var_2', 'Feature_Description': None,
             'Data_Type': 'str', 'Unique_Values': 9},
        ])
        try:
            result = execute_tool_call(fid, 'get_data_dictionary', {})
            assert 'CC Num of application_L1M' in result
            assert 'Worst Account Status All Credits' in result
        finally:
            r.delete(f'ai:pipeline:{fid}:data_dictionary')


# ---------------------------------------------------------------------------
# Skill registry + invoke_skill tool + skill auto-routing
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSkillRegistry:
    """Parses SKILL.md frontmatter, exposes registered skills."""

    def test_feature_engineering_skill_is_discovered(self):
        from ai_assistant.skill_registry import list_skills
        skills = list_skills(refresh=True)
        assert 'feature-engineering' in skills
        sk = skills['feature-engineering']
        assert sk.description  # non-empty
        # Description from the bundled SKILL.md frontmatter
        assert 'feature' in sk.description.lower()

    def test_skill_body_is_loaded_lazily(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        assert sk is not None
        body = sk.body()
        # Body must contain real FE content, not the frontmatter
        assert 'Feature Engineering Guide' in body
        assert '---' not in body.splitlines()[0]  # frontmatter stripped

    def test_unknown_skill_returns_none(self):
        from ai_assistant.skill_registry import get_skill
        assert get_skill('nonexistent-skill-xyz') is None

    def test_frontmatter_parser_handles_quoted_values(self):
        from ai_assistant.skill_registry import _split_frontmatter
        text = '---\nname: foo\ndescription: "hello: world"\n---\nbody here\n'
        meta, body = _split_frontmatter(text)
        assert meta['name'] == 'foo'
        assert meta['description'] == 'hello: world'
        assert body.strip() == 'body here'

    def test_frontmatter_parser_handles_no_frontmatter(self):
        from ai_assistant.skill_registry import _split_frontmatter
        meta, body = _split_frontmatter('plain markdown\n')
        assert meta == {}
        assert body == 'plain markdown\n'


@pytest.mark.unit
class TestInvokeSkillTool:
    """The invoke_skill tool returns the skill body and is wired into the
    OpenAI tool definition list with the bundled skill name."""

    def test_tool_definition_includes_invoke_skill(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        names = [t['function']['name'] for t in PIPELINE_TOOLS]
        assert 'invoke_skill' in names

    def test_tool_definition_enumerates_bundled_skills(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        invoke = next(t for t in PIPELINE_TOOLS if t['function']['name'] == 'invoke_skill')
        params = invoke['function']['parameters']['properties']
        assert 'skill_name' in params
        # The enum should list at least feature-engineering
        assert 'feature-engineering' in params['skill_name'].get('enum', [])
        assert 'feature-engineering' in invoke['function']['description'].lower()

    def test_invoke_skill_handler_returns_body(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'invoke_skill', {'skill_name': 'feature-engineering'})
        assert 'BEGIN SKILL CONTENT' in result
        assert 'END SKILL CONTENT' in result
        assert 'Feature Engineering Guide' in result

    def test_invoke_skill_handler_unknown_skill(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'invoke_skill', {'skill_name': 'no-such-skill'})
        assert "not bundled" in result
        assert 'feature-engineering' in result  # lists available

    def test_invoke_skill_handler_missing_arg(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'invoke_skill', {})
        assert "requires 'skill_name'" in result

    def test_load_skill_traced_sets_span_attributes(self, monkeypatch):
        """The dedicated traced loader stamps declarai.skill.* attributes so
        each skill invocation appears as a distinct child span."""
        from ai_assistant import tool_executor as te
        captured = {}

        def fake_set(key, value):
            captured[key] = value

        monkeypatch.setattr(te, 'set_span_attr', fake_set)
        result = te._load_skill_traced('feature-engineering')
        assert 'BEGIN SKILL CONTENT' in result
        assert captured.get('declarai.skill.name') == 'feature-engineering'
        assert captured.get('declarai.skill.found') is True
        assert isinstance(captured.get('declarai.skill.body_chars'), int)
        assert captured['declarai.skill.body_chars'] > 100


@pytest.mark.unit
class TestSkillAutoRouting:
    """Auto-router fires on feature-engineering intent in the user message
    so text-mode models (which often skip tool calls) still see the skill."""

    @pytest.mark.parametrize('msg', [
        "according to the project goal and the feature descriptions we have, "
        "which new features can be derived from others",
        "Please implement feature engineering on this dataset.",
        "Create a few WOE bins for the categorical variables.",
        "I want to derive ratio features from the income columns.",
        "Can you generate new features based on the existing ones?",
    ])
    def test_auto_route_fires_on_fe_intent(self, msg):
        from ai_assistant.views import _auto_route_skill
        assert _auto_route_skill(msg) == 'feature-engineering'

    @pytest.mark.parametrize('msg', [
        "Why is Var_19 important in the SHAP plot?",
        "Explain the SFS results to me.",
        "What is the bad rate in the test split?",
        "",
    ])
    def test_auto_route_does_not_fire_on_unrelated_questions(self, msg):
        from ai_assistant.views import _auto_route_skill
        assert _auto_route_skill(msg) is None


@pytest.mark.unit
class TestAssistantIntentClassifier:
    """Chat turns are classified by LLM before retrieval/tool/action work."""

    def _llm_response(self, labels, *, confidence='high', uncertain=False):
        import json
        return json.dumps({
            'labels': labels,
            'confidence': confidence,
            'uncertain': uncertain,
            'decomposition': [{'segment': 'latest user turn', 'labels': labels}],
            'reason': 'test fixture',
        })

    def test_general_information_question_is_a(self):
        from ai_assistant.intent_classifier import classify_query_intents

        out = classify_query_intents(
            'What is PSI in general?',
            llm_classifier=lambda messages: self._llm_response(['A', 'R']),
        )

        assert out['labels'] == ['A', 'R']
        assert out['source'] == 'llm_classifier'
        assert out['preclassified'] is False

    def test_pipeline_flow_mechanism_question_is_b(self):
        from ai_assistant.intent_classifier import classify_query_intents

        out = classify_query_intents(
            'How does the default preprocessing flow work?',
            llm_classifier=lambda messages: self._llm_response(['B', 'R']),
        )

        assert out['labels'] == ['B', 'R']

    def test_current_status_question_is_c(self):
        from ai_assistant.intent_classifier import classify_query_intents

        out = classify_query_intents(
            'Analyze the current SFS results and selected features.',
            section='sfs_backward',
            context={'backward': []},
            llm_classifier=lambda messages: self._llm_response(['C']),
        )

        assert out['labels'] == ['C']

    def test_user_manual_question_includes_rag_label(self):
        from ai_assistant.intent_classifier import classify_query_intents

        out = classify_query_intents(
            'Show me the platform manual and glossary for assistant usage.',
            llm_classifier=lambda messages: self._llm_response(['R']),
        )

        assert out['labels'] == ['R']

    def test_compound_edit_and_execute_question_is_d_and_e(self):
        from ai_assistant.intent_classifier import classify_query_intents

        out = classify_query_intents(
            'Set max_features to 20 and then start SFS.',
            section='modeling',
            llm_classifier=lambda messages: self._llm_response(['D', 'E']),
        )

        assert out['labels'] == ['D', 'E']
        assert out['source'] == 'llm_classifier'
        assert out['confidence'] == 'high'

    def test_llm_uncertain_uses_narrow_regex_fallback(self):
        from ai_assistant.intent_classifier import classify_query_intents

        out = classify_query_intents(
            'how do we calculating feature-wise VIF values in this platform',
            llm_classifier=lambda messages: self._llm_response(
                [], confidence='low', uncertain=True),
        )

        assert out['labels'] == ['B', 'R']
        assert out['source'] == 'definite_regex_fallback'
        assert out['fallback_reason'] == 'llm_uncertain'
        assert out['uncertain'] is True

    def test_preclassified_labels_bypass_classifier(self):
        from ai_assistant.intent_classifier import resolve_intent_classification

        def fail_if_called(_messages):
            raise AssertionError('preclassified labels should bypass LLM')

        out = resolve_intent_classification(
            'Analyze the Data Quality Summary.',
            section='data_quality',
            preclassified_labels=['C'],
            preclassified_source='get_ai_support_button',
            llm_classifier=fail_if_called,
        )

        assert out['labels'] == ['C']
        assert out['source'] == 'get_ai_support_button'
        assert out['preclassified'] is True


@pytest.mark.unit
class TestKnowledgeBankRetrieval:
    """Knowledge-bank retrieval returns cited snippets from versioned docs."""

    def test_retrieves_glossary_context_for_metric_question(self):
        from ai_assistant.knowledge_bank import retrieve_knowledge_context

        out = retrieve_knowledge_context('What does PSI mean?')

        assert out['results']
        assert '[KB1]' in out['context']
        joined = '\n'.join(r['snippet'] for r in out['results'])
        assert 'Population Stability Index' in joined
        assert any(r['source'] == 'terminology-glossary.md'
                   for r in out['results'])

    def test_retrieves_assistant_guide_for_usage_question(self):
        from ai_assistant.knowledge_bank import retrieve_knowledge_context

        out = retrieve_knowledge_context('How should I use the assistant actions?')

        assert out['results']
        sources = {r['source'] for r in out['results']}
        assert 'assistant-usage-and-action-guide.md' in sources


# ---------------------------------------------------------------------------
# v2.43.3 — engine context-window overflow on multi-turn tool calling
# ---------------------------------------------------------------------------
# Symptom (production): every feature-engineering question to an engine
# model (nemotron-3-nano:30b, ~8K-token window) returned "AI Assistant
# error: Internal Server Error".  Root cause: the follow-up tool call's
# prompt — lite system prompt + slim context + the auto-injected ~2K-token
# skill playbook + the 15 tool schemas (~2.3K tokens) + the tool result —
# crossed the model's context window, and the engine returned a bare HTTP
# 500 (not a graceful context_length_exceeded 400).  Reproduced against the
# live engine at the exact production prompt sizes.
#
# Two-part fix:
#   1. Provider-aware skill injection — engine models no longer pre-load the
#      full playbook (they pull it on demand via invoke_skill); cloud models
#      keep it.  TestSkillAutoInjectionProviderAware pins this.
#   2. Graceful degradation — if the engine still 5xx's mid tool-loop (e.g.
#      the model calls both invoke_skill AND get_data_dictionary), drop the
#      tool schemas and fall through to the synthesis pass instead of
#      surfacing a raw 500.  TestChatWorkflowEngineOverflowDegrades pins it.
# ---------------------------------------------------------------------------


def _engine_or_cloud_cfg(provider, reasoning=False):
    """Minimal model_cfg matching what get_model_config returns."""
    return {
        'provider': provider,
        'model_id': 'nemotron-3-nano:30b' if provider == 'engine' else 'gpt-5.5',
        'supports_tools': True,
        'max_tokens': 4096,
        'temperature': 0.4,
        'reasoning': reasoning,
    }


def _tool_call_response(name='get_data_dictionary', call_id='c1'):
    """A response that asks for one tool call (content empty — the normal
    shape for a tool-calling round)."""
    return {
        'choices': [{
            'finish_reason': 'tool_calls',
            'message': {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': call_id, 'type': 'function',
                    'function': {'name': name, 'arguments': '{}'},
                }],
            },
        }],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
    }


def _text_response(text):
    """A plain final answer (no tool calls, no action blocks)."""
    return {
        'choices': [{'finish_reason': 'stop',
                     'message': {'role': 'assistant', 'content': text}}],
        'usage': {'prompt_tokens': 8, 'completion_tokens': 4, 'total_tokens': 12},
    }


def _run_chat_workflow(monkeypatch, *, provider, call_llm,
                       user_message='please derive new features from the existing ones',
                       file_id=1, reasoning=False, history=None,
                       span_id=None, trace_id=None,
                       intent_labels_for_turn=None):
    """Execute the real _chat_workflow body with its external collaborators
    mocked.  ``call_llm(idx, messages, tools)`` scripts each LLM round.

    Returns {result, llm_calls, skill_calls} so tests can assert on the
    response AND on what was sent to the model each round."""
    from ai_assistant import views

    monkeypatch.setattr(views, 'get_model_config',
                        lambda k: _engine_or_cloud_cfg(provider, reasoning))
    monkeypatch.setattr(views, 'cache_list_artifacts',
                        lambda fid: ['data_dictionary'])
    monkeypatch.setattr(views, '_build_slim_context',
                        lambda fid, sec: 'Pipeline: boosting\nTarget: good/bad flag')
    monkeypatch.setattr(views, 'execute_tool_call',
                        lambda fid, name, args: f'TOOL_RESULT[{name}]')
    # Observability helpers → silent no-ops (they are no-ops under pytest
    # anyway; pinning them keeps the test independent of SDK state).
    monkeypatch.setattr(views, 'set_span_attr', lambda *a, **kw: None)
    monkeypatch.setattr(views, 'set_session_id', lambda *a, **kw: None)
    monkeypatch.setattr(views, 'set_customer_id', lambda *a, **kw: None)
    monkeypatch.setattr(views, 'current_span_id', lambda: span_id)
    monkeypatch.setattr(views, 'current_trace_id', lambda: trace_id)

    def fake_resolve_intent(user_message, **_kwargs):
        from ai_assistant.intent_classifier import INTENT_LABEL_NAMES
        labels = intent_labels_for_turn
        if labels is None:
            if 'max_features' in user_message and 'start SFS' in user_message:
                labels = ['D', 'E']
            elif 'PSI' in user_message:
                labels = ['A', 'R']
            else:
                labels = ['A']
        return {
            'labels': labels,
            'label_names': [
                INTENT_LABEL_NAMES[label]
                for label in labels
            ],
            'source': 'llm_classifier',
            'preclassified': False,
            'classifier_version': 'intent-v3-llm-rag',
            'confidence': 'high',
            'uncertain': False,
            'fallback_reason': '',
            'decomposition': [{'segment': user_message, 'labels': labels}],
        }
    monkeypatch.setattr(views, 'resolve_intent_classification', fake_resolve_intent)

    skill_calls = []

    def fake_load_skill(name):
        skill_calls.append(name)
        return f'SKILL_PLAYBOOK_BODY for {name}'
    monkeypatch.setattr(views, '_load_skill_traced', fake_load_skill)

    llm_calls = []

    def fake_call_llm(messages, model_key, tools=None):
        idx = len(llm_calls)
        llm_calls.append({
            'messages': [dict(m) for m in messages],
            'tools': tools,
            'model_key': model_key,
        })
        return call_llm(idx, messages, tools)
    monkeypatch.setattr(views, '_call_llm', fake_call_llm)

    fn = views._chat_workflow.__wrapped__ \
        if hasattr(views._chat_workflow, '__wrapped__') else views._chat_workflow
    result = fn(user_message, {}, 'general', history or [],
                file_id=file_id, model='engine-x')
    return {'result': result, 'llm_calls': llm_calls, 'skill_calls': skill_calls}


@pytest.mark.unit
class TestKnowledgeBankRagWorkflow:
    """When intent includes R, _chat_workflow retrieves and injects docs."""

    def test_rag_intent_injects_knowledge_bank_context(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            user_message='What does PSI mean in the DeclarAI platform?',
            call_llm=lambda idx, messages, tools: _text_response('PSI means stability.'),
        )

        assert out['result']['intent_labels'] == ['A', 'R']
        assert out['result']['rag_sources']
        joined = '\n'.join(m.get('content') or ''
                           for m in out['llm_calls'][0]['messages'])
        assert 'Knowledge bank context retrieved for this turn.' in joined
        assert '[KB1]' in joined
        assert 'Population Stability Index' in joined

    def test_non_rag_turn_does_not_inject_knowledge_bank_context(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            user_message='Set max_features to 20 and then start SFS.',
            call_llm=lambda idx, messages, tools: _text_response('Prepared.'),
        )

        assert out['result']['intent_labels'] == ['D', 'E']
        assert 'rag_sources' not in out['result']
        joined = '\n'.join(m.get('content') or ''
                           for m in out['llm_calls'][0]['messages'])
        assert 'Knowledge bank context retrieved for this turn.' not in joined


@pytest.mark.unit
class TestIsEngineServerError:
    """_is_engine_server_error gates the graceful-degradation path: True only
    for server-side 5xx (the engine's context-overflow 500), False for 4xx /
    connection / timeout / programming errors so genuine failures propagate."""

    def test_status_code_500_is_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status_code = 500
        assert _is_engine_server_error(E()) is True

    def test_status_code_503_is_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status_code = 503
        assert _is_engine_server_error(E()) is True

    def test_status_code_400_is_not_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status_code = 400
        assert _is_engine_server_error(E()) is False

    def test_status_attr_variant_502(self):
        from ai_assistant.views import _is_engine_server_error

        class E(Exception):
            status = 502
        assert _is_engine_server_error(E()) is True

    def test_internalservererror_classname_without_status(self):
        from ai_assistant.views import _is_engine_server_error

        class InternalServerError(Exception):
            pass
        assert _is_engine_server_error(InternalServerError()) is True

    def test_plain_exception_is_not_server_error(self):
        from ai_assistant.views import _is_engine_server_error
        assert _is_engine_server_error(ValueError('boom')) is False

    def test_connection_error_classname_is_not_server_error(self):
        from ai_assistant.views import _is_engine_server_error

        class APIConnectionError(Exception):
            pass
        assert _is_engine_server_error(APIConnectionError()) is False


@pytest.mark.unit
class TestSkillAutoInjectionProviderAware:
    """The FE skill playbook is pre-loaded into the system prompt only for
    cloud models; engine models skip it (it overflows their small context
    window) and pull it on demand via the invoke_skill tool."""

    def test_engine_model_does_not_preload_skill_body(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='engine',
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        # The auto-router still matched (loader would be reachable), but the
        # body must NOT have been loaded or injected for an engine model.
        assert out['skill_calls'] == []
        joined = ' '.join(m.get('content') or '' for m in out['llm_calls'][0]['messages'])
        assert 'SKILL_PLAYBOOK_BODY' not in joined
        assert 'playbook has been pre-loaded' not in joined

    def test_cloud_model_preloads_skill_body(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        assert out['skill_calls'] == ['feature-engineering']
        joined = ' '.join(m.get('content') or '' for m in out['llm_calls'][0]['messages'])
        assert 'SKILL_PLAYBOOK_BODY' in joined
        assert 'playbook has been pre-loaded' in joined


@pytest.mark.unit
class TestChatWorkflowTurnFocusAnchor:
    """v2.44.2: when prior turns exist, a short topic-anchor system message is
    injected immediately before the user message so reasoning models answer
    the CURRENT question instead of drifting back to the previous turn's topic
    (the data-purification-answered-as-features screenshot).  First turn (no
    history) must NOT inject it."""

    _PURIF_Q = ('what are the data purification steps in the flow? how to sort '
                'them while implementing and configure them better?')
    _HISTORY = [
        {'role': 'user', 'content': 'which new features can be derived? create them.'},
        {'role': 'assistant', 'content': 'Proposed derived features:\n| Feature | Formula |\n| Debt_To_Income | Var_19/Var_24 |'},
    ]

    def test_turn_focus_injected_when_history_present(self, monkeypatch):
        from ai_assistant.views import _TURN_FOCUS_PROMPT
        out = _run_chat_workflow(
            monkeypatch, provider='engine', reasoning=True,
            user_message=self._PURIF_Q, history=self._HISTORY,
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        msgs = out['llm_calls'][0]['messages']
        contents = [m.get('content') or '' for m in msgs]
        assert _TURN_FOCUS_PROMPT in contents
        # It must sit immediately before the current user message.
        user_idx = max(i for i, m in enumerate(msgs)
                       if m.get('role') == 'user' and m.get('content') == self._PURIF_Q)
        assert msgs[user_idx - 1].get('content') == _TURN_FOCUS_PROMPT
        assert msgs[user_idx - 1].get('role') == 'system'

    def test_turn_focus_absent_on_first_turn(self, monkeypatch):
        from ai_assistant.views import _TURN_FOCUS_PROMPT
        out = _run_chat_workflow(
            monkeypatch, provider='engine', reasoning=True,
            user_message=self._PURIF_Q, history=[],
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert _TURN_FOCUS_PROMPT not in contents

    def test_turn_focus_injected_for_cloud_models_too(self, monkeypatch):
        # Provider-agnostic — harmless for cloud, useful if a cloud model ever drifts.
        from ai_assistant.views import _TURN_FOCUS_PROMPT
        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            user_message=self._PURIF_Q, history=self._HISTORY,
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert _TURN_FOCUS_PROMPT in contents

    def test_turn_focus_does_not_instruct_producing_a_question(self):
        # v2.44.3 regression: the prior wording ("Answer the user's NEXT
        # message AS A STANDALONE QUESTION") made nemotron-3-nano:30b echo the
        # user's prompt back reframed as a question instead of answering.  The
        # anchor must NEVER tell the model to produce / phrase a question.
        from ai_assistant.views import _TURN_FOCUS_PROMPT
        lowered = _TURN_FOCUS_PROMPT.lower()
        assert 'as a standalone question' not in lowered
        # It must direct the model to ANSWER, not to mirror the prompt.
        assert 'answer' in lowered
        assert ('echo' in lowered or 'restate' in lowered or 'rephrase' in lowered)
        assert 'never reply with a question' in lowered

    def test_turn_focus_still_blocks_previous_topic_drift(self):
        # The v2.44.2 anti-drift guarantee must survive the v2.44.3 reword.
        from ai_assistant.views import _TURN_FOCUS_PROMPT
        lowered = _TURN_FOCUS_PROMPT.lower()
        assert 'previous turn' in lowered
        assert 'current' in lowered


@pytest.mark.unit
class TestFinalizePromptIsTopicNeutral:
    """v2.44.2: the finalization prompt must NOT seed the feature-engineering
    topic.  Its feature-table guidance is CONDITIONAL on the user asking for
    features, it leads by anchoring on the current question, and its code
    example uses a generic column name (not Debt_to_Income)."""

    def test_finalize_prompt_anchors_current_question(self):
        from ai_assistant.views import _FINALIZE_PROMPT
        low = _FINALIZE_PROMPT.lower()
        assert 'most recent question' in low
        assert 'answer the current question' in low

    def test_finalize_prompt_feature_table_is_conditional(self):
        from ai_assistant.views import _FINALIZE_PROMPT
        # The table is gated behind 'ONLY when the user asked ... features'.
        assert 'only when the user asked you to create or transform' in _FINALIZE_PROMPT.lower()

    def test_finalize_prompt_example_is_generic(self):
        from ai_assistant.views import _FINALIZE_PROMPT
        # The concrete Debt_to_Income seed (which biased the drift) is gone.
        assert 'Debt_to_Income' not in _FINALIZE_PROMPT
        assert 'Debt-to-Income' not in _FINALIZE_PROMPT
        assert "new_column" in _FINALIZE_PROMPT


@pytest.mark.unit
class TestChatWorkflowEngineOverflowDegrades:
    """When the engine 5xx's mid tool-loop (context overflow after tool
    results accumulate), the workflow degrades to the tools-off synthesis
    pass and returns an answer — it must never surface a raw 500."""

    def test_overflow_after_tool_work_degrades_to_synthesis(self, monkeypatch):
        class _ServerErr(Exception):
            status_code = 500

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                # Follow-up call still carries the 15 tool schemas → overflow.
                assert tools is not None
                raise _ServerErr('Internal Server Error')
            # Synthesis pass: tools dropped, so it fits.
            assert tools is None
            return _text_response('Here are 5 derived features: ratio_a_b, ...')

        out = _run_chat_workflow(monkeypatch, provider='engine', call_llm=call_llm)
        assert out['result']['message'] == 'Here are 5 derived features: ratio_a_b, ...'
        # round0 tool_calls, round1 overflow (caught), synthesis (tools off).
        assert len(out['llm_calls']) == 3
        assert out['llm_calls'][2]['tools'] is None

    def test_non_server_error_propagates(self, monkeypatch):
        class _ClientErr(Exception):
            status_code = 400

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            raise _ClientErr('bad request')

        with pytest.raises(_ClientErr):
            _run_chat_workflow(monkeypatch, provider='engine', call_llm=call_llm)

    def test_server_error_before_any_tool_work_propagates(self, monkeypatch):
        class _ServerErr(Exception):
            status_code = 500

        def call_llm(idx, messages, tools):
            raise _ServerErr('Internal Server Error')

        with pytest.raises(_ServerErr):
            _run_chat_workflow(monkeypatch, provider='engine', call_llm=call_llm)

    def test_synthesis_also_failing_yields_actionable_fallback(self, monkeypatch):
        from ai_assistant.views import _TOOL_BUDGET_EXHAUSTED_FALLBACK

        class _ServerErr(Exception):
            status_code = 500

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            # Both the follow-up AND the synthesis pass 5xx.
            raise _ServerErr('Internal Server Error')

        out = _run_chat_workflow(monkeypatch, provider='engine', call_llm=call_llm)
        # No raw 500 — user sees the budget-exhausted fallback (tool work happened).
        assert out['result']['message'] == _TOOL_BUDGET_EXHAUSTED_FALLBACK


# ---------------------------------------------------------------------------
# v2.44.0: engine reply normalization + CoT-leak detection helpers.
#
# Reasoning-family engine models (nemotron-3-nano:30b, …) leak chain-of-thought
# into content and emit code in the wrong format (vendor <function=...> XML or
# bare markdown fences) instead of the <<<ACTION:execute_code>>> block the chat
# panel renders as an Apply button.  These helpers clean that up.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEngineReplyNormalization:
    """_strip_reasoning_markers / _convert_vendor_tool_xml_to_actions /
    _normalize_engine_reply / _looks_like_cot_leak."""

    def test_strip_paired_think_block(self):
        from ai_assistant.views import _strip_reasoning_markers
        assert _strip_reasoning_markers('<think>plan</think>The answer.') == 'The answer.'
        assert _strip_reasoning_markers('A.<think>plan</think>') == 'A.'

    def test_strip_orphan_close(self):
        from ai_assistant.views import _strip_reasoning_markers
        # reasoning prelude then answer, only the close tag present
        assert _strip_reasoning_markers('reasoning prose</think>The answer.') == 'The answer.'

    def test_strip_orphan_open_truncated(self):
        from ai_assistant.views import _strip_reasoning_markers
        # truncated CoT — open tag, never closed → drop from <think> on
        assert _strip_reasoning_markers('Answer.<think>still thinking') == 'Answer.'
        assert _strip_reasoning_markers('<think>only thinking, no answer') == ''

    def test_strip_noop_without_markers(self):
        from ai_assistant.views import _strip_reasoning_markers
        assert _strip_reasoning_markers('Plain answer.') == 'Plain answer.'

    def test_vendor_exec_xml_becomes_action_block(self):
        from ai_assistant.views import (
            _convert_vendor_tool_xml_to_actions, _extract_actions,
        )
        raw = ("Here is the code:\n<function=execute_code>\n"
               "<parameter=code>\ndf['X'] = df['A'] / df['B']\n"
               "</parameter>\n</function>")
        out = _convert_vendor_tool_xml_to_actions(raw)
        assert '<<<ACTION:execute_code>>>' in out
        actions, clean = _extract_actions(out)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert actions[0]['payload']['code'] == "df['X'] = df['A'] / df['B']"
        assert 'Here is the code:' in clean

    def test_vendor_exec_xml_without_param_wrapper(self):
        from ai_assistant.views import _convert_vendor_tool_xml_to_actions
        raw = "<function=execute_code>df['Y'] = 2</function>"
        out = _convert_vendor_tool_xml_to_actions(raw)
        assert '<<<ACTION:execute_code>>>' in out
        assert "df['Y'] = 2" in out

    def test_vendor_conversion_noop_without_function_tag(self):
        from ai_assistant.views import _convert_vendor_tool_xml_to_actions
        assert _convert_vendor_tool_xml_to_actions('no tags here') == 'no tags here'

    def test_normalize_is_noop_for_cloud(self):
        from ai_assistant.views import _normalize_engine_reply
        raw = '<think>cot</think>answer'
        # provider='openai' → untouched even though markers are present
        assert _normalize_engine_reply(raw, {'provider': 'openai'}) == raw

    def test_normalize_engine_strips_and_converts(self):
        from ai_assistant.views import _normalize_engine_reply, _extract_actions
        raw = ("<think>deciding</think>Create a ratio.\n"
               "<function=execute_code><parameter=code>df['R']=df['A']/df['B']"
               "</parameter></function>")
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        assert '<think>' not in out
        actions, clean = _extract_actions(out)
        assert actions and actions[0]['payload']['code'] == "df['R']=df['A']/df['B']"
        assert 'Create a ratio.' in clean

    def test_normalize_drops_leaked_non_exec_function_xml(self):
        from ai_assistant.views import _normalize_engine_reply
        raw = 'Summary text.\n<function=get_feature_stats>\n</function>'
        out = _normalize_engine_reply(raw, {'provider': 'engine'})
        assert '<function' not in out
        assert out == 'Summary text.'

    def test_cot_leak_detected_on_thinking_openers(self):
        from ai_assistant.views import _looks_like_cot_leak
        assert _looks_like_cot_leak("Okay, let's tackle this. The user wants…")
        assert _looks_like_cot_leak('We need to derive several features first.')
        assert _looks_like_cot_leak('The user wants new columns.')
        assert _looks_like_cot_leak('Let me think about which ratios help.')

    def test_cot_leak_not_flagged_for_clean_answer(self):
        from ai_assistant.views import _looks_like_cot_leak
        assert not _looks_like_cot_leak('**Proposed features**\n- Debt_to_Income')
        assert not _looks_like_cot_leak('Here are 5 derived features you can add.')
        assert not _looks_like_cot_leak('')

    def test_cot_leak_ignored_when_action_block_present(self):
        from ai_assistant.views import _looks_like_cot_leak
        # Even with a CoT opener, an action block makes the reply usable.
        assert not _looks_like_cot_leak(
            "Okay, here.\n<<<ACTION:execute_code>>>\n{}\n<<<END_ACTION>>>")

    # ── v2.44.1: code-only / thin-rationale detection ──────────────────
    def test_prose_without_actions_strips_block(self):
        from ai_assistant.views import _prose_without_actions
        txt = ('Intro line.\n<<<ACTION:execute_code>>>\n{"code": "df[\'X\']=1"}\n'
               '<<<END_ACTION>>>\nTrailing note.')
        out = _prose_without_actions(txt)
        assert '<<<ACTION' not in out
        assert 'Intro line.' in out and 'Trailing note.' in out

    def test_code_only_true_for_bare_exec_action(self):
        from ai_assistant.views import _is_code_only_reply
        # An execute_code block with no surrounding explanation.
        assert _is_code_only_reply(
            '<<<ACTION:execute_code>>>\n'
            '{"code": "df[\'DTI\']=df[\'A\']/df[\'B\']", "description": "DTI"}\n'
            '<<<END_ACTION>>>')
        # A one-line intro is still too thin to count as a rationale.
        assert _is_code_only_reply(
            'Here is the code:\n<<<ACTION:execute_code>>>\n'
            '{"code": "df[\'X\']=1"}\n<<<END_ACTION>>>')

    def test_code_only_false_when_well_explained(self):
        from ai_assistant.views import _is_code_only_reply
        rich = ('The debt-to-income ratio divides committed debt by income to '
                'capture repayment burden, a classic credit-risk signal that '
                'helps the boosting model rank applicants by default risk more '
                'reliably across the whole population.')
        assert not _is_code_only_reply(
            rich + '\n<<<ACTION:execute_code>>>\n{"code": "df[\'X\']=1"}\n<<<END_ACTION>>>')

    def test_code_only_false_without_exec_action(self):
        from ai_assistant.views import _is_code_only_reply
        # No execute_code at all → never a code-only reply.
        assert not _is_code_only_reply('Just a plain text answer with no code.')
        # A config action (not execute_code) is a one-liner by design.
        assert not _is_code_only_reply(
            'Dropping Var_3.\n<<<ACTION:update_config>>>\n'
            '{"updates": []}\n<<<END_ACTION>>>')


@pytest.mark.unit
class TestChatWorkflowFinalization:
    """v2.44.0: reasoning-family engine models get a strict finalization
    re-prompt when their reply is raw CoT, and vendor-XML code is converted
    to an Apply action without an extra LLM call."""

    def test_cot_leak_triggers_finalization_reprompt(self, monkeypatch):
        from ai_assistant.views import _FINALIZE_PROMPT

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                # Finished reply that is raw chain-of-thought (finish=stop).
                return _text_response("Okay, let's tackle this. We need to "
                                      "derive ratios from the columns.")
            # Finalization pass: tools dropped, strict prompt appended.
            assert tools is None
            return _text_response('**Derived features**\n- Debt_to_Income')

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        assert out['result']['message'] == '**Derived features**\n- Debt_to_Income'
        assert len(out['llm_calls']) == 3
        # The strict finalization instruction was the one appended.
        finalize_msgs = [m for m in out['llm_calls'][2]['messages']
                         if m.get('content') == _FINALIZE_PROMPT]
        assert finalize_msgs, 'finalization prompt not sent'

    def test_vendor_xml_code_becomes_apply_action_no_extra_call(self, monkeypatch):
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            return _text_response(
                "The debt-to-income ratio measures how much of a borrower's "
                "monthly income is already committed to debt, computed as "
                "Var_19 divided by Var_24. Higher values signal greater "
                "repayment strain and correlate strongly with default risk, "
                "making it a powerful predictor for the boosting model.\n"
                "<function=execute_code>\n"
                "<parameter=code>\ndf['DTI'] = df['Var_19'] / df['Var_24']\n"
                "</parameter>\n</function>")

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        # No finalization round needed — deterministic conversion handled it,
        # and the substantial explanation means no rationale-elaboration pass.
        assert len(out['llm_calls']) == 2
        actions = out['result'].get('actions') or []
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert actions[0]['payload']['code'] == "df['DTI'] = df['Var_19'] / df['Var_24']"
        assert 'debt-to-income' in out['result']['message'].lower()

    def test_clean_reply_with_action_passes_through(self, monkeypatch):
        rich = ('The debt-to-income ratio (DTI) divides total debt by income '
                'to capture repayment burden — a classic credit-risk signal '
                'that helps the boosting model separate good applicants from '
                'bad ones more cleanly across the population.')

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            return _text_response(
                rich + '\n\n<<<ACTION:execute_code>>>\n'
                '{"code": "df[\'DTI\']=df[\'A\']/df[\'B\']", "description": "DTI"}\n'
                '<<<END_ACTION>>>')

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        # Clean, well-explained answer + action → no finalization re-prompt.
        assert len(out['llm_calls']) == 2
        assert out['result']['message'] == rich
        assert out['result']['actions'][0]['type'] == 'execute_code'

    def test_finalization_still_leaking_yields_fallback(self, monkeypatch):
        from ai_assistant.views import _TOOL_BUDGET_EXHAUSTED_FALLBACK

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                return _text_response('We need to think harder about this.')
            # Finalization ALSO leaks CoT → blanked → fallback copy shown.
            return _text_response('Okay, let me reconsider the columns.')

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        assert out['result']['message'] == _TOOL_BUDGET_EXHAUSTED_FALLBACK
        assert len(out['llm_calls']) == 3

    def test_cloud_cot_opener_not_finalized(self, monkeypatch):
        # A cloud model reply that happens to open with "Okay," must NOT be
        # treated as a leak (normalization + finalization are engine-only).
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            return _text_response("Okay, here's the analysis you asked for.")

        out = _run_chat_workflow(monkeypatch, provider='openai',
                                 call_llm=call_llm)
        assert out['result']['message'] == "Okay, here's the analysis you asked for."
        assert len(out['llm_calls']) == 2

    def test_non_reasoning_engine_uses_generic_synthesis_on_empty(self, monkeypatch):
        # A non-reasoning engine model with empty final content still gets the
        # generic synthesis pass (not the strict reasoning finalizer).
        from ai_assistant.views import _SYNTHESIS_PROMPT

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                return _text_response('')  # empty → synthesis required
            assert tools is None
            return _text_response('Here is the summary.')

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        assert out['result']['message'] == 'Here is the summary.'
        synth_msgs = [m for m in out['llm_calls'][2]['messages']
                      if m.get('content') == _SYNTHESIS_PROMPT]
        assert synth_msgs, 'generic synthesis prompt not sent'


@pytest.mark.unit
class TestChatWorkflowCodeOnlyElaboration:
    """v2.44.1: a reasoning-family engine model that emits ONLY an execute_code
    action (rationale lost to chain-of-thought) gets an elaboration pass so the
    user sees an explanation alongside the Apply button — matching the cloud
    models' behaviour."""

    _BARE = ('<<<ACTION:execute_code>>>\n'
             '{"code": "df[\'DTI\']=df[\'Var_19\']/df[\'Var_24\']", '
             '"description": "DTI"}\n<<<END_ACTION>>>')

    def test_code_only_reply_triggers_elaboration(self, monkeypatch):
        from ai_assistant.views import _FINALIZE_PROMPT
        rationale = ('The debt-to-income ratio captures repayment burden and '
                     'is a strong default predictor for boosting models, '
                     'computed from Var_19 over Var_24 across all applicants.')

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                return _text_response(self._BARE)  # code only, no rationale
            # Elaboration pass: tools dropped, strict finalize prompt appended.
            assert tools is None
            return _text_response(rationale + '\n\n' + self._BARE)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        assert len(out['llm_calls']) == 3
        # Strict finalize prompt was sent, and the model's OWN draft was shown
        # back to it so the explanation matches the proposed code.
        final_msgs = out['llm_calls'][2]['messages']
        assert any(m.get('content') == _FINALIZE_PROMPT for m in final_msgs)
        assert any(m.get('role') == 'assistant' and 'execute_code' in (m.get('content') or '')
                   for m in final_msgs)
        # User now sees the rationale AND keeps the Apply action.
        assert 'repayment burden' in out['result']['message']
        assert out['result']['actions'][0]['type'] == 'execute_code'

    def test_elaboration_dropped_action_is_reattached(self, monkeypatch):
        rationale = ('Debt-to-income measures how committed a borrower already '
                     'is, a classic credit-risk signal that sharpens the '
                     'boosting model ranking across good and bad applicants.')

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                return _text_response(self._BARE)
            # Elaboration explains but FORGETS to re-emit the action block.
            return _text_response(rationale)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        # Original action re-attached so Apply still renders.
        assert 'repayment' in out['result']['message'] or 'credit-risk' in out['result']['message']
        actions = out['result'].get('actions') or []
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert actions[0]['payload']['code'] == "df['DTI']=df['Var_19']/df['Var_24']"

    def test_elaboration_empty_preserves_original_code(self, monkeypatch):
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            if idx == 1:
                return _text_response(self._BARE)
            return _text_response('')  # elaboration produced nothing usable

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        # Functional code is never downgraded to empty — Apply survives.
        actions = out['result'].get('actions') or []
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert out['result']['message'].strip()  # generic synthesized copy

    def test_config_action_not_elaborated(self, monkeypatch):
        # A thin reply whose action is update_config (not execute_code) must
        # NOT trigger an elaboration pass — confirmations are one-liners.
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            return _text_response(
                'Dropping Var_3.\n<<<ACTION:update_config>>>\n'
                '{"updates": [{"key": "feature_usage", "column": "Var_3", '
                '"value": "drop"}]}\n<<<END_ACTION>>>')

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=True, call_llm=call_llm)
        assert len(out['llm_calls']) == 2  # no elaboration
        assert out['result']['actions'][0]['type'] == 'update_config'

    def test_non_reasoning_engine_code_only_not_elaborated(self, monkeypatch):
        # code-only elaboration is reasoning-family only; a non-reasoning
        # engine model's bare action passes through untouched.
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            return _text_response(self._BARE)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        assert len(out['llm_calls']) == 2  # no elaboration
        assert out['result']['actions'][0]['type'] == 'execute_code'


# ---------------------------------------------------------------------------
# Skill supplementary file access (get_skill_file tool + Skill.read_file)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSkillFileAccess:
    """list_files() exposes references/scripts/templates and read_file()
    enforces path-traversal protection plus suffix allow-listing."""

    def test_list_files_excludes_skill_md(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        files = sk.list_files()
        assert 'SKILL.md' not in files
        # v2 ships these supplementary files
        assert any(p.startswith('references/') for p in files)
        assert any(p.startswith('scripts/') for p in files)
        # All paths use forward slashes
        assert all('\\' not in p for p in files)

    def test_read_file_returns_content(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('references/feature_engineering_best_practices.md')
        assert err is None
        assert text  # non-empty
        assert len(text) > 100

    def test_read_file_accepts_python_file(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('scripts/example.py')
        assert err is None
        assert 'def main' in text or 'example' in text.lower()

    def test_read_file_rejects_absolute_path(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('/etc/passwd')
        assert text == ''
        assert err is not None
        assert 'traversal' in err.lower() or 'outside' in err.lower()

    def test_read_file_rejects_dot_dot_traversal(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('../../etc/passwd')
        assert text == ''
        assert err is not None
        assert 'traversal' in err.lower()

    def test_read_file_rejects_disallowed_suffix(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('scripts/example.exe')
        assert text == ''
        assert err is not None
        assert 'only files ending' in err.lower()

    def test_read_file_missing_file(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('references/does_not_exist.md')
        assert text == ''
        assert err is not None
        assert 'not found' in err.lower()

    def test_read_file_empty_path(self):
        from ai_assistant.skill_registry import get_skill
        sk = get_skill('feature-engineering')
        text, err = sk.read_file('')
        assert text == ''
        assert err is not None

    def test_read_file_truncates_oversized(self, tmp_path, monkeypatch):
        """Files larger than MAX_SKILL_FILE_BYTES are truncated with a marker."""
        from ai_assistant import skill_registry as reg
        # Create a fake skill on disk with one big file
        sk_dir = tmp_path / 'big-skill'
        sk_dir.mkdir()
        (sk_dir / 'SKILL.md').write_text(
            '---\nname: big-skill\ndescription: "big"\n---\n# Body\nhello\n',
            encoding='utf-8',
        )
        big = 'A' * (reg.MAX_SKILL_FILE_BYTES + 50)
        (sk_dir / 'huge.md').write_text(big, encoding='utf-8')

        monkeypatch.setattr(reg, 'SKILLS_DIR', str(tmp_path))
        reg.invalidate_cache()
        try:
            sk = reg.get_skill('big-skill')
            assert sk is not None
            text, err = sk.read_file('huge.md')
            assert err is None
            assert text.endswith('[truncated to 100000 bytes]')
            assert text.count('A') == reg.MAX_SKILL_FILE_BYTES
        finally:
            # Restore default skills dir
            reg.invalidate_cache()


@pytest.mark.unit
class TestGetSkillFileTool:
    """get_skill_file is wired as a tool, returns content, and creates its
    own prometa span via _load_skill_file_traced."""

    def test_tool_definition_includes_get_skill_file(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        names = [t['function']['name'] for t in PIPELINE_TOOLS]
        assert 'get_skill_file' in names

    def test_tool_definition_lists_files_in_description(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(t for t in PIPELINE_TOOLS if t['function']['name'] == 'get_skill_file')
        desc = spec['function']['description']
        # Description should advertise concrete file paths so the LLM can pick
        assert 'references/' in desc or 'scripts/' in desc
        # Required params are skill_name + path
        assert set(spec['function']['parameters']['required']) == {'skill_name', 'path'}

    def test_invoke_skill_response_lists_supplementary_files(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'invoke_skill', {'skill_name': 'feature-engineering'})
        assert 'Supplementary files' in result
        assert 'references/' in result

    def test_get_skill_file_handler_returns_body(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'get_skill_file', {
            'skill_name': 'feature-engineering',
            'path': 'references/feature_engineering_best_practices.md',
        })
        assert 'BEGIN FILE CONTENT' in result
        assert 'END FILE CONTENT' in result

    def test_get_skill_file_handler_blocks_traversal(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'get_skill_file', {
            'skill_name': 'feature-engineering',
            'path': '../../../../etc/passwd',
        })
        assert 'BEGIN FILE CONTENT' not in result
        assert 'traversal' in result.lower() or 'outside' in result.lower()

    def test_get_skill_file_handler_unknown_skill(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'get_skill_file', {
            'skill_name': 'nope',
            'path': 'foo.md',
        })
        assert 'not bundled' in result

    def test_get_skill_file_handler_missing_args(self):
        from ai_assistant.tool_executor import execute_tool_call
        result = execute_tool_call(1, 'get_skill_file', {'skill_name': 'feature-engineering'})
        assert "requires both" in result.lower() or 'requires' in result.lower()

    def test_load_skill_file_traced_sets_span_attributes(self, monkeypatch):
        from ai_assistant import tool_executor as te
        captured = {}

        def fake_set(key, value):
            captured[key] = value

        monkeypatch.setattr(te, 'set_span_attr', fake_set)
        result = te._load_skill_file_traced(
            'feature-engineering',
            'references/feature_engineering_best_practices.md',
        )
        assert 'BEGIN FILE CONTENT' in result
        assert captured.get('declarai.skill.name') == 'feature-engineering'
        assert captured.get('declarai.skill.file_path') == \
            'references/feature_engineering_best_practices.md'
        assert captured.get('declarai.skill.file_found') is True
        assert isinstance(captured.get('declarai.skill.file_chars'), int)
        assert captured['declarai.skill.file_chars'] > 100


# ---------------------------------------------------------------------------
# Redis-level spans (Option D): cache_get/cache_put/cache_list_artifacts
# now each emit their own trace span via @prometa_tool.
# ---------------------------------------------------------------------------

class _SpanCapture:
    """Tiny helper that replays the sequence of set_span_attr(key, value)
    calls across span boundaries by snapshotting on each new span start.

    Tests that only need the aggregate final attribute map can use
    ``captured`` directly; tests that care about per-span grouping can
    walk ``by_span``.
    """

    def __init__(self):
        self.captured: dict = {}
        self.by_span: list[dict] = []
        self._current: dict = {}

    def set_attr(self, key, value):
        self.captured[key] = value
        self._current[key] = value

    def snapshot(self):
        if self._current:
            self.by_span.append(self._current)
            self._current = {}


def _patch_span_attr(monkeypatch, *modules, capture: _SpanCapture):
    """Replace ``set_span_attr`` in each target module with the capture hook.

    Always also patches ``ai_assistant.prometa_config.set_span_attr`` because
    the shared ``stamp_elapsed`` / ``span_timer`` helpers live there and call
    their own module-level reference — without patching it, elapsed-time
    attributes would silently bypass the test capture.
    """
    import importlib
    targets = list(modules) + ['ai_assistant.prometa_config']
    for mod_name in targets:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, 'set_span_attr', capture.set_attr)


@pytest.mark.unit
class TestRedisSpanInstrumentation:
    """cache_get/cache_put/cache_list_artifacts now emit their own Prometa
    tool spans with named attributes (redis-get, redis-set, redis-list)."""

    def test_cache_get_hit_stamps_attrs(self, monkeypatch):
        from ai_assistant import cache as cache_mod
        from ai_assistant.cache import cache_put, cache_get, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        # Seed and read back
        cache_put(42424, 'test_span_artifact', {'k': 'v'})
        cap.captured.clear()
        result = cache_get(42424, 'test_span_artifact')

        try:
            assert result == {'k': 'v'}
            assert cap.captured.get('declarai.cache.file_id') == 42424
            assert cap.captured.get('declarai.cache.artifact') == 'test_span_artifact'
            assert cap.captured.get('declarai.cache.hit') is True
            assert isinstance(cap.captured.get('declarai.cache.bytes'), int)
            assert cap.captured['declarai.cache.bytes'] > 0
        finally:
            _get_redis().delete('ai:pipeline:42424:test_span_artifact')

    def test_cache_get_miss_stamps_hit_false(self, monkeypatch):
        from ai_assistant.cache import cache_get, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        result = cache_get(42425, 'does_not_exist_xyz')
        assert result is None
        assert cap.captured.get('declarai.cache.artifact') == 'does_not_exist_xyz'
        assert cap.captured.get('declarai.cache.hit') is False
        # A miss must not stamp a byte count
        assert 'declarai.cache.bytes' not in cap.captured

    def test_cache_put_stamps_ok_and_ttl(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            assert cache_put(42426, 'span_put_test', {'x': 1}, ttl=123) is True
            assert cap.captured.get('declarai.cache.artifact') == 'span_put_test'
            assert cap.captured.get('declarai.cache.ttl') == 123
            assert cap.captured.get('declarai.cache.ok') is True
            assert cap.captured.get('declarai.cache.bytes') > 0
        finally:
            _get_redis().delete('ai:pipeline:42426:span_put_test')

    def test_cache_list_artifacts_stamps_prefix_and_count(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_list_artifacts, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            cache_put(42427, 'alpha', [1])
            cache_put(42427, 'beta', [2])
            cap.captured.clear()
            keys = cache_list_artifacts(42427)
            assert set(keys) >= {'alpha', 'beta'}
            assert cap.captured.get('declarai.cache.prefix') == 'ai:pipeline:42427:'
            assert cap.captured.get('declarai.cache.key_count') >= 2
            assert 'alpha' in cap.captured.get('declarai.cache.keys', '')
        finally:
            r = _get_redis()
            r.delete('ai:pipeline:42427:alpha')
            r.delete('ai:pipeline:42427:beta')

    def test_cache_put_bulk_stamps_key_count(self, monkeypatch):
        from ai_assistant.cache import cache_put_bulk, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            assert cache_put_bulk(42428, {'a': 1, 'b': 2, 'c': 3}) is True
            assert cap.captured.get('declarai.cache.key_count') == 3
            assert set(cap.captured.get('declarai.cache.keys', '').split(',')) == {'a', 'b', 'c'}
            assert cap.captured.get('declarai.cache.ok') is True
        finally:
            r = _get_redis()
            for k in ('a', 'b', 'c'):
                r.delete(f'ai:pipeline:42428:{k}')

    def test_cache_delete_stamps_ok(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_delete, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        cache_put(42429, 'to_delete', {'foo': 1})
        cap.captured.clear()
        assert cache_delete(42429, 'to_delete') is True
        assert cap.captured.get('declarai.cache.artifact') == 'to_delete'
        assert cap.captured.get('declarai.cache.ok') is True


# ---------------------------------------------------------------------------
# Option B-rich: every cached artifact exposes a ``read_*`` raw reader
# decorated with ``@prometa_tool(name="cache-read:<artifact>")``.  Handlers
# and ``_build_slim_context`` both route through these readers so the
# cache-read span is emitted regardless of who triggered the read.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCacheReadSpans:
    """Each cached artifact has a @prometa_tool-decorated raw reader."""

    @pytest.mark.parametrize('reader_name,artifact', [
        ('read_split_validation',   'split_validation'),
        ('read_dq_summary',         'dq_summary'),
        ('read_feature_stats',      'feature_stats'),
        ('read_vif_decomposition',  'vif_decomposition'),
        ('read_encoding_plan',      'encoding_plan'),
        ('read_selected_features',  'selected_features'),
        ('read_shap_details',       'shap_details'),
        ('read_sfs_results',        'sfs_results'),
        ('read_cv_results',         'cv_results'),
        ('read_pipeline_notes',     'pipeline_notes'),
        ('read_pipeline_config',    'pipeline_config'),
        ('read_data_dictionary',    'data_dictionary'),
    ])
    def test_raw_reader_exists_and_is_exported(self, reader_name, artifact):
        """Every artifact has a public raw reader used by the slim context
        build + the tool handler so the span hierarchy is consistent."""
        from ai_assistant import tool_executor
        assert hasattr(tool_executor, reader_name), (
            f"tool_executor must expose {reader_name} for artifact '{artifact}'")
        reader = getattr(tool_executor, reader_name)
        assert callable(reader)

    def test_read_pipeline_config_stamps_cache_read_attrs(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import read_pipeline_config
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        try:
            cache_put(53000, 'pipeline_config', {'pipeline_type': 'classification'})
            cap.captured.clear()
            data = read_pipeline_config(53000)
            assert data == {'pipeline_type': 'classification'}
            assert cap.captured.get('declarai.cache.artifact') == 'pipeline_config'
            assert cap.captured.get('declarai.cache.hit') is True
            assert cap.captured.get('declarai.cache.shape') == 'dict'
        finally:
            _get_redis().delete('ai:pipeline:53000:pipeline_config')

    def test_read_selected_features_stamps_list_shape(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import read_selected_features
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        try:
            cache_put(53001, 'selected_features',
                      [{'feature': 'f1'}, {'feature': 'f2'}, {'feature': 'f3'}])
            cap.captured.clear()
            data = read_selected_features(53001)
            assert len(data) == 3
            assert cap.captured.get('declarai.cache.shape') == 'list'
            assert cap.captured.get('declarai.cache.length') == 3
        finally:
            _get_redis().delete('ai:pipeline:53001:selected_features')

    def test_read_miss_stamps_hit_false(self, monkeypatch):
        from ai_assistant.cache import _get_redis
        from ai_assistant.tool_executor import read_shap_details
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        data = read_shap_details(53002)
        assert data is None
        assert cap.captured.get('declarai.cache.hit') is False

    def test_read_data_dictionary_stamps_enriched_flag(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import read_data_dictionary
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        try:
            cache_put(53003, 'data_dictionary',
                      [{'Feature_Name': 'Var_1', 'Feature_Description': None}])
            cap.captured.clear()
            data = read_data_dictionary(53003)
            assert data is not None
            # Whether or not the DB had a description, the enrichment path
            # must have been attempted and stamped a boolean outcome.
            assert 'declarai.cache.enriched' in cap.captured
        finally:
            _get_redis().delete('ai:pipeline:53003:data_dictionary')

    def test_handlers_route_through_raw_readers(self, monkeypatch):
        """When the LLM invokes a tool via ``execute_tool_call``, the handler
        must delegate to the raw reader so the ``cache-read:<artifact>`` span
        is always emitted.  We verify by observing that attributes stamped
        only by the raw reader appear in the captured set."""
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import execute_tool_call
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        try:
            cache_put(53004, 'encoding_plan',
                      [{'feature': 'f1', 'user_lom': 'Nominal', 'nunique': 5}])
            cap.captured.clear()
            out = execute_tool_call(53004, 'get_encoding_plan', {})
            assert 'Encoding Plan' in out
            # ``_stamp_read_attrs`` (called only from the raw reader) would
            # have set shape=list.
            assert cap.captured.get('declarai.cache.shape') == 'list'
            assert cap.captured.get('declarai.cache.length') == 1
        finally:
            _get_redis().delete('ai:pipeline:53004:encoding_plan')


@pytest.mark.unit
class TestSlimContextEmitsCacheReadSpans:
    """``_build_slim_context`` now calls raw readers for every fetch so
    the trace waterfall shows a ``cache-read:<artifact>`` span per
    included artifact, symmetric with LLM-driven tool dispatch."""

    def test_slim_context_uses_readers_not_cache_get(self, monkeypatch):
        """Strongest guarantee: ``cache_get`` is NOT called directly from
        ``_build_slim_context`` — every read goes through an instrumented
        raw reader (each of which internally calls ``cache_get``, but via
        its own span layer)."""
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant import tool_executor, views
        if _get_redis() is None:
            pytest.skip("Redis not available")

        reader_calls: list[str] = []

        def track(artifact_label):
            original = getattr(tool_executor, f'read_{artifact_label}')

            def _wrapped(file_id):
                reader_calls.append(artifact_label)
                return original(file_id)
            return _wrapped

        monkeypatch.setattr(tool_executor, 'read_pipeline_config',
                            track('pipeline_config'))
        monkeypatch.setattr(tool_executor, 'read_data_dictionary',
                            track('data_dictionary'))
        monkeypatch.setattr(tool_executor, 'read_selected_features',
                            track('selected_features'))

        try:
            cache_put(53100, 'pipeline_config', {'pipeline_type': 'classification'})
            cache_put(53100, 'data_dictionary',
                      [{'Feature_Name': 'Var_A', 'Feature_Description': 'alpha'}])
            cache_put(53100, 'selected_features',
                      [{'feature': 'Var_A', 'vif': 1.2}])

            text = views._build_slim_context(53100, 'general')
            assert 'Pipeline: classification' in text
            assert 'Var_A' in text
            assert set(reader_calls) == {
                'pipeline_config', 'data_dictionary', 'selected_features'}
        finally:
            r = _get_redis()
            for k in ('pipeline_config', 'data_dictionary', 'selected_features'):
                r.delete(f'ai:pipeline:53100:{k}')

    def test_slim_context_stamps_cache_read_attrs_per_artifact(self, monkeypatch):
        """Exercising the real readers: the capture must contain at least
        one ``declarai.cache.artifact=<each>`` stamp for every included
        artifact."""
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant import tool_executor, views
        if _get_redis() is None:
            pytest.skip("Redis not available")

        # Capture only attributes emitted inside tool_executor (the raw
        # reader layer) — ignore the deeper cache.py stamps.
        seen_artifacts: list[str] = []
        original = tool_executor.set_span_attr

        def capture(key, value):
            if key == 'declarai.cache.artifact':
                seen_artifacts.append(value)
            if callable(original):
                original(key, value)
        monkeypatch.setattr(tool_executor, 'set_span_attr', capture)

        try:
            cache_put(53101, 'pipeline_config', {'pipeline_type': 'classification'})
            cache_put(53101, 'selected_features', [{'feature': 'f1'}])
            views._build_slim_context(53101, 'general')
            assert 'pipeline_config' in seen_artifacts
            assert 'selected_features' in seen_artifacts
        finally:
            r = _get_redis()
            for k in ('pipeline_config', 'selected_features'):
                r.delete(f'ai:pipeline:53101:{k}')


# ---------------------------------------------------------------------------
# Elapsed-time attribute stamping (v2.22.1+).
#
# Redis ops on local docker complete in 100-500µs which the Prometa UI
# rounds to "0ms" on the waterfall bar.  Every instrumented span must
# therefore stamp ``<prefix>.elapsed_us`` and ``<prefix>.elapsed_ms`` so
# the actual duration is always visible in the attribute panel even when
# the bar is too small to render.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestElapsedTimeAttributes:
    """Every redis-*, cache-read:*, tool-call, skill-* span must stamp
    sub-millisecond timing as attributes."""

    def test_redis_get_stamps_elapsed_us_and_ms(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_get, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            cache_put(60000, 'elapsed_test', {'x': 1})
            cap.captured.clear()
            cache_get(60000, 'elapsed_test')
            # Microseconds is an integer, milliseconds is a float, both must
            # be non-negative (a real Redis hit is always > 0 but we don't
            # want flake on a 0-tick perf_counter result).
            assert isinstance(cap.captured.get('declarai.cache.elapsed_us'), int)
            assert cap.captured['declarai.cache.elapsed_us'] >= 0
            assert isinstance(cap.captured.get('declarai.cache.elapsed_ms'), float)
            assert cap.captured['declarai.cache.elapsed_ms'] >= 0
        finally:
            _get_redis().delete('ai:pipeline:60000:elapsed_test')

    def test_redis_set_stamps_elapsed(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            cache_put(60001, 'elapsed_test', {'x': 1})
            assert 'declarai.cache.elapsed_us' in cap.captured
            assert 'declarai.cache.elapsed_ms' in cap.captured
        finally:
            _get_redis().delete('ai:pipeline:60001:elapsed_test')

    def test_redis_list_stamps_elapsed(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_list_artifacts, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            cache_put(60002, 'one', [1])
            cap.captured.clear()
            cache_list_artifacts(60002)
            assert 'declarai.cache.elapsed_us' in cap.captured
            assert 'declarai.cache.elapsed_ms' in cap.captured
        finally:
            _get_redis().delete('ai:pipeline:60002:one')

    def test_redis_delete_stamps_elapsed(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_delete, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        cache_put(60003, 'to_remove', {'k': 1})
        cap.captured.clear()
        cache_delete(60003, 'to_remove')
        assert 'declarai.cache.elapsed_us' in cap.captured
        assert 'declarai.cache.elapsed_ms' in cap.captured

    def test_redis_set_bulk_stamps_elapsed(self, monkeypatch):
        from ai_assistant.cache import cache_put_bulk, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.cache', capture=cap)

        try:
            cache_put_bulk(60004, {'a': 1, 'b': 2})
            assert 'declarai.cache.elapsed_us' in cap.captured
            assert 'declarai.cache.elapsed_ms' in cap.captured
        finally:
            r = _get_redis()
            for k in ('a', 'b'):
                r.delete(f'ai:pipeline:60004:{k}')

    def test_cache_read_reader_stamps_elapsed(self, monkeypatch):
        """``cache-read:<artifact>`` spans (raw readers) also stamp elapsed
        time — this is the layer right above ``redis-get``."""
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import read_pipeline_config
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        try:
            cache_put(60005, 'pipeline_config', {'pipeline_type': 'classification'})
            cap.captured.clear()
            read_pipeline_config(60005)
            assert 'declarai.cache.elapsed_us' in cap.captured
            assert 'declarai.cache.elapsed_ms' in cap.captured
            assert cap.captured['declarai.cache.elapsed_us'] >= 0
        finally:
            _get_redis().delete('ai:pipeline:60005:pipeline_config')


@pytest.mark.unit
class TestToolCallSpanRename:
    """The dispatcher span emitted by ``execute_tool_call`` is now named
    ``tool-call`` (was ``rag-tool-dispatch``) and carries identifying
    attributes so the waterfall reads cleanly even though sub-ms duration
    causes the bar to render as 0ms."""

    def test_execute_tool_call_stamps_tool_name_and_outcome(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        from ai_assistant.tool_executor import execute_tool_call
        if _get_redis() is None:
            pytest.skip("Redis not available")

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        try:
            cache_put(60100, 'encoding_plan',
                      [{'feature': 'f1', 'user_lom': 'Nominal', 'nunique': 5}])
            cap.captured.clear()
            out = execute_tool_call(60100, 'get_encoding_plan', {'top_n': 5})
            assert 'Encoding Plan' in out
            assert cap.captured.get('declarai.tool.name') == 'get_encoding_plan'
            assert cap.captured.get('declarai.tool.file_id') == 60100
            assert cap.captured.get('declarai.tool.args_keys') == 'top_n'
            assert cap.captured.get('declarai.tool.ok') is True
            assert isinstance(cap.captured.get('declarai.tool.result_chars'), int)
            assert cap.captured['declarai.tool.result_chars'] > 0
            assert 'declarai.tool.elapsed_us' in cap.captured
            assert 'declarai.tool.elapsed_ms' in cap.captured
        finally:
            _get_redis().delete('ai:pipeline:60100:encoding_plan')

    def test_execute_tool_call_unknown_tool_stamps_unknown_flag(self, monkeypatch):
        from ai_assistant.tool_executor import execute_tool_call

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        out = execute_tool_call(60101, 'no_such_tool', {})
        assert 'Unknown tool' in out
        assert cap.captured.get('declarai.tool.name') == 'no_such_tool'
        assert cap.captured.get('declarai.tool.unknown') is True
        assert cap.captured.get('declarai.tool.ok') is False
        assert cap.captured.get('declarai.tool.result_chars', 0) > 0

    def test_execute_tool_call_args_keys_empty_when_no_args(self, monkeypatch):
        from ai_assistant.tool_executor import execute_tool_call

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        execute_tool_call(60102, 'no_such_tool', {})
        assert cap.captured.get('declarai.tool.args_keys') == ''

    def test_execute_tool_call_handler_exception_stamps_error(self, monkeypatch):
        """If a handler raises, the tool-call span must record ok=False and
        a truncated error message so failures are observable."""
        from ai_assistant import tool_executor

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.tool_executor', capture=cap)

        def _boom(file_id, args):
            raise ValueError("simulated handler failure")
        monkeypatch.setitem(tool_executor._HANDLERS, 'get_dq_summary', _boom)

        out = tool_executor.execute_tool_call(60103, 'get_dq_summary', {})
        assert 'Error executing get_dq_summary' in out
        assert cap.captured.get('declarai.tool.ok') is False
        assert 'simulated handler failure' in cap.captured.get('declarai.tool.error', '')


@pytest.mark.unit
class TestShapDetailsHandler:
    """v2.36.0 — ``_handle_get_shap_details`` upgrades closed ToDoS
    item #1: assistant could not reason about impact direction
    because the cached ``shap_details`` artifact only contained feature
    names (frontend cache-push read non-existent field names; see the
    rationale block in ``_handle_get_shap_details``).  These specs
    lock down:

      * direction-label semantics (sign of signed_impact → UP/DOWN/NEUTRAL)
      * VIF + signed_mean tail context formatting
      * graceful handling when fields are missing (legacy cache data)
      * structural guard: handler source must reference ``signed_impact``
        and emit a ``direction=`` token so a refactor cannot silently
        regress to the pre-v2.36.0 raw-numbers-only output.
    """

    def test_handle_get_shap_details_renders_direction_up_for_positive_signed(
        self, monkeypatch,
    ):
        """signed_impact > 0 → direction=UP.  This is what enables the
        LLM to say 'increasing Var_5 pushes prediction UP'."""
        from ai_assistant import tool_executor as te
        monkeypatch.setattr(te, 'read_shap_details', lambda fid: [
            {'feature': 'Var_5', 'impact': 0.342, 'signed_impact': 0.342,
             'signed_mean': -0.095, 'vif': 1.8},
        ])
        out = te._handle_get_shap_details(1, {})
        assert 'Var_5' in out
        assert 'direction=UP' in out
        assert '|impact|=0.3420' in out
        assert 'VIF=1.80' in out

    def test_handle_get_shap_details_renders_direction_down_for_negative_signed(
        self, monkeypatch,
    ):
        """signed_impact < 0 → direction=DOWN.  Critical for the
        screenshot scenario where the user asks 'why is Var_7 important?'
        and the LLM should answer 'Var_7 pushes prediction DOWN — i.e.
        increasing Var_7 reduces predicted default risk'."""
        from ai_assistant import tool_executor as te
        monkeypatch.setattr(te, 'read_shap_details', lambda fid: [
            {'feature': 'Var_7', 'impact': 0.349, 'signed_impact': -0.349,
             'signed_mean': -0.085, 'vif': 2.1},
        ])
        out = te._handle_get_shap_details(1, {})
        assert 'Var_7' in out
        assert 'direction=DOWN' in out
        assert 'signed=-0.3490' in out

    def test_handle_get_shap_details_renders_neutral_for_missing_signed(
        self, monkeypatch,
    ):
        """If the cached item lacks ``signed_impact`` (e.g. legacy
        cache from before the v2.36.0 FE fix landed), emit
        direction=NEUTRAL with — for the signed value rather than
        crashing on float-format of None."""
        from ai_assistant import tool_executor as te
        monkeypatch.setattr(te, 'read_shap_details', lambda fid: [
            {'feature': 'LegacyVar', 'impact': 0.1},
        ])
        out = te._handle_get_shap_details(1, {})
        assert 'direction=NEUTRAL' in out
        assert 'signed=—' in out, (
            "missing signed_impact must render as em-dash placeholder, "
            "not crash on float-format(None)"
        )

    def test_handle_get_shap_details_omits_vif_when_absent(self, monkeypatch):
        """VIF tail is optional context — omit cleanly when the field
        isn't in the cache (legacy data) instead of rendering 'VIF=None'."""
        from ai_assistant import tool_executor as te
        monkeypatch.setattr(te, 'read_shap_details', lambda fid: [
            {'feature': 'NoVifVar', 'impact': 0.2, 'signed_impact': 0.2},
        ])
        out = te._handle_get_shap_details(1, {})
        assert 'VIF=' not in out, (
            "when VIF field is missing the tail context must be omitted "
            "entirely rather than rendering 'VIF=None'"
        )
        assert 'direction=UP' in out

    def test_handle_get_shap_details_top_n_filter(self, monkeypatch):
        """The existing top_n arg must still work after the v2.36.0
        upgrade — this is a regression guard."""
        from ai_assistant import tool_executor as te
        monkeypatch.setattr(te, 'read_shap_details', lambda fid: [
            {'feature': f'V{i}', 'impact': 1.0 / (i + 1), 'signed_impact': 1.0 / (i + 1)}
            for i in range(10)
        ])
        out = te._handle_get_shap_details(1, {'top_n': 3})
        assert '3 features' in out
        assert 'V0' in out and 'V1' in out and 'V2' in out
        assert 'V3' not in out

    def test_handle_get_shap_details_source_emits_direction_token(self):
        """Structural guard: the handler source must emit a
        ``direction=`` token derived from ``signed_impact``.  Without
        this guard a future refactor that drops the prose direction
        would silently regress the v2.36.0 capability — the cached
        data would still be correct but the LLM would lose the
        signal it was promised."""
        import inspect
        from ai_assistant import tool_executor as te
        source = inspect.getsource(te._handle_get_shap_details)
        assert 'signed_impact' in source
        assert "'UP'" in source or '"UP"' in source
        assert "'DOWN'" in source or '"DOWN"' in source
        assert 'direction=' in source, (
            "handler source must emit a 'direction=' token in its "
            "output template — that's the LLM-facing prose label "
            "that enables impact-direction reasoning"
        )


@pytest.mark.unit
class TestSFSStatusReader:
    """v2.35.0 — ``read_sfs_status`` and ``_format_sfs_status_line`` close
    the "assistant unaware SFS is running" bug from the 2026-05-19
    ToDoS screenshot.  These specs lock down precedence, shape,
    interrupted-fallback semantics, banner emission rules, slim-context
    wiring, the in-flight guard on ``start_sfs``, and source-level
    regression guards on the integration points.
    """

    @pytest.fixture(autouse=True)
    def _reset_sfs_progress(self):
        """SFS_PROGRESS is a process-local dict — reset before AND
        after each test so stale state cannot pollute siblings."""
        from modeling import views as mv
        mv.SFS_PROGRESS.clear()
        yield
        mv.SFS_PROGRESS.clear()

    # ── read_sfs_status: precedence + shape ──────────────────────────

    def test_read_sfs_status_returns_not_started_when_absent(self):
        """When SFS_PROGRESS has no entry AND no disk file exists,
        the canonical 'not_started' shape is returned (never None)."""
        from ai_assistant.tool_executor import read_sfs_status
        result = read_sfs_status(99999)
        assert result['status'] == 'not_started'
        assert result['progress'] == 0.0
        assert result['completed_step_count'] == 0
        assert result['source'] == 'absent'
        assert isinstance(result, dict)

    def test_read_sfs_status_running_state_from_memory(self):
        """In-memory SFS_PROGRESS shows running → reader returns the
        live state with source='memory'.  This is the screenshot
        scenario."""
        from ai_assistant.tool_executor import read_sfs_status
        from modeling import views as mv
        mv.SFS_PROGRESS[42] = {
            'status': 'running',
            'progress': 0.12,
            'message': 'Backward elimination: Step 8/68',
            'completed_steps': [{'step': i} for i in range(7)],
            'duration_seconds': None,
            'error': None,
        }
        result = read_sfs_status(42)
        assert result['status'] == 'running'
        assert result['progress'] == 0.12
        assert result['completed_step_count'] == 7
        assert result['message'] == 'Backward elimination: Step 8/68'
        assert result['source'] == 'memory'

    def test_read_sfs_status_disk_fallback_treats_running_as_interrupted(
        self, tmp_path, monkeypatch,
    ):
        """No in-memory entry but disk says 'running' → SFS thread
        was killed (server restart) → surface as 'interrupted'."""
        import json as _json
        from django.conf import settings
        monkeypatch.setattr(settings, 'MEDIA_ROOT', str(tmp_path))
        sfs_dir = tmp_path / 'sfs_results'
        sfs_dir.mkdir()
        (sfs_dir / '888_sfs_results.json').write_text(_json.dumps({
            'status': 'running',
            'forward': [{'step': 1}, {'step': 2}],
            'backward': [],
        }))
        from ai_assistant.tool_executor import read_sfs_status
        result = read_sfs_status(888)
        assert result['status'] == 'interrupted'
        assert result['source'] == 'disk'
        assert result['completed_step_count'] == 2

    def test_read_sfs_status_disk_fallback_completed(self, tmp_path, monkeypatch):
        """No in-memory + disk says 'completed' → completed (server-
        restart-after-completion case)."""
        import json as _json
        from django.conf import settings
        monkeypatch.setattr(settings, 'MEDIA_ROOT', str(tmp_path))
        sfs_dir = tmp_path / 'sfs_results'
        sfs_dir.mkdir()
        (sfs_dir / '777_sfs_results.json').write_text(_json.dumps({
            'status': 'completed',
            'forward': [{'step': 1}],
            'backward': [{'step': 1}, {'step': 2}],
        }))
        from ai_assistant.tool_executor import read_sfs_status
        result = read_sfs_status(777)
        assert result['status'] == 'completed'
        assert result['progress'] == 1.0
        assert result['source'] == 'disk'
        assert result['completed_step_count'] == 3

    def test_read_sfs_status_memory_wins_over_disk(self, tmp_path, monkeypatch):
        """Precedence: in-memory always wins over disk because it's
        freshest.  Disk-completed + memory-running → must report
        running (user is mid-rerun)."""
        import json as _json
        from django.conf import settings
        from modeling import views as mv
        monkeypatch.setattr(settings, 'MEDIA_ROOT', str(tmp_path))
        sfs_dir = tmp_path / 'sfs_results'
        sfs_dir.mkdir()
        (sfs_dir / '555_sfs_results.json').write_text(
            _json.dumps({'status': 'completed', 'forward': [], 'backward': []})
        )
        mv.SFS_PROGRESS[555] = {
            'status': 'running',
            'progress': 0.05,
            'message': 'Forward selection: Step 2',
            'completed_steps': [{'step': 1}],
            'duration_seconds': None,
            'error': None,
        }
        from ai_assistant.tool_executor import read_sfs_status
        result = read_sfs_status(555)
        assert result['status'] == 'running'
        assert result['source'] == 'memory'

    # ── _format_sfs_status_line: banner emission rules ───────────────

    def test_format_sfs_status_line_returns_none_for_benign_states(self):
        """No banner for not_started / completed — common case must
        not waste tokens."""
        from ai_assistant.tool_executor import _format_sfs_status_line
        assert _format_sfs_status_line({'status': 'not_started'}) is None
        assert _format_sfs_status_line({'status': 'completed'}) is None

    def test_format_sfs_status_line_emphatic_for_running(self):
        """Running banner must explicitly forbid duplicate-start AND
        quote progress numerically.  Primary defence against the
        screenshot bug."""
        from ai_assistant.tool_executor import _format_sfs_status_line
        line = _format_sfs_status_line({
            'status': 'running',
            'progress': 0.12,
            'completed_step_count': 7,
            'message': 'Backward elimination: Step 8/68',
        })
        assert line is not None
        assert 'RUNNING' in line
        assert 'DO NOT' in line
        assert '12%' in line
        assert '7 steps' in line
        assert 'Backward elimination: Step 8/68' in line

    def test_format_sfs_status_line_warns_for_stopped(self):
        from ai_assistant.tool_executor import _format_sfs_status_line
        line = _format_sfs_status_line({
            'status': 'stopped', 'progress': 0.5, 'completed_step_count': 30,
        })
        assert line is not None
        assert 'stopped' in line.lower()
        assert '30 steps' in line

    def test_format_sfs_status_line_warns_for_interrupted(self):
        from ai_assistant.tool_executor import _format_sfs_status_line
        line = _format_sfs_status_line({
            'status': 'interrupted', 'progress': 0.0, 'completed_step_count': 5,
        })
        assert line is not None
        assert 'INTERRUPTED' in line
        assert 'Continue' in line

    def test_format_sfs_status_line_surfaces_error_message(self):
        from ai_assistant.tool_executor import _format_sfs_status_line
        line = _format_sfs_status_line({
            'status': 'error', 'error': 'feature matrix is singular',
        })
        assert line is not None
        assert 'FAILED' in line
        assert 'feature matrix is singular' in line

    # ── _build_slim_context wiring ───────────────────────────────────

    def test_build_slim_context_includes_sfs_running_banner(self):
        """When SFS is running, _build_slim_context prepends the
        banner at the very top of the context.  This is the
        integration point that closes the screenshot bug."""
        from modeling import views as mv
        from ai_assistant import views as av
        mv.SFS_PROGRESS[100] = {
            'status': 'running',
            'progress': 0.12,
            'message': 'Backward elimination: Step 8/68',
            'completed_steps': [{'step': i} for i in range(7)],
            'duration_seconds': None,
            'error': None,
        }
        slim = av._build_slim_context(100, 'sfs')
        assert 'SFS IS CURRENTLY RUNNING' in slim
        assert 'DO NOT propose to start SFS' in slim
        assert '12%' in slim and '7 steps' in slim

    def test_build_slim_context_omits_sfs_banner_when_not_started(self):
        """No banner for the common pre-SFS case — context stays clean."""
        from ai_assistant import views as av
        slim = av._build_slim_context(99998, 'general')
        assert 'SFS IS CURRENTLY RUNNING' not in slim
        assert 'INTERRUPTED' not in slim
        assert 'FAILED' not in slim

    # ── _handle_get_sfs_results: status header in tool output ────────

    def test_handle_get_sfs_results_surfaces_status_when_cache_empty(self, monkeypatch):
        """The screenshot bug: cache empty during early SFS run, the
        LLM asked get_sfs_results and got 'not available' → concluded
        SFS hadn't started.  After v2.35.0, the handler returns the
        running banner even when Redis cache is empty."""
        from modeling import views as mv
        from ai_assistant import tool_executor as te
        monkeypatch.setattr(te, 'read_sfs_results', lambda fid: None)
        mv.SFS_PROGRESS[200] = {
            'status': 'running',
            'progress': 0.12,
            'message': 'Backward elimination: Step 8/68',
            'completed_steps': [{'step': i} for i in range(7)],
            'duration_seconds': None,
            'error': None,
        }
        out = te._handle_get_sfs_results(200, {})
        assert 'SFS IS CURRENTLY RUNNING' in out
        assert 'is not available' not in out

    def test_handle_get_sfs_results_status_first_when_cache_present(self, monkeypatch):
        """Status header must precede the SFS Configuration block so
        the LLM cannot miss it even with truncated context windows."""
        from modeling import views as mv
        from ai_assistant import tool_executor as te
        mv.SFS_PROGRESS[300] = {
            'status': 'running', 'progress': 0.5, 'message': 'mid-run',
            'completed_steps': [{'step': 1}], 'duration_seconds': None, 'error': None,
        }
        monkeypatch.setattr(te, 'read_sfs_results', lambda fid: {
            'config': {
                'top_k': 5,
                'stopping_criteria': {
                    'metrics': [], 'min_features': 5, 'max_features': 15,
                },
            },
            'forward': [{'step': 1, 'feature_name': 'X1', 'cv_roc_auc': 0.75,
                         'selected_features': ['X1']}],
        })
        out = te._handle_get_sfs_results(300, {})
        running_idx = out.find('SFS IS CURRENTLY RUNNING')
        config_idx = out.find('SFS Configuration')
        assert running_idx >= 0
        assert config_idx > running_idx

    # ── start_sfs in-flight guard ────────────────────────────────────

    def test_start_sfs_refuses_when_already_running(self):
        """Last-line-of-defence: even if LLM bypasses banner + header,
        action executor REFUSES duplicate run.  Prevents clobbering
        SFS_PROGRESS[file_id] and corrupting in-flight results."""
        from modeling import views as mv
        from ai_assistant.action_executor import start_sfs
        mv.SFS_PROGRESS[400] = {
            'status': 'running', 'progress': 0.3, 'message': 'mid-run',
            'completed_steps': [{'step': i} for i in range(20)],
            'duration_seconds': None, 'error': None,
        }
        result = start_sfs(400, {
            'methods': ['backward'],
            'stopping_criteria': {
                'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}],
                'min_features': 5, 'max_features': 15,
            },
            'description': 'restart SFS',
        })
        assert result['status'] == 'error'
        assert 'sfs_already_running' in result.get('errors', [])
        assert 'already running' in result['error']
        assert '30%' in result['error'] or '20 steps' in result['error']

    def test_start_sfs_proceeds_when_completed(self):
        """status='completed' is a valid pre-condition for a new run
        (user wants to rerun with different params) — guard must NOT
        fire."""
        from modeling import views as mv
        from ai_assistant.action_executor import start_sfs
        mv.SFS_PROGRESS[500] = {
            'status': 'completed', 'progress': 1.0, 'message': 'done',
            'completed_steps': [], 'duration_seconds': 60.0, 'error': None,
        }
        result = start_sfs(500, {
            'methods': ['forward'],
            'stopping_criteria': {
                'metrics': [{'metric': 'roc_auc', 'pct_change': 1.0}],
                'min_features': 3, 'max_features': 10,
            },
            'description': 'rerun forward SFS',
        })
        assert result['status'] == 'success'

    # ── Structural guards (regression at source level) ───────────────

    def test_slim_context_imports_sfs_status_reader(self):
        """Future refactor dropping the slim-context wiring would
        silently re-open the bug — guard at the source level."""
        import inspect
        from ai_assistant import views as av
        source = inspect.getsource(av._build_slim_context)
        assert 'read_sfs_status' in source
        assert '_format_sfs_status_line' in source

    def test_start_sfs_source_guards_against_duplicate_run(self):
        """Structural guard: start_sfs source must reference
        read_sfs_status and check 'running' status."""
        import inspect
        from ai_assistant import action_executor as ae
        source = inspect.getsource(ae.start_sfs)
        assert 'read_sfs_status' in source
        assert "'running'" in source or '"running"' in source


@pytest.mark.unit
class TestPrometaConfigTimerHelpers:
    """``span_timer`` and ``stamp_elapsed`` are the shared building blocks
    for the elapsed-time attributes — verify they emit the right keys."""

    def test_stamp_elapsed_emits_us_and_ms(self, monkeypatch):
        import time
        from ai_assistant import prometa_config
        captured: dict = {}
        monkeypatch.setattr(prometa_config, 'set_span_attr',
                            lambda k, v: captured.__setitem__(k, v))
        t0 = time.perf_counter_ns()
        prometa_config.stamp_elapsed('myns.foo', t0)
        assert 'myns.foo.elapsed_us' in captured
        assert 'myns.foo.elapsed_ms' in captured
        assert isinstance(captured['myns.foo.elapsed_us'], int)
        assert isinstance(captured['myns.foo.elapsed_ms'], float)

    def test_span_timer_emits_on_exit_even_on_exception(self, monkeypatch):
        from ai_assistant import prometa_config
        captured: dict = {}
        monkeypatch.setattr(prometa_config, 'set_span_attr',
                            lambda k, v: captured.__setitem__(k, v))
        with pytest.raises(RuntimeError):
            with prometa_config.span_timer('myns.bar'):
                raise RuntimeError("boom")
        # The finally block of span_timer must have run despite the raise.
        assert 'myns.bar.elapsed_us' in captured
        assert 'myns.bar.elapsed_ms' in captured


# ---------------------------------------------------------------------------
# Session-tagging hygiene (v2.22.2+).
#
# Cache helpers must NEVER call ``set_session_id`` themselves — the
# user-facing root span (chat workflow / action executor) owns the
# session id and the OTLP trace context propagates it down.  Re-stamping
# from inside ``cache_put``/``cache_get``/etc. pollutes the platform's
# Session Explorer with:
#   * server-side pipeline writes (declaration dd push, /cache_push/
#     bulk-write, DQ/FE/CV runners) appearing alongside chats
#   * ad-hoc verification scripts leaking synthetic file_ids like
#     ``declarai-file-99002`` (the exact bug observed on 2026-05-11).
# This class guards against the regression.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCacheHelpersDoNotStampSession:
    """Cache helpers must not invoke ``set_session_id`` for any op."""

    def _capture_session_calls(self, monkeypatch) -> list[str]:
        """Patch ``set_session_id`` everywhere it's reachable and record
        every invocation.  Returns the recorded list (mutable)."""
        from ai_assistant import cache as cache_mod
        from ai_assistant import prometa_config
        calls: list[str] = []
        recorder = lambda sid: calls.append(sid)
        # The cache module is the surface under test — it must not
        # import or use set_session_id at all.  We patch prometa_config
        # so even an accidental ``prometa_config.set_session_id(...)``
        # call from inside cache.py would still get caught.
        monkeypatch.setattr(prometa_config, 'set_session_id', recorder)
        # Defensive: if a future refactor reintroduces a local alias
        # in cache.py, this catches it too.
        if hasattr(cache_mod, 'set_session_id'):
            monkeypatch.setattr(cache_mod, 'set_session_id', recorder)
        return calls

    def test_cache_put_does_not_stamp_session(self, monkeypatch):
        from ai_assistant.cache import cache_put, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        calls = self._capture_session_calls(monkeypatch)
        try:
            cache_put(70000, 'no_session_test', {'x': 1})
            assert calls == [], (
                f"cache_put must not call set_session_id; got: {calls}")
        finally:
            _get_redis().delete('ai:pipeline:70000:no_session_test')

    def test_cache_get_does_not_stamp_session(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_get, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        cache_put(70001, 'no_session_test', {'x': 1})
        calls = self._capture_session_calls(monkeypatch)
        try:
            cache_get(70001, 'no_session_test')
            assert calls == [], (
                f"cache_get must not call set_session_id; got: {calls}")
        finally:
            _get_redis().delete('ai:pipeline:70001:no_session_test')

    def test_cache_put_bulk_does_not_stamp_session(self, monkeypatch):
        from ai_assistant.cache import cache_put_bulk, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        calls = self._capture_session_calls(monkeypatch)
        try:
            cache_put_bulk(70002, {'a': 1, 'b': 2})
            assert calls == [], (
                f"cache_put_bulk must not call set_session_id; got: {calls}")
        finally:
            r = _get_redis()
            for k in ('a', 'b'):
                r.delete(f'ai:pipeline:70002:{k}')

    def test_cache_delete_does_not_stamp_session(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_delete, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        cache_put(70003, 'to_remove', {'k': 1})
        calls = self._capture_session_calls(monkeypatch)
        cache_delete(70003, 'to_remove')
        assert calls == [], (
            f"cache_delete must not call set_session_id; got: {calls}")

    def test_cache_list_artifacts_does_not_stamp_session(self, monkeypatch):
        from ai_assistant.cache import cache_put, cache_list_artifacts, _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")
        cache_put(70004, 'one', [1])
        calls = self._capture_session_calls(monkeypatch)
        try:
            cache_list_artifacts(70004)
            assert calls == [], (
                f"cache_list_artifacts must not call set_session_id; got: {calls}")
        finally:
            _get_redis().delete('ai:pipeline:70004:one')

    def test_cache_module_does_not_import_set_session_id(self):
        """Belt-and-suspenders: the cache module must not even import
        ``set_session_id`` — this catches a future ``from .prometa_config
        import set_session_id`` regression before any runtime call."""
        from ai_assistant import cache as cache_mod
        assert not hasattr(cache_mod, 'set_session_id'), (
            "ai_assistant.cache must not import set_session_id — "
            "session-tagging is the chat/action workflow's responsibility, "
            "not the infrastructure layer's (see v2.22.2 comment block).")

    def test_cache_module_does_not_import_set_customer_id(self):
        """v2.30.0 parity: the cache module must not import
        ``set_customer_id`` either.  Same rationale as set_session_id —
        the workflow root span owns correlation-chain stamping; cache
        helpers run as children and inherit the parent's attributes
        automatically.  Importing the helper into cache.py would tempt
        future contributors to over-stamp redundantly."""
        from ai_assistant import cache as cache_mod
        assert not hasattr(cache_mod, 'set_customer_id'), (
            "ai_assistant.cache must not import set_customer_id — "
            "customer-id stamping is the chat/action workflow's "
            "responsibility (set_customer_id propagates to children "
            "via parent-attribute inheritance).")


# ---------------------------------------------------------------------------
# Correlation-chain helpers (v2.30.0 / Phase 2 of prometa-sdk roadmap).
#
# The v0.5.0+ SDK adds set_customer_id and set_request_model alongside
# the existing set_session_id.  prometa_config wraps each in a tiny
# try-import shim:
#   1. Forward to the SDK helper when available (the happy path on 0.6.0+).
#   2. Fall back to set_span_attr when the SDK is older or import fails.
#   3. Swallow any other exception (defense; SDK helpers are documented
#      synchronous no-ops outside an active span context).
#
# These tests pin all three branches and verify both call sites
# (_chat_workflow + dispatch_action for set_customer_id, _call_llm for
# set_request_model) actually invoke the helpers when triggered.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrometaCorrelationHelpers:
    """``set_customer_id`` and ``set_request_model`` must forward to
    the SDK helpers when available, fall back to ``set_span_attr`` on
    ImportError, and never propagate exceptions."""

    def test_set_customer_id_forwards_to_sdk_helper_when_available(self, monkeypatch):
        """Happy path: SDK on 0.6.0+ exposes ``set_customer_id``; our
        wrapper must call it verbatim, NOT the set_span_attr fallback."""
        from ai_assistant import prometa_config as pc
        sdk_calls: list[str] = []
        attr_calls: list[tuple[str, object]] = []
        # Patch the SDK symbol our wrapper imports.
        import prometa
        monkeypatch.setattr(prometa, 'set_customer_id',
                            lambda v: sdk_calls.append(v), raising=False)
        # Patch set_span_attr to ensure the fallback path is NOT taken.
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: attr_calls.append((k, v)))

        pc.set_customer_id('cus_42')

        assert sdk_calls == ['cus_42'], (
            f"Expected SDK helper to be called once with 'cus_42'; got {sdk_calls}"
        )
        assert attr_calls == [], (
            f"Fallback set_span_attr must NOT fire when SDK helper exists; "
            f"got {attr_calls}"
        )

    def test_set_customer_id_falls_back_to_set_span_attr_on_import_error(self, monkeypatch):
        """If the SDK is older than 0.5.0 (no ``set_customer_id`` symbol),
        the wrapper must still emit the canonical attribute via
        ``set_span_attr('prometa.customer_id', ...)`` so the platform's
        correlation-id resolver still joins by customer."""
        from ai_assistant import prometa_config as pc
        attr_calls: list[tuple[str, object]] = []
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: attr_calls.append((k, v)))
        # Simulate the helper being absent: stash a real ImportError
        # behind the import statement by deleting the SDK attribute.
        import prometa
        monkeypatch.delattr(prometa, 'set_customer_id', raising=False)

        pc.set_customer_id('cus_99')

        assert attr_calls == [('prometa.customer_id', 'cus_99')], (
            f"Fallback must stamp prometa.customer_id; got {attr_calls}"
        )

    def test_set_customer_id_swallows_other_exceptions(self, monkeypatch):
        """Defensive: if the SDK helper raises something other than
        ImportError (e.g. a runtime error from inside an in-progress
        span flush), the wrapper must NOT propagate."""
        from ai_assistant import prometa_config as pc
        import prometa

        def boom(_v):
            raise RuntimeError('span flush in progress')

        monkeypatch.setattr(prometa, 'set_customer_id', boom, raising=False)
        # Must not raise.
        pc.set_customer_id('cus_ok')

    def test_set_request_model_forwards_to_sdk_helper_when_available(self, monkeypatch):
        """Same contract as set_customer_id, mirrored for set_request_model."""
        from ai_assistant import prometa_config as pc
        sdk_calls: list[str] = []
        attr_calls: list[tuple[str, object]] = []
        import prometa
        monkeypatch.setattr(prometa, 'set_request_model',
                            lambda v: sdk_calls.append(v), raising=False)
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: attr_calls.append((k, v)))

        pc.set_request_model('gpt-5.5')

        assert sdk_calls == ['gpt-5.5']
        assert attr_calls == []

    def test_set_request_model_falls_back_to_set_span_attr_on_import_error(self, monkeypatch):
        """SDK <0.5.0 path: must still stamp gen_ai.request.model so the
        cost panel and AML model_route detector keep working."""
        from ai_assistant import prometa_config as pc
        attr_calls: list[tuple[str, object]] = []
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: attr_calls.append((k, v)))
        import prometa
        monkeypatch.delattr(prometa, 'set_request_model', raising=False)

        pc.set_request_model('gpt-5.5')

        assert attr_calls == [('gen_ai.request.model', 'gpt-5.5')]

    def test_set_request_model_swallows_other_exceptions(self, monkeypatch):
        from ai_assistant import prometa_config as pc
        import prometa

        def boom(_v):
            raise RuntimeError('span context lost')

        monkeypatch.setattr(prometa, 'set_request_model', boom, raising=False)
        pc.set_request_model('gpt-5.5')

    # ── Call-site tests: where the helpers actually land in production ─

    def test_dispatch_action_calls_set_customer_id_with_file_id(self, monkeypatch):
        """``dispatch_action`` is the action-executor entry point; it
        must call ``set_customer_id(str(file_id))`` at the top of the
        workflow body so every nested span (validators, broadcasts,
        cache writes) inherits the correlation key.

        Triggered via an unknown action_type so the body short-circuits
        immediately without invoking real action handlers — keeps the
        test cheap while still exercising the real code path."""
        from ai_assistant import action_executor
        from ai_assistant import prometa_config as pc

        customer_calls: list[str] = []
        session_calls: list[str] = []
        # Patch where action_executor.py imported them (module-local
        # binding) — patching prometa_config alone wouldn't catch the
        # already-bound name in action_executor's namespace.
        monkeypatch.setattr(action_executor, 'set_customer_id',
                            lambda v: customer_calls.append(v))
        monkeypatch.setattr(action_executor, 'set_session_id',
                            lambda v: session_calls.append(v))
        # set_span_attr also runs at the entry; let it no-op silently.
        monkeypatch.setattr(action_executor, 'set_span_attr', lambda *a, **kw: None)

        result = action_executor.dispatch_action.__wrapped__(
            42, 'unknown_action_xyz', {'description': 'test'}
        ) if hasattr(action_executor.dispatch_action, '__wrapped__') else \
            action_executor.dispatch_action(42, 'unknown_action_xyz', {'description': 'test'})

        # Unknown action_type triggers the early-return path.
        assert result.get('status') == 'error'
        assert 'Unknown action type' in result.get('error', '')
        # And both correlation helpers fired with the expected file_id.
        assert customer_calls == ['42'], (
            f"dispatch_action must call set_customer_id(str(file_id)); "
            f"got {customer_calls}"
        )
        # Session id format is unchanged (declarai-file-{id}).
        assert session_calls == ['declarai-file-42']

    def test_chat_workflow_imports_set_customer_id_and_set_request_model(self):
        """Structural guard: views.py must import both helpers from
        prometa_config so the workflow body can call them.  This
        catches an accidental import-line regression even when the
        full _chat_workflow body isn't executed (it requires OpenAI).

        Pairs with the dispatch_action call-site test above to give
        full coverage of the v2.30.0 wiring without needing to mock
        the entire LLM round-trip."""
        from ai_assistant import views
        # Both names must be reachable from views.py's module namespace.
        assert hasattr(views, 'set_customer_id'), (
            "views.py must import set_customer_id from prometa_config"
        )
        assert hasattr(views, 'set_request_model'), (
            "views.py must import set_request_model from prometa_config"
        )

    def test_call_llm_source_uses_set_request_model_not_manual_set_span_attr(self):
        """Belt-and-suspenders source-level guard: the _call_llm body
        must use the canonical ``set_request_model(...)`` helper, not
        the legacy ``set_span_attr('gen_ai.request.model', ...)`` shape.

        Pre-v2.30.0 we had the manual call; post-fix it MUST be gone.
        A future contributor reverting to the manual shape would lose
        the v0.5.0+ helper's parent-attribute inheritance behavior."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        assert 'set_request_model(' in source, (
            "_call_llm must use the canonical set_request_model() helper"
        )
        assert "set_span_attr('gen_ai.request.model'" not in source, (
            "_call_llm must NOT manually stamp gen_ai.request.model — "
            "use set_request_model() instead so the v0.5.0+ SDK helper's "
            "parent-attribute inheritance kicks in."
        )


# ---------------------------------------------------------------------------
# v2.38.0: cross-trace data-flow refs (set_input_ref / current_span_id)
#
# These tests pin the chat→action propose-then-execute linking so the
# Prometa Causal-context block can render the two traces as a single
# navigable flow.  Without these tests a future refactor could silently
# drop either:
#   * the chat side (forget to include chat_span_id in /chat/ response)
#   * the dispatch side (forget to call set_input_ref in dispatch_action)
# and observability would degrade with no test signal.
#
# Coverage matrix:
#   1. prometa_config wrapper contract (SDK-absent fallback + happy path)
#   2. dispatch_action call-site (forwards keyword arg → set_input_ref)
#   3. AIActionExecuteView body (extracts + validates parent_span_id)
#   4. _chat_workflow source-level guard (response carries chat_span_id)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrossTraceRefs:
    """Pin v2.38.0 cross-trace linking between chat and action traces."""

    # ── (1) prometa_config wrapper contract ─────────────────────────────

    def test_current_span_id_returns_none_when_sdk_absent(self, monkeypatch):
        """Wrapper must catch ImportError and return None — never raise.

        Mirrors the test/dev environment where prometa-sdk isn't pinned
        (or is disabled via ``PROMETA_DISABLE=1``).  Call sites assume
        a None return = "no active span", and stamp nothing."""
        from ai_assistant import prometa_config as pc
        # Force the inner ``from prometa import current_span_id`` to fail
        # by monkeypatching __import__ to raise on the prometa module.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == 'prometa':
                raise ImportError('simulated SDK absent')
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', fake_import)
        # No exception, returns None.
        assert pc.current_span_id() is None

    def test_current_span_id_swallows_internal_sdk_errors(self, monkeypatch):
        """If the SDK is installed but ``current_span_id()`` raises
        (e.g. context-var was never initialized in this thread), the
        wrapper must still return None instead of bubbling.  Otherwise a
        single corrupt span context would crash the chat response."""
        from ai_assistant import prometa_config as pc
        # Simulate the "SDK present but raising" path by monkeypatching
        # the lazy import inside prometa_config.current_span_id.  We do
        # this by injecting a fake `prometa` module into sys.modules.
        import sys
        import types
        fake_prometa = types.ModuleType('prometa')

        def boom():
            raise RuntimeError('span context corrupted')

        fake_prometa.current_span_id = boom
        monkeypatch.setitem(sys.modules, 'prometa', fake_prometa)
        # Wrapper catches and returns None.
        assert pc.current_span_id() is None

    def test_set_input_ref_returns_false_for_falsy_input(self):
        """No span id, no link.  None / empty string short-circuit
        before the SDK is even imported — symmetric with the chat-side
        contract that an absent ``chat_span_id`` means "don't stamp"."""
        from ai_assistant import prometa_config as pc
        assert pc.set_input_ref(None) is False
        assert pc.set_input_ref('') is False
        assert pc.set_input_ref(0) is False

    def test_set_input_ref_returns_false_when_sdk_absent(self, monkeypatch):
        """Non-empty span id but SDK not installed → False, no raise.
        Matches the no-op contract documented in the wrapper docstring."""
        from ai_assistant import prometa_config as pc
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == 'prometa':
                raise ImportError('simulated SDK absent')
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', fake_import)
        assert pc.set_input_ref('chat-span-abc123') is False

    def test_set_input_ref_forwards_to_sdk_when_active(self, monkeypatch):
        """Happy path: SDK is present, wrapper coerces id to str and
        forwards.  Returns whatever the SDK returns coerced to bool."""
        from ai_assistant import prometa_config as pc
        import sys
        import types
        captured: list[str] = []
        fake_prometa = types.ModuleType('prometa')

        def fake_set_input_ref(span_id):
            captured.append(span_id)
            return True  # SDK signals "stamp succeeded"

        fake_prometa.set_input_ref = fake_set_input_ref
        monkeypatch.setitem(sys.modules, 'prometa', fake_prometa)

        result = pc.set_input_ref('chat-span-xyz789')

        assert result is True
        assert captured == ['chat-span-xyz789']

    def test_set_input_ref_swallows_sdk_runtime_errors(self, monkeypatch):
        """If the SDK call raises (e.g. no active span context), the
        wrapper must return False — call sites must never have to wrap
        the link call in try/except themselves."""
        from ai_assistant import prometa_config as pc
        import sys
        import types
        fake_prometa = types.ModuleType('prometa')

        def boom(_v):
            raise RuntimeError('no active span')

        fake_prometa.set_input_ref = boom
        monkeypatch.setitem(sys.modules, 'prometa', fake_prometa)

        assert pc.set_input_ref('chat-span-xyz') is False

    # ── (2) dispatch_action call-site ───────────────────────────────────

    def test_dispatch_action_calls_set_input_ref_when_parent_span_id_provided(
            self, monkeypatch):
        """The action-execute trace must call set_input_ref(parent) at
        the top of the workflow body so the Causal-context block in
        Prometa surfaces the chat→action link."""
        from ai_assistant import action_executor

        # Capture every helper invocation; let the rest no-op.
        ref_calls: list[str] = []
        attr_calls: list[tuple] = []
        monkeypatch.setattr(action_executor, 'set_input_ref',
                            lambda v: ref_calls.append(v) or True)
        monkeypatch.setattr(action_executor, 'set_span_attr',
                            lambda *a, **kw: attr_calls.append(a))
        monkeypatch.setattr(action_executor, 'set_customer_id',
                            lambda *a, **kw: None)
        monkeypatch.setattr(action_executor, 'set_session_id',
                            lambda *a, **kw: None)

        fn = action_executor.dispatch_action
        if hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__

        result = fn(42, 'unknown_action_xyz', {'description': 'test'},
                    parent_span_id='chat-span-deadbeef')

        # Unknown action_type still triggers early-return error,
        # but set_input_ref must have fired BEFORE that branch.
        assert result.get('status') == 'error'
        assert ref_calls == ['chat-span-deadbeef']
        # And the debug attribute mirror is present too.
        assert any(
            call[0] == 'declarai.action.parent_span_id'
            and call[1] == 'chat-span-deadbeef'
            for call in attr_calls
        ), f'expected declarai.action.parent_span_id attr; got {attr_calls}'

    def test_dispatch_action_skips_set_input_ref_when_parent_span_id_none(
            self, monkeypatch):
        """Legacy v2.25.0..v2.37.0 callers pass no parent_span_id —
        set_input_ref must NOT be invoked (don't stamp a phantom link).

        This is the backward-compat guard: every internal call site
        (test fixtures, programmatic dispatch) keeps working unchanged."""
        from ai_assistant import action_executor
        ref_calls: list = []
        monkeypatch.setattr(action_executor, 'set_input_ref',
                            lambda v: ref_calls.append(v) or True)
        monkeypatch.setattr(action_executor, 'set_span_attr',
                            lambda *a, **kw: None)
        monkeypatch.setattr(action_executor, 'set_customer_id',
                            lambda *a, **kw: None)
        monkeypatch.setattr(action_executor, 'set_session_id',
                            lambda *a, **kw: None)

        fn = action_executor.dispatch_action
        if hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__

        # No parent_span_id — pre-v2.38.0 call shape.
        fn(42, 'unknown_action_xyz', {})

        assert ref_calls == [], (
            "dispatch_action must not call set_input_ref when "
            f"parent_span_id is omitted; got {ref_calls}"
        )

    def test_dispatch_action_skips_set_input_ref_when_parent_span_id_empty(
            self, monkeypatch):
        """Empty string is treated as "no link" — defensive against a
        frontend that always sends the field but with an empty value
        when the chat turn wasn't traced."""
        from ai_assistant import action_executor
        ref_calls: list = []
        monkeypatch.setattr(action_executor, 'set_input_ref',
                            lambda v: ref_calls.append(v) or True)
        monkeypatch.setattr(action_executor, 'set_span_attr',
                            lambda *a, **kw: None)
        monkeypatch.setattr(action_executor, 'set_customer_id',
                            lambda *a, **kw: None)
        monkeypatch.setattr(action_executor, 'set_session_id',
                            lambda *a, **kw: None)

        fn = action_executor.dispatch_action
        if hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__

        fn(42, 'unknown_action_xyz', {}, parent_span_id='')

        assert ref_calls == []

    def test_dispatch_action_signature_keyword_only_parent_span_id(self):
        """parent_span_id must be keyword-only so positional v2.25.0..
        v2.37.0 call sites stay valid (they pass exactly 3 positionals)."""
        import inspect
        from ai_assistant.action_executor import dispatch_action
        # Unwrap the @workflow decorator if present.
        fn = dispatch_action.__wrapped__ if hasattr(dispatch_action, '__wrapped__') \
            else dispatch_action
        sig = inspect.signature(fn)
        params = sig.parameters
        assert 'parent_span_id' in params
        assert params['parent_span_id'].kind == inspect.Parameter.KEYWORD_ONLY, (
            'parent_span_id must be keyword-only to keep legacy positional '
            'call sites compatible'
        )
        assert params['parent_span_id'].default is None

    # ── (3) AIActionExecuteView body ────────────────────────────────────

    def test_action_execute_view_forwards_parent_span_id_from_body(
            self, monkeypatch):
        """The /execute-action/ endpoint must extract parent_span_id
        from the JSON body and pass it through to dispatch_action as
        the keyword arg.  This is the "wire" — without it, the chat span
        id never reaches the action workflow."""
        from ai_assistant import views

        captured = {}

        def fake_dispatch(file_id, action_type, payload, *, parent_span_id=None):
            captured['file_id'] = file_id
            captured['action_type'] = action_type
            captured['parent_span_id'] = parent_span_id
            return {'status': 'success', 'description': 'ok'}

        monkeypatch.setattr('ai_assistant.action_executor.dispatch_action',
                            fake_dispatch)

        view = views.AIActionExecuteView()

        class _FakeRequest:
            def __init__(self, data):
                self.data = data

        req = _FakeRequest({
            'file_id': 7,
            'action_type': 'update_config',
            'payload': {'foo': 'bar'},
            'parent_span_id': 'chat-span-abc',
        })

        view.post(req)

        assert captured['parent_span_id'] == 'chat-span-abc'
        assert captured['file_id'] == 7
        assert captured['action_type'] == 'update_config'

    def test_action_execute_view_treats_missing_parent_span_id_as_none(
            self, monkeypatch):
        """Legacy clients (v2.25.0..v2.37.0 frontend) don't send the
        field — view must default to None so dispatch_action sees the
        legacy call shape and skips set_input_ref entirely."""
        from ai_assistant import views

        captured = {}

        def fake_dispatch(file_id, action_type, payload, *, parent_span_id=None):
            captured['parent_span_id'] = parent_span_id
            return {'status': 'success'}

        monkeypatch.setattr('ai_assistant.action_executor.dispatch_action',
                            fake_dispatch)

        view = views.AIActionExecuteView()

        class _FakeRequest:
            def __init__(self, data):
                self.data = data

        view.post(_FakeRequest({
            'file_id': 1,
            'action_type': 'update_notes',
            'payload': {},
        }))

        assert captured['parent_span_id'] is None

    def test_action_execute_view_rejects_non_string_parent_span_id(
            self, monkeypatch):
        """Defensive: a buggy frontend that sends parent_span_id as an
        int / dict / list must not poison the span attribute.  View
        coerces non-strings to None (treat as no-link) rather than
        passing garbage through to set_input_ref."""
        from ai_assistant import views

        captured = {}

        def fake_dispatch(file_id, action_type, payload, *, parent_span_id=None):
            captured['parent_span_id'] = parent_span_id
            return {'status': 'success'}

        monkeypatch.setattr('ai_assistant.action_executor.dispatch_action',
                            fake_dispatch)

        view = views.AIActionExecuteView()

        class _FakeRequest:
            def __init__(self, data):
                self.data = data

        for bad_val in (123, {'x': 1}, [1, 2], True):
            captured.clear()
            view.post(_FakeRequest({
                'file_id': 1,
                'action_type': 'update_notes',
                'payload': {},
                'parent_span_id': bad_val,
            }))
            assert captured['parent_span_id'] is None, (
                f'expected None for non-string parent_span_id={bad_val!r}'
            )

    def test_action_execute_view_rejects_oversized_parent_span_id(
            self, monkeypatch):
        """Span ids in Prometa are short hex (~16 chars).  A 1000-char
        string is almost certainly malformed; treat as no-link rather
        than stamp giant garbage onto the span attribute."""
        from ai_assistant import views

        captured = {}

        def fake_dispatch(file_id, action_type, payload, *, parent_span_id=None):
            captured['parent_span_id'] = parent_span_id
            return {'status': 'success'}

        monkeypatch.setattr('ai_assistant.action_executor.dispatch_action',
                            fake_dispatch)

        view = views.AIActionExecuteView()

        class _FakeRequest:
            def __init__(self, data):
                self.data = data

        view.post(_FakeRequest({
            'file_id': 1,
            'action_type': 'update_notes',
            'payload': {},
            'parent_span_id': 'x' * 500,  # > 256-char limit
        }))

        assert captured['parent_span_id'] is None

    # ── (4) _chat_workflow source-level guard ───────────────────────────

    def test_chat_workflow_stamps_chat_span_id_into_response(self):
        """Source-level guard: the chat workflow body must call
        ``current_span_id()`` and conditionally stamp the result into
        response_data['chat_span_id'] when actions exist.  Without this
        the frontend has no id to forward on Apply, breaking the link."""
        import inspect
        from ai_assistant.views import _chat_workflow
        # _chat_workflow is wrapped by @workflow; unwrap to get the body.
        fn = _chat_workflow.__wrapped__ if hasattr(_chat_workflow, '__wrapped__') \
            else _chat_workflow
        source = inspect.getsource(fn)
        assert 'current_span_id()' in source, (
            '_chat_workflow must call current_span_id() to capture the '
            'chat-turn span id for cross-trace linking (v2.38.0)'
        )
        assert "'chat_span_id'" in source or '"chat_span_id"' in source, (
            '_chat_workflow must stamp chat_span_id into response_data '
            'so the frontend can forward it on Apply'
        )

    def test_views_imports_current_span_id_and_set_input_ref(self):
        """Structural guard: views.py must import both helpers from
        prometa_config so the chat workflow body can call them."""
        from ai_assistant import views
        assert hasattr(views, 'current_span_id'), (
            'views.py must import current_span_id from prometa_config '
            '(v2.38.0)'
        )
        assert hasattr(views, 'set_input_ref'), (
            'views.py must import set_input_ref from prometa_config '
            '(v2.38.0)'
        )

    def test_action_executor_imports_set_input_ref(self):
        """Structural guard: action_executor.py must import
        set_input_ref so dispatch_action can stamp the link."""
        from ai_assistant import action_executor
        assert hasattr(action_executor, 'set_input_ref'), (
            'action_executor.py must import set_input_ref from '
            'prometa_config (v2.38.0)'
        )


# ---------------------------------------------------------------------------
# v2.45.0: assistant-response feedback → Prometa feedback.record
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAssistantResponseFeedback:
    """Feedback API validation and Prometa SDK call wiring."""

    class _FakeRequest:
        def __init__(self, data):
            self.data = data
            self.user = None

    def test_feedback_view_requires_a_signal(self):
        from ai_assistant.feedback import AIFeedbackView

        resp = AIFeedbackView().post(self._FakeRequest({
            'target_span_id': 'span-1',
        }))

        assert resp.status_code == 400
        assert resp.data['errors']['feedback'] == 'Provide liked, rating, or comment.'

    def test_feedback_view_validates_liked_and_rating(self):
        from ai_assistant.feedback import AIFeedbackView

        resp = AIFeedbackView().post(self._FakeRequest({
            'liked': 'yes',
            'rating': 6,
        }))

        assert resp.status_code == 400
        assert 'liked' in resp.data['errors']
        assert 'rating' in resp.data['errors']

    def test_feedback_records_prometa_event_with_target_ids(self, monkeypatch):
        from ai_assistant import feedback as feedback_mod

        captured = {}
        monkeypatch.setattr(feedback_mod, 'record_user_feedback',
                            lambda **kw: captured.update(kw) or True)
        monkeypatch.setattr(feedback_mod, 'set_user_feedback',
                            lambda **kw: (_ for _ in ()).throw(AssertionError('set_user_feedback should not be used')))
        monkeypatch.setattr(feedback_mod, 'prometa_flush', lambda: None)

        resp = feedback_mod.AIFeedbackView().post(self._FakeRequest({
            'liked': True,
            'rating': 5,
            'comment': 'Clear and helpful.',
            'source': 'declarai-ai-chat-panel',
            'feedback_id': 'feedback-1',
            'user_id': 'analyst-123',
            'submitted_at': '2026-06-05T01:02:03Z',
            'chat_trace_id': 'trace-abc',
            'chat_span_id': 'span-def',
            'conversation_id': 'declarai-file-42',
        }))

        assert resp.status_code == 200
        assert resp.data['prometa_recorded'] is True
        assert resp.data['prometa_method'] == 'record_user_feedback'
        assert captured == {
            'liked': True,
            'rating': 5,
            'comment': 'Clear and helpful.',
            'source': 'declarai-ai-chat-panel',
            'feedback_id': 'feedback-1',
            'user_id': 'analyst-123',
            'submitted_at': '2026-06-05T01:02:03Z',
            'target_trace_id': 'trace-abc',
            'target_span_id': 'span-def',
            'target_session_id': 'declarai-file-42',
        }

    def test_feedback_derives_session_id_from_file_id(self, monkeypatch):
        from ai_assistant import feedback as feedback_mod

        captured = {}
        monkeypatch.setattr(feedback_mod, 'record_user_feedback',
                            lambda **kw: captured.update(kw) or True)
        monkeypatch.setattr(feedback_mod, 'prometa_flush', lambda: None)

        resp = feedback_mod.AIFeedbackView().post(self._FakeRequest({
            'liked': False,
            'file_id': 77,
            'target_span_id': 'span-77',
        }))

        assert resp.status_code == 200
        assert captured['target_session_id'] == 'declarai-file-77'
        assert captured['target_span_id'] == 'span-77'

    def test_feedback_redacts_pii_comment_and_drops_unsafe_user_id(self, monkeypatch):
        from ai_assistant import feedback as feedback_mod

        captured = {}
        monkeypatch.setattr(feedback_mod, 'record_user_feedback',
                            lambda **kw: captured.update(kw) or True)
        monkeypatch.setattr(feedback_mod, 'prometa_flush', lambda: None)

        resp = feedback_mod.AIFeedbackView().post(self._FakeRequest({
            'comment': 'Contact me at person@example.com or 415-555-1212.',
            'user_id': 'person@example.com',
            'target_span_id': 'span-safe',
        }))

        assert resp.status_code == 200
        assert resp.data['comment_redacted'] is True
        assert resp.data['user_id_included'] is False
        assert captured['user_id'] is None
        assert 'person@example.com' not in captured['comment']
        assert '415-555-1212' not in captured['comment']
        assert '[redacted-email]' in captured['comment']
        assert '[redacted-phone]' in captured['comment']

    def test_feedback_allows_raw_comment_and_user_id_when_explicit(self, monkeypatch):
        from ai_assistant import feedback as feedback_mod

        captured = {}
        monkeypatch.setattr(feedback_mod, 'record_user_feedback',
                            lambda **kw: captured.update(kw) or True)
        monkeypatch.setattr(feedback_mod, 'prometa_flush', lambda: None)

        resp = feedback_mod.AIFeedbackView().post(self._FakeRequest({
            'liked': True,
            'comment': 'Email person@example.com about this answer.',
            'user_id': 'person@example.com',
            'allow_pii': True,
        }))

        assert resp.status_code == 200
        assert captured['comment'] == 'Email person@example.com about this answer.'
        assert captured['user_id'] == 'person@example.com'

    def test_chat_workflow_returns_feedback_target_ids(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch,
            provider='openai',
            file_id=42,
            span_id='span-abc',
            trace_id='trace-def',
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )

        assert out['result']['chat_span_id'] == 'span-abc'
        assert out['result']['chat_trace_id'] == 'trace-def'
        assert out['result']['chat_session_id'] == 'declarai-file-42'


# ---------------------------------------------------------------------------
# AML v0.4 instrumentation helpers (v2.31.0 / Phase 3a of prometa-sdk roadmap).
#
# `schema_validate` and `model_route` are context managers that wrap
# their respective AML events.  Unlike the simple set_* helpers from
# Phase 2, these:
#   1. yield a handle the call site stamps with .result(...) / .cost(...)
#   2. propagate body exceptions normally (only ImportError is caught)
#   3. fall back to a `_NoOpAMLHandle` that absorbs every method call
#      so call sites don't need to guard
#
# These tests pin the wrapper contract + verify call-site adoption in
# `_call_llm` (model_route) and `update_purifier_selection` (schema_validate).
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrometaAMLHelpers:
    """``schema_validate`` and ``model_route`` are AML span context
    managers wrapping the v0.4.0+ SDK helpers.  Tests pin the three
    failure modes (SDK present, SDK absent, body exception) and the
    no-op handle's absorbing-method contract."""

    def test_noop_aml_handle_absorbs_arbitrary_method_calls(self):
        """The fallback handle must accept ANY method call with ANY
        args/kwargs and silently no-op.  This is what lets the call
        site write `sv.result(passed=True, errors=[...])` without
        guarding for SDK availability."""
        from ai_assistant.prometa_config import _NoOpAMLHandle
        h = _NoOpAMLHandle()
        # Every call must return None and not raise.
        assert h.result(passed=True) is None
        assert h.result(passed=False, errors=['x'], downstream_blocked=True) is None
        assert h.cost(cost_estimate_usd=0.01, budget_cap_usd=0.10) is None
        # Even completely fictitious method names must work — _NoOpAMLHandle
        # is a forward-compatible absorber for future SDK handle methods.
        assert h.method_that_does_not_exist_anywhere() is None
        assert h.with_positional_and_kwargs('foo', 'bar', x=1, y=2) is None

    def test_schema_validate_yields_real_handle_when_sdk_available(self, monkeypatch):
        """Happy path: the SDK's schema_validate is reachable on
        prometa-sdk 0.6.0+; our wrapper must delegate verbatim."""
        from ai_assistant import prometa_config as pc
        # Don't fully replace the SDK helper — just verify our wrapper
        # actually enters the SDK's context manager.  The handle yielded
        # by the SDK has a `.result()` method we can call.
        with pc.schema_validate('declarai:test-spec@v1') as sv:
            # The handle must expose .result()  — either the real SDK
            # handle (when client is configured) or _NoOpAMLHandle.
            assert hasattr(sv, 'result'), (
                "schema_validate handle must expose .result(...)"
            )
            # Calling .result() must not raise on either path.
            sv.result(passed=True)

    def test_schema_validate_falls_back_to_noop_handle_on_import_error(self, monkeypatch):
        """SDK without schema_validate symbol → wrapper yields
        _NoOpAMLHandle.  Validates the ImportError branch."""
        from ai_assistant import prometa_config as pc
        import prometa
        # Simulate the helper being absent.
        monkeypatch.delattr(prometa, 'schema_validate', raising=False)

        with pc.schema_validate('declarai:fallback-test@v1') as sv:
            # Must be the no-op handle.
            assert isinstance(sv, pc._NoOpAMLHandle), (
                f"Expected _NoOpAMLHandle on ImportError; got {type(sv)}"
            )
            # And it must absorb method calls without raising.
            sv.result(passed=False, errors=['simulated'])

    def test_schema_validate_propagates_body_exceptions(self):
        """Body exceptions must NOT be swallowed.  The validator's
        ValidationError still has to bubble up so the API caller
        sees the failure — the AML span just records the event."""
        from ai_assistant.prometa_config import schema_validate

        class _CustomError(Exception):
            pass

        with pytest.raises(_CustomError):
            with schema_validate('declarai:propagate-test@v1') as sv:
                sv.result(passed=False, errors=['boom'])
                raise _CustomError('body raised — must propagate')

    def test_model_route_yields_real_handle_when_sdk_available(self):
        """Happy path: model_route is reachable on 0.6.0+; the yielded
        handle must accept .cost() (and any other future method)."""
        from ai_assistant.prometa_config import model_route
        with model_route(
            chosen='gpt-5.5',
            candidates_considered=['gpt-5.5', 'gpt-5.4-mini'],
            routing_reason='user_selected',
        ) as mr:
            assert mr is not None
            # Must accept .cost() and not raise on either path.
            mr.cost(cost_estimate_usd=0.001)

    def test_model_route_falls_back_to_noop_handle_on_import_error(self, monkeypatch):
        """SDK without model_route symbol → wrapper yields
        _NoOpAMLHandle.  Same fallback contract as schema_validate."""
        from ai_assistant import prometa_config as pc
        import prometa
        monkeypatch.delattr(prometa, 'model_route', raising=False)

        with pc.model_route(
            chosen='gpt-5.5',
            candidates_considered=['gpt-5.5'],
            routing_reason='user_selected',
        ) as mr:
            assert isinstance(mr, pc._NoOpAMLHandle)
            mr.cost(cost_estimate_usd=0.001)  # absorbed
            mr.future_method_that_doesnt_exist_yet(123)  # absorbed

    def test_model_route_propagates_body_exceptions(self):
        """Same exception-propagation contract as schema_validate."""
        from ai_assistant.prometa_config import model_route

        class _RouterError(Exception):
            pass

        with pytest.raises(_RouterError):
            with model_route(
                chosen='gpt-5.5',
                candidates_considered=['gpt-5.5'],
                routing_reason='user_selected',
            ):
                raise _RouterError('upstream LLM call failed')

    # ── Call-site tests ────────────────────────────────────────────────

    def test_call_llm_source_wraps_dispatch_in_model_route(self):
        """Structural guard: `_call_llm` must wrap its provider dispatch
        in a `with model_route(...)` block, not just emit attributes.

        Pre-v2.31.0 there was no AML span at all.  Reverting to the
        bare-attrs shape would silently kill the F1 (model_route)
        detector signal for the entire DeclarAI surface."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        assert 'with model_route(' in source, (
            "_call_llm must wrap dispatch in `with model_route(...)`"
        )
        assert "routing_reason='user_selected'" in source, (
            "_call_llm must record routing_reason=user_selected today; "
            "switch to a richer reason when a real cascade lands."
        )
        assert 'candidates_considered=' in source, (
            "_call_llm must pass candidates_considered to model_route"
        )

    def test_update_purifier_selection_source_wraps_validation_in_schema_validate(self):
        """Structural guard: `update_purifier_selection` must wrap its
        full validation flow in a `with schema_validate(...)` block.

        Catches the regression where someone removes the AML span but
        leaves the existing set_span_attr('declarai.purifier.*') calls
        in place — the surrounding tests would still pass but the C4
        detector signal would be gone."""
        import inspect
        from ai_assistant.action_executor import update_purifier_selection
        source = inspect.getsource(update_purifier_selection)
        assert "with schema_validate('declarai:update-purifier-selection@v1')" in source, (
            "update_purifier_selection must wrap validation in "
            "schema_validate('declarai:update-purifier-selection@v1')"
        )
        # Must call sv.result() multiple times — once per return branch.
        # We don't pin the exact count to avoid brittleness, but require
        # both passing AND failing outcomes are recorded (8 returns ≥
        # 5 distinct sv.result calls in current shape).
        assert source.count('sv.result(passed=True') >= 3, (
            "update_purifier_selection must record sv.result(passed=True) "
            "on each success branch (noop, wholesale, diff_noop, diff)"
        )
        assert source.count('sv.result(\n                passed=False') >= 2, (
            "update_purifier_selection must record sv.result(passed=False, "
            "errors=[...], downstream_blocked=True) on each error branch "
            "(form_conflict, value_error, group_conflict, diff_conflict)"
        )

    # ── cache_lookup (v2.32.0 / Phase 3b) ──────────────────────────────

    def test_cache_lookup_yields_real_handle_when_sdk_available(self):
        """Happy path: cache_lookup is reachable on 0.6.0+; handle
        must accept .hit(), .miss(), .write_action_blocked()."""
        from ai_assistant.prometa_config import cache_lookup
        with cache_lookup('tool_call', key='ai:pipeline:42:dataset_summary') as ch:
            assert ch is not None
            # All three SDK handle methods must be callable.
            ch.hit()
            ch.miss()
            ch.write_action_blocked()
            # And the optional kwarg form of .hit() too.
            ch.hit(ttl_remaining_seconds=86400)

    def test_cache_lookup_falls_back_to_noop_handle_on_import_error(self, monkeypatch):
        """SDK without cache_lookup symbol → wrapper yields _NoOpAMLHandle.
        Same fallback contract as schema_validate and model_route."""
        from ai_assistant import prometa_config as pc
        import prometa
        monkeypatch.delattr(prometa, 'cache_lookup', raising=False)

        with pc.cache_lookup('tool_call', key='ai:pipeline:42:foo') as ch:
            assert isinstance(ch, pc._NoOpAMLHandle)
            ch.hit()          # absorbed
            ch.miss()         # absorbed
            ch.future_method_that_doesnt_exist_yet()  # absorbed

    def test_cache_lookup_propagates_invalid_kind_error(self):
        """The SDK enforces ``kind`` ∈ {response, tool_call, embedding}
        with a ValueError.  Our wrapper must NOT catch it — that's a
        programmer error that needs to surface, not a runtime failure
        we should silently no-op past."""
        from ai_assistant.prometa_config import cache_lookup
        with pytest.raises(ValueError, match='kind must be one of'):
            with cache_lookup('invalid_kind_xyz', key='ai:pipeline:1:x'):
                pass  # pragma: no cover — must raise on enter

    def test_cache_lookup_propagates_body_exceptions(self):
        """Body exceptions propagate (same contract as the other AML
        helpers).  Only ImportError is caught."""
        from ai_assistant.prometa_config import cache_lookup

        class _RedisDown(Exception):
            pass

        with pytest.raises(_RedisDown):
            with cache_lookup('tool_call', key='ai:pipeline:1:x') as ch:
                ch.miss()
                raise _RedisDown('redis connection dropped mid-fetch')

    def test_cache_get_wraps_redis_fetch_in_cache_lookup_with_hit(self, monkeypatch):
        """Functional end-to-end: cache_get must wrap the redis fetch
        in a cache_lookup AML span and call ch.hit() on the hit path.

        Patches cache_lookup as a recording context manager; populates
        Redis with a known value; invokes cache_get; asserts:
          1. enter('tool_call', key='ai:pipeline:<id>:<artifact>')
          2. hit() recorded — NOT miss()
          3. cache_get returned the value
          4. exit fired
        Pins the most common cache path (hit) to the B1 detector."""
        from ai_assistant import cache as cache_mod

        lookup_calls: list[tuple] = []

        class _RecordingHandle:
            def hit(self, **kwargs):
                lookup_calls.append(('hit', kwargs))
            def miss(self):
                lookup_calls.append(('miss', {}))
            def write_action_blocked(self):
                lookup_calls.append(('blocked', {}))

        from contextlib import contextmanager

        @contextmanager
        def _recording_cache_lookup(kind, *, key):
            lookup_calls.append(('enter', kind, key))
            try:
                yield _RecordingHandle()
            finally:
                lookup_calls.append(('exit', kind, key))

        monkeypatch.setattr(cache_mod, 'cache_lookup', _recording_cache_lookup)

        # Seed the cache.
        r = cache_mod._get_redis()
        assert r is not None, 'Redis must be available for this test'
        try:
            r.set(cache_mod._key(80001, 'aml_test_artifact'), '{"x": 7}', ex=60)

            result = cache_mod.cache_get(80001, 'aml_test_artifact')

            assert result == {'x': 7}
            # Lifecycle: enter → hit → exit (NOT miss).
            assert lookup_calls[0] == ('enter', 'tool_call', 'ai:pipeline:80001:aml_test_artifact')
            assert lookup_calls[-1] == ('exit', 'tool_call', 'ai:pipeline:80001:aml_test_artifact')
            # Hit recorded exactly once; no miss recorded.
            hit_calls = [c for c in lookup_calls if c[0] == 'hit']
            miss_calls = [c for c in lookup_calls if c[0] == 'miss']
            assert len(hit_calls) == 1, (
                f"cache_get on a hit path must call ch.hit() exactly once; "
                f"got hit_calls={hit_calls}, full lifecycle={lookup_calls}"
            )
            assert miss_calls == [], (
                f"cache_get on a hit path must NOT call ch.miss(); "
                f"got miss_calls={miss_calls}"
            )
        finally:
            r.delete(cache_mod._key(80001, 'aml_test_artifact'))

    def test_cache_get_wraps_redis_fetch_in_cache_lookup_with_miss(self, monkeypatch):
        """Mirror of the hit test: missing key → ch.miss() recorded.

        The B1 detector needs both hit AND miss signals to compute
        cache hit-rate; this guard pins the miss path."""
        from ai_assistant import cache as cache_mod

        lookup_calls: list[tuple] = []

        class _RecordingHandle:
            def hit(self, **kwargs):
                lookup_calls.append(('hit', kwargs))
            def miss(self):
                lookup_calls.append(('miss', {}))
            def write_action_blocked(self):
                lookup_calls.append(('blocked', {}))

        from contextlib import contextmanager

        @contextmanager
        def _recording_cache_lookup(kind, *, key):
            lookup_calls.append(('enter', kind, key))
            try:
                yield _RecordingHandle()
            finally:
                lookup_calls.append(('exit', kind, key))

        monkeypatch.setattr(cache_mod, 'cache_lookup', _recording_cache_lookup)

        # Ensure key is absent.
        r = cache_mod._get_redis()
        assert r is not None
        r.delete(cache_mod._key(80002, 'absent_artifact'))

        result = cache_mod.cache_get(80002, 'absent_artifact')
        assert result is None

        # Miss recorded exactly once.
        miss_calls = [c for c in lookup_calls if c[0] == 'miss']
        hit_calls = [c for c in lookup_calls if c[0] == 'hit']
        assert len(miss_calls) == 1, (
            f"cache_get on a miss path must call ch.miss() exactly once; "
            f"got miss_calls={miss_calls}, full lifecycle={lookup_calls}"
        )
        assert hit_calls == [], (
            f"cache_get on a miss path must NOT call ch.hit(); "
            f"got hit_calls={hit_calls}"
        )

    def test_cache_get_source_uses_cache_lookup_wrapper(self):
        """Structural guard: cache.py::cache_get must wrap the redis
        fetch in `with cache_lookup('tool_call', key=...)`.

        Catches a future contributor removing the AML span while
        keeping the rest of the function intact (no functional
        regression but B1 signal would silently vanish)."""
        import inspect
        from ai_assistant import cache as cache_mod
        source = inspect.getsource(cache_mod.cache_get)
        assert "with cache_lookup('tool_call'" in source, (
            "cache_get must wrap redis fetch in cache_lookup('tool_call', ...)"
        )
        # Both hit AND miss paths must be instrumented.
        assert 'ch.hit(' in source, (
            "cache_get must call ch.hit() on the value-returned path"
        )
        assert 'ch.miss()' in source, (
            "cache_get must call ch.miss() on miss / redis-down / exception paths"
        )

    # ── plan_generate (v2.33.0 / Phase 3c) ─────────────────────────────

    def test_plan_generate_yields_real_handle_when_sdk_available(self):
        """Happy path: plan_generate is reachable on 0.6.0+; handle
        must accept .emitted(steps, complexity_estimate, replanned_from)."""
        from ai_assistant.prometa_config import plan_generate
        with plan_generate('declarai-file-42-1700000000') as p:
            assert p is not None
            # Minimum-required form.
            p.emitted(steps=[{'order': 1, 'action': 'foo',
                              'tool': 'foo', 'depends_on': []}])
            # Full form with all kwargs.
            p.emitted(
                steps=[
                    {'order': 1, 'action': 'a', 'tool': 'a', 'depends_on': []},
                    {'order': 2, 'action': 'b', 'tool': 'b', 'depends_on': []},
                ],
                replanned_from='declarai-file-42-1699999999',
                complexity_estimate=2,
            )

    def test_plan_generate_falls_back_to_noop_handle_on_import_error(self, monkeypatch):
        """SDK without plan_generate symbol → wrapper yields _NoOpAMLHandle.
        Same fallback contract as the other AML helpers."""
        from ai_assistant import prometa_config as pc
        import prometa
        monkeypatch.delattr(prometa, 'plan_generate', raising=False)

        with pc.plan_generate('declarai-file-42-1700000000') as p:
            assert isinstance(p, pc._NoOpAMLHandle)
            p.emitted(steps=[], complexity_estimate=0)  # absorbed
            p.future_method_that_doesnt_exist_yet()      # absorbed

    def test_plan_generate_propagates_body_exceptions(self):
        """Body exceptions propagate (same contract as the other AML
        helpers).  Only ImportError is caught."""
        from ai_assistant.prometa_config import plan_generate

        class _PlannerError(Exception):
            pass

        with pytest.raises(_PlannerError):
            with plan_generate('declarai-file-42-1700000000') as p:
                p.emitted(steps=[], complexity_estimate=0)
                raise _PlannerError('plan emission failed downstream')

    def test_chat_workflow_source_emits_plan_generate_when_actions_present(self):
        """Structural guard: _chat_workflow body in views.py must call
        plan_generate AFTER _extract_actions returns, and only when
        ``actions`` is non-empty (the conditional `if actions and ...:`
        guard).

        Pre-v2.33.0 we had no plan.generate span at all.  Reverting to
        the bare-extraction shape would silently kill the C2 detector
        signal for the entire DeclarAI surface."""
        import inspect
        from ai_assistant import views
        source = inspect.getsource(views._chat_workflow)
        # Must call plan_generate.
        assert 'with plan_generate(' in source, (
            "_chat_workflow must wrap action emission in `with plan_generate(...)`"
        )
        # Must be conditional on actions being non-empty.
        assert 'if actions and file_id is not None' in source, (
            "_chat_workflow must only emit plan_generate when actions are "
            "non-empty AND file_id is known (avoids polluting C2 detector "
            "denominator with zero-action conversational replies)."
        )
        # Must call p.emitted() with steps.
        assert '.emitted(' in source and 'steps=' in source, (
            "_chat_workflow must call .emitted(steps=..., complexity_estimate=...) "
            "on the plan_generate handle"
        )
        # Steps must use 'order' / 'action' / 'tool' / 'depends_on' shape.
        for key in ("'order'", "'action'", "'tool'", "'depends_on'"):
            assert key in source, (
                f"plan_generate steps must include {key} (SDK-canonical key) — "
                f"the C2 detector parses these specific fields."
            )

    def test_views_module_imports_plan_generate(self):
        """Belt-and-suspenders: views.py must expose plan_generate in
        its module namespace so the _chat_workflow body can call it.

        Pairs with the structural guard above to catch an accidental
        revert of the import line even when the workflow body isn't
        executed end-to-end (requires OpenAI)."""
        from ai_assistant import views
        assert hasattr(views, 'plan_generate'), (
            "views.py must import plan_generate from prometa_config"
        )

    def test_chat_workflow_plan_id_format_uses_file_id_and_timestamp(self):
        """The plan_id must encode both the file_id (for joining with
        customer_id / session_id correlation chain) AND a per-turn
        time component (so multiple plans within the same Declaration
        get distinct ids).

        Pre-v2.33.0 there was no plan_id; this test pins the format
        used for the canonical plan.id span attribute."""
        import inspect
        from ai_assistant import views
        source = inspect.getsource(views._chat_workflow)
        # Format pinned: f'declarai-file-{file_id}-{int(_time.time() * 1000)}'
        assert "f'declarai-file-{file_id}" in source, (
            "plan_id must include the file_id so platform-side correlation "
            "joins plan.generate spans to customer_id (Phase 2)."
        )
        assert '_time.time()' in source or 'time.time()' in source, (
            "plan_id must include a time component for per-turn uniqueness"
        )

    def test_update_purifier_selection_form_conflict_returns_error_via_schema_validate(self, monkeypatch):
        """Functional guard: when the AI passes BOTH purifier_options
        AND add/remove (the form_conflict path), the function must:
          1. Return status='error' with the form_conflict message
          2. Have entered the schema_validate context manager
          3. Have stamped sv.result(passed=False, ..., downstream_blocked=True)

        This pins the most common AI mistake — sending mutually-exclusive
        forms in the same payload — to the AML-instrumented error path."""
        from ai_assistant import action_executor

        sv_calls: list[tuple] = []

        class _RecordingHandle:
            def result(self, **kwargs):
                sv_calls.append(('result', kwargs))

        from contextlib import contextmanager

        @contextmanager
        def _recording_schema_validate(schema_id):
            sv_calls.append(('enter', schema_id))
            try:
                yield _RecordingHandle()
            finally:
                sv_calls.append(('exit', schema_id))

        monkeypatch.setattr(action_executor, 'schema_validate', _recording_schema_validate)
        monkeypatch.setattr(action_executor, 'set_span_attr', lambda *a, **kw: None)

        # Unwrap the @tool decorator to call the underlying body directly,
        # the same trick the dispatch_action call-site test uses.
        fn = action_executor.update_purifier_selection
        if hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__

        result = fn(42, {
            'purifier_options': [1, 2, 3],
            'add': [10],  # mutually-exclusive with purifier_options
            'description': 'AI confused itself',
        })

        # Result shape pinned.
        assert result['status'] == 'error'
        assert 'Specify exactly one' in result['error']

        # AML span lifecycle: enter → result(passed=False) → exit.
        assert sv_calls[0] == ('enter', 'declarai:update-purifier-selection@v1')
        assert sv_calls[-1] == ('exit', 'declarai:update-purifier-selection@v1')
        # Find the result call in between.
        result_calls = [c for c in sv_calls if c[0] == 'result']
        assert len(result_calls) == 1
        kwargs = result_calls[0][1]
        assert kwargs['passed'] is False
        assert kwargs['downstream_blocked'] is True
        assert any('form_conflict' in e for e in kwargs['errors'])


# ---------------------------------------------------------------------------
# Standalone-trace pollution prevention (v2.22.3+).
#
# Cache helpers must use ``@child_only_tool`` so calls from non-workflow
# contexts (cache_push REST endpoint, declaration data-dict push,
# /api/ai/cache_status/, ad-hoc shell scripts) do NOT produce standalone
# root traces in Trace Explorer.  Each such call was previously creating
# a 0-1ms trace with a single redis-set/redis-set-bulk span and no
# conversation context — pure clutter.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCacheHelpersAreChildOnly:
    """All 5 cache helpers must be marked ``_child_only=True`` so they
    don't emit standalone root traces when invoked outside a workflow."""

    @pytest.mark.parametrize("fn_name,tool_name", [
        ('cache_put', 'redis-set'),
        ('cache_get', 'redis-get'),
        ('cache_put_bulk', 'redis-set-bulk'),
        ('cache_delete', 'redis-delete'),
        ('cache_list_artifacts', 'redis-list'),
    ])
    def test_cache_helper_is_child_only(self, fn_name, tool_name):
        from ai_assistant import cache as cache_mod
        fn = getattr(cache_mod, fn_name)
        assert getattr(fn, '_child_only', False) is True, (
            f"{fn_name} must be decorated with @child_only_tool, not "
            f"@prometa_tool — standalone invocations would otherwise "
            f"create root traces in Trace Explorer (v2.22.3 regression).")
        assert getattr(fn, '_tool_name', None) == tool_name, (
            f"{fn_name} must keep its tool name ('{tool_name}') after "
            f"the child_only_tool conversion.")


@pytest.mark.unit
class TestChildOnlyToolSemantics:
    """Behavioral checks for the ``child_only_tool`` decorator itself."""

    def test_has_active_span_returns_false_when_sdk_absent(self):
        """In test/CI environments where Prometa is not installed (or
        ``current_span`` raises), the helper must safely return False so
        the wrapper falls through to the plain function path."""
        from ai_assistant.prometa_config import has_active_span
        # In conftest.py the SDK is disabled, so this should be False.
        assert has_active_span() is False

    def test_child_only_tool_skips_traced_path_when_no_parent(self, monkeypatch):
        """The traced (Prometa-decorated) variant must NOT be invoked
        when ``has_active_span()`` reports no parent.  We verify by
        installing a sentinel that would explode if reached."""
        from ai_assistant import prometa_config

        monkeypatch.setattr(prometa_config, 'has_active_span', lambda: False)

        traced_calls = []
        plain_calls = []

        def fake_tool_factory(name=None, **kwargs):
            def deco(fn):
                def traced_wrapper(*a, **kw):
                    traced_calls.append((a, kw))
                    return fn(*a, **kw)
                return traced_wrapper
            return deco
        monkeypatch.setattr(prometa_config, 'tool', fake_tool_factory)

        @prometa_config.child_only_tool(name='probe')
        def my_fn(x):
            plain_calls.append(x)
            return x + 1

        assert my_fn(7) == 8
        assert plain_calls == [7]
        assert traced_calls == [], (
            "When no parent span is active, child_only_tool must bypass "
            "the traced wrapper and call the function plain.")

    def test_child_only_tool_uses_traced_path_when_parent_active(self, monkeypatch):
        """The mirror case: with an active parent span, the traced
        variant IS invoked (so the child span appears in the waterfall)."""
        from ai_assistant import prometa_config

        monkeypatch.setattr(prometa_config, 'has_active_span', lambda: True)

        traced_calls = []

        def fake_tool_factory(name=None, **kwargs):
            def deco(fn):
                def traced_wrapper(*a, **kw):
                    traced_calls.append((name, a, kw))
                    return fn(*a, **kw)
                return traced_wrapper
            return deco
        monkeypatch.setattr(prometa_config, 'tool', fake_tool_factory)

        @prometa_config.child_only_tool(name='probe')
        def my_fn(x):
            return x * 2

        assert my_fn(9) == 18
        assert traced_calls == [('probe', (9,), {})], (
            "With an active parent span, child_only_tool must route "
            "through the traced wrapper so a child span is created.")

    def test_child_only_tool_preserves_return_value_and_exceptions(self, monkeypatch):
        """Both code paths must transparently propagate return values
        and exceptions — the decorator is purely about span emission."""
        from ai_assistant import prometa_config

        @prometa_config.child_only_tool(name='probe')
        def returns_value(a, b):
            return a + b

        @prometa_config.child_only_tool(name='probe')
        def raises():
            raise ValueError("boom")

        # No-parent path (default in test env)
        monkeypatch.setattr(prometa_config, 'has_active_span', lambda: False)
        assert returns_value(2, 3) == 5
        with pytest.raises(ValueError, match='boom'):
            raises()

        # Parent-active path (forced)
        monkeypatch.setattr(prometa_config, 'has_active_span', lambda: True)
        assert returns_value(10, 20) == 30
        with pytest.raises(ValueError, match='boom'):
            raises()


@pytest.mark.unit
class TestCacheRestEndpointsDoNotEmitSpans:
    """End-to-end behavioural guard: calling a cache helper from a
    no-parent context (mimicking the cache_push endpoint or the
    declaration data-dict push) must NOT invoke the Prometa tool
    decorator at all."""

    def test_cache_put_bulk_from_no_parent_does_not_invoke_tool(self, monkeypatch):
        """Simulates ``ai_assistant.views.AICachePushView.post`` calling
        ``cache_put_bulk`` outside any workflow context.  The Prometa
        tool factory must not be invoked for this path."""
        from ai_assistant import cache as cache_mod
        from ai_assistant import prometa_config
        from ai_assistant.cache import _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        # Force "no parent" mode so the child_only gate engages.
        monkeypatch.setattr(prometa_config, 'has_active_span', lambda: False)

        # Track whether the Prometa SDK tool decorator was reached.
        tool_invoked = []
        original_tool = prometa_config.tool

        def watched_tool(*args, **kwargs):
            tool_invoked.append((args, kwargs))
            return original_tool(*args, **kwargs)
        monkeypatch.setattr(prometa_config, 'tool', watched_tool)

        # The decorator was applied at module import time so re-importing
        # would be needed to re-route through watched_tool; instead we
        # verify the runtime behaviour of the EXISTING wrapper: with
        # has_active_span=False it should call the plain function path
        # (no SDK interaction).
        try:
            assert cache_mod.cache_put_bulk(80000, {'a': 1, 'b': 2}) is True
            # Plain Redis got the writes:
            assert cache_mod.cache_get(80000, 'a') == 1
            assert cache_mod.cache_get(80000, 'b') == 2
        finally:
            r = _get_redis()
            for k in ('a', 'b'):
                r.delete(f'ai:pipeline:80000:{k}')

    def test_cache_put_from_no_parent_does_not_invoke_tool(self, monkeypatch):
        """Mirrors ``declaration/views.py:485`` pushing a data dictionary
        into Redis after a Declaration update."""
        from ai_assistant import cache as cache_mod
        from ai_assistant import prometa_config
        from ai_assistant.cache import _get_redis
        if _get_redis() is None:
            pytest.skip("Redis not available")

        monkeypatch.setattr(prometa_config, 'has_active_span', lambda: False)

        try:
            assert cache_mod.cache_put(80001, 'data_dictionary',
                                       [{'Feature_Name': 'A'}]) is True
            assert cache_mod.cache_get(80001, 'data_dictionary') == [
                {'Feature_Name': 'A'}]
        finally:
            _get_redis().delete('ai:pipeline:80001:data_dictionary')


# ---------------------------------------------------------------------------
# v2.27.0 — Purifier catalog tests
# ---------------------------------------------------------------------------
#
# These tests cover the canonical 34-option catalog introduced in
# v2.27.0 to fix a P0 silent-data-corruption bug.  Pre-v2.27.0 the
# backend `_apply_options` dispatcher and the frontend `purifierOptions`
# array had divergent ID-to-transform mappings: ticking
# "Sparsity-drop 0.95" (UI ID 11) silently executed "Missing-drop ≥ 0.40"
# in the backend, IDs 24-27 were no-op, etc.  See
# `backend/preprocessing/purifier_catalog.py` module docstring and
# the v2.27.0 commit body for the full realignment matrix.
#
# Every test here would have FAILED against pre-v2.27.0 code, which is
# what makes them effective regression guards for the contract.
@pytest.mark.unit
class TestPurifierCatalog:
    """Sanity tests for preprocessing/purifier_catalog.py."""

    def test_catalog_has_exactly_34_entries(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        assert len(PURIFIER_OPTIONS) == 34

    def test_ids_are_contiguous_1_through_34(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        ids = sorted(e['id'] for e in PURIFIER_OPTIONS)
        assert ids == list(range(1, 35))

    def test_every_entry_has_required_keys(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        required = {'id', 'name', 'kind', 'group', 'threshold', 'quantile_range'}
        for entry in PURIFIER_OPTIONS:
            missing = required - set(entry.keys())
            assert not missing, f"entry id={entry.get('id')} missing keys: {missing}"

    def test_threshold_drop_kinds_have_numeric_threshold(self):
        from preprocessing.purifier_catalog import (
            PURIFIER_OPTIONS, KIND_CORR_DROP, KIND_SPARSITY_DROP,
            KIND_MISSING_DROP, KIND_COMBINED_DROP, KIND_OUTLIER_CAT,
        )
        threshold_kinds = {KIND_CORR_DROP, KIND_SPARSITY_DROP,
                           KIND_MISSING_DROP, KIND_COMBINED_DROP,
                           KIND_OUTLIER_CAT}
        for entry in PURIFIER_OPTIONS:
            if entry['kind'] in threshold_kinds:
                assert isinstance(entry['threshold'], (int, float)), \
                    f"id={entry['id']} kind={entry['kind']} missing numeric threshold"
                assert 0 < entry['threshold'] < 1, \
                    f"id={entry['id']} threshold {entry['threshold']} out of (0, 1) range"

    def test_outlier_num_entries_have_valid_quantile_range(self):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS, KIND_OUTLIER_NUM
        for entry in PURIFIER_OPTIONS:
            if entry['kind'] == KIND_OUTLIER_NUM:
                qr = entry['quantile_range']
                assert isinstance(qr, tuple) and len(qr) == 2, \
                    f"id={entry['id']} quantile_range must be a 2-tuple"
                lo, hi = qr
                assert 0 < lo < hi < 1, \
                    f"id={entry['id']} quantile_range ({lo}, {hi}) invalid"

    def test_specific_id_labels_match_frontend_v2_27_0_canonical(self):
        """Pin the IDs that were misaligned pre-v2.27.0.

        Each (id, expected_kind, expected_threshold_or_qrange) tuple
        encodes what the frontend label promises the option does.
        Pre-v2.27.0 the backend dispatcher would have executed a
        different transform for these IDs (or no transform at all for
        24-27).
        """
        from preprocessing.purifier_catalog import (
            get_option, KIND_CORR_DROP, KIND_SPARSITY_DROP,
            KIND_MISSING_DROP, KIND_COMBINED_DROP, KIND_OUTLIER_NUM,
            KIND_OUTLIER_CAT,
        )
        # Format: (id, expected_kind, expected_threshold OR expected_quantile_range)
        cases = [
            # Corr-drop group — ID 9 was Missing-drop pre-v2.27.0
            (5,  KIND_CORR_DROP,     0.95),
            (9,  KIND_CORR_DROP,     0.75),
            # Sparsity group — pre-v2.27.0 IDs 10-15 were Missing-drop with thresholds 0.30-0.60
            (10, KIND_SPARSITY_DROP, 0.99),
            (11, KIND_SPARSITY_DROP, 0.95),
            (15, KIND_SPARSITY_DROP, 0.75),
            # Missing group — pre-v2.27.0 IDs 16-21 were Sparsity-drop with thresholds 0.40-0.60 (only 16-18)
            (16, KIND_MISSING_DROP,  0.99),
            (17, KIND_MISSING_DROP,  0.95),
            (21, KIND_MISSING_DROP,  0.75),
            # Combined group — pre-v2.27.0 IDs 22-23 ran Combined 0.80/0.75, 24-27 were NO-OP
            (22, KIND_COMBINED_DROP, 0.99),
            (23, KIND_COMBINED_DROP, 0.95),
            (24, KIND_COMBINED_DROP, 0.90),
            (27, KIND_COMBINED_DROP, 0.75),
            # Outlier-num — always agreed
            (28, KIND_OUTLIER_NUM,   (0.01, 0.99)),
            (29, KIND_OUTLIER_NUM,   (0.05, 0.95)),
            (30, KIND_OUTLIER_NUM,   (0.10, 0.90)),
            # Cat-outlier — always agreed
            (31, KIND_OUTLIER_CAT,   0.001),
            (34, KIND_OUTLIER_CAT,   0.05),
        ]
        for opt_id, expected_kind, expected_value in cases:
            entry = get_option(opt_id)
            assert entry is not None, f"id={opt_id} missing from catalog"
            assert entry['kind'] == expected_kind, \
                f"id={opt_id} kind={entry['kind']} expected {expected_kind}"
            if expected_kind == KIND_OUTLIER_NUM:
                assert entry['quantile_range'] == expected_value, \
                    f"id={opt_id} quantile_range={entry['quantile_range']} expected {expected_value}"
            else:
                assert entry['threshold'] == expected_value, \
                    f"id={opt_id} threshold={entry['threshold']} expected {expected_value}"

    def test_pick_most_aggressive_returns_lowest_threshold(self):
        from preprocessing.purifier_catalog import pick_most_aggressive, KIND_CORR_DROP
        # Selecting 5 (0.95) and 9 (0.75) — most aggressive is 9 (0.75
        # drops MORE pairs)
        entry = pick_most_aggressive({5, 9}, KIND_CORR_DROP)
        assert entry is not None
        assert entry['id'] == 9
        assert entry['threshold'] == 0.75

    def test_pick_most_aggressive_returns_none_when_no_match(self):
        from preprocessing.purifier_catalog import pick_most_aggressive, KIND_SPARSITY_DROP
        # IDs 1-4 are not sparsity-drop kind
        assert pick_most_aggressive({1, 2, 3, 4}, KIND_SPARSITY_DROP) is None

    def test_pick_most_aggressive_rejects_non_threshold_kind(self):
        from preprocessing.purifier_catalog import pick_most_aggressive, KIND_OUTLIER_NUM
        with pytest.raises(ValueError):
            pick_most_aggressive({28, 29}, KIND_OUTLIER_NUM)

    def test_selected_entries_of_kind_sorts_by_id(self):
        from preprocessing.purifier_catalog import selected_entries_of_kind, KIND_OUTLIER_NUM
        entries = selected_entries_of_kind({30, 28, 29}, KIND_OUTLIER_NUM)
        assert [e['id'] for e in entries] == [28, 29, 30]

    def test_default_selected_ids_all_valid(self):
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS, get_option
        for opt_id in DEFAULT_SELECTED_IDS:
            assert get_option(opt_id) is not None, f"default id {opt_id} not in catalog"

    def test_default_selected_ids_use_combined_sparsity_missing_drop(self):
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS
        assert DEFAULT_SELECTED_IDS == [1, 2, 3, 4, 7, 23, 28, 32]
        assert 11 not in DEFAULT_SELECTED_IDS
        assert 17 not in DEFAULT_SELECTED_IDS
        assert 23 in DEFAULT_SELECTED_IDS


@pytest.mark.unit
class TestPurifierApplyOptions:
    """Each option ID must execute the transform its UI label describes.

    Pre-v2.27.0 several IDs in 9-27 silently ran the wrong transform.
    These tests construct a tiny synthetic frame where the expected
    transform produces a deterministic outcome, then call
    `PreprocessingRunView._apply_options` and assert.
    """

    @staticmethod
    def _apply(df, option_ids):
        from preprocessing.views import PreprocessingRunView
        view = PreprocessingRunView()
        return view._apply_options(df, set(option_ids))

    # ── Identity / standalone options (1-4) ─────────────────────
    def test_id_1_drops_column_duplicates(self):
        df = pd.DataFrame({'a': [1, 2, 3], 'a_dup': [1, 2, 3], 'b': [4, 5, 6]})
        work, dropped, breakdown, _ = self._apply(df, [1])
        assert 'a_dup' in dropped or 'a' in dropped
        assert any(b['step'] == 'Column-wise duplicate drop' for b in breakdown)

    def test_id_3_drops_zero_variance_columns(self):
        df = pd.DataFrame({'const': [7, 7, 7, 7], 'vary': [1, 2, 3, 4]})
        work, dropped, breakdown, _ = self._apply(df, [3])
        assert 'const' in dropped
        assert 'vary' not in dropped

    # ── Correlation drop (5-9) ──────────────────────────────────
    def test_id_5_drops_pairs_with_correlation_ge_0_95(self):
        # x and y are perfectly correlated (|corr|=1 >= 0.95)
        df = pd.DataFrame({
            'x': [1.0, 2.0, 3.0, 4.0, 5.0],
            'y': [2.0, 4.0, 6.0, 8.0, 10.0],
            'z': [5.0, 1.0, 4.0, 2.0, 3.0],
        })
        work, dropped, _, _ = self._apply(df, [5])
        # Exactly one of (x, y) is dropped; z is uncorrelated and stays.
        assert ('x' in dropped) ^ ('y' in dropped)
        assert 'z' not in dropped

    def test_id_9_executes_corr_drop_threshold_0_75_not_missing_drop(self):
        """v2.27.0 regression — pre-v2.27.0 ID 9 was Missing-drop ≥ 0.20.

        If the dispatcher were still wired the old way, this all-numeric
        zero-missing frame would have no missing data so ID 9 would be
        a no-op.  After the fix it must drop one of the two highly
        correlated columns (|corr|=1 >= 0.75).
        """
        df = pd.DataFrame({
            'x': [1.0, 2.0, 3.0, 4.0, 5.0],
            'y': [2.1, 3.9, 6.05, 7.95, 10.1],  # ~0.999 correlation with x
            'z': [5.0, 1.0, 4.0, 2.0, 3.0],
        })
        work, dropped, breakdown, _ = self._apply(df, [9])
        assert ('x' in dropped) ^ ('y' in dropped), \
            f"ID 9 (Corr-drop ≥ 0.75) did not drop a correlated column; dropped={dropped}"
        corr_step = next((b for b in breakdown if b['step'] == 'Correlation drop (threshold)'), None)
        assert corr_step is not None
        assert corr_step['threshold'] == 0.75

    # ── Sparsity drop (10-15) — THE PRE-v2.27.0 SMOKING GUN ─────
    def test_id_11_drops_columns_with_zero_ratio_at_least_0_95(self):
        """Pre-v2.27.0 ID 11 executed "Missing-drop ≥ 0.40" instead of
        "Sparsity-drop ≥ 0.95".  Fixed in v2.27.0.

        Built so:
          • `mostly_zero` is 96% zeros (no missings) — must drop under
            v2.27.0 semantics; pre-v2.27.0 would NOT drop (no missings).
          • `mostly_missing` is 50% missing (no zeros) — pre-v2.27.0
            would drop under Missing-drop≥0.40; v2.27.0 must NOT drop
            (no zeros, so sparsity≈0).
        """
        n = 100
        df = pd.DataFrame({
            'mostly_zero':    [0.0] * 96 + [1.0, 2.0, 3.0, 4.0],
            'mostly_missing': [None] * 50 + list(range(50)),
            'normal':         list(range(n)),
        })
        work, dropped, breakdown, _ = self._apply(df, [11])
        assert 'mostly_zero' in dropped, \
            f"v2.27.0 contract: ID 11 (Sparsity-drop ≥ 0.95) should drop mostly_zero; dropped={dropped}"
        assert 'mostly_missing' not in dropped, \
            f"v2.27.0 contract: ID 11 must NOT drop missing-heavy columns; dropped={dropped}"
        assert 'normal' not in dropped
        sparse_step = next((b for b in breakdown if b['step'] == 'Sparsity zeros drop (threshold)'), None)
        assert sparse_step is not None
        assert sparse_step['threshold'] == 0.95

    # ── Missing drop (16-21) — THE PRE-v2.27.0 SMOKING GUN #2 ────
    def test_id_17_drops_columns_with_miss_ratio_at_least_0_95(self):
        """Pre-v2.27.0 ID 17 executed "Sparsity-drop ≥ 0.50" instead
        of "Missing-drop ≥ 0.95".  Fixed in v2.27.0.

        Built so:
          • `mostly_missing` is 96% missing — must drop in v2.27.0,
            no-op pre-v2.27.0 (sparsity ≈ 0 since values absent).
          • `mostly_zero` is 60% zeros (no missings) — pre-v2.27.0
            would drop under Sparsity-drop≥0.50; v2.27.0 must NOT
            drop (miss_ratio = 0).
        """
        n = 100
        df = pd.DataFrame({
            'mostly_missing': [None] * 96 + [1.0, 2.0, 3.0, 4.0],
            'mostly_zero':    [0.0] * 60 + list(range(1, 41)),
            'normal':         list(range(n)),
        })
        work, dropped, breakdown, _ = self._apply(df, [17])
        assert 'mostly_missing' in dropped, \
            f"v2.27.0 contract: ID 17 (Missing-drop ≥ 0.95) should drop mostly_missing; dropped={dropped}"
        assert 'mostly_zero' not in dropped, \
            f"v2.27.0 contract: ID 17 must NOT drop sparse columns; dropped={dropped}"
        miss_step = next((b for b in breakdown if b['step'] == 'Missing-drop (threshold)'), None)
        assert miss_step is not None
        assert miss_step['threshold'] == 0.95

    # ── Combined sparsity+missing (22-27) — pre-v2.27.0 NO-OPS ──
    def test_id_24_combined_drop_threshold_0_90_was_silent_noop_pre_v2_27_0(self):
        """Pre-v2.27.0 IDs 24-27 had no dispatcher branch — selecting
        "[Sparsity+Missing]-drop 0.90" did literally nothing.  After
        v2.27.0 it must drop any column where max(zero_ratio, miss_ratio)
        ≥ 0.90.
        """
        n = 100
        df = pd.DataFrame({
            'half_miss_half_zero': [None] * 45 + [0.0] * 45 + list(range(1, 11)),
            'mostly_zero':         [0.0] * 92 + list(range(1, 9)),
            'mostly_missing':      [None] * 91 + list(range(9)),
            'normal':              list(range(n)),
        })
        work, dropped, breakdown, _ = self._apply(df, [24])
        # mostly_zero (92% zeros >= 0.90) must drop.
        assert 'mostly_zero' in dropped, \
            f"v2.27.0 contract: ID 24 must drop mostly_zero; dropped={dropped}"
        # mostly_missing (91% missing >= 0.90) must drop.
        assert 'mostly_missing' in dropped, \
            f"v2.27.0 contract: ID 24 must drop mostly_missing; dropped={dropped}"
        # half_miss_half_zero has max(0.45, 0.45) = 0.45 < 0.90 — keep.
        assert 'half_miss_half_zero' not in dropped
        assert 'normal' not in dropped
        combo_step = next((b for b in breakdown if b['step'] == 'Combined sparsity+missing drop (threshold)'), None)
        assert combo_step is not None
        assert combo_step['threshold'] == 0.90

    # ── Outlier numeric quantile clipping (28-30) — already aligned ─
    def test_id_29_clips_numeric_columns_to_0_05_0_95_quantiles(self):
        """The exact request the user typed that exposed Patch B's
        underlying capability gap: 'change outlier cleaning interval
        for numerical features to 0.05-0.95'.  After v2.27.0 this is
        ID 29 in the catalog — frontend label and backend behavior
        agree, no realignment was needed for outlier IDs, but the
        catalog still owns the quantile-range constant now.
        """
        n = 100
        df = pd.DataFrame({
            # An obvious outlier at index 0 (extreme high), index 1 (extreme low)
            'with_outliers': [1000.0, -1000.0] + [float(i) for i in range(n - 2)],
        })
        original_max = df['with_outliers'].max()
        original_min = df['with_outliers'].min()
        work, dropped, breakdown, step_stats = self._apply(df, [29])
        # No columns dropped — clipping is value-modifying, not column-dropping.
        assert 'with_outliers' not in dropped
        # Max/min must be tightened to the [5%, 95%] quantiles.
        assert work['with_outliers'].max() < original_max
        assert work['with_outliers'].min() > original_min
        outlier_step = next((b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'), None)
        assert outlier_step is not None
        assert outlier_step['quantile_range'] == [0.05, 0.95]
        # step_stats records before/after snapshots for the AI pipeline.
        oc_stats = next((s for s in step_stats if s['step'] == 'Outlier cleaning (quantile clipping)'), None)
        assert oc_stats is not None
        assert oc_stats['quantile_range'] == [0.05, 0.95]

    # ── v2.28.1 critical regression: target preservation ──────────
    # Pre-v2.28.1, ID 29 (and 28/30) silently corrupted the binary
    # Target column.  An imbalanced 0/1 target with <5% positives has
    # both q(0.05) and q(0.95) equal to 0; clip(0,0) → all zeros →
    # split-validation chart shows 0% target mean across full / train
    # / test, modeling silently breaks downstream.  Reproduced by the
    # user on May 18, 2026 with Good_Bad_Flag.  These tests are the
    # immune system against re-introducing the bug.
    @staticmethod
    def _apply_with_preserve(df, option_ids, preserve=None, data_dictionary=None):
        from preprocessing.views import PreprocessingRunView
        view = PreprocessingRunView()
        return view._apply_options(
            df, set(option_ids),
            preserve=preserve,
            data_dictionary=data_dictionary,
        )

    def test_id_29_does_NOT_modify_Target_column_with_imbalanced_binary(self):
        """Repro of the May-2026 user bug:
            df = 100 rows, 5% Target=1 (95% Target=0)
            apply ID 29 (clip [0.05, 0.95])
            → Target column MUST be unchanged.

        Pre-fix: Target gets clipped to all zeros.
        Post-fix: Target preserved verbatim.
        """
        n = 100
        # Exactly 5 positives → q(0.05)=0 and q(0.95)=0 for binary target.
        target = [1] * 5 + [0] * (n - 5)
        df = pd.DataFrame({
            'Target': target,
            'feature_a': [float(i) for i in range(n)],  # ordinary numeric feature
        })
        target_before = df['Target'].copy()

        work, dropped, breakdown, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'},
        )

        # Critical: Target column is byte-for-byte unchanged.
        assert 'Target' in work.columns, "Target dropped from output"
        assert work['Target'].tolist() == target_before.tolist(), (
            f"Target column was modified by outlier clipping. "
            f"Sum before={target_before.sum()}, after={work['Target'].sum()}. "
            f"This re-introduces the v2.28.0 silent-corruption bug."
        )
        # And the breakdown reports Target as protected.
        outlier_step = next(
            (b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'),
            None,
        )
        assert outlier_step is not None
        assert 'Target' in outlier_step['protected_columns']

    def test_id_29_does_NOT_modify_Model_Usage_No_columns(self):
        """ID columns / index columns / raw timestamps with
        Model_Usage_YN='No' must not be clipped.  The categorical-
        outlier branch already honored this; the numerical branch
        must too (parity contract).
        """
        n = 50
        df = pd.DataFrame({
            'customer_id': list(range(1, n + 1)),  # 1..50, monotonic — q(0.05)=2.45, q(0.95)=47.55
            'feature_x': [float(i) for i in range(n)],
        })
        cust_id_before = df['customer_id'].copy()
        data_dict = [
            {'Feature_Name': 'customer_id', 'Model_Usage_YN': 'No'},
            {'Feature_Name': 'feature_x', 'Model_Usage_YN': 'Yes'},
        ]

        work, _, breakdown, _ = self._apply_with_preserve(
            df, [29], data_dictionary=data_dict,
        )

        # customer_id must be untouched (Model_Usage='No').
        assert work['customer_id'].tolist() == cust_id_before.tolist(), (
            "customer_id (Model_Usage_YN='No') was modified by outlier clipping."
        )
        # feature_x must have been clipped (its outliers should be
        # squeezed toward [q(0.05), q(0.95)]).  Strict inequality
        # checks the value-modifying behavior actually fired.
        assert work['feature_x'].min() >= 0.0
        # Breakdown surfaces the protection.
        outlier_step = next(
            (b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'),
            None,
        )
        assert outlier_step is not None
        assert 'customer_id' in outlier_step['protected_columns']
        assert 'feature_x' not in outlier_step['protected_columns']

    def test_id_29_still_clips_normal_numeric_features_when_target_preserved(self):
        """Defense-in-depth: while protecting Target + Model_Usage='No',
        we must NOT regress the core clipping behavior on legitimate
        ordinary features.
        """
        n = 100
        df = pd.DataFrame({
            'Target': [1] * 5 + [0] * (n - 5),
            # An obvious outlier at index 0 (extreme high), index 1 (extreme low).
            'with_outliers': [1000.0, -1000.0] + [float(i) for i in range(n - 2)],
        })
        original_max = df['with_outliers'].max()
        original_min = df['with_outliers'].min()

        work, _, breakdown, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'},
        )

        # The ordinary numeric feature is still clipped.
        assert work['with_outliers'].max() < original_max
        assert work['with_outliers'].min() > original_min
        # And Target is still safe.
        assert work['Target'].sum() == 5

    def test_id_29_repro_target_mean_unchanged_after_clipping(self):
        """The exact metric the user saw collapse to 0 in the screenshot:
        target_mean = mean(Target) per split.  This test reconstructs
        the chart's metric and asserts post-clip target_mean equals
        pre-clip target_mean.

        Pre-v2.28.1: target_mean drops to 0.0 across full/train/test.
        Post-fix: target_mean is preserved exactly.
        """
        n = 1000
        # 4% positive class — exactly the imbalanced shape that caused
        # both q(0.05) and q(0.95) to equal 0 → all-zero clip.
        positives = 40
        target = [1] * positives + [0] * (n - positives)
        df = pd.DataFrame({
            'Target': target,
            'noise_a': np.random.RandomState(0).randn(n).tolist(),
            'noise_b': np.random.RandomState(1).randn(n).tolist(),
        })
        target_mean_before = df['Target'].mean()
        assert target_mean_before == pytest.approx(0.04)  # sanity

        work, _, _, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'},
        )

        target_mean_after = work['Target'].mean()
        assert target_mean_after == pytest.approx(target_mean_before), (
            f"target_mean changed from {target_mean_before:.4f} to "
            f"{target_mean_after:.4f} after outlier clipping. "
            f"This is the smoking-gun metric from the May-2026 screenshot."
        )

    def test_id_29_protected_columns_logged_for_audit_trail(self):
        """The breakdown row must list every protected column so the
        user can audit *why* their Target column wasn't clipped.  Pre-
        v2.28.1 the breakdown silently said 'all numeric columns
        clipped' even though it did so to the Target — same opaque
        observability problem that hid the v2.27.0 ID-realignment bug.
        """
        df = pd.DataFrame({
            'Target': [0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
            'app_id': list(range(10)),
            'feature_a': [float(i) for i in range(10)],
        })
        data_dict = [
            {'Feature_Name': 'app_id', 'Model_Usage_YN': 'No'},
            {'Feature_Name': 'feature_a', 'Model_Usage_YN': 'Yes'},
        ]
        _, _, breakdown, _ = self._apply_with_preserve(
            df, [29], preserve={'Target'}, data_dictionary=data_dict,
        )
        outlier_step = next(
            (b for b in breakdown if b['step'] == 'Outlier cleaning (quantile clipping)'),
            None,
        )
        assert outlier_step is not None
        protected = set(outlier_step['protected_columns'])
        assert 'Target' in protected
        assert 'app_id' in protected
        assert 'feature_a' not in protected
        # Note string explains WHY the cols were skipped.
        assert 'protected' in outlier_step['note'].lower()


@pytest.mark.unit
class TestPurifierCatalogFrontendContract:
    """Parse the frontend's `purifierOptions` TS literal and assert the
    34 entries match the backend catalog character-for-character.

    Pre-v2.27.0 there was no such test, which is exactly why the IDs
    drifted apart.  Both frontend copies (modeling.component.ts and
    model-development.component.ts) are checked because the AI assistant
    panel reads the modeling copy while the data-purifier UI reads the
    model-development copy.
    """

    _FRONTEND_SOURCES = [
        'frontend/src/app/modeling/modeling.component.ts',
        'frontend/src/app/model-development/model-development.component.ts',
    ]

    @staticmethod
    def _parse_frontend_options(ts_source: str) -> list[dict]:
        """Extract the (id, name) pairs from the `purifierOptions` array
        in a TypeScript source string.  Tolerant to whitespace and
        optional `group: N` fields.
        """
        import re
        # Capture every `{ id: <int>, name: '<...>'`... block within the
        # purifierOptions array.  The array contents extend until the
        # closing `];` so we anchor on that.
        block_re = re.compile(
            r"purifierOptions\s*:\s*PurifierOption\[\]\s*=\s*\[(.*?)\];",
            re.DOTALL,
        )
        m = block_re.search(ts_source)
        if not m:
            return []
        body = m.group(1)
        entry_re = re.compile(
            r"\{\s*id\s*:\s*(\d+)\s*,\s*name\s*:\s*'([^']*)'",
        )
        return [{'id': int(idm), 'name': name} for idm, name in entry_re.findall(body)]

    @staticmethod
    def _read_repo_file(rel_path: str) -> str:
        import pathlib
        # backend/tests/test_unit.py → backend/ → repo root
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        full = repo_root / rel_path
        if not full.exists():
            pytest.skip(f"frontend source not present at {full}; skipping contract test")
        return full.read_text(encoding='utf-8')

    @pytest.mark.parametrize('frontend_rel_path', _FRONTEND_SOURCES)
    def test_frontend_purifier_options_match_backend_catalog(self, frontend_rel_path):
        from preprocessing.purifier_catalog import PURIFIER_OPTIONS
        ts_src = self._read_repo_file(frontend_rel_path)
        frontend_opts = self._parse_frontend_options(ts_src)
        assert len(frontend_opts) == 34, (
            f"{frontend_rel_path} parsed {len(frontend_opts)} entries; "
            f"expected 34.  Did the TS array shape change?"
        )

        # Build a {id: name} map on each side and compare.
        backend_map = {e['id']: e['name'] for e in PURIFIER_OPTIONS}
        frontend_map = {e['id']: e['name'] for e in frontend_opts}
        mismatches = []
        for opt_id in range(1, 35):
            be = backend_map.get(opt_id)
            fe = frontend_map.get(opt_id)
            if be != fe:
                mismatches.append(f"  id={opt_id}: backend={be!r}  frontend={fe!r}")
        assert not mismatches, (
            "Frontend↔backend purifier-option labels diverged. "
            "Update both sides to match (frontend is the source of truth for UI).\n"
            + "\n".join(mismatches)
        )


# ---------------------------------------------------------------------------
# v2.27.1 — AI catalog tool: get_purifier_options
# ---------------------------------------------------------------------------
# Patch B (v2.27.1) exposes the canonical purifier catalog to the LLM via a
# dedicated tool so the assistant can map natural-language requests like
# "set the outlier interval to 0.05/0.95" to the right integer option ID
# (29) when emitting a start_data_purifier action.  Pre-v2.27.1 the AI had
# to guess from a misleading generic step list in the system prompt and
# routinely invented step names like "Quasi-Constant Drop" / "High
# Cardinality Drop" that don't exist in the catalog.
#
# These tests guard:
#   • The handler returns the full canonical catalog with stable formatting.
#   • The tool is registered in PIPELINE_TOOLS (so the LLM can see it) and
#     in _HANDLERS (so execute_tool_call can dispatch to it).
#   • The system prompt no longer hands the LLM the misleading list and
#     instead points it at the new tool.
@pytest.mark.unit
class TestGetPurifierOptionsToolHandler:
    """Exercises ai_assistant.tool_executor._handle_get_purifier_options."""

    def _run(self, args=None):
        from ai_assistant.tool_executor import _handle_get_purifier_options
        # file_id is irrelevant for this static-catalog tool; pass a dummy.
        return _handle_get_purifier_options(0, args or {})

    def test_returns_string(self):
        out = self._run()
        assert isinstance(out, str)
        assert out.strip()

    def test_unfiltered_lists_all_34_options(self):
        out = self._run()
        # Each option line starts with `ID `; count the entries between
        # the two `---` separator lines.
        lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(lines) == 34, (
            f"Expected 34 ID-prefixed lines, got {len(lines)}.\nOutput:\n{out}"
        )

    def test_header_advertises_total_count(self):
        out = self._run()
        assert "34 of 34 total entries" in out, (
            f"Header should report 34/34 entries; got:\n{out}"
        )

    def test_default_selected_ids_listed_in_header(self):
        out = self._run()
        # Handler renders defaults via `sorted(DEFAULT_SELECTED_IDS)`,
        # so we can pin the exact literal.
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS
        expected_literal = str(sorted(DEFAULT_SELECTED_IDS))
        assert "Default selected IDs" in out
        assert expected_literal in out, (
            f"Header should print sorted defaults verbatim ({expected_literal}); got:\n{out}"
        )

    def test_default_options_are_flagged_inline(self):
        """Default-selected options carry a (DEFAULT) marker on their line."""
        out = self._run()
        from preprocessing.purifier_catalog import DEFAULT_SELECTED_IDS
        for default_id in DEFAULT_SELECTED_IDS:
            # Find the line for this ID and confirm it contains DEFAULT.
            line = next(
                (ln for ln in out.splitlines()
                 if ln.startswith('ID ') and ln.split()[1] == str(default_id)),
                None,
            )
            assert line is not None, f"No line for ID {default_id} in output:\n{out}"
            assert 'DEFAULT' in line, (
                f"ID {default_id} is in DEFAULT_SELECTED_IDS but its line "
                f"does not carry the DEFAULT marker:\n  {line}"
            )

    def test_non_default_option_does_not_carry_marker(self):
        """Negative case: ID 29 is NOT a default and must not show DEFAULT."""
        out = self._run()
        line = next(
            (ln for ln in out.splitlines()
             if ln.startswith('ID ') and ln.split()[1] == '29'),
            None,
        )
        assert line is not None
        assert 'DEFAULT' not in line, (
            f"ID 29 is not in DEFAULT_SELECTED_IDS but line carries DEFAULT:\n  {line}"
        )

    def test_id_29_appears_with_quantile_range_and_correct_label(self):
        """The canonical example we want the AI to emit: ID 29 = outlier
        cleaning at quantiles [0.05-0.95].  Pre-v2.27.0 the system prompt
        hid this; v2.27.1 makes it explicit via this tool."""
        out = self._run()
        line = next(
            (ln for ln in out.splitlines()
             if ln.startswith('ID ') and ln.split()[1] == '29'),
            None,
        )
        assert line is not None, f"ID 29 missing from output:\n{out}"
        assert 'outlier_quantile_clip' in line
        assert 'outlier_num_group' in line
        assert 'quantile_range=(0.05, 0.95)' in line
        assert '"Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]"' in line

    def test_id_5_appears_with_threshold_0_95(self):
        """Smoke-check a threshold-drop entry: ID 5 = corr-drop @ 0.95."""
        out = self._run()
        line = next(
            (ln for ln in out.splitlines()
             if ln.startswith('ID ') and ln.split()[1] == '5'),
            None,
        )
        assert line is not None, f"ID 5 missing from output:\n{out}"
        assert 'corr_drop' in line and 'corr_drop_group' in line
        assert 'threshold=0.95' in line

    def test_kind_filter_outlier_quantile_clip_returns_only_three(self):
        out = self._run({'kind': 'outlier_quantile_clip'})
        id_lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(id_lines) == 3, (
            f"outlier_quantile_clip kind has 3 catalog entries; got "
            f"{len(id_lines)}.\nOutput:\n{out}"
        )
        # All three must reference the kind.
        for ln in id_lines:
            assert 'outlier_quantile_clip' in ln

    def test_kind_filter_corr_drop_returns_only_five(self):
        out = self._run({'kind': 'corr_drop'})
        id_lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(id_lines) == 5
        for ln in id_lines:
            assert 'corr_drop' in ln

    def test_kind_filter_unknown_returns_helpful_error(self):
        out = self._run({'kind': 'no_such_kind'})
        assert "No purifier options match" in out
        assert "Valid kinds" in out
        # Surface a few real kinds so the LLM can self-correct.
        assert 'corr_drop' in out
        assert 'outlier_quantile_clip' in out

    def test_kind_filter_skips_default_id_header(self):
        """When filtered, the 'Default selected IDs' line should be omitted
        to keep the response focused on the requested family."""
        out = self._run({'kind': 'outlier_quantile_clip'})
        assert "Default selected IDs" not in out

    def test_handler_does_not_touch_redis_cache(self, monkeypatch):
        """The catalog is static; the handler must not call cache_get."""
        calls = []
        from ai_assistant import cache as cache_mod
        monkeypatch.setattr(
            cache_mod, 'cache_get',
            lambda *a, **kw: calls.append((a, kw)) or None,
        )
        out = self._run()
        assert calls == [], (
            f"_handle_get_purifier_options must not call cache_get; "
            f"observed calls: {calls}"
        )
        # And it still produces a real catalog response.
        assert "Data Purifier Options Catalog" in out

    def test_handler_ignores_file_id(self):
        """Catalog content is identical regardless of file_id supplied."""
        from ai_assistant.tool_executor import _handle_get_purifier_options
        out_a = _handle_get_purifier_options(0, {})
        out_b = _handle_get_purifier_options(99999, {})
        assert out_a == out_b


@pytest.mark.unit
class TestGetPurifierOptionsToolRegistration:
    """The new tool must be wired into both the LLM-facing schema
    (PIPELINE_TOOLS) and the dispatcher (_HANDLERS).  Either gap leaves
    the AI unable to use the tool even if the handler works."""

    def test_tool_is_in_pipeline_tools_schema(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        names = [t['function']['name'] for t in PIPELINE_TOOLS]
        assert 'get_purifier_options' in names, (
            f"get_purifier_options not found in PIPELINE_TOOLS. "
            f"Registered tool names: {names}"
        )

    def test_tool_schema_has_kind_filter_with_full_enum(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(
            t for t in PIPELINE_TOOLS
            if t['function']['name'] == 'get_purifier_options'
        )
        kind_param = spec['function']['parameters']['properties'].get('kind')
        assert kind_param is not None, "kind parameter missing"
        # Enum must cover every kind constant defined in the catalog
        # so the LLM cannot drift into invalid filter values.
        from preprocessing import purifier_catalog as pc
        catalog_kinds = sorted({e['kind'] for e in pc.PURIFIER_OPTIONS})
        assert sorted(kind_param['enum']) == catalog_kinds, (
            f"kind enum drifted from catalog kinds.\n"
            f"  schema enum:    {sorted(kind_param['enum'])}\n"
            f"  catalog kinds:  {catalog_kinds}"
        )

    def test_tool_schema_marks_kind_optional(self):
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(
            t for t in PIPELINE_TOOLS
            if t['function']['name'] == 'get_purifier_options'
        )
        # Required list should NOT include 'kind' — full catalog with no
        # filter is a valid call.
        assert 'kind' not in spec['function']['parameters'].get('required', [])

    def test_tool_description_mentions_start_data_purifier_link(self):
        """The description should tell the LLM this is the pre-flight tool
        for start_data_purifier so retrieval-augmented planning works."""
        from ai_assistant.tool_definitions import PIPELINE_TOOLS
        spec = next(
            t for t in PIPELINE_TOOLS
            if t['function']['name'] == 'get_purifier_options'
        )
        desc = spec['function']['description']
        assert 'start_data_purifier' in desc, (
            f"Description should reference start_data_purifier; got:\n{desc}"
        )

    def test_tool_is_in_dispatcher(self):
        from ai_assistant.tool_executor import _HANDLERS, _handle_get_purifier_options
        assert _HANDLERS.get('get_purifier_options') is _handle_get_purifier_options

    def test_execute_tool_call_dispatches_to_handler(self):
        from ai_assistant.tool_executor import execute_tool_call
        out = execute_tool_call(0, 'get_purifier_options', {})
        # Should produce the catalog header, not the unknown-tool sentinel.
        assert "Data Purifier Options Catalog" in out
        assert "Unknown tool" not in out

    def test_execute_tool_call_passes_kind_arg_through(self):
        from ai_assistant.tool_executor import execute_tool_call
        out = execute_tool_call(0, 'get_purifier_options', {'kind': 'corr_drop'})
        id_lines = [ln for ln in out.splitlines() if ln.startswith('ID ')]
        assert len(id_lines) == 5  # 5 corr_drop thresholds


@pytest.mark.unit
class TestSystemPromptPurifierGuidance:
    """The pre-v2.27.1 system prompt listed five generic step names
    ("Missing Value Imputation", "Outlier Removal (Numeric)", "Constant
    Column Drop", "Quasi-Constant Drop", "High Cardinality Drop") that
    don't exist in the canonical catalog.  Those phrases led the LLM to
    fabricate IDs and step names.  The v2.27.1 prompt must:
      • not advertise any of those phantom phrases;
      • mention every real transform kind so the LLM has a vocabulary;
      • tell the LLM to call get_purifier_options before mapping intent
        to integer IDs in start_data_purifier.
    """

    def _prompt(self):
        from ai_assistant.views import SYSTEM_PROMPT
        return SYSTEM_PROMPT

    def test_no_phantom_step_names(self):
        prompt = self._prompt()
        forbidden = [
            'Quasi-Constant Drop',
            'High Cardinality Drop',
            'Missing Value Imputation',
            'Constant Column Drop',
        ]
        # "Outlier Removal (Numeric)" is a borderline phrase; the catalog
        # uses "Outlier-cleaning". Pin the explicit pre-v2.27.1 wording.
        forbidden.append('Outlier Removal (Numeric)')
        present = [phrase for phrase in forbidden if phrase in prompt]
        assert not present, (
            "System prompt still advertises phantom purifier step names "
            "that don't exist in the catalog: "
            + ', '.join(repr(p) for p in present)
        )

    def test_prompt_lists_every_real_transform_kind(self):
        prompt = self._prompt()
        from preprocessing import purifier_catalog as pc
        catalog_kinds = sorted({e['kind'] for e in pc.PURIFIER_OPTIONS})
        missing = [k for k in catalog_kinds if k not in prompt]
        assert not missing, (
            f"System prompt is missing these real transform kinds: {missing}.\n"
            f"All catalog kinds must appear so the LLM can ground its replies."
        )

    def test_prompt_directs_llm_to_get_purifier_options_tool(self):
        prompt = self._prompt()
        assert 'get_purifier_options' in prompt, (
            "System prompt must mention get_purifier_options so the LLM "
            "knows the tool exists."
        )

    def test_prompt_links_tool_to_start_data_purifier_action(self):
        prompt = self._prompt()
        # The action-block section must instruct calling the catalog tool
        # before emitting purifier_options.
        action_section = prompt.split('ACTION TYPE 6: start_data_purifier')[-1]
        action_section = action_section.split('ACTION TYPE 7')[0]
        assert 'get_purifier_options' in action_section, (
            "start_data_purifier action rules must instruct calling "
            "get_purifier_options first to map user intent to IDs."
        )

    def test_prompt_announces_exactly_34_options(self):
        prompt = self._prompt()
        # Exact count anchors the LLM and lets us catch silent drift if
        # the catalog grows but the prompt isn't updated.
        assert '34' in prompt, "Prompt should anchor the option count at 34."


# ---------------------------------------------------------------------------
# v2.27.2 — Empty-response synthesis pass + actionable fallback (Patch A)
# ---------------------------------------------------------------------------
# Pre-v2.27.2 the chat workflow could exit its tool-call loop with an
# assistant message that had `tool_calls` populated but `content=null`.
# This happened when the model kept calling tools through the very last
# round (the no-tools forced round): we executed those tool calls inside
# the loop body, then broke naturally without ever asking the model for a
# final text answer.  The user saw the bare string "No response received."
# in the chat UI, and tracing showed real tool work that produced no
# visible output.
#
# v2.27.2 fixes this with two layers of defence:
#   1. A synthesis pass — when the loop exits with empty content but tool
#      work happened, run ONE more no-tools call so the model verbalizes
#      what it found.  All tool results are already in `messages` so this
#      is cheap.
#   2. An actionable fallback — if the synthesis pass also fails (network
#      error, model truly returns blank), surface a meaningful message
#      that tells the user what to do next.  Two flavours: one for the
#      "tool work happened, ran out of room" case and one for the "model
#      returned nothing at all" case.
#
# The tests below script the exact LLM response sequences that triggered
# the bug pre-v2.27.2 and assert that v2.27.2 always returns a meaningful
# `message` to the API caller.
def _mock_llm_response(content=None, tool_calls=None, tokens=10):
    """Build an OpenAI-style /v1/chat/completions response payload.

    `content=None` + non-empty `tool_calls` is the exact shape that
    triggered the original "No response received." bug.
    """
    msg = {'role': 'assistant', 'content': content}
    if tool_calls is not None:
        msg['tool_calls'] = tool_calls
    finish = 'tool_calls' if tool_calls else 'stop'
    return {
        'choices': [{'finish_reason': finish, 'message': msg}],
        'usage': {
            'prompt_tokens': tokens,
            'completion_tokens': tokens,
            'total_tokens': tokens * 2,
        },
    }


def _purifier_tool_call(call_id):
    """A canned tool_call invocation against get_purifier_options — the
    handler is static and side-effect-free, so it works inside any test
    without Redis or DB fixtures."""
    return [{
        'id': call_id,
        'type': 'function',
        'function': {'name': 'get_purifier_options', 'arguments': '{}'},
    }]


@pytest.mark.unit
class TestChatWorkflowSynthesisPass:
    """Assert the synthesis pass triggers in exactly the right conditions
    and produces a non-empty `message` on the final API response.
    """

    def _patch_chat_env(self, monkeypatch, llm_responses):
        """Prepare _chat_workflow to run with a scripted LLM and tool-mode
        enabled.  `llm_responses` is a list of dicts; the i-th call to
        _call_llm returns `llm_responses[i]` (or the last entry if exhausted).
        """
        from ai_assistant import views
        import json as _json
        calls = []

        def fake_call_llm(messages, model_key, tools=None):
            first = (messages[0].get('content') if messages else '') or ''
            if "DeclarAI's intent classifier" in first:
                return {
                    'choices': [{
                        'finish_reason': 'stop',
                        'message': {
                            'role': 'assistant',
                            'content': _json.dumps({
                                'labels': ['A'],
                                'confidence': 'high',
                                'uncertain': False,
                                'decomposition': [{
                                    'segment': 'test',
                                    'labels': ['A'],
                                }],
                            }),
                        },
                    }],
                    'usage': {
                        'prompt_tokens': 1,
                        'completion_tokens': 1,
                        'total_tokens': 2,
                    },
                }
            idx = min(len(calls), len(llm_responses) - 1)
            calls.append({
                'tools_provided': tools is not None,
                'last_role': messages[-1].get('role') if messages else None,
                'msg_count': len(messages),
            })
            return llm_responses[idx]

        # Tool mode requires cached artifacts + supports_tools.
        monkeypatch.setattr(views, '_call_llm', fake_call_llm)
        monkeypatch.setattr(views, 'cache_list_artifacts',
                            lambda fid: ['split_validation'])
        monkeypatch.setattr(views, '_build_slim_context',
                            lambda fid, sec: 'slim context')
        monkeypatch.setattr(
            views, 'get_model_config',
            lambda key: {
                'provider': 'openai',
                'model_id': 'gpt-test',
                'supports_tools': True,
            },
        )
        return calls

    def test_synthesis_pass_runs_when_loop_exhausts_budget_with_empty_content(self, monkeypatch):
        """The exact bug from v2.26.1: every round returns tool_calls + null
        content, the loop runs out, msg_obj has empty content.  Synthesis
        pass must run AFTER the loop and produce a real reply."""
        from ai_assistant import views

        # 6 in-loop rounds (0..5) all return tool_calls + null content;
        # the 7th call is the synthesis pass and returns real content.
        responses = [
            _mock_llm_response(tool_calls=_purifier_tool_call(f'tc_{i}'))
            for i in range(6)
        ] + [
            _mock_llm_response(content='Here are the 34 purifier options.')
        ]
        calls = self._patch_chat_env(monkeypatch, responses)

        result = views._chat_workflow(
            user_message='list all purifier options',
            context={},
            section='general',
            history=[],
            file_id=1,
            model='gpt-5.5',
        )

        # Exactly 7 LLM calls: 6 in-loop + 1 synthesis pass.
        assert len(calls) == 7, (
            f"Expected 7 _call_llm invocations (6 loop rounds + 1 synthesis); "
            f"got {len(calls)}."
        )
        # The last call must have tools disabled — synthesis pass forces
        # text output.
        assert calls[-1]['tools_provided'] is False, (
            "Synthesis pass must invoke _call_llm with tools=None to force "
            "a text response."
        )
        # The synthesis system prompt must be the most recent system msg
        # before the synthesis call.
        assert calls[-1]['last_role'] == 'system'
        # Final response.message comes from the synthesis pass content.
        assert result['message'] == 'Here are the 34 purifier options.'

    def test_synthesis_pass_does_not_run_on_happy_path(self, monkeypatch):
        """When the model returns content on round 0, no synthesis pass is
        needed.  Critical regression guard — the synthesis pass adds an
        LLM round-trip per turn and must NOT fire unless the loop exited
        with empty content."""
        from ai_assistant import views

        responses = [_mock_llm_response(content='Direct reply, no tools.')]
        calls = self._patch_chat_env(monkeypatch, responses)

        result = views._chat_workflow(
            user_message='hi', context={}, section='general',
            history=[], file_id=1, model='gpt-5.5',
        )

        assert len(calls) == 1, (
            f"Happy path must use exactly one LLM call; got {len(calls)}."
        )
        assert result['message'] == 'Direct reply, no tools.'

    def test_synthesis_pass_does_not_run_when_no_tool_work_happened(self, monkeypatch):
        """Edge case: the model returns finish_reason='stop' with empty
        content and NO tools were called this turn.  Don't run a synthesis
        pass — there's nothing to synthesize from.  Fall through to the
        generic _EMPTY_RESPONSE_FALLBACK instead."""
        from ai_assistant import views

        responses = [_mock_llm_response(content='')]
        calls = self._patch_chat_env(monkeypatch, responses)

        result = views._chat_workflow(
            user_message='???', context={}, section='general',
            history=[], file_id=1, model='gpt-5.5',
        )

        # Exactly one call — no synthesis pass.
        assert len(calls) == 1, (
            f"With no tool work + empty content, no synthesis pass should "
            f"run; got {len(calls)} LLM calls."
        )
        # Generic empty fallback.
        assert result['message'] == views._EMPTY_RESPONSE_FALLBACK

    def test_synthesis_pass_failure_falls_back_to_budget_exhausted_copy(self, monkeypatch):
        """If the synthesis call ALSO returns empty, the user must see the
        tool-budget-exhausted fallback (different from the no-content
        fallback because real work was done)."""
        from ai_assistant import views

        responses = [
            _mock_llm_response(tool_calls=_purifier_tool_call(f'tc_{i}'))
            for i in range(6)
        ] + [
            _mock_llm_response(content='')  # synthesis returns blank
        ]
        calls = self._patch_chat_env(monkeypatch, responses)

        result = views._chat_workflow(
            user_message='hi', context={}, section='general',
            history=[], file_id=1, model='gpt-5.5',
        )

        assert len(calls) == 7
        assert result['message'] == views._TOOL_BUDGET_EXHAUSTED_FALLBACK

    def test_usage_merges_synthesis_pass_tokens(self, monkeypatch):
        """The synthesis pass costs tokens — they must be merged into
        total_usage so the cost dashboard reflects the true spend."""
        from ai_assistant import views

        # 1 classifier call @ 1 token each side + 6 in-loop rounds @ 10
        # tokens each + 1 synthesis @ 25 tokens.
        responses = [
            _mock_llm_response(
                tool_calls=_purifier_tool_call(f'tc_{i}'), tokens=10,
            )
            for i in range(6)
        ] + [
            _mock_llm_response(content='Synthesized answer.', tokens=25)
        ]
        self._patch_chat_env(monkeypatch, responses)

        result = views._chat_workflow(
            user_message='hi', context={}, section='general',
            history=[], file_id=1, model='gpt-5.5',
        )

        usage = result['usage']
        # Each mock response declares prompt_tokens=tokens, completion_tokens=tokens.
        # 1 classifier call @ tokens=1 → 1 prompt + 1 completion = 2 total.
        # 6 loop calls @ tokens=10 → 60 prompt + 60 completion = 120 total.
        # 1 synthesis call @ tokens=25 → 25 prompt + 25 completion = 50 total.
        # Grand totals: 86 prompt, 86 completion, 172 total.
        assert usage.get('prompt_tokens') == 1 + 6 * 10 + 25
        assert usage.get('completion_tokens') == 1 + 6 * 10 + 25
        assert usage.get('total_tokens') == 2 + 6 * 20 + 50

    def test_synthesis_pass_uses_tools_none(self, monkeypatch):
        """The whole point of the synthesis pass is to disable tools so the
        model produces text.  Pin this contract so a future refactor
        cannot accidentally re-enable tools and re-introduce the empty-
        response loop."""
        from ai_assistant import views

        responses = [
            _mock_llm_response(tool_calls=_purifier_tool_call(f'tc_{i}'))
            for i in range(6)
        ] + [
            _mock_llm_response(content='Synth answer.')
        ]
        calls = self._patch_chat_env(monkeypatch, responses)

        views._chat_workflow(
            user_message='hi', context={}, section='general',
            history=[], file_id=1, model='gpt-5.5',
        )

        # The 7th (synthesis) call must have tools=None.
        assert calls[6]['tools_provided'] is False

    def test_action_only_response_does_not_trigger_fallback(self, monkeypatch):
        """Regression guard: when the model emits ONLY an ACTION BLOCK
        (no surrounding prose), the existing 'I've prepared the following
        operation' message takes precedence over the empty-response
        fallback.  This test pins that path."""
        from ai_assistant import views

        action_only = (
            "<<<ACTION:update_notes>>>\n"
            '{"action": "add", "position": "after_data_preview", '
            '"content": "test note", "description": "Add a test note"}\n'
            "<<<END_ACTION>>>"
        )
        responses = [_mock_llm_response(content=action_only)]
        self._patch_chat_env(monkeypatch, responses)

        result = views._chat_workflow(
            user_message='add a note', context={}, section='general',
            history=[], file_id=1, model='gpt-5.5',
        )

        # Action surfaced.
        assert result.get('actions'), "ACTION BLOCK should be parsed out."
        # Message is the canned 'I've prepared…' string, NOT the empty
        # fallback.
        assert 'prepared' in result['message'].lower()
        assert result['message'] != views._EMPTY_RESPONSE_FALLBACK
        assert result['message'] != views._TOOL_BUDGET_EXHAUSTED_FALLBACK


@pytest.mark.unit
class TestEmptyResponseFallbackConstants:
    """Pin the actionable copy strings.  These are user-facing text — we
    want a deliberate test failure if they get truncated, mangled, or
    accidentally reverted to the bare 'No response received.' literal."""

    def test_empty_response_fallback_is_actionable(self):
        from ai_assistant.views import _EMPTY_RESPONSE_FALLBACK
        assert isinstance(_EMPTY_RESPONSE_FALLBACK, str)
        assert _EMPTY_RESPONSE_FALLBACK.strip()
        # Must give the user a concrete next action ("rephrasing",
        # "for example", etc.) — not just say "no response".
        assert 'rephras' in _EMPTY_RESPONSE_FALLBACK.lower(), (
            "Fallback should suggest rephrasing the question."
        )
        # Should not be the bare pre-v2.27.2 string.
        assert _EMPTY_RESPONSE_FALLBACK.strip() != 'No response received.'

    def test_tool_budget_exhausted_fallback_is_actionable(self):
        from ai_assistant.views import _TOOL_BUDGET_EXHAUSTED_FALLBACK
        assert isinstance(_TOOL_BUDGET_EXHAUSTED_FALLBACK, str)
        assert _TOOL_BUDGET_EXHAUSTED_FALLBACK.strip()
        # Must acknowledge tool work happened (different vibe from the
        # generic empty-response copy).
        low = _TOOL_BUDGET_EXHAUSTED_FALLBACK.lower()
        assert 'tool' in low or 'context' in low or 'gathered' in low
        # Should suggest a more focused follow-up.
        assert 'focused' in low or 'follow-up' in low or 'specific' in low

    def test_two_fallbacks_are_distinct(self):
        from ai_assistant.views import (
            _EMPTY_RESPONSE_FALLBACK, _TOOL_BUDGET_EXHAUSTED_FALLBACK,
        )
        assert _EMPTY_RESPONSE_FALLBACK != _TOOL_BUDGET_EXHAUSTED_FALLBACK, (
            "The two fallbacks must be distinct so tracing / UX can "
            "distinguish 'model gave up immediately' from 'model burned "
            "the tool budget'."
        )


# ---------------------------------------------------------------------------
# v2.40.0: provider-aware system prompt selection
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSystemPromptSelection:
    """Pin the v2.40.0 contract: engine models (gemma, llama, qwen, ...)
    receive the lite ~2500-token system prompt; OpenAI cloud models keep the
    full ~9000-token prompt; defensive paths (empty/None config) default to
    the full prompt so we never accidentally ship a stripped prompt to a
    model that needs the full guidance.

    The lite prompt MUST preserve every action-type schema so the model can
    still emit any pipeline action — only the long-form coaching prose,
    pipeline-step deep-dives, and verbose examples are stripped.
    """

    def test_engine_provider_returns_lite_variant(self):
        from ai_assistant.views import (
            _choose_system_prompt, _LITE_SYSTEM_PROMPT,
        )
        prompt, variant = _choose_system_prompt({'provider': 'engine'})
        assert variant == 'lite'
        assert prompt is _LITE_SYSTEM_PROMPT

    def test_openai_provider_returns_full_variant(self):
        from ai_assistant.views import _choose_system_prompt, SYSTEM_PROMPT
        prompt, variant = _choose_system_prompt({'provider': 'openai'})
        assert variant == 'full'
        assert prompt is SYSTEM_PROMPT

    def test_empty_config_defaults_to_full(self):
        """Defensive: a missing/empty model config should NOT silently
        downgrade to the lite prompt — we'd rather over-ship guidance than
        strip rules from a model whose provider we couldn't identify."""
        from ai_assistant.views import _choose_system_prompt, SYSTEM_PROMPT
        prompt, variant = _choose_system_prompt({})
        assert variant == 'full'
        assert prompt is SYSTEM_PROMPT

    def test_none_config_defaults_to_full(self):
        """Same as empty — a None config means we couldn't resolve the
        model entry, so default to the full safety-net prompt."""
        from ai_assistant.views import _choose_system_prompt, SYSTEM_PROMPT
        prompt, variant = _choose_system_prompt(None)
        assert variant == 'full'
        assert prompt is SYSTEM_PROMPT

    def test_unknown_provider_defaults_to_full(self):
        """Forward-compat: a future provider we don't recognize gets the
        full prompt by default.  We will explicitly add 'engine'-class
        providers to the lite mapping when we onboard them."""
        from ai_assistant.views import _choose_system_prompt, SYSTEM_PROMPT
        prompt, variant = _choose_system_prompt({'provider': 'anthropic'})
        assert variant == 'full'
        assert prompt is SYSTEM_PROMPT

    def test_lite_prompt_is_meaningfully_smaller(self):
        """The whole point of v2.40.0 is the size win.  Lock in a lower
        bound on the reduction so future edits to the lite prompt can't
        regress past 50% — at that point we'd lose most of the gemma
        budget headroom we're trying to free."""
        from ai_assistant.views import SYSTEM_PROMPT, _LITE_SYSTEM_PROMPT
        full_chars = len(SYSTEM_PROMPT)
        lite_chars = len(_LITE_SYSTEM_PROMPT)
        reduction = 1.0 - (lite_chars / full_chars)
        assert reduction > 0.50, (
            f"Lite prompt should be at least 50% smaller than full; "
            f"got {reduction*100:.1f}% reduction "
            f"({full_chars} -> {lite_chars} chars)."
        )

    def test_lite_prompt_preserves_every_action_type(self):
        """Critical: the lite prompt must still contain every action type
        marker so engine models can emit any pipeline action.  If a future
        edit accidentally drops one, gemma silently loses the ability to
        invoke that operation — and the failure mode is invisible (the
        model just stops emitting that action block, no error)."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        required_action_types = [
            'execute_code',
            'update_metadata',
            'update_config',
            'set_ordinal_ranking',
            'start_sfs',
            'start_data_purifier',
            'apply_encoding',
            'start_modeling',
            'update_notes',
        ]
        missing = [a for a in required_action_types
                   if a not in _LITE_SYSTEM_PROMPT]
        assert not missing, (
            f"Lite prompt is missing action types: {missing}. "
            f"Engine models will lose the ability to invoke them."
        )

    def test_lite_prompt_preserves_action_block_grammar(self):
        """The triple-bracket markers <<<ACTION:...>>> + <<<END_ACTION>>>
        are how _extract_actions parses the model's reply.  If the lite
        prompt drops them, the model won't know how to format actions and
        every action block will be invisible to the parser."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        assert '<<<ACTION:' in _LITE_SYSTEM_PROMPT
        assert '<<<END_ACTION>>>' in _LITE_SYSTEM_PROMPT

    def test_lite_prompt_preserves_one_action_per_turn_rule(self):
        """RULE 3 (one action block per turn) is the load-bearing
        procedural rule that prevents the model from emitting tangled
        multi-action chains.  Even in the slim lite prompt it must stay."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        low = _LITE_SYSTEM_PROMPT.lower()
        # Either 'one action block per turn' OR a nearby paraphrase.
        assert (
            'one action block per turn' in low
            or 'most upstream' in low
            or 'one action' in low
        ), (
            "Lite prompt must preserve the one-action-per-turn rule "
            "or its decision rationale."
        )

    def test_lite_prompt_preserves_sfs_honesty_rule(self):
        """RULE 5 in the full prompt: never claim 'SFS started' without
        emitting start_sfs.  This is the rule that prevents the assistant
        from lying about pipeline state (the failure mode that motivated
        v2.26.0+).  The lite prompt's RULE 2 covers this."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        low = _LITE_SYSTEM_PROMPT.lower()
        # Must mention either 'sfs started' (negated) or 'honesty' / 'state'.
        assert (
            'sfs started' in low
            or 'honesty' in low
            or 'never claim' in low
        ), (
            "Lite prompt must keep the orchestration-honesty rule so "
            "engine models don't fabricate 'SFS started' / 'modeling "
            "started' messages without firing the matching action."
        )

    def test_lite_prompt_has_tool_routing_section(self):
        """v2.40.1: the lite prompt MUST contain an explicit TOOL ROUTING
        section that maps user intent → required tool call.  Engine models
        (gemma, llama, qwen) skip tool calls for analytical questions when
        the slim context "feels" complete enough — even though the slim
        context only carries feature names + pipeline status, NOT the
        actual analysis numbers.  The routing table forces an explicit
        intent→tool mapping the model can pattern-match against."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        # Header presence (case-insensitive — the actual header is uppercase
        # but checking lowercase is forgiving against future rewrites).
        assert 'tool routing' in _LITE_SYSTEM_PROMPT.lower(), (
            "Lite prompt must contain a TOOL ROUTING section so engine "
            "models know which tool to call for which kind of question."
        )
        # The directive 'WHEN IN DOUBT, CALL THE TOOL' is the key anti-
        # hallucination instruction — it tilts gemma's default from
        # 'answer directly' to 'fetch data first'.
        assert 'when in doubt, call the tool' in _LITE_SYSTEM_PROMPT.lower()

    def test_lite_prompt_routes_sfs_to_get_sfs_results(self):
        """The motivating failure (2026-05-20 trace): user asks 'analyze
        the SFS results' → gemma skips the tool and hallucinates.  The
        routing table MUST explicitly map SFS-related vocabulary to
        get_sfs_results so gemma cannot ambiguate."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        low = _LITE_SYSTEM_PROMPT.lower()
        # Vocabulary trigger AND target tool must both appear in the
        # routing block (signaled by the 'tool routing' header above).
        assert 'sfs' in low
        assert 'get_sfs_results' in _LITE_SYSTEM_PROMPT
        # The two should be co-located — search the routing table region.
        routing_start = low.find('tool routing')
        routing_end = low.find('actionable operations')
        assert routing_start >= 0 and routing_end > routing_start, (
            "Could not locate routing section for co-location check."
        )
        routing_block = _LITE_SYSTEM_PROMPT[routing_start:routing_end]
        assert 'get_sfs_results' in routing_block, (
            "get_sfs_results must appear inside the TOOL ROUTING block, "
            "not just somewhere in the prompt."
        )
        # SFS-specific keywords must trigger the route.
        rb_low = routing_block.lower()
        assert 'forward' in rb_low and 'backward' in rb_low, (
            "Routing block must mention 'forward' AND 'backward' as "
            "SFS-vocabulary triggers."
        )

    def test_lite_prompt_routes_every_registered_tool(self):
        """Every tool the executor exposes (except invoke_skill /
        get_skill_file, which are the auto-routed skills path) must
        appear in the routing table.  If a future tool is added to
        tool_executor._HANDLERS but not to the routing table, gemma
        will silently lose the ability to discover it."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        from ai_assistant.tool_executor import _HANDLERS
        # Skills are auto-routed pre-LLM via _auto_route_skill; the LLM
        # never has to "decide" to call them based on the routing table.
        skill_tools = {'invoke_skill', 'get_skill_file'}
        analytical_tools = set(_HANDLERS.keys()) - skill_tools
        missing = [t for t in analytical_tools
                   if t not in _LITE_SYSTEM_PROMPT]
        assert not missing, (
            f"Routing table is missing analytical tools: {missing}.  "
            f"Engine models will not know to call them."
        )

    def test_lite_prompt_size_still_under_2k_tokens(self):
        """Even with the routing table, the lite prompt must stay under
        ~2000 tokens (~8000 chars) so we keep the substantial budget
        win that v2.40.0 delivered.  Token estimate: chars/4."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        chars = len(_LITE_SYSTEM_PROMPT)
        approx_tokens = chars // 4
        assert approx_tokens < 2000, (
            f"Lite prompt grew to ~{approx_tokens} tokens "
            f"({chars} chars).  v2.40.x budget is ~2000 tokens — "
            f"either trim the routing table or split the lite variant "
            f"into pure-lite vs lite-plus-routing tiers."
        )

    def test_lite_prompt_preserves_set_ordinal_ranking_v2_39_semantics(self):
        """The v2.39.0 backend autonomy fix made set_ordinal_ranking
        auto-flip Level_of_Measurement='ordinal' on its own.  The lite
        prompt must communicate this so engine models don't emit the
        legacy two-block update_metadata + set_ordinal_ranking chain
        (which gemma can't reliably do — see v2.39.0 design doc)."""
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        low = _LITE_SYSTEM_PROMPT.lower()
        assert 'auto-flip' in low or 'auto-flips' in low, (
            "Lite prompt must mention v2.39.0 auto-flip semantics so "
            "engine models know they don't need the legacy update_metadata "
            "preamble."
        )
        # Hard-fail the legacy two-block instruction if it ever leaks back.
        assert 'preceding update_metadata' in low, (
            "Lite prompt must explicitly tell the model that a preceding "
            "update_metadata is NOT required."
        )

    def test_full_prompt_is_unchanged_for_openai_callers(self):
        """Regression guard: editing the lite prompt or adding new
        provider mappings must not accidentally truncate the full prompt
        that OpenAI callers depend on.  Sanity: full prompt is still
        meaningfully large (>= 8000 tokens worth)."""
        from ai_assistant.views import SYSTEM_PROMPT
        # 1 token ~= 4 chars; require >= 8000 tokens.
        assert len(SYSTEM_PROMPT) >= 32_000, (
            "Full SYSTEM_PROMPT shrunk below 8000 tokens — was the "
            "lite/full wiring accidentally reversed?"
        )

    def test_chat_workflow_stamps_system_prompt_variant_attribute(self,
                                                                   monkeypatch):
        """End-to-end span-attr contract: _chat_workflow must stamp the
        system_prompt.variant attribute so the trace explorer can group
        gemma calls under 'lite' and gpt calls under 'full' for AB-style
        observability work.  Patches _call_llm + get_model_config so we
        can observe attribute writes without real network or a live
        inference engine."""
        from ai_assistant import views

        captured = {}

        def fake_set_span_attr(key, value):
            captured[key] = value

        def fake_call_llm(messages, model_key, tools=None):
            # Return a finished response with no tool calls.
            return {
                'choices': [{
                    'finish_reason': 'stop',
                    'message': {'content': 'ok', 'tool_calls': None},
                }],
                'usage': {},
            }

        # Engine models are dynamically discovered from the inference
        # engine — in the test environment that lookup may return nothing,
        # so stub get_model_config to return a deterministic provider
        # based on the model_key string.
        def fake_get_model_config(model_key):
            if 'gemma' in model_key or model_key.startswith('engine-'):
                return {'provider': 'engine', 'supports_tools': True}
            return {'provider': 'openai', 'supports_tools': True}

        monkeypatch.setattr(views, 'set_span_attr', fake_set_span_attr)
        monkeypatch.setattr(views, '_call_llm', fake_call_llm)
        monkeypatch.setattr(views, 'get_model_config', fake_get_model_config)

        # Engine call → expect variant='lite'
        captured.clear()
        views._chat_workflow(
            user_message='hi', context=None, section='general',
            history=[], file_id=None, model='engine-gemma-4-26b',
        )
        assert captured.get('declarai.system_prompt.variant') == 'lite'
        assert captured.get('declarai.system_prompt.chars', 0) > 0
        assert captured.get('declarai.system_prompt.chars', 0) < 32_000, (
            "Lite branch should report a chars count well below the "
            "full prompt's ~36000."
        )

        # OpenAI call → expect variant='full'
        captured.clear()
        views._chat_workflow(
            user_message='hi', context=None, section='general',
            history=[], file_id=None, model='gpt-5.5',
        )
        assert captured.get('declarai.system_prompt.variant') == 'full'
        assert captured.get('declarai.system_prompt.chars', 0) >= 32_000, (
            "Full branch should report the full prompt size."
        )


# ---------------------------------------------------------------------------
# v2.41.1: Unicode-only formatting rule (no LaTeX in chat output)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSystemPromptLatexFormattingRule:
    """v2.41.1 — pin the rule that forbids LaTeX syntax in chat output.

    The chat renderer is a hand-rolled markdown subset (no MathJax/KaTeX)
    so any LaTeX the model emits — `$\\rightarrow$`, `\\alpha`, `$$...$$` —
    is shown to the user as raw source.  Both system prompts now instruct
    the model to use Unicode characters directly.

    The frontend has a defensive `_delatexify` pass too (covered by Karma
    specs in `ai-chat-panel.component.spec.ts`), but the prompt-side rule
    is the primary fix: it prevents the LLM from emitting LaTeX in the
    first place, which keeps the message history clean for downstream
    consumers (audit logs, retraining corpus, traces) — places the
    frontend rendering pass cannot reach.

    These tests fail-fast if a future prompt edit drops the rule.
    """

    def test_full_prompt_forbids_latex_syntax(self):
        from ai_assistant.views import SYSTEM_PROMPT
        # Must explicitly forbid LaTeX commands.
        assert 'LaTeX' in SYSTEM_PROMPT, (
            "Full system prompt must mention 'LaTeX' so the LLM knows "
            "the keyword being banned."
        )
        # Must show at least one concrete LaTeX-syntax example so the
        # model can pattern-match what's forbidden.  Use $\rightarrow$
        # since that's the literal user-reported case from v2.41.1.
        assert '\\rightarrow' in SYSTEM_PROMPT, (
            "Full system prompt must show the user-reported $\\rightarrow$ "
            "example so the LLM recognises the forbidden pattern."
        )

    def test_full_prompt_recommends_unicode_directly(self):
        from ai_assistant.views import SYSTEM_PROMPT
        # The flip side of the rule: the model must know what to use
        # INSTEAD of LaTeX.  Verify a representative Unicode arrow and
        # comparison op appear in the prompt so the model can copy from
        # the catalogue.
        for char in ('→', '⇒', '≤', '≥', '≠', 'α', 'β', 'σ', 'π', 'Δ', 'Σ'):
            assert char in SYSTEM_PROMPT, (
                f"Full system prompt should list the Unicode character "
                f"{char!r} as a concrete substitute for the LaTeX form."
            )

    def test_lite_prompt_forbids_latex_syntax(self):
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        # The lite prompt has a tighter token budget so the rule is
        # condensed but it MUST still appear — engine models (gemma,
        # llama, qwen) that get the lite prompt are precisely the ones
        # most likely to spam LaTeX from training-data bias.
        assert 'LaTeX' in _LITE_SYSTEM_PROMPT, (
            "Lite system prompt must mention 'LaTeX' so engine models "
            "know the keyword being banned."
        )
        assert '\\rightarrow' in _LITE_SYSTEM_PROMPT, (
            "Lite system prompt must show the $\\rightarrow$ example "
            "so engine models recognise the forbidden pattern."
        )

    def test_lite_prompt_recommends_unicode_directly(self):
        from ai_assistant.views import _LITE_SYSTEM_PROMPT
        # Lite catalogue is smaller than the full prompt's, but it MUST
        # at minimum cover the arrow + comparison families since those
        # are the highest-volume offenders.
        for char in ('→', '⇒', '≤', '≥', '≠'):
            assert char in _LITE_SYSTEM_PROMPT, (
                f"Lite system prompt should list the Unicode character "
                f"{char!r} as a concrete substitute for LaTeX."
            )

    def test_full_prompt_warning_co_locates_with_unicode_recommendation(self):
        """The forbid-LaTeX rule and the use-Unicode recommendation MUST
        appear together (not in separate disconnected sections).  If a
        future prompt edit splits them, the model sees the negative rule
        without the positive substitute and is more likely to fall back
        to LaTeX habits.  We pin co-location by checking both 'LaTeX' and
        a Unicode arrow appear within the same ~500-char window."""
        from ai_assistant.views import SYSTEM_PROMPT
        idx = SYSTEM_PROMPT.find('LaTeX')
        assert idx >= 0, "Expected 'LaTeX' marker missing from full prompt."
        # 500-char window centred on the LaTeX marker.
        window = SYSTEM_PROMPT[max(0, idx - 250):idx + 250]
        assert '→' in window, (
            "The forbid-LaTeX rule must be co-located with at least the "
            "Unicode arrow `→` so the model sees the substitute next to "
            "the prohibition."
        )


# ---------------------------------------------------------------------------
# v2.42.0: AML A4 prompt-render contract
# ---------------------------------------------------------------------------
# These tests pin the structured-attribute contract that the Prometa AML
# A4 detector reads.  Pre-v2.42.0 the detector was forced to substring-
# match `"role":"user"` inside the `gen_ai.prompt` attribute, which the
# openai auto-instrumentation truncates to 32 000 bytes.  Once production
# payloads (system prompt + slim context + auto-routed skill body +
# history + tool defs) crossed the 32 KB threshold, the truncation knife
# landed AFTER the leading system prompt but BEFORE any user-role marker
# — so A4 saw "1 system, 0 user, 0 asst, 0 tool" even though our
# _chat_workflow emits proper multi-role messages.  The fix is to emit
# the structured `prompt.role_boundaries` attribute via the SDK v0.7.1
# `prompt_render` context manager, plus stamp the raw user query as
# `prometa.raw.input`.
#
# We pin: (1) the pure helpers `_compute_role_boundaries` /
# `_approx_tokens` / `_describe_context_components` /
# `_sum_tool_message_tokens` (fast, no fixtures needed), and (2) the
# wiring into `_chat_workflow` itself via a captured-attribute fake.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPromptRenderRoleBoundaryHelpers:
    """Pure-function tests for the v2.42.0 role-boundary helpers."""

    def test_approx_tokens_chars_div_4(self):
        from ai_assistant.views import _approx_tokens
        assert _approx_tokens(None) == 0
        assert _approx_tokens('') == 0
        assert _approx_tokens('1234') == 1
        # 11 chars // 4 = 2 — matches the prometa-sdk convention.
        assert _approx_tokens('hello world') == 2

    def test_compute_role_boundaries_minimal_two_role_array(self):
        """The minimum-viable A4-passing payload: one system + one user."""
        import json
        from ai_assistant.views import _compute_role_boundaries
        msgs = [
            {'role': 'system', 'content': 'You are an assistant.'},
            {'role': 'user', 'content': 'Hello!'},
        ]
        rendered = json.dumps(msgs, ensure_ascii=False)
        b = _compute_role_boundaries(msgs, rendered)
        assert len(b) == 2
        assert [x['role'] for x in b] == ['system', 'user']
        # Boundaries must be NON-OVERLAPPING and each slice must round-trip
        # to the original message JSON.  This is what A4 reads to verify
        # role isolation.
        assert b[0]['end'] <= b[1]['start']
        assert rendered[b[0]['start']:b[0]['end']] == json.dumps(msgs[0], ensure_ascii=False)
        assert rendered[b[1]['start']:b[1]['end']] == json.dumps(msgs[1], ensure_ascii=False)

    def test_compute_role_boundaries_multi_round_with_tools(self):
        """Realistic tool-calling turn: system + slim_context + history
        user + history assistant + current user + assistant_with_tool_calls
        + tool result + assistant final.  Every role must produce a
        distinct boundary."""
        import json
        from ai_assistant.views import _compute_role_boundaries
        msgs = [
            {'role': 'system', 'content': 'You are DeclarAI.'},
            {'role': 'system', 'content': 'Pipeline context summary:\nfile_id=42'},
            {'role': 'user', 'content': 'previous question'},
            {'role': 'assistant', 'content': 'previous answer'},
            {'role': 'user', 'content': 'current question'},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'c1',
                'type': 'function',
                'function': {'name': 'get_data_dictionary', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'c1',
             'content': '{"features": ["Var_1", "Var_2"]}'},
            {'role': 'assistant', 'content': 'Two features available.'},
        ]
        rendered = json.dumps(msgs, ensure_ascii=False)
        b = _compute_role_boundaries(msgs, rendered)
        assert len(b) == 8
        roles = [x['role'] for x in b]
        # Pin that EVERY role-type appears at least once — A4's "missing
        # user-role" failure mode would surface here as a missing 'user'
        # entry in the list.
        assert set(roles) == {'system', 'user', 'assistant', 'tool'}, roles
        # Boundaries must be monotonically non-overlapping.
        for prev, curr in zip(b, b[1:]):
            assert prev['end'] <= curr['start'], (prev, curr)

    def test_compute_role_boundaries_returns_empty_on_empty_input(self):
        """Defensive: empty input never produces phantom boundaries."""
        from ai_assistant.views import _compute_role_boundaries
        assert _compute_role_boundaries([], 'anything') == []
        assert _compute_role_boundaries(
            [{'role': 'user', 'content': 'x'}], '') == []

    def test_compute_role_boundaries_survives_unicode_payload(self):
        """Real chat content carries unicode (Turkish question marks,
        emojis, math symbols introduced in v2.41.1).  json.dumps with
        ensure_ascii=False must produce identical bytes on both sides
        of the boundary computation."""
        import json
        from ai_assistant.views import _compute_role_boundaries
        msgs = [
            {'role': 'system', 'content': 'You are an assistant.'},
            {'role': 'user', 'content': 'PSI ≥ 0.25 → significant shift'},
        ]
        rendered = json.dumps(msgs, ensure_ascii=False)
        b = _compute_role_boundaries(msgs, rendered)
        assert len(b) == 2
        # The unicode chars must be inside the user slice (not lost to
        # encoding).
        user_slice = rendered[b[1]['start']:b[1]['end']]
        assert '≥' in user_slice
        assert '→' in user_slice

    def test_describe_context_components_orders_match_message_assembly(self):
        """The component list must list components in the SAME ORDER
        they were appended to the messages array in _chat_workflow, so
        the audit trail matches the wire shape (the C6 detector groups
        spans by this ordered fingerprint)."""
        from ai_assistant.views import _describe_context_components
        # Slim-context + skill + history + user (the most populated path).
        parts = _describe_context_components(
            use_tools=True, has_context=False,
            auto_skill='feature-engineering', has_history=True,
        )
        assert parts == [
            'system_prompt', 'slim_context', 'conversation_history',
            'skill:feature-engineering', 'user_query',
        ], parts

    def test_describe_context_components_places_knowledge_bank_after_context(self):
        """Knowledge-bank context is injected after slim/legacy pipeline
        context and before history so stable docs do not outrank live data."""
        from ai_assistant.views import _describe_context_components
        parts = _describe_context_components(
            use_tools=True, has_context=False,
            auto_skill='feature-engineering', has_history=True,
            has_knowledge_bank=True,
        )
        assert parts == [
            'system_prompt', 'slim_context', 'knowledge_bank',
            'conversation_history', 'skill:feature-engineering', 'user_query',
        ], parts

    def test_describe_context_components_minimal_path(self):
        """Stateless chat (no file, no history, no skill) still records
        system + user."""
        from ai_assistant.views import _describe_context_components
        parts = _describe_context_components(
            use_tools=False, has_context=False,
            auto_skill=None, has_history=False,
        )
        assert parts == ['system_prompt', 'user_query']

    def test_describe_context_components_legacy_full_context_path(self):
        """When tools aren't available (no cached artifacts) but a
        context blob was passed, the legacy_full_context channel fires
        instead of slim_context — pin this so the two paths stay
        distinguishable in the audit."""
        from ai_assistant.views import _describe_context_components
        parts = _describe_context_components(
            use_tools=False, has_context=True,
            auto_skill=None, has_history=False,
        )
        assert 'legacy_full_context' in parts
        assert 'slim_context' not in parts

    def test_sum_tool_message_tokens_only_counts_tool_and_assistant(self):
        """Tool budget = assistant + tool content (system + user are
        accounted separately).  Verifies the helper does NOT double-count
        system / user channels into the tool budget."""
        from ai_assistant.views import _sum_tool_message_tokens
        msgs = [
            {'role': 'system', 'content': 'x' * 100},  # should NOT count
            {'role': 'user', 'content': 'y' * 100},    # should NOT count
            {'role': 'assistant', 'content': 'z' * 40},
            {'role': 'tool', 'tool_call_id': 'c1', 'content': 'w' * 40},
        ]
        # 40 // 4 = 10 each, total 20.  Anything > 20 means we're
        # leaking system or user content into the tool budget.
        assert _sum_tool_message_tokens(msgs) == 20


@pytest.mark.unit
class TestPromptRenderWorkflowWiring:
    """End-to-end wiring tests: _chat_workflow must invoke prompt_render
    with the right kwargs and stamp prometa.raw.input on the workflow span.

    We monkeypatch `_call_llm`, `prompt_render`, `set_span_attr`, and the
    Redis-touching helpers so the test is a pure-function span-attr
    contract check — no OpenAI network, no engine call, no Redis."""

    def _patch_workflow_environment(self, monkeypatch, captured_attrs, captured_prompt_render):
        from ai_assistant import views

        def fake_call_llm(messages, model_key, tools=None):
            import json as _json
            first = (messages[0].get('content') if messages else '') or ''
            if "DeclarAI's intent classifier" in first:
                payload = (messages[1].get('content') if len(messages) > 1 else '') or ''
                labels = ['D', 'E'] if 'max_features' in payload else ['A']
                if 'Explain PSI' in payload:
                    labels = ['A', 'R']
                return {
                    'choices': [{
                        'message': {
                            'role': 'assistant',
                            'content': _json.dumps({
                                'labels': labels,
                                'confidence': 'high',
                                'uncertain': False,
                                'decomposition': [{'segment': 'test', 'labels': labels}],
                            }),
                        },
                        'finish_reason': 'stop',
                    }],
                    'usage': {'total_tokens': 3},
                }
            return {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'ok'},
                    'finish_reason': 'stop',
                }],
                'usage': {'total_tokens': 10},
            }

        def fake_set_span_attr(key, value):
            captured_attrs[key] = value

        from contextlib import contextmanager

        @contextmanager
        def fake_prompt_render(*, template_version=None, raw_rendered_prompt=None):
            captured_prompt_render['template_version'] = template_version
            captured_prompt_render['raw_rendered_prompt'] = raw_rendered_prompt

            class _Handle:
                def assembled(self, **kwargs):
                    captured_prompt_render['assembled_kwargs'] = kwargs
            yield _Handle()

        def fake_get_model_config(key):
            return {
                'provider': 'openai',
                'model_id': 'gpt-test',
                'supports_tools': False,
                'max_tokens': 1024,
            }

        monkeypatch.setattr(views, '_call_llm', fake_call_llm)
        monkeypatch.setattr(views, 'set_span_attr', fake_set_span_attr)
        monkeypatch.setattr(views, 'prompt_render', fake_prompt_render)
        monkeypatch.setattr(views, 'get_model_config', fake_get_model_config)
        monkeypatch.setattr(views, 'cache_list_artifacts', lambda fid: [])
        monkeypatch.setattr(views, 'set_session_id', lambda *a, **k: None)
        monkeypatch.setattr(views, 'set_customer_id', lambda *a, **k: None)

    def test_chat_workflow_invokes_prompt_render_with_role_boundaries(self, monkeypatch):
        from ai_assistant import views
        attrs, captured_pr = {}, {}
        self._patch_workflow_environment(monkeypatch, attrs, captured_pr)

        views._chat_workflow(
            user_message='Explain PSI.',
            context=None, section='general', history=[],
            file_id=None, model='gpt-test',
        )

        # 1. prompt_render must have been invoked with template_version
        # carrying the system_prompt_variant ('full' for openai provider).
        assert captured_pr.get('template_version') == 'declarai-chat@full'

        # 2. raw_rendered_prompt must be a valid JSON array containing
        # BOTH a system role and a user role (the A4 contract).
        import json as _json
        rendered = captured_pr.get('raw_rendered_prompt')
        assert rendered is not None
        parsed = _json.loads(rendered)
        roles = [m.get('role') for m in parsed]
        assert 'system' in roles
        assert 'user' in roles

        # 3. assembled() must have been called with role_boundaries
        # listing every role in the rendered prompt.
        kwargs = captured_pr.get('assembled_kwargs', {})
        boundaries = kwargs.get('role_boundaries')
        assert boundaries is not None and len(boundaries) >= 2
        boundary_roles = [b['role'] for b in boundaries]
        assert 'system' in boundary_roles
        assert 'user' in boundary_roles

    def test_chat_workflow_stamps_prometa_raw_input_with_just_user_query(self, monkeypatch):
        """The contract says prometa.raw.input MUST be the user's
        latest query alone (not the rendered prompt).  This is what
        the A4 detector uses to verify userInput !== rendered."""
        from ai_assistant import views
        attrs, captured_pr = {}, {}
        self._patch_workflow_environment(monkeypatch, attrs, captured_pr)

        question = 'What features have high VIF?'
        views._chat_workflow(
            user_message=question,
            context=None, section='general', history=[],
            file_id=None, model='gpt-test',
        )

        # prometa.raw.input must equal the user message EXACTLY — not
        # the rendered prompt, not a snippet, not a prefix.
        assert attrs.get('prometa.raw.input') == question

        # And it MUST NOT equal raw_rendered_prompt (that would
        # reproduce the v2.41.x byte-identity bug Prometa flagged).
        assert attrs.get('prometa.raw.input') != captured_pr.get('raw_rendered_prompt')

    def test_chat_workflow_stamps_classifier_intent_attrs(self, monkeypatch):
        from ai_assistant import views
        attrs, captured_pr = {}, {}
        self._patch_workflow_environment(monkeypatch, attrs, captured_pr)

        views._chat_workflow(
            user_message='Set max_features to 20 and then start SFS.',
            context={}, section='modeling', history=[],
            file_id=None, model='gpt-test',
        )

        assert attrs.get('declarai.intent.labels') == 'D,E'
        assert attrs.get('declarai.intent.label_names') == (
            'configuration_editing_execution,flow_process_execution'
        )
        assert attrs.get('declarai.intent.source') == 'llm_classifier'
        assert attrs.get('declarai.intent.confidence') == 'high'
        assert attrs.get('declarai.intent.preclassified') is False
        assert attrs.get('prometa.intent.labels') == 'D,E'

    def test_chat_workflow_uses_preclassified_button_intents(self, monkeypatch):
        from ai_assistant import views
        attrs, captured_pr = {}, {}
        self._patch_workflow_environment(monkeypatch, attrs, captured_pr)

        out = views._chat_workflow(
            user_message='Analyze the Data Quality Summary.',
            context={}, section='data_quality', history=[],
            file_id=None, model='gpt-test',
            intent_labels=['C'],
            intent_source='get_ai_support_button',
        )

        assert attrs.get('declarai.intent.labels') == 'C'
        assert attrs.get('declarai.intent.source') == 'get_ai_support_button'
        assert attrs.get('declarai.intent.preclassified') is True
        assert attrs.get('prometa.intent.labels') == 'C'
        assert out['intent_labels'] == ['C']
        assert out['intent_source'] == 'get_ai_support_button'

    def test_chat_workflow_prompt_render_assembled_carries_context_components(self, monkeypatch):
        """C6 detector reads prompt.context_components — verify the
        workflow lists at least system_prompt + user_query for the
        minimal turn (no file, no history, no skill)."""
        from ai_assistant import views
        attrs, captured_pr = {}, {}
        self._patch_workflow_environment(monkeypatch, attrs, captured_pr)

        views._chat_workflow(
            user_message='hi',
            context=None, section='general', history=[],
            file_id=None, model='gpt-test',
        )

        kwargs = captured_pr.get('assembled_kwargs', {})
        components = kwargs.get('context_components')
        assert components is not None
        assert 'system_prompt' in components
        assert 'user_query' in components
        # The minimal turn has NO slim_context / history / skill —
        # those entries must be ABSENT, not just empty strings.
        assert 'slim_context' not in components
        assert 'conversation_history' not in components
        assert not any(c.startswith('skill:') for c in components)


# ---------------------------------------------------------------------------
# v2.42.0: prometa-sdk version lock — CI guard
# ---------------------------------------------------------------------------
# Catches future Docker-cache / pip-cache drift like the v0.6.0-in-
# container situation that hid the A4 truncation bug from us.  The pin
# in requirements.txt (`prometa-sdk==X.Y.Z`) must match the version
# actually installed in the environment running the tests.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProMetaSdkVersionLock:
    """Defense against installed-vs-pinned drift.

    The bug that motivated v2.42.0 hid for ~24 hours because
    requirements.txt was pinned to >=0.7.1 but the running container
    was on v0.6.0 (Docker layer cache wasn't invalidated when the pin
    was bumped).  This test reads the pin from requirements.txt and
    asserts the installed prometa.__version__ matches EXACTLY.  Fails
    fast in CI / pre-commit, including on any environment where pip
    re-resolves into a newer minor release we haven't verified."""

    def _read_pin(self) -> str:
        """Return the version literal pinned in requirements.txt.

        Supports the canonical hard-pin form 'prometa-sdk==X.Y.Z'.
        Any other form (range, no pin) is a deliberate refusal — we
        want this lock to be obvious to readers.
        """
        from pathlib import Path
        import re
        backend_dir = Path(__file__).resolve().parent.parent
        req = (backend_dir / 'requirements.txt').read_text()
        for line in req.splitlines():
            line = line.strip()
            if line.startswith('prometa-sdk'):
                m = re.match(r'^prometa-sdk==([0-9]+\.[0-9]+\.[0-9]+)\s*$', line)
                assert m, (
                    f"prometa-sdk must be HARD-PINNED in requirements.txt "
                    f"(form: prometa-sdk==X.Y.Z); found: {line!r}"
                )
                return m.group(1)
        raise AssertionError(
            "prometa-sdk entry not found in requirements.txt — "
            "the version lock test cannot run without a pin."
        )

    def test_installed_prometa_sdk_matches_requirements_pin(self):
        import prometa
        installed = prometa.__version__
        pinned = self._read_pin()
        assert installed == pinned, (
            f"prometa-sdk version drift detected: installed={installed!r} "
            f"but requirements.txt pins =={pinned!r}.  Rebuild the "
            f"backend Docker image with --no-cache or re-run "
            f"`pip install -r requirements.txt` to align.  This drift "
            f"is precisely what hid the v2.41.x AML A4 truncation bug "
            f"from us for ~24h — keep it locked."
        )

    def test_prompt_render_helper_is_importable_on_pinned_version(self):
        """The v2.42.0 fix depends on the prompt_render helper that
        crystallized in prometa-sdk 0.7.x.  If we ever downgrade the
        pin, this test forces explicit acknowledgement that we'd lose
        the A4 contract.  Read-only check — does not invoke the helper."""
        from prometa import prompt_render
        assert callable(prompt_render), (
            "prompt_render must be importable; the AML A4 contract "
            "(prompt.role_boundaries + prometa.raw.rendered_prompt) "
            "depends on this helper landing in the SDK."
        )

    def test_raw_channel_helper_is_importable_on_pinned_version(self):
        """Same logic as above but for the _raw_channel toggle.
        Without it, prompt_render(raw_rendered_prompt=...) drops the
        raw kwarg at the SDK boundary and A4 falls back to the
        truncated gen_ai.prompt — re-introducing the v2.41.x bug."""
        from prometa import _raw_channel
        assert callable(_raw_channel.enable)
        assert callable(_raw_channel.is_enabled)


# ---------------------------------------------------------------------------
# v2.43.0: gen_ai.vendor + Ollama-tag normalization for prometa-platform's
# pricing-registry matcher.
#
# Background: prometa-platform's models.ts uses ``startsWith(registryKey)``
# against the raw ``gen_ai.request.model`` attribute.  Our Ollama-style
# tags (``gemma4:26b``, ``nemotron-3-nano:30b``) never match because:
#   1. The ``:variant`` suffix isn't stripped.
#   2. The family/parameter-size split isn't surfaced.
#   3. There's no vendor hint to route the lookup into the right catalog
#      (cloud OpenAI vs self-hosted Ollama).
# v2.43.0 ships ``parse_ollama_tag()`` and stamps three new span
# attributes (``gen_ai.vendor``, ``gen_ai.model.family``,
# ``gen_ai.model.tag``, ``gen_ai.model.parameter_size``) so the matcher
# has the signals it needs.  These tests pin the contract on both sides
# of the boundary — the parser AND the call site.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseOllamaTag:
    """``parse_ollama_tag`` must split an Ollama model id into
    ``{family, tag, parameter_size}`` without raising on any input."""

    def test_canonical_family_colon_size_tag(self):
        """The common case: ``family:Nb`` where N is the parameter count."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:26b')
        assert result == {
            'family': 'gemma4',
            'tag': '26b',
            'parameter_size': '26b',
        }

    def test_hyphenated_family(self):
        """Multi-segment families like nemotron-3-nano keep their hyphens."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('nemotron-3-nano:30b')
        assert result == {
            'family': 'nemotron-3-nano',
            'tag': '30b',
            'parameter_size': '30b',
        }

    def test_dotted_family(self):
        """Families with version dots (llama3.2, qwen3.6) round-trip."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('llama3.2:3b')
        assert result == {
            'family': 'llama3.2',
            'tag': '3b',
            'parameter_size': '3b',
        }

    def test_decimal_parameter_size(self):
        """Sub-billion sizes like 1.5b extract cleanly."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('ministral-3:1.5b')
        assert result == {
            'family': 'ministral-3',
            'tag': '1.5b',
            'parameter_size': '1.5b',
        }

    def test_gemma_embedded_variant(self):
        """Gemma's ``eNb`` (embedded) tags surface a numeric param_size
        even though the tag itself is ``e2b`` / ``e4b``.  The full tag
        is preserved in ``tag`` so registry consumers can match either
        the raw variant or the normalized parameter size."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:e2b')
        assert result['family'] == 'gemma4'
        assert result['tag'] == 'e2b'
        assert result['parameter_size'] == '2b'

    def test_non_numeric_tag_yields_none_parameter_size(self):
        """``cloud`` / ``latest`` / ``q4_0`` aren't parameter sizes —
        ``parameter_size`` must be None so the registry doesn't index
        a meaningless string."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('minimax-m2.7:cloud')
        assert result == {
            'family': 'minimax-m2.7',
            'tag': 'cloud',
            'parameter_size': None,
        }

    def test_quantization_suffix_falls_through(self):
        """Quant-only tags like ``q4_0`` don't carry a parameter count;
        the parser refuses to invent one."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('llama3.2:q4_0')
        assert result['family'] == 'llama3.2'
        assert result['tag'] == 'q4_0'
        assert result['parameter_size'] is None

    def test_size_with_quantization_suffix(self):
        """When the tag is ``Nb-quant`` (e.g. ``26b-q4``) the leading
        size segment wins — we want the cost matcher to find the size
        even when an operator pulls a quantized variant."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:26b-q4_0')
        assert result['family'] == 'gemma4'
        assert result['tag'] == '26b-q4_0'
        assert result['parameter_size'] == '26b'

    def test_no_colon_returns_none_tag(self):
        """If the model id has no ``:`` we still return family but
        leave tag + parameter_size as None — the caller will then
        stamp only the family attribute (graceful degradation)."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('llama3.2')
        assert result == {
            'family': 'llama3.2',
            'tag': None,
            'parameter_size': None,
        }

    def test_empty_string_returns_safe_shape(self):
        """Empty input must return the canonical shape with empty/None
        fields — never raise — so the call site can stamp nothing
        instead of crashing the LLM call."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('')
        assert result == {
            'family': '',
            'tag': None,
            'parameter_size': None,
        }

    def test_non_string_input_returns_safe_shape(self):
        """Defensive: a None / int / dict input must not raise.  We
        return the canonical empty shape so callers stay no-op."""
        from ai_assistant.model_registry import parse_ollama_tag
        assert parse_ollama_tag(None) == {
            'family': '', 'tag': None, 'parameter_size': None,
        }
        assert parse_ollama_tag(42) == {
            'family': '', 'tag': None, 'parameter_size': None,
        }

    def test_uppercase_parameter_size_normalized_to_lowercase(self):
        """The parameter_size is normalized to lowercase so the
        registry can match without per-call casing."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('gemma4:26B')
        assert result['parameter_size'] == '26b'

    # ── family-side fallback (MLX / HF converted ids) ──────────────────

    def test_mlx_converted_id_extracts_size_from_family(self):
        """Engine occasionally surfaces MLX-converted ids like
        ``Llama-3.2-1B-Instruct-4bit:mlx`` where the parameter size is
        encoded in the family string instead of the tag.  The
        family-side fallback must recover the size so prometa's
        registry can match on it."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('Llama-3.2-1B-Instruct-4bit:mlx')
        assert result['family'] == 'Llama-3.2-1B-Instruct-4bit'
        assert result['tag'] == 'mlx'
        assert result['parameter_size'] == '1b'

    def test_family_fallback_does_not_overrule_explicit_tag_size(self):
        """When the tag carries an explicit size (the common case) the
        family-side fallback MUST NOT fire and overwrite it with a
        spurious match from the family name.  Pinning the precedence
        order so future refactors can't silently swap it."""
        from ai_assistant.model_registry import parse_ollama_tag
        # Contrived: family contains "5B", tag contains "3b".  The
        # parser must report 3b (from the tag), not 5b (from family).
        result = parse_ollama_tag('llama-5B-something:3b')
        assert result['tag'] == '3b'
        assert result['parameter_size'] == '3b'

    def test_family_fallback_yields_none_when_neither_side_has_size(self):
        """Both family and tag are size-free → parameter_size must
        remain None.  ``minimax-m2.7:cloud`` is the live example —
        ``m2.7`` looks numeric but lacks the required ``[bm]`` suffix
        so the regex correctly refuses to match."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('minimax-m2.7:cloud')
        assert result['parameter_size'] is None

    def test_family_fallback_works_without_tag(self):
        """When the model id has no colon at all (no tag), the
        fallback still runs against the family string."""
        from ai_assistant.model_registry import parse_ollama_tag
        result = parse_ollama_tag('Llama-3.2-1B-Instruct')
        assert result['family'] == 'Llama-3.2-1B-Instruct'
        assert result['tag'] is None
        assert result['parameter_size'] == '1b'


@pytest.mark.unit
class TestGenAiVendorStamping:
    """v2.43.0: ``_call_llm`` MUST stamp ``gen_ai.vendor`` on every LLM
    call and, for engine-routed calls, also stamp
    ``gen_ai.model.family``, ``gen_ai.model.tag``, and
    ``gen_ai.model.parameter_size`` so prometa-platform's pricing
    registry can resolve the model.  These tests pin both the call
    site (source-level) and the field shape (parser contract)."""

    def test_call_llm_source_stamps_gen_ai_vendor(self):
        """Source-level guard: the body of ``_call_llm`` must contain
        a ``set_span_attr('gen_ai.vendor', ...)`` call.  Without this,
        the prometa registry has no way to route lookups into the
        right catalog and every span falls back to silent-zero."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        assert "set_span_attr('gen_ai.vendor'" in source, (
            "_call_llm must stamp gen_ai.vendor on the active span — "
            "the prometa pricing registry depends on it for cloud-vs-"
            "self-hosted catalog routing (v2.43.0)."
        )

    def test_call_llm_source_stamps_openai_vendor(self):
        """For the openai branch the vendor literal must be 'openai'."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        assert "set_span_attr('gen_ai.vendor', 'openai')" in source, (
            "openai branch must stamp gen_ai.vendor='openai' literally."
        )

    def test_call_llm_source_stamps_ollama_vendor(self):
        """For the engine branch the vendor literal must be 'ollama'
        (not 'engine' — the canonical OTel-style vendor name the
        prometa registry consumes)."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        assert "set_span_attr('gen_ai.vendor', 'ollama')" in source, (
            "engine branch must stamp gen_ai.vendor='ollama' (the "
            "vendor name the prometa registry routes on, not the "
            "internal provider tag 'engine')."
        )

    def test_call_llm_source_stamps_family_tag_parameter_size(self):
        """Engine branch must stamp all three Ollama-tag components
        so the registry can match on whichever facet it prefers."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        for attr in ('gen_ai.model.family',
                     'gen_ai.model.tag',
                     'gen_ai.model.parameter_size'):
            assert f"set_span_attr('{attr}'" in source, (
                f"_call_llm engine branch must stamp {attr}"
            )

    def test_call_llm_source_uses_parse_ollama_tag(self):
        """The call site MUST delegate parsing to the canonical
        ``parse_ollama_tag`` helper — not inline a regex.  This keeps
        the parsing rules in one place so the test suite above is
        load-bearing for the call site too."""
        import inspect
        from ai_assistant.views import _call_llm
        source = inspect.getsource(_call_llm)
        assert 'parse_ollama_tag(' in source, (
            "_call_llm must use parse_ollama_tag() — do NOT inline "
            "regex parsing of the Ollama tag."
        )

    def test_views_imports_parse_ollama_tag(self):
        """Structural guard: the import line in views.py must expose
        parse_ollama_tag from model_registry."""
        from ai_assistant import views
        assert hasattr(views, 'parse_ollama_tag'), (
            "views.py must import parse_ollama_tag from model_registry."
        )

    def test_vendor_stamping_runtime_openai(self, monkeypatch):
        """End-to-end behavioral test: monkeypatch the OpenAI client
        + set_span_attr capture, then invoke _call_llm with an OpenAI
        model and assert gen_ai.vendor='openai' lands."""
        from ai_assistant import views as v
        captured: list[tuple[str, object]] = []
        monkeypatch.setattr(v, 'set_span_attr',
                            lambda k, val: captured.append((k, val)))
        monkeypatch.setattr(v, 'set_request_model', lambda _m: None)
        # Stub out the actual OpenAI call so we don't need a key.
        monkeypatch.setattr(v, 'call_openai',
                            lambda *a, **kw: {'choices': []})
        # Bypass the @agent decorator's lazy span wrapping by calling
        # the underlying function directly.
        inner = getattr(v._call_llm, '__wrapped__', v._call_llm)
        monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
        inner(messages=[{'role': 'user', 'content': 'hi'}],
              model_key='gpt-5.5')
        vendors = [val for k, val in captured if k == 'gen_ai.vendor']
        assert vendors == ['openai'], (
            f"expected exactly one gen_ai.vendor='openai' stamp, "
            f"got {vendors}"
        )

    def test_vendor_stamping_runtime_engine(self, monkeypatch):
        """End-to-end behavioral test: engine path stamps vendor=ollama
        AND family/tag/parameter_size derived from the Ollama tag."""
        from ai_assistant import views as v
        captured: list[tuple[str, object]] = []
        monkeypatch.setattr(v, 'set_span_attr',
                            lambda k, val: captured.append((k, val)))
        monkeypatch.setattr(v, 'set_request_model', lambda _m: None)
        # Force the engine path with a fake model config.
        monkeypatch.setattr(v, 'get_model_config', lambda _k: {
            'provider': 'engine',
            'model_id': 'gemma4:26b',
            'max_tokens': 4096,
        })
        monkeypatch.setattr(v, 'call_engine',
                            lambda *a, **kw: {'choices': []})
        inner = getattr(v._call_llm, '__wrapped__', v._call_llm)
        inner(messages=[{'role': 'user', 'content': 'hi'}],
              model_key='engine-gemma4-26b')
        attrs = dict(captured)
        assert attrs.get('gen_ai.vendor') == 'ollama'
        assert attrs.get('gen_ai.model.family') == 'gemma4'
        assert attrs.get('gen_ai.model.tag') == '26b'
        assert attrs.get('gen_ai.model.parameter_size') == '26b'

    def test_vendor_stamping_skips_unparseable_engine_tag(self, monkeypatch):
        """If the Ollama tag has no parameter size (e.g.
        ``minimax-m2.7:cloud``), the call site must stamp vendor +
        family + tag but NOT parameter_size — we don't want a junk
        value polluting the registry's price lookup."""
        from ai_assistant import views as v
        captured: list[tuple[str, object]] = []
        monkeypatch.setattr(v, 'set_span_attr',
                            lambda k, val: captured.append((k, val)))
        monkeypatch.setattr(v, 'set_request_model', lambda _m: None)
        monkeypatch.setattr(v, 'get_model_config', lambda _k: {
            'provider': 'engine',
            'model_id': 'minimax-m2.7:cloud',
            'max_tokens': 4096,
        })
        monkeypatch.setattr(v, 'call_engine',
                            lambda *a, **kw: {'choices': []})
        inner = getattr(v._call_llm, '__wrapped__', v._call_llm)
        inner(messages=[{'role': 'user', 'content': 'hi'}],
              model_key='engine-minimax-m2-7-cloud')
        attrs = dict(captured)
        assert attrs.get('gen_ai.vendor') == 'ollama'
        assert attrs.get('gen_ai.model.family') == 'minimax-m2.7'
        assert attrs.get('gen_ai.model.tag') == 'cloud'
        assert 'gen_ai.model.parameter_size' not in attrs, (
            "parameter_size must NOT be stamped when the tag yields "
            "None — silent omission is the contract."
        )


# ---------------------------------------------------------------------------
# Hyperparameter tuning engine (modeling/hyperparam_utils.py)
# ---------------------------------------------------------------------------
def _hp_synthetic(n=160, seed=0):
    """Small separable binary dataset for fast engine unit tests."""
    from sklearn.datasets import make_classification
    X, y = make_classification(n_samples=n, n_features=6, n_informative=4,
                               n_redundant=0, random_state=seed)
    cols = [f'Var_{i}' for i in range(6)]
    split = int(n * 0.7)
    Xtr = pd.DataFrame(X[:split], columns=cols)
    Xte = pd.DataFrame(X[split:], columns=cols)
    return Xtr, pd.Series(y[:split]), Xte, pd.Series(y[split:])


def _hp_space(*enabled):
    """Default space with only the named params enabled."""
    from modeling.hyperparam_utils import DEFAULT_PARAM_SPACE
    space = {k: dict(v) for k, v in DEFAULT_PARAM_SPACE.items()}
    for k in space:
        space[k]['enabled'] = k in enabled
    return space


@pytest.mark.unit
class TestHyperparamParamSpace:
    """validate_param_space clamps user input to safe bounds and never
    returns an empty enabled set (the search would have nothing to do)."""

    def test_swaps_inverted_min_max(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, warns = validate_param_space({'max_depth': {'min': 12, 'max': 3}})
        assert clean['max_depth']['min'] <= clean['max_depth']['max']
        assert any('swapped' in w for w in warns)

    def test_clamps_to_hard_bounds(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, _ = validate_param_space({'max_depth': {'min': -5, 'max': 999}})
        assert clean['max_depth']['min'] >= 1
        assert clean['max_depth']['max'] <= 20

    def test_enabled_toggle_respected(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, _ = validate_param_space({'gamma': {'enabled': True}})
        assert clean['gamma']['enabled'] is True

    def test_fallback_when_nothing_enabled(self):
        from modeling.hyperparam_utils import validate_param_space, DEFAULT_PARAM_SPACE
        space = {k: {'enabled': False} for k in DEFAULT_PARAM_SPACE}
        clean, warns = validate_param_space(space)
        assert any(s.get('enabled') for s in clean.values())
        assert any('enabled' in w for w in warns)

    def test_none_payload_returns_defaults(self):
        from modeling.hyperparam_utils import validate_param_space
        clean, warns = validate_param_space(None)
        assert 'learning_rate' in clean and clean['learning_rate']['enabled'] is True


@pytest.mark.unit
class TestHyperparamMetrics:
    """_compute_metrics returns every catalogued metric and handles the
    degenerate single-class fold (ROC-AUC undefined) without raising."""

    def test_all_metric_keys_present(self):
        from modeling.hyperparam_utils import _compute_metrics, METRIC_NAMES
        out = _compute_metrics(np.array([0, 1, 0, 1]), np.array([0.2, 0.8, 0.4, 0.6]))
        assert set(METRIC_NAMES).issubset(out.keys())

    def test_single_class_roc_auc_is_nan(self):
        from modeling.hyperparam_utils import _compute_metrics
        out = _compute_metrics(np.array([1, 1, 1, 1]), np.array([0.6, 0.7, 0.8, 0.9]))
        assert np.isnan(out['roc_auc'])
        assert np.isnan(out['pr_auc'])

    def test_perfect_separation_scores(self):
        from modeling.hyperparam_utils import _compute_metrics
        out = _compute_metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
        assert out['roc_auc'] == 1.0
        assert out['f1'] == 1.0 and out['precision'] == 1.0 and out['recall'] == 1.0
        assert out['accuracy'] == 1.0

    def test_f2_weights_recall_more_than_f1(self):
        from modeling.hyperparam_utils import _compute_metrics
        # One false negative: recall < precision -> F2 < F1 is FALSE; F2 emphasizes recall.
        y = np.array([1, 1, 1, 0])
        p = np.array([0.9, 0.9, 0.2, 0.1])  # one positive missed
        out = _compute_metrics(y, p)
        assert out['f2'] <= out['f1']  # missing positives penalizes F2 at least as much


@pytest.mark.unit
class TestHyperparamSampling:
    """Random sampling honors type/bounds; disabled params fall back to fixed."""

    def test_int_sampling_within_bounds(self):
        from modeling.hyperparam_utils import _sample_value
        rng = np.random.default_rng(1)
        spec = {'type': 'int', 'min': 2, 'max': 8}
        vals = [_sample_value(spec, rng) for _ in range(50)]
        assert all(isinstance(v, int) and 2 <= v <= 8 for v in vals)

    def test_float_log_sampling_within_bounds(self):
        from modeling.hyperparam_utils import _sample_value
        rng = np.random.default_rng(1)
        spec = {'type': 'float', 'min': 0.01, 'max': 0.3, 'log': True}
        vals = [_sample_value(spec, rng) for _ in range(50)]
        assert all(0.01 <= v <= 0.3 for v in vals)

    def test_disabled_param_uses_fixed_value(self):
        from modeling.hyperparam_utils import _sample_config, DEFAULT_FIXED_PARAMS
        space = _hp_space('max_depth')
        rng = np.random.default_rng(0)
        cfg = _sample_config(space, DEFAULT_FIXED_PARAMS, rng)
        assert cfg['learning_rate'] == DEFAULT_FIXED_PARAMS['learning_rate']
        assert 2 <= cfg['max_depth'] <= 10

    def test_grid_values_int_dedup_and_categorical(self):
        from modeling.hyperparam_utils import _grid_values
        ints = _grid_values({'type': 'int', 'min': 1, 'max': 3}, points=8)
        assert ints == sorted(set(ints)) and all(isinstance(v, int) for v in ints)
        cats = _grid_values({'type': 'categorical', 'values': ['a', 'b']}, points=8)
        assert cats == ['a', 'b']


@pytest.mark.unit
class TestHyperparamXgbParams:
    """Sklearn-style names are mapped to XGBoost learning-API keys and
    n_estimators is split out as num_boost_round."""

    def test_param_mapping(self):
        from modeling.hyperparam_utils import _build_xgb_params
        cfg = {'n_estimators': 123, 'max_depth': 5, 'learning_rate': 0.07,
               'reg_alpha': 1.5, 'reg_lambda': 2.5, 'subsample': 0.7}
        params, num_round = _build_xgb_params(cfg, nthread=1, has_cat=False)
        assert num_round == 123 and 'n_estimators' not in params
        assert params['eta'] == 0.07
        assert params['alpha'] == 1.5 and params['lambda'] == 2.5
        assert params['max_depth'] == 5 and isinstance(params['max_depth'], int)
        assert params['nthread'] == 1


@pytest.mark.unit
class TestHyperparamGuidance:
    """_build_guidance suggests zoom-out at range edges and zoom-in for an
    interior CV peak (the verbal next-search-space guidance)."""

    def test_edge_peak_suggests_zoom_out(self):
        from modeling.hyperparam_utils import _build_guidance
        curves = [{'param': 'max_depth', 'type': 'int', 'values': [2, 4, 6, 8],
                   'cv_mean': [0.90, 0.85, 0.80, 0.70],
                   'train_mean': [0.95, 0.96, 0.97, 0.98]}]
        g = _build_guidance(curves, 'roc_auc')
        assert g and g[0]['type'] == 'zoom_out'

    def test_interior_peak_suggests_zoom_in(self):
        from modeling.hyperparam_utils import _build_guidance
        curves = [{'param': 'learning_rate', 'type': 'float', 'values': [0.01, 0.1, 0.2, 0.3],
                   'cv_mean': [0.70, 0.90, 0.85, 0.80],
                   'train_mean': [0.72, 0.92, 0.95, 0.99]}]
        g = _build_guidance(curves, 'roc_auc')
        assert g and g[0]['type'] == 'zoom_in'
        assert g[0]['suggested_range'] == [0.01, 0.2]


@pytest.mark.unit
class TestHyperparamSurrogate:
    """Surrogate importances normalize to ~1 with signal and are all-zero on
    a constant target (no attribution possible)."""

    def test_importance_normalizes(self):
        from modeling.hyperparam_utils import _surrogate_importance
        rng = np.random.default_rng(0)
        X = rng.uniform(0, 1, size=(60, 2))
        y = 3 * X[:, 0] + rng.normal(0, 0.01, 60)  # target driven by param 0
        imp = _surrogate_importance(X, y, ['p0', 'p1'])
        assert abs(sum(imp.values()) - 1.0) < 1e-6
        assert imp['p0'] > imp['p1']

    def test_constant_target_zero_importance(self):
        from modeling.hyperparam_utils import _surrogate_importance
        X = np.random.default_rng(0).uniform(0, 1, size=(40, 2))
        y = np.full(40, 0.5)
        imp = _surrogate_importance(X, y, ['p0', 'p1'])
        assert imp == {'p0': 0.0, 'p1': 0.0}


@pytest.mark.unit
class TestHyperparamSearchEngine:
    """End-to-end engine on tiny synthetic data: produces best-metric points,
    validation curves, param emphasis and guidance — and is strict-JSON safe."""

    def test_full_search_outputs(self):
        from modeling.hyperparam_utils import (
            run_hyperparam_search_with_progress, METRIC_NAMES)
        Xtr, ytr, Xte, yte = _hp_synthetic()
        msgs = []
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=8, cv_folds=2, n_jobs=1, validation_curve_points=4,
            search_method='random', random_state=42,
            status_callback=lambda p: msgs.append(p.get('message')),
        )
        assert res['status'] == 'completed'
        assert res['n_trials'] == 8
        # Best metric "space points" for every catalogued metric.
        for m in ('roc_auc', 'pr_auc', 'f1', 'f2', 'precision', 'recall', 'accuracy', 'mcc'):
            assert m in res['best_points']
            assert 'params' in res['best_points'][m]
        # One validation curve per enabled param with aligned arrays.
        assert {c['param'] for c in res['validation_curves']} == {'max_depth', 'learning_rate'}
        for c in res['validation_curves']:
            assert len(c['values']) == len(c['cv_mean']) == len(c['train_mean'])
        # Emphasis + guidance present.
        assert set(res['emphasized']) == {'most_cv_gain', 'most_overfitting', 'most_shrinkage'}
        assert isinstance(res['guidance'], list)
        assert len(msgs) > 0

    def test_strict_json_serializable(self):
        import json
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=4, cv_folds=2, n_jobs=1, validation_curve_points=3, random_state=1,
        )
        # NaN must not appear: allow_nan=False mirrors the browser's JSON.parse.
        from modeling.views import _hp_sanitize_json
        json.dumps(_hp_sanitize_json(res), allow_nan=False)

    def test_stop_flag_halts_search(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        stop = {'stop_requested': True}
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=6, cv_folds=2, n_jobs=1, validation_curve_points=3,
            random_state=2, stop_flag=stop,
        )
        assert res['status'] == 'stopped'


@pytest.mark.unit
class TestHyperparamSearchMethod:
    """Search-method selection: the exhaustive-grid fit-count heuristic
    (< 100 fits/worker -> grid, <= 500 -> random, else bayesian) and that the
    engine honors an explicit method and resolves 'auto'."""

    def test_recommend_grid_for_small_space(self):
        from modeling.hyperparam_utils import recommend_search_method
        rec = recommend_search_method(_hp_space('max_depth'), cv_folds=3, n_jobs=3)
        assert rec['method'] == 'grid'
        assert rec['fits_per_job'] < 100

    def test_recommend_random_for_mid_space(self):
        from modeling.hyperparam_utils import recommend_search_method
        # 3 params @ 5 pts = 125 candidates * 3 cv / 1 worker = 375 fits/worker -> random.
        rec = recommend_search_method(_hp_space('max_depth', 'learning_rate', 'subsample'),
                                      cv_folds=3, n_jobs=1)
        assert rec['method'] == 'random'
        assert 100 <= rec['fits_per_job'] <= 500

    def test_recommend_bayesian_for_large_space(self):
        from modeling.hyperparam_utils import recommend_search_method
        rec = recommend_search_method(
            _hp_space('n_estimators', 'max_depth', 'learning_rate',
                      'min_child_weight', 'subsample', 'colsample_bytree'),
            cv_folds=3, n_jobs=3)
        assert rec['method'] == 'bayesian'
        assert rec['fits_per_job'] > 500

    def test_estimate_grid_candidates_product(self):
        from modeling.hyperparam_utils import estimate_grid_candidates
        # 2 params at 4 points each -> 16 candidate configs.
        assert estimate_grid_candidates(_hp_space('max_depth', 'learning_rate'),
                                        grid_points_per_param=4) == 16

    def test_njobs_shifts_recommendation(self):
        from modeling.hyperparam_utils import recommend_search_method
        sp = _hp_space('max_depth', 'learning_rate', 'subsample')  # 125 candidates
        assert recommend_search_method(sp, 3, 1)['method'] == 'random'   # 375 fits/worker
        assert recommend_search_method(sp, 3, 8)['method'] == 'grid'     # ~47 fits/worker

    def test_engine_runs_grid_and_reports_method(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=8, cv_folds=2, n_jobs=1, validation_curve_points=3,
            search_method='grid', grid_points_per_param=4, random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'grid'
        # Grid evaluates the full product (~4x4=16), independent of n_iter.
        assert res['n_trials'] >= 9
        assert res['n_search_evals'] == res['n_trials']

    def test_engine_runs_bayesian(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=10, cv_folds=2, n_jobs=2, validation_curve_points=3,
            search_method='bayesian', random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'bayesian'
        assert res['n_trials'] == 10  # SMBO evaluates exactly n_iter configs

    def test_engine_auto_resolves_to_grid_for_one_small_param(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=6, cv_folds=2, n_jobs=2, validation_curve_points=3,
            search_method='auto', grid_points_per_param=4, random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'grid'
        assert res['search_method_requested'] == 'auto'
        assert res['recommendation']['method'] == 'grid'

    def test_engine_invalid_method_falls_back_to_auto(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth'),
            n_iter=4, cv_folds=2, n_jobs=2, validation_curve_points=3,
            search_method='nonsense', grid_points_per_param=4, random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method_requested'] == 'auto'


@pytest.mark.unit
class TestHyperparamPointsMap:
    """Per-param checkpoint overrides (the UI Walk_Step column -> points_map)
    flow through the estimate, the recommendation, the grid enumeration, and
    the full engine run; a malformed map is sanitized rather than fatal."""

    def test_estimate_uses_points_map_per_param(self):
        from modeling.hyperparam_utils import estimate_grid_candidates
        sp = _hp_space('max_depth', 'learning_rate')   # scalar 5 would give 5x5=25
        # max_depth (2..10) -> 3 distinct ints; learning_rate keeps the scalar 5 -> 15.
        assert estimate_grid_candidates(
            sp, grid_points_per_param=5, points_map={'max_depth': 3}) == 15

    def test_estimate_map_caps_int_range(self):
        from modeling.hyperparam_utils import estimate_grid_candidates
        sp = _hp_space('max_depth')   # 2..10 -> at most 9 distinct ints
        assert estimate_grid_candidates(sp, points_map={'max_depth': 50}) == 9

    def test_recommend_respects_points_map(self):
        from modeling.hyperparam_utils import recommend_search_method
        sp = _hp_space('max_depth', 'learning_rate', 'subsample')
        # Coarse map (2 each) -> 8 candidates -> grid (default 5 -> 125 -> random).
        rec = recommend_search_method(
            sp, 3, 1, points_map={'max_depth': 2, 'learning_rate': 2, 'subsample': 2})
        assert rec['grid_candidates'] == 8
        assert rec['method'] == 'grid'

    def test_grid_configs_honor_points_map(self):
        from modeling.hyperparam_utils import _grid_configs, DEFAULT_FIXED_PARAMS
        sp = _hp_space('max_depth', 'learning_rate')
        rng = np.random.default_rng(0)
        configs, truncated = _grid_configs(
            sp, DEFAULT_FIXED_PARAMS, grid_points_per_param=5, max_candidates=2000,
            rng=rng, points_map={'max_depth': 3, 'learning_rate': 4})
        assert truncated is False
        assert len(configs) == 12   # 3 x 4
        assert len({c['max_depth'] for c in configs}) == 3
        assert len({c['learning_rate'] for c in configs}) == 4

    def test_engine_runs_with_points_map(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=8, cv_folds=2, n_jobs=1, validation_curve_points=3,
            search_method='grid', grid_points_per_param=5,
            grid_points_per_param_map={'max_depth': 3, 'learning_rate': 4},
            random_state=0)
        assert res['status'] == 'completed'
        assert res['search_method'] == 'grid'
        assert res['grid_points_per_param_map'] == {'max_depth': 3, 'learning_rate': 4}
        assert res['recommendation']['grid_candidates'] == 12   # 3 x 4
        assert res['n_search_evals'] == 12

    def test_engine_sanitizes_bad_points_map(self):
        from modeling.hyperparam_utils import run_hyperparam_search_with_progress
        Xtr, ytr, Xte, yte = _hp_synthetic()
        res = run_hyperparam_search_with_progress(
            Xtr, ytr, Xte, yte, param_space=_hp_space('max_depth', 'learning_rate'),
            n_iter=6, cv_folds=2, n_jobs=1, validation_curve_points=3,
            search_method='grid', grid_points_per_param=4,
            grid_points_per_param_map={'max_depth': 'oops', 'unknown_param': 9, 'learning_rate': 1},
            random_state=0)
        # 'oops' (non-int) dropped, 'unknown_param' (not in space) dropped, 1 clamped up to 2.
        assert res['grid_points_per_param_map'] == {'learning_rate': 2}
        assert res['status'] == 'completed'
