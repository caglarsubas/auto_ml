"""Unit tests — turn-progress channel for the AI Assistant.

The chat panel used to show one opaque typing indicator for a whole 5–60s
turn.  ``ai_assistant/progress.py`` + the ``stream: true`` branch on
``AIAssistantView`` narrate the turn instead: one step row per workflow phase
(intent, context, retrieval, LLM rounds, tool calls, synthesis, actions).

These tests pin three things:
  1. The emitter is inert when nobody is listening — the non-streaming
     endpoint, Codeline, and the rest of this suite pay nothing for it.
  2. ``_chat_workflow`` narrates the phases it actually runs, in order.
  3. ``_stream_chat_turn`` frames those events as NDJSON and always
     terminates with exactly one ``result`` or one ``error`` line.
"""
import json

import pytest

from tests.unit._shared import (
    _run_chat_workflow,
    _text_response,
    _tool_call_response,
)


def _collect(events):
    """Bind a sink that appends to ``events`` for the duration of the block."""
    from ai_assistant import progress
    return progress.bind_sink(progress.ProgressSink(events.append))


@pytest.mark.unit
class TestProgressEmitterIsInertByDefault:
    """No sink bound → every call is a no-op, so nothing else pays for it."""

    def test_emit_without_sink_is_a_noop(self):
        from ai_assistant import progress
        progress.emit('anything', 'Anything')  # must not raise
        assert progress.is_active() is False

    def test_step_without_sink_still_runs_the_block(self):
        from ai_assistant import progress
        ran = []
        with progress.step('x', 'X') as handle:
            ran.append(True)
            handle.detail = 'ignored'
        assert ran == [True]

    def test_sink_is_unbound_after_the_block(self):
        from ai_assistant import progress
        events = []
        with _collect(events):
            assert progress.is_active() is True
        assert progress.is_active() is False


@pytest.mark.unit
class TestProgressEventShape:
    """Every event carries the fields the panel de-duplicates and orders on."""

    def test_step_emits_running_then_done(self):
        from ai_assistant import progress
        events = []
        with _collect(events):
            with progress.step('retrieval', 'Searching the knowledge bank') as handle:
                handle.detail = '3 sources'
        assert [e['state'] for e in events] == ['running', 'done']
        assert all(e['id'] == 'retrieval' for e in events)
        assert events[1]['detail'] == '3 sources'

    def test_detail_set_inside_the_block_is_not_leaked_to_running(self):
        # The running row appears before the work is done, so it cannot know
        # the outcome — only the done row carries the refined detail.
        from ai_assistant import progress
        events = []
        with _collect(events):
            with progress.step('retrieval', 'Searching') as handle:
                handle.detail = '3 sources'
        assert 'detail' not in events[0]

    def test_step_emits_error_and_reraises(self):
        from ai_assistant import progress
        events = []
        with pytest.raises(ValueError):
            with _collect(events):
                with progress.step('tool:0:0:get_dq_summary', 'Reading DQ'):
                    raise ValueError('redis down')
        assert events[-1]['state'] == 'error'
        assert 'redis down' in events[-1]['detail']

    def test_events_are_sequenced_and_timed(self):
        from ai_assistant import progress
        events = []
        with _collect(events):
            progress.emit('a', 'A')
            progress.emit('b', 'B')
        assert [e['seq'] for e in events] == [1, 2]
        assert all(e['type'] == 'step' for e in events)
        assert all(isinstance(e['elapsed_ms'], int) for e in events)

    def test_a_broken_sink_never_breaks_the_turn(self):
        from ai_assistant import progress

        def explode(_event):
            raise RuntimeError('client hung up')

        with progress.bind_sink(progress.ProgressSink(explode)):
            progress.emit('a', 'A')  # must not propagate


@pytest.mark.unit
class TestChatWorkflowNarratesItsPhases:
    """The real workflow body emits a step row for each phase it runs."""

    def test_tool_calling_turn_narrates_intent_context_tools_and_rounds(self, monkeypatch):
        events = []

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response(name='get_dq_summary')
            return _text_response('Here is what the data-quality summary says.')

        with _collect(events):
            _run_chat_workflow(monkeypatch, provider='openai', call_llm=call_llm)

        ids = [e['id'] for e in events]
        assert ids.index('intent') < ids.index('context') < ids.index('llm:0')
        assert 'tool:0:0:get_dq_summary' in ids
        assert ids.index('llm:0') < ids.index('tool:0:0:get_dq_summary') < ids.index('llm:1')

    def test_tool_step_label_is_human_readable_not_the_function_name(self, monkeypatch):
        events = []

        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response(name='get_vif_decomposition')
            return _text_response('done')

        with _collect(events):
            _run_chat_workflow(monkeypatch, provider='openai', call_llm=call_llm)

        labels = [e['label'] for e in events if e['id'].endswith('get_vif_decomposition')]
        assert labels and all(l == 'Reading VIF decomposition' for l in labels)

    def test_unknown_tool_degrades_to_a_readable_label(self):
        from ai_assistant.views import _tool_step_label
        assert _tool_step_label('get_brand_new_thing') == 'Get brand new thing'

    def test_retrieval_step_only_appears_when_intent_asks_for_it(self, monkeypatch):
        with_r, without_r = [], []

        def call_llm(idx, messages, tools):
            return _text_response('PSI measures population stability.')

        monkeypatch.setattr(
            'ai_assistant.views.retrieve_knowledge_context',
            lambda q: {'context': 'KB SNIPPET', 'results': [
                {'source': 'a.md', 'title': 'A', 'heading': 'H', 'chunk_id': 'c1'},
            ]},
        )
        with _collect(with_r):
            _run_chat_workflow(monkeypatch, provider='openai', call_llm=call_llm,
                               intent_labels_for_turn=['A', 'R'])
        with _collect(without_r):
            _run_chat_workflow(monkeypatch, provider='openai', call_llm=call_llm,
                               intent_labels_for_turn=['A'])

        assert 'retrieval' in [e['id'] for e in with_r]
        assert 'retrieval' not in [e['id'] for e in without_r]
        detail = [e.get('detail') for e in with_r
                  if e['id'] == 'retrieval' and e['state'] == 'done']
        assert detail == ['1 source']

    def test_actions_step_reports_how_many_actions_the_turn_produced(self, monkeypatch):
        events = []
        reply = (
            'Here you go.\n\n'
            '<<<ACTION:execute_code>>>\n'
            '{"description": "add a ratio feature", "code": "df[\'r\'] = 1"}\n'
            '<<<END_ACTION>>>'
        )

        with _collect(events):
            out = _run_chat_workflow(monkeypatch, provider='openai',
                                     call_llm=lambda *a: _text_response(reply))

        assert out['result'].get('actions')
        action_rows = [e for e in events if e['id'] == 'actions']
        assert action_rows and action_rows[-1]['detail'] == '1 action to review'

    def test_narration_is_optional_result_is_identical_without_a_sink(self, monkeypatch):
        def call_llm(idx, messages, tools):
            if idx == 0:
                return _tool_call_response(name='get_dq_summary')
            return _text_response('Same answer either way.')

        quiet = _run_chat_workflow(monkeypatch, provider='openai', call_llm=call_llm)
        events = []
        with _collect(events):
            loud = _run_chat_workflow(monkeypatch, provider='openai', call_llm=call_llm)

        assert quiet['result']['message'] == loud['result']['message']
        assert events, 'sanity: the narrated run really did emit'


@pytest.mark.unit
class TestStreamChatTurnFraming:
    """``_stream_chat_turn`` frames the events as NDJSON for the panel."""

    def _lines(self, chunks):
        return [json.loads(c) for c in chunks if c.strip()]

    def test_steps_precede_a_single_terminal_result_line(self, monkeypatch):
        from ai_assistant import views, progress

        def fake_workflow(**kwargs):
            progress.emit('intent', 'Reading your question', 'done')
            progress.emit('llm:0', 'Thinking', 'done')
            return {'message': 'hello', 'usage': {}}

        monkeypatch.setattr(views, '_chat_workflow', fake_workflow)
        lines = self._lines(views._stream_chat_turn({'user_message': 'hi'}))

        assert [l['type'] for l in lines] == ['step', 'step', 'result']
        assert lines[-1]['data']['message'] == 'hello'

    def test_workflow_failure_becomes_a_terminal_error_line(self, monkeypatch):
        from ai_assistant import views

        def boom(**kwargs):
            raise RuntimeError('engine unreachable')

        monkeypatch.setattr(views, '_chat_workflow', boom)
        lines = self._lines(views._stream_chat_turn({'user_message': 'hi'}))

        assert lines[-1]['type'] == 'error'
        assert 'engine unreachable' in lines[-1]['error']
        assert lines[-1]['status'] == 500

    def test_missing_api_key_keeps_its_503(self, monkeypatch):
        from ai_assistant import views

        def boom(**kwargs):
            raise EnvironmentError('OpenAI API key not configured.')

        monkeypatch.setattr(views, '_chat_workflow', boom)
        lines = self._lines(views._stream_chat_turn({'user_message': 'hi'}))

        assert lines[-1]['type'] == 'error'
        assert lines[-1]['status'] == 503

    def test_every_line_is_standalone_json(self, monkeypatch):
        from ai_assistant import views, progress

        def fake_workflow(**kwargs):
            progress.emit('intent', 'Reading your question', 'done', 'about concept')
            return {'message': 'ok'}

        monkeypatch.setattr(views, '_chat_workflow', fake_workflow)
        for chunk in views._stream_chat_turn({'user_message': 'hi'}):
            assert chunk.endswith('\n')
            json.loads(chunk)  # each chunk parses on its own — NDJSON contract

    def test_heartbeat_keeps_an_idle_connection_alive(self, monkeypatch):
        import time
        from ai_assistant import views

        monkeypatch.setattr(views, '_STREAM_HEARTBEAT_SECONDS', 0.05)

        def slow_workflow(**kwargs):
            time.sleep(0.25)
            return {'message': 'took a while'}

        monkeypatch.setattr(views, '_chat_workflow', slow_workflow)
        lines = self._lines(views._stream_chat_turn({'user_message': 'hi'}))

        assert any(l['type'] == 'ping' for l in lines)
        assert lines[-1]['type'] == 'result'


@pytest.mark.unit
class TestStreamingIsOptOnly:
    """The default (non-streaming) contract is untouched."""

    def test_plain_post_still_returns_a_json_body(self, monkeypatch):
        from rest_framework.test import APIRequestFactory
        from ai_assistant import views

        monkeypatch.setattr(views, '_chat_workflow',
                            lambda **kw: {'message': 'plain', 'usage': {}})
        request = APIRequestFactory().post(
            '/api/ai-assistant/chat/', {'message': 'hi'}, format='json')
        response = views.AIAssistantView.as_view()(request)

        assert response.status_code == 200
        assert response.data['message'] == 'plain'

    def test_stream_flag_switches_to_ndjson(self, monkeypatch):
        from rest_framework.test import APIRequestFactory
        from ai_assistant import views

        monkeypatch.setattr(views, '_chat_workflow',
                            lambda **kw: {'message': 'streamed', 'usage': {}})
        request = APIRequestFactory().post(
            '/api/ai-assistant/chat/', {'message': 'hi', 'stream': True}, format='json')
        response = views.AIAssistantView.as_view()(request)

        assert response.streaming is True
        assert response['Content-Type'] == 'application/x-ndjson'
        assert response['X-Accel-Buffering'] == 'no'
        body = b''.join(response.streaming_content).decode()
        last = json.loads(body.strip().splitlines()[-1])
        assert last == {'type': 'result', 'data': {'message': 'streamed', 'usage': {}}}

    def test_empty_message_is_still_rejected_before_streaming(self, monkeypatch):
        from rest_framework.test import APIRequestFactory
        from ai_assistant import views

        request = APIRequestFactory().post(
            '/api/ai-assistant/chat/', {'message': '  ', 'stream': True}, format='json')
        response = views.AIAssistantView.as_view()(request)

        assert response.status_code == 400
