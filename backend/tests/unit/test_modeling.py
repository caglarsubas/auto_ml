"""Unit tests - modeling (pipeline runs, SFS logic, SHAP, status readers).

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


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
            'pipeline_codelines': {
                'after_data_preview': {
                    'id': 'cl-1',
                    'position': 'after_data_preview',
                    'mode': 'code',
                    'code': 'print(df.shape)',
                    'intent': '',
                }
            },
        }
        run = PipelineRun.objects.create(name='State Test', state=state)
        run.refresh_from_db()
        assert run.state['declaration']['file_id'] == 42
        assert run.state['modeling']['substep'] == 'encoding_completed'
        assert run.state['pipeline_notes']['after_data_preview'] == 'Looks good'
        assert run.state['pipeline_codelines']['after_data_preview']['code'] == 'print(df.shape)'

    def test_pipeline_run_ordering(self):
        """Runs are ordered by most recently updated (descending)."""
        from datetime import timedelta
        from django.utils import timezone
        from modeling.models import PipelineRun
        run1 = PipelineRun.objects.create(name='First')
        run2 = PipelineRun.objects.create(name='Second')
        # Pin updated_at deterministically (auto_now would otherwise depend on
        # wall-clock resolution; .update() bypasses auto_now).
        now = timezone.now()
        PipelineRun.objects.filter(pk=run1.pk).update(updated_at=now - timedelta(seconds=1))
        PipelineRun.objects.filter(pk=run2.pk).update(updated_at=now)
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
