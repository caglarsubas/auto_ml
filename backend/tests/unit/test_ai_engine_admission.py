"""Unit tests — engine admission telemetry (llm-inference-engine PR #107).

The engine stamps the scheduler lease that admitted a request onto the response
headers. Before this, the whole span between "request sent" and "first byte
back" was opaque to us and the chat panel labelled it "Thinking" — a guess that
reads as wrong precisely when the request was queued.

The engine team called out four contract rules that the numbers are useless
without. Each one has a test here, because getting any of them wrong produces
exactly the class of misleading progress the channel exists to remove.
"""
import pytest

from tests.unit._shared import _run_chat_workflow, _text_response


@pytest.mark.unit
class TestParseAdmissionHeaders:
    """Rule 4: absent, never zeroed."""

    def _parse(self, headers):
        from ai_assistant.model_registry import parse_admission_headers
        return parse_admission_headers(headers)

    def test_reads_the_full_header_set(self):
        out = self._parse({
            'x-engine-queue-wait-ms': '4120',
            'x-engine-queue-depth': '3',
            'x-engine-tenant-queue-depth': '1',
            'x-engine-resource': 'ollama_http:nemotron-3-nano:30b',
        })
        assert out == {
            'queue_wait_ms': 4120,
            'queue_depth': 3,
            'tenant_queue_depth': 1,
            'resource': 'ollama_http:nemotron-3-nano:30b',
        }

    def test_a_request_that_never_queued_yields_no_keys_not_zeros(self):
        # "Did not queue" must stay distinguishable from "queued for 0 ms".
        assert self._parse({}) == {}
        assert self._parse({'content-type': 'application/json'}) == {}

    def test_a_present_zero_wait_is_kept(self):
        # Zero is a real measurement when the header is there — only ABSENCE
        # means "never reached the scheduler".
        assert self._parse({'x-engine-queue-wait-ms': '0'}) == {'queue_wait_ms': 0}

    def test_malformed_values_are_dropped_not_coerced(self):
        out = self._parse({
            'x-engine-queue-wait-ms': 'not-a-number',
            'x-engine-queue-depth': '2',
        })
        assert out == {'queue_depth': 2}

    def test_missing_headers_object_is_safe(self):
        assert self._parse(None) == {}


@pytest.mark.unit
class TestAdmissionDetail:
    """Rules 2 and 3: depths count the request itself; 0 means disabled."""

    def _detail(self, admission):
        from ai_assistant.views import _admission_detail
        return _admission_detail(admission)

    def test_depth_of_one_means_nobody_ahead(self):
        # Rule 2: an admitted request under a live scheduler always reports at
        # least 1. Rendering the raw depth as "1 ahead" would be the off-by-one
        # the engine team explicitly warned about.
        detail = self._detail({'queue_wait_ms': 4120, 'queue_depth': 1})
        assert detail == 'queued 4.1s'
        assert 'ahead' not in detail

    def test_depth_of_three_means_two_ahead(self):
        assert self._detail({'queue_wait_ms': 4120, 'queue_depth': 3}) == \
            'queued 4.1s, 2 ahead'

    def test_depth_of_zero_means_scheduler_disabled_not_nobody_ahead(self):
        # Rule 3: 0 is "the scheduler is off", not "you were first in line".
        detail = self._detail({'queue_wait_ms': 4120, 'queue_depth': 0})
        assert detail == 'queued 4.1s'

    def test_no_wait_measurement_reports_nothing(self):
        assert self._detail({'queue_depth': 3}) is None
        assert self._detail({}) is None

    def test_a_trivial_wait_with_nobody_ahead_is_suppressed_as_noise(self):
        assert self._detail({'queue_wait_ms': 4, 'queue_depth': 1}) is None

    def test_a_trivial_wait_is_still_reported_when_others_were_queued(self):
        assert self._detail({'queue_wait_ms': 4, 'queue_depth': 4}) == \
            'queued 4ms, 3 ahead'

    def test_wait_formatting_across_boundaries(self):
        assert self._detail({'queue_wait_ms': 820}) == 'queued 820ms'
        assert self._detail({'queue_wait_ms': 4120}) == 'queued 4.1s'
        assert self._detail({'queue_wait_ms': 65000}) == 'queued 1m 05s'


@pytest.mark.unit
class TestAdmissionReachesTheProgressRow:
    """The point of the whole exercise: attribute the wait in the step list."""

    def _steps(self, monkeypatch, llm_result):
        from ai_assistant import progress
        events = []

        def call_llm(idx, messages, tools):
            return llm_result

        with progress.bind_sink(progress.ProgressSink(events.append)):
            _run_chat_workflow(monkeypatch, provider='engine', call_llm=call_llm)
        return events

    def test_queue_wait_is_attributed_on_the_llm_row(self, monkeypatch):
        result = dict(_text_response('Recall is 0.82.'))
        result['declarai_admission'] = {'queue_wait_ms': 9200, 'queue_depth': 3}
        steps = self._steps(monkeypatch, result)

        row = [e for e in steps if e['id'] == 'llm:0' and e['state'] == 'done']
        assert row, steps
        assert 'queued 9.2s, 2 ahead' in row[0]['detail']

    def test_a_turn_that_never_queued_says_nothing_about_queuing(self, monkeypatch):
        steps = self._steps(monkeypatch, _text_response('Recall is 0.82.'))
        row = [e for e in steps if e['id'] == 'llm:0' and e['state'] == 'done']
        assert row
        assert 'queued' not in (row[0].get('detail') or '')

    def test_admission_never_breaks_the_answer(self, monkeypatch):
        result = dict(_text_response('Recall is 0.82.'))
        result['declarai_admission'] = {'queue_wait_ms': 'garbage'}
        from ai_assistant import progress
        events = []
        with progress.bind_sink(progress.ProgressSink(events.append)):
            out = _run_chat_workflow(monkeypatch, provider='engine',
                                     call_llm=lambda *a: result)
        assert out['result']['message'] == 'Recall is 0.82.'


@pytest.mark.unit
class TestCallEngineCapturesHeaders:
    """The capture must not disturb the instrumented SDK call path."""

    def test_event_hook_is_registered_on_the_transport_not_the_call(self):
        # We route engine traffic through the plain SDK method specifically so
        # prometa's openai auto-instrumentation wraps it. Reading headers via
        # `with_raw_response` would be a different call path and could drop
        # those spans, so the capture has to live on the transport.
        import inspect
        from ai_assistant import model_registry
        src = inspect.getsource(model_registry.call_engine)
        code = '\n'.join(line for line in src.splitlines()
                         if not line.lstrip().startswith('#'))
        assert 'event_hooks' in code
        assert 'with_raw_response' not in code
        assert 'client.chat.completions.create(**kwargs)' in code

    def test_headers_seen_by_the_hook_land_on_the_result(self, monkeypatch):
        from ai_assistant import model_registry

        captured = {}

        class _FakeResponse:
            headers = {
                'x-engine-queue-wait-ms': '4120',
                'x-engine-queue-depth': '2',
            }

        class _FakeCompletions:
            def create(self, **kwargs):
                # Simulate the transport firing its response hook mid-call.
                for hook in captured['hooks']:
                    hook(_FakeResponse())

                class _R:
                    def model_dump(self):
                        return {'choices': [{'message': {'content': 'hi'},
                                             'finish_reason': 'stop'}]}
                return _R()

        class _FakeClient:
            def __init__(self, **kwargs):
                pass
            chat = type('chat', (), {'completions': _FakeCompletions()})()

        class _FakeHttpx:
            def Client(self, **kwargs):
                captured['hooks'] = kwargs['event_hooks']['response']
                return type('c', (), {'close': lambda self: None})()

        import sys
        monkeypatch.setitem(sys.modules, 'httpx', _FakeHttpx())
        monkeypatch.setitem(sys.modules, 'openai',
                            type('m', (), {'OpenAI': _FakeClient}))

        out = model_registry.call_engine(
            [{'role': 'user', 'content': 'hi'}],
            {'model_id': 'nemotron-3-nano:30b', 'max_tokens': 100,
             'temperature': 0.4, 'supports_tools': False},
        )
        assert out['declarai_admission'] == {'queue_wait_ms': 4120, 'queue_depth': 2}
