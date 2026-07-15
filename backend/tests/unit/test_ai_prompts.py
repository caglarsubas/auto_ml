"""Unit tests - AI assistant system prompt and prompt rendering.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


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
