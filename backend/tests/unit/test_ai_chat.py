"""Unit tests - AI assistant chat workflow and intent handling.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from tests.unit._shared import (
    _mock_llm_response,
    _purifier_tool_call,
    _run_chat_workflow,
    _text_response,
    _tool_call_response,
)


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
class TestCodelineRefineFocusAnchor:
    """v3.5.0: a Codeline is an iterative cell — the user asks once, then keeps
    pushing the SAME artifact forward.  The generic turn anchor is wrong for
    those follow-ups (it forbids reusing the previous turn's topic and format),
    so Codeline ``refine`` / ``auto_fix`` turns get the refinement anchor
    instead.  A Codeline's FIRST ask, and every right-side panel turn, keep the
    generic anchor."""

    _FEEDBACK = 'use monthly buckets and plot train and test separately'
    _HISTORY = [
        {'role': 'user', 'content': 'draw the target ratio over time'},
        {'role': 'assistant', 'content': 'Here is the weekly bad rate.\n\n```python\nprint(df.head())\n```'},
    ]

    def _run(self, monkeypatch, *, turn_kind, source='codeline', history=None):
        return _run_chat_workflow(
            monkeypatch, provider='engine',
            user_message=self._FEEDBACK,
            history=self._HISTORY if history is None else history,
            context={'codeline_position': 'after_data_preview',
                     'codeline_turn_kind': turn_kind},
            source=source,
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )

    def test_refine_turn_replaces_generic_anchor(self, monkeypatch):
        from ai_assistant.views import (
            _CODELINE_REFINE_FOCUS_PROMPT, _TURN_FOCUS_PROMPT,
        )
        out = self._run(monkeypatch, turn_kind='refine')
        msgs = out['llm_calls'][0]['messages']
        contents = [m.get('content') or '' for m in msgs]
        assert _CODELINE_REFINE_FOCUS_PROMPT in contents
        assert _TURN_FOCUS_PROMPT not in contents
        # It must sit immediately before the current user message.
        user_idx = max(i for i, m in enumerate(msgs)
                       if m.get('role') == 'user' and m.get('content') == self._FEEDBACK)
        assert msgs[user_idx - 1].get('role') == 'system'
        assert msgs[user_idx - 1].get('content') == _CODELINE_REFINE_FOCUS_PROMPT

    def test_auto_fix_turn_uses_refine_anchor(self, monkeypatch):
        from ai_assistant.views import (
            _CODELINE_REFINE_FOCUS_PROMPT, _TURN_FOCUS_PROMPT,
        )
        out = self._run(monkeypatch, turn_kind='auto_fix')
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert _CODELINE_REFINE_FOCUS_PROMPT in contents
        assert _TURN_FOCUS_PROMPT not in contents

    def test_first_codeline_ask_keeps_generic_anchor(self, monkeypatch):
        """A re-ask with a rewritten intent IS a new question — the generic
        anti-drift anchor still applies to it."""
        from ai_assistant.views import (
            _CODELINE_REFINE_FOCUS_PROMPT, _TURN_FOCUS_PROMPT,
        )
        out = self._run(monkeypatch, turn_kind='intent')
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert _TURN_FOCUS_PROMPT in contents
        assert _CODELINE_REFINE_FOCUS_PROMPT not in contents

    def test_panel_source_ignores_codeline_turn_kind(self, monkeypatch):
        """``codeline_turn_kind`` only means something for Codeline requests —
        the right-side panel must never pick up the refinement anchor."""
        from ai_assistant.views import (
            _CODELINE_REFINE_FOCUS_PROMPT, _TURN_FOCUS_PROMPT,
        )
        out = self._run(monkeypatch, turn_kind='refine', source='panel')
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert _TURN_FOCUS_PROMPT in contents
        assert _CODELINE_REFINE_FOCUS_PROMPT not in contents

    def test_no_anchor_at_all_without_history(self, monkeypatch):
        from ai_assistant.views import (
            _CODELINE_REFINE_FOCUS_PROMPT, _TURN_FOCUS_PROMPT,
        )
        out = self._run(monkeypatch, turn_kind='refine', history=[])
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert _TURN_FOCUS_PROMPT not in contents
        assert _CODELINE_REFINE_FOCUS_PROMPT not in contents

    def test_history_is_replayed_to_the_model(self, monkeypatch):
        """The point of the feature: prior turns reach the model, so the
        revision builds on the draft instead of restarting."""
        out = self._run(monkeypatch, turn_kind='refine')
        contents = [m.get('content') or '' for m in out['llm_calls'][0]['messages']]
        assert 'draw the target ratio over time' in contents
        assert any('Here is the weekly bad rate.' in c for c in contents)

    def test_refine_anchor_demands_complete_revised_code(self):
        from ai_assistant.views import _CODELINE_REFINE_FOCUS_PROMPT
        lowered = _CODELINE_REFINE_FOCUS_PROMPT.lower()
        # Must keep accepted work rather than regenerate from scratch...
        assert 'feedback' in lowered
        assert 'execute_code' in lowered
        # ...and must never invite a partial answer.
        assert 'complete' in lowered
        assert 'never a diff' in lowered

    def test_turn_kind_normalization(self):
        from ai_assistant.views import _resolve_codeline_turn_kind
        assert _resolve_codeline_turn_kind({'codeline_turn_kind': 'REFINE'}) == 'refine'
        assert _resolve_codeline_turn_kind({'codeline_turn_kind': ' auto_fix '}) == 'auto_fix'
        # Unknown / missing / malformed → treated as a first ask, which is the
        # pre-v3.5.0 behaviour an older frontend build would get.
        assert _resolve_codeline_turn_kind({'codeline_turn_kind': 'nonsense'}) == 'intent'
        assert _resolve_codeline_turn_kind({}) == 'intent'
        assert _resolve_codeline_turn_kind(None) == 'intent'


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

    def test_markdown_json_code_becomes_apply_action_no_retry(self, monkeypatch):
        raw = '''The error suggests the first run failed, so here is the corrected action block:

```json
{
  "code": "
df['Var_6_year'] = pd.to_numeric(df['Var_6'].astype(str).str[-4:], errors='coerce').fillna(0)
df['Debt_to_Income_Ratio'] = df['Var_19'] / df['Var_24'].replace(0, 1)
",
  "description": "Create corrected derived features"
}
```'''

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_data_dictionary')
            return _text_response(raw)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        assert len(out['llm_calls']) == 2
        actions = out['result'].get('actions') or []
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        assert "df['Debt_to_Income_Ratio']" in actions[0]['payload']['code']
        assert 'corrected action block' in out['result']['message']

    def test_action_heading_markdown_json_returns_multiple_apply_actions(self, monkeypatch):
        raw = '''Action: Optimized Purification
```json
{
  "purifier_options": [1, 2, 3, 4, 29, 8, 18, 33],
  "split": {"strategy": "random", "percent": 25},
  "description": "Run optimized purification."
}
```

Action: Add Temporal Validation for Dates
```json
{
  "code": "df['Valid_Date_Flag'] = df['Var_6'].notna().astype(int)",
  "description": "Create valid-date flag."
}
```
I will now execute these actions in sequence.'''

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('get_purifier_options')
            return _text_response(raw)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        actions = out['result'].get('actions') or []
        assert [a['type'] for a in actions] == [
            'start_data_purifier',
            'execute_code',
        ]
        assert actions[0]['payload']['purifier_options'] == [1, 2, 3, 4, 29, 8, 18, 33]
        assert "df['Valid_Date_Flag']" in actions[1]['payload']['code']

    def test_python_correction_fence_returns_execute_code_action(self, monkeypatch):
        raw = '''The error occurs because Var_3 contains non-numeric values.

Here's the corrected code block:

`python
Parse timestamps (if not already datetime)
df['Application_Datetime'] = pd.to_datetime(df['Application_Datetime'], errors='coerce')
df['Var_6'] = pd.to_datetime(df['Var_6'], errors='coerce')

Convert Var_3 to numeric (0/1) and handle non-numeric values
df['Var_3_numeric'] = pd.to_numeric(df['Var_3'], errors='coerce').fillna(0).astype(int)

Legal Action Risk (recency): Use years since last legal action (0 if no action)
df['legal_action_risk'] = df['Var_3_numeric'] * (
    (df['Application_Datetime'] - df['Var_6']).dt.days / 365
).replace([np.inf, -np.inf], 0).fillna(0)
`'''

        def call_llm(idx, messages, tools):
            return _text_response(raw)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        actions = out['result'].get('actions') or []
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        code = actions[0]['payload']['code']
        assert "df['legal_action_risk']" in code
        assert '# Legal Action Risk' in code

    def test_standalone_python_correction_returns_execute_code_action(self, monkeypatch):
        raw = '''`python
Create Debt_to_Income ratio
df['Debt_to_Income'] = df['Var_19'] / df['Var_24'].replace(0, 1)

Create Credit_Utilization ratio
df['Credit_Utilization'] = df['Var_18'] / df['Var_17'].replace(0, 1)
`'''

        def call_llm(idx, messages, tools):
            return _text_response(raw)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        actions = out['result'].get('actions') or []
        assert len(actions) == 1
        assert actions[0]['type'] == 'execute_code'
        code = actions[0]['payload']['code']
        assert "df['Credit_Utilization']" in code
        assert '# Create Credit_Utilization ratio' in code

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

    def test_non_reasoning_engine_partial_table_uses_compact_retry(self, monkeypatch):
        from ai_assistant.views import _PARTIAL_REPLY_RETRY_PROMPT

        final = (
            'Here are the strongest derived features.\n\n'
            '| Feature | Formula / transformation | Meaning | Why it helps the model |\n'
            '| --- | --- | --- | --- |\n'
            '| DTI | Var_19 / Var_24 | debt burden | separates risky borrowers |\n\n'
            '<<<ACTION:execute_code>>>\n'
            '{"code": "df[\'DTI\']=df[\'Var_19\']/df[\'Var_24\'].replace(0, 1)", '
            '"description": "Create DTI"}\n'
            '<<<END_ACTION>>>'
        )

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('invoke_skill')
            if idx == 1:
                return _text_response(
                    'Below is a table of proposed features.\n\n'
                    '| Feature | Formula | Meaning'
                )
            assert tools is None
            return _text_response(final)

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        assert len(out['llm_calls']) == 3
        retry_messages = out['llm_calls'][2]['messages']
        assert retry_messages[0]['content'] == _PARTIAL_REPLY_RETRY_PROMPT
        assert all('TOOL_RESULT[invoke_skill]' not in (m.get('content') or '')
                   for m in retry_messages)
        assert 'strongest derived features' in out['result']['message']
        assert out['result']['actions'][0]['type'] == 'execute_code'

    def test_partial_retry_still_partial_falls_back(self, monkeypatch):
        from ai_assistant.views import _TOOL_BUDGET_EXHAUSTED_FALLBACK

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response('invoke_skill')
            if idx == 1:
                return _text_response('| Feature | Formula | Meaning')
            return _text_response('| Feature | Formula | Meaning')

        out = _run_chat_workflow(monkeypatch, provider='engine',
                                 reasoning=False, call_llm=call_llm)
        assert len(out['llm_calls']) == 3
        assert out['result']['message'] == _TOOL_BUDGET_EXHAUSTED_FALLBACK

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
