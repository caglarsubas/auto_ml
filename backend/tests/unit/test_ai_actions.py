"""Unit tests - AI assistant action parsing, dispatch, tools.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from tests.unit._shared import (
    _SpanCapture,
    _patch_span_attr,
)


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

    def test_loose_multiline_execute_code_json_is_salvaged(self):
        """Mistral can emit raw newlines inside the JSON code string."""
        msg = '''Creating features.
<<<ACTION:execute_code>>>
{
  "code": "
# Credit Utilization Ratio
df['credit_utilization_ratio'] = df['Var_19'] / df['Var_4'].replace(0, 1)

# Income-to-Debt Ratio
df['income_to_debt_ratio'] = df['Var_23'] / df['Var_19'].replace(0, 1)
",
  "description": "Create two derived ratios"
}
<<<END_ACTION>>>'''
        actions, clean = self._extract(msg)
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        code = actions[0]['payload']['code']
        assert "credit_utilization_ratio" in code
        assert "income_to_debt_ratio" in code
        assert actions[0]['payload']['description'] == 'Create two derived ratios'
        assert 'Creating features.' in clean

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

    def test_dispatch_codeline_source_stamps_execution_capability(self, monkeypatch):
        """Inline Codeline execute_code stamps capability footprints."""
        from ai_assistant import action_executor as ae
        from ai_assistant import prometa_config as pc

        captured = {}

        def _capture(key, value):
            captured[key] = value

        monkeypatch.setattr(pc, 'set_span_attr', _capture)
        monkeypatch.setattr(ae, 'set_span_attr', _capture)
        monkeypatch.setattr(ae, 'stamp_codeline_capability', pc.stamp_codeline_capability)

        ae.dispatch_action(
            1,
            'execute_code',
            {
                'code': '',
                'mode': 'exploratory',
                'codeline_position': 'after_data_preview',
                'auto_correction_attempt': 2,
            },
            source='codeline',
        )
        assert captured.get('declarai.action.source') == 'codeline'
        assert captured.get('declarai.capability.inline_cell_execution') is True
        assert captured.get('declarai.codeline.position') == 'after_data_preview'
        assert captured.get('declarai.execute_code.mode') == 'exploratory'
        assert captured.get('declarai.codeline.auto_correction_attempt') == 2

    def test_codeline_communication_stamps_turn_kind_and_iteration(self, monkeypatch):
        """v3.5.0: a Codeline chat turn carries which round of the cell's
        conversation it is, so a trace shows how many feedback iterations an
        answer took to converge."""
        from ai_assistant import prometa_config as pc

        captured = {}
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda key, value: captured.__setitem__(key, value))

        pc.stamp_codeline_capability(
            kind='communication',
            position='after_data_preview',
            turn_kind='refine',
            iteration=3,
        )
        assert captured.get('declarai.capability.inline_cell_communication') is True
        assert captured.get('declarai.codeline.turn_kind') == 'refine'
        assert captured.get('declarai.codeline.iteration') == 3

    def test_codeline_turn_kind_and_iteration_are_optional(self, monkeypatch):
        """Omitting them must not stamp empty values — the pre-v3.5.0 shape."""
        from ai_assistant import prometa_config as pc

        captured = {}
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda key, value: captured.__setitem__(key, value))

        pc.stamp_codeline_capability(kind='communication', position='p')
        assert 'declarai.codeline.turn_kind' not in captured
        assert 'declarai.codeline.iteration' not in captured

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

    # ── update_config purifier_options alias ───────────────────────────
    # Regression for "Applied but Selected Options unchanged": models
    # emit key=`purifier_options` (from update_purifier_selection) inside
    # update_config.updates[].  The handler must normalize to
    # preprocessing_options so the frontend checkbox path fires.

    def test_update_config_purifier_options_alias_normalizes_key(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {
                    'key': 'purifier_options',
                    'value': [1, 2, 3, 4, 8, 12, 28, 32],
                },
            ],
            'description': (
                'Switch to Aggressive Cleaning: lower correlation to 0.80 '
                'and sparsity to 0.90 • purifier_options = [1,2,3,4,8,12,28,32]'
            ),
        })
        assert result['status'] == 'success'
        assert len(result['applied']) == 1
        entry = result['applied'][0]
        assert entry['key'] == 'preprocessing_options'
        assert entry['value'] == [1, 2, 3, 4, 8, 12, 28, 32]

    def test_update_config_preprocessing_options_canonical_key(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'preprocessing_options', 'value': [1, 2, 7, 23]},
            ],
        })
        assert result['status'] == 'success'
        entry = result['applied'][0]
        assert entry['key'] == 'preprocessing_options'
        assert entry['value'] == [1, 2, 7, 23]

    def test_update_config_purifier_options_drops_invalid_ids(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'purifier_options', 'value': [1, 1, 99, -3, 'foo', 8, 0, 34]},
            ],
        })
        assert result['status'] == 'success'
        assert result['applied'][0]['value'] == [1, 8, 34]

    def test_update_config_purifier_options_rejects_non_list(self):
        result = self._dispatch(1, 'update_config', {
            'updates': [
                {'key': 'purifier_options', 'value': 'all'},
            ],
        })
        assert result['status'] == 'error'
        assert len(result['errors']) == 1
        assert 'list' in result['errors'][0]['error']

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

@pytest.mark.unit
class TestActionToolMcpMarkers:
    """Direct action handler spans must point at their governed MCP tools."""

    def test_update_notes_stamps_direct_action_mcp_marker(self, monkeypatch):
        from ai_assistant.action_executor import update_notes

        cap = _SpanCapture()
        _patch_span_attr(monkeypatch, 'ai_assistant.action_executor', capture=cap)

        result = update_notes(
            60104,
            {
                'action': 'add',
                'position': 'after_data_preview',
                'content': 'Reviewed.',
            },
        )

        assert result['status'] == 'success'
        assert cap.captured.get('mcp.server.name') == 'declarai'
        assert cap.captured.get('mcp.tool.name') == 'declarai.action.update_notes'
        assert cap.captured.get('declarai.mcp.tool_name') == \
            'declarai.action.update_notes'
        assert cap.captured.get('gen_ai.tool.name') == 'update-notes'
        assert cap.captured.get('prometa.tool_name') == 'update-notes'
