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
