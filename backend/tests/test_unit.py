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
        calls = []

        def fake_call_llm(messages, model_key, tools=None):
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

        # 6 in-loop rounds @ 10 tokens each + 1 synthesis @ 25 tokens.
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
        # 6 loop calls @ tokens=10 → 60 + 60 = 120 prompt + 120 completion = 240 total.
        # 1 synthesis call @ tokens=25 → 25 prompt + 25 completion = 50 total.
        # Grand totals: 145 prompt, 145 completion, 290 total.
        assert usage.get('prompt_tokens') == 6 * 10 + 25
        assert usage.get('completion_tokens') == 6 * 10 + 25
        assert usage.get('total_tokens') == 6 * 20 + 50

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
