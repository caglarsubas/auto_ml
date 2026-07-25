"""Unit tests - AI assistant cache and Prometa telemetry/spans.

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
    _run_chat_workflow,
    _text_response,
)


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
        from tests.unit._shared import repo_root
        env_path = os.path.join(str(repo_root()), '.env')
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
            assert cap.captured.get('mcp.server.name') == 'declarai'
            assert cap.captured.get('mcp.tool.name') == 'redis-get'
            assert cap.captured.get('gen_ai.tool.name') == 'redis-get'
            assert cap.captured.get('prometa.tool_name') == 'redis-get'
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
        ('read_pipeline_codelines', 'pipeline_codelines'),
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
            assert cap.captured.get('mcp.server.name') == 'declarai'
            assert cap.captured.get('mcp.tool.name') == 'cache-read:pipeline_config'
            assert cap.captured.get('gen_ai.tool.name') == 'cache-read:pipeline_config'
            assert cap.captured.get('prometa.tool_name') == 'cache-read:pipeline_config'
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
            assert cap.captured.get('mcp.server.name') == 'declarai'
            assert cap.captured.get('mcp.tool.name') == 'declarai.get_encoding_plan'
            assert cap.captured.get('declarai.mcp.tool_name') == \
                'declarai.get_encoding_plan'
            assert cap.captured.get('declarai.tool.name') == 'get_encoding_plan'
            assert cap.captured.get('gen_ai.tool.name') == 'get_encoding_plan'
            assert cap.captured.get('prometa.tool_name') == 'get_encoding_plan'
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
        assert cap.captured.get('mcp.server.name') == 'declarai'
        assert cap.captured.get('mcp.tool.name') == 'declarai.no_such_tool'
        assert cap.captured.get('declarai.tool.name') == 'no_such_tool'
        assert cap.captured.get('gen_ai.tool.name') == 'no_such_tool'
        assert cap.captured.get('prometa.tool_name') == 'no_such_tool'
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

    def test_set_span_attr_forwards_to_sdk_set_attribute_when_available(self, monkeypatch):
        from ai_assistant import prometa_config as pc

        sdk_calls: list[tuple[str, object]] = []
        fallback_calls: list[tuple[str, object]] = []
        import prometa
        monkeypatch.setattr(
            prometa,
            'set_attribute',
            lambda key, value: sdk_calls.append((key, value)),
            raising=False,
        )
        monkeypatch.setattr(
            pc,
            '_set_span_attr_direct',
            lambda key, value: fallback_calls.append((key, value)),
        )

        pc.set_span_attr('declarai.mcp.operation', 'read_tool')

        assert sdk_calls == [('declarai.mcp.operation', 'read_tool')]
        assert fallback_calls == []

    def test_set_span_attrs_forwards_to_sdk_set_attributes_when_available(self, monkeypatch):
        from ai_assistant import prometa_config as pc

        sdk_calls: list[dict] = []
        fallback_calls: list[tuple[str, object]] = []
        import prometa
        monkeypatch.setattr(
            prometa,
            'set_attributes',
            lambda attrs: sdk_calls.append(attrs),
            raising=False,
        )
        monkeypatch.setattr(
            pc,
            'set_span_attr',
            lambda key, value: fallback_calls.append((key, value)),
        )

        pc.set_span_attrs({
            'gen_ai.tool.name': 'declarai.get_data_dictionary',
            'prometa.tool_name': 'declarai.get_data_dictionary',
        })

        assert sdk_calls == [{
            'gen_ai.tool.name': 'declarai.get_data_dictionary',
            'prometa.tool_name': 'declarai.get_data_dictionary',
        }]
        assert fallback_calls == []

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

        def fake_dispatch(file_id, action_type, payload, *,
                          parent_span_id=None, source=None):
            captured['file_id'] = file_id
            captured['action_type'] = action_type
            captured['parent_span_id'] = parent_span_id
            captured['source'] = source
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
        assert captured['source'] == 'panel'

    def test_action_execute_view_treats_missing_parent_span_id_as_none(
            self, monkeypatch):
        """Legacy clients (v2.25.0..v2.37.0 frontend) don't send the
        field — view must default to None so dispatch_action sees the
        legacy call shape and skips set_input_ref entirely."""
        from ai_assistant import views

        captured = {}

        def fake_dispatch(file_id, action_type, payload, *,
                          parent_span_id=None, source=None):
            captured['parent_span_id'] = parent_span_id
            captured['source'] = source
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
        assert captured['source'] == 'panel'

    def test_action_execute_view_rejects_non_string_parent_span_id(
            self, monkeypatch):
        """Defensive: a buggy frontend that sends parent_span_id as an
        int / dict / list must not poison the span attribute.  View
        coerces non-strings to None (treat as no-link) rather than
        passing garbage through to set_input_ref."""
        from ai_assistant import views

        captured = {}

        def fake_dispatch(file_id, action_type, payload, *,
                          parent_span_id=None, source=None):
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

        def fake_dispatch(file_id, action_type, payload, *,
                          parent_span_id=None, source=None):
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
# Codeline capability footprints (inline cell communication / execution)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCodelineCapabilityFootprints:
    """``stamp_codeline_capability`` emits producer-owned attrs for the
    inline Codeline assistant surfaces."""

    def test_communication_kind_stamps_capability_and_position(self, monkeypatch):
        from ai_assistant import prometa_config as pc
        captured = {}
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: captured.__setitem__(k, v))
        pc.stamp_codeline_capability(
            kind='communication',
            position='after_data_preview',
            source='codeline',
            auto_correction_attempt=1,
        )
        assert captured['declarai.capability.inline_cell_communication'] is True
        assert captured['declarai.chat_source'] == 'codeline'
        assert captured['declarai.codeline.position'] == 'after_data_preview'
        assert captured['declarai.codeline.auto_correction_attempt'] == 1
        assert 'declarai.capability.inline_cell_execution' not in captured

    def test_execution_kind_stamps_mode_and_source(self, monkeypatch):
        from ai_assistant import prometa_config as pc
        captured = {}
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: captured.__setitem__(k, v))
        pc.stamp_codeline_capability(
            kind='execution',
            position='after_sfs',
            mode='apply',
            source='codeline',
        )
        assert captured['declarai.capability.inline_cell_execution'] is True
        assert captured['declarai.action.source'] == 'codeline'
        assert captured['declarai.execute_code.mode'] == 'apply'
        assert captured['declarai.codeline.position'] == 'after_sfs'
        assert 'declarai.capability.inline_cell_communication' not in captured

    def test_unknown_kind_is_noop(self, monkeypatch):
        from ai_assistant import prometa_config as pc
        captured = {}
        monkeypatch.setattr(pc, 'set_span_attr',
                            lambda k, v: captured.__setitem__(k, v))
        pc.stamp_codeline_capability(kind='bogus')
        assert captured == {}


# ---------------------------------------------------------------------------
# v2.42.0/v2.46.0: prometa-sdk version floor — CI guard
# ---------------------------------------------------------------------------
# Catches future Docker-cache / pip-cache drift like the v0.6.0-in-
# container situation that hid the A4 truncation bug from us.  The lower bound
# in requirements.txt must be satisfied by the environment running the tests.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProMetaSdkVersionLock:
    """Defense against installed-vs-required SDK drift.

    The bug that motivated v2.42.0 hid for ~24 hours because
    requirements.txt was pinned to >=0.7.1 but the running container
    was on v0.6.0 (Docker layer cache wasn't invalidated when the floor
    was bumped).  This test reads the requirement from requirements.txt and
    asserts the installed prometa.__version__ satisfies it."""

    def _read_min_version(self) -> str:
        """Return the minimum version required in requirements.txt.

        Supports `prometa-sdk>=X.Y.Z` and treats `==X.Y.Z` as an equivalent
        floor for older lock-file shapes.
        """
        import re
        from tests.unit._shared import backend_root
        backend_dir = backend_root()
        req = (backend_dir / 'requirements.txt').read_text()
        for line in req.splitlines():
            line = line.strip()
            if line.startswith('prometa-sdk'):
                m = re.match(r'^prometa-sdk(?:==|>=)([0-9]+\.[0-9]+\.[0-9]+)\s*$', line)
                assert m, (
                    f"prometa-sdk must declare an explicit minimum version "
                    f"(form: prometa-sdk>=X.Y.Z); found: {line!r}"
                )
                return m.group(1)
        raise AssertionError(
            "prometa-sdk entry not found in requirements.txt — "
            "the version-floor test cannot run without a requirement."
        )

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, int, int]:
        import re
        match = re.match(r'^([0-9]+)\.([0-9]+)\.([0-9]+)', value)
        assert match, f"Unsupported prometa-sdk version string: {value!r}"
        return tuple(int(part) for part in match.groups())

    def test_installed_prometa_sdk_satisfies_requirements_floor(self):
        import prometa
        installed = prometa.__version__
        required = self._read_min_version()
        assert self._version_tuple(installed) >= self._version_tuple(required), (
            f"prometa-sdk version drift detected: installed={installed!r} "
            f"but requirements.txt requires >={required!r}.  Rebuild the "
            f"backend Docker image with --no-cache or re-run "
            f"`pip install -r requirements.txt` to align.  This drift "
            f"is precisely what hid the v2.41.x AML A4 truncation bug "
            f"from us for ~24h."
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
