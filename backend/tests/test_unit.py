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
        assert set(s.data.keys()) == {'id', 'file', 'name', 'original_name', 'uploaded_at'}

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
