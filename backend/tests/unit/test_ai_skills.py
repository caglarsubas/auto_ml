"""Unit tests - AI assistant skills and knowledge bank.

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from tests.unit._shared import (
    _run_chat_workflow,
    _text_response,
)


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
        from ai_assistant import prometa_config
        captured = {}

        def fake_set(key, value):
            captured[key] = value

        monkeypatch.setattr(te, 'set_span_attr', fake_set)
        monkeypatch.setattr(prometa_config, 'set_span_attr', fake_set)
        result = te._load_skill_traced('feature-engineering')
        assert 'BEGIN SKILL CONTENT' in result
        assert captured.get('mcp.server.name') == 'declarai'
        assert captured.get('mcp.tool.name') == 'declarai.invoke_skill'
        assert captured.get('gen_ai.tool.name') == 'skill-invoke'
        assert captured.get('prometa.tool_name') == 'skill-invoke'
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

@pytest.mark.unit
class TestKnowledgeBankRetrieval:
    """Knowledge-bank retrieval returns cited snippets from versioned docs."""

    def test_retrieves_glossary_context_for_metric_question(self, monkeypatch):
        monkeypatch.setenv('RAG_MODE', 'lexical')
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical('What does PSI mean?')

        assert out['results']
        assert '[KB1]' in out['context']
        joined = '\n'.join(r['snippet'] for r in out['results'])
        assert 'Population Stability Index' in joined
        assert any(r['source'] == 'terminology-glossary.md'
                   for r in out['results'])

    def test_retrieves_assistant_guide_for_usage_question(self, monkeypatch):
        monkeypatch.setenv('RAG_MODE', 'lexical')
        from ai_assistant.knowledge_bank import retrieve_knowledge_context_lexical

        out = retrieve_knowledge_context_lexical(
            'How should I use the assistant actions?'
        )

        assert out['results']
        sources = {r['source'] for r in out['results']}
        assert 'assistant-usage-and-action-guide.md' in sources

    def test_falls_back_to_lexical_without_api_key(self, monkeypatch):
        from django.conf import settings

        monkeypatch.delenv('OPENAI_API_KEY', raising=False)
        monkeypatch.setattr(settings, 'OPENAI_API_KEY', '')
        monkeypatch.setattr(settings, 'RAG_MODE', 'hybrid')

        from ai_assistant.knowledge_bank import retrieve_knowledge_context

        out = retrieve_knowledge_context('What does PSI mean?')
        assert out['results']
        assert any(r['source'] == 'terminology-glossary.md'
                   for r in out['results'])

    def test_hybrid_retrieval_uses_vector_hits(self, monkeypatch):
        from ai_assistant.knowledge_bank import (
            load_knowledge_chunks,
            retrieve_knowledge_context_lexical,
        )

        chunks = load_knowledge_chunks()
        glossary = next(
            c for c in chunks if c.source == 'terminology-glossary.md'
            and 'psi' in (c.heading + c.content).lower()
        )

        monkeypatch.setattr(
            'ai_assistant.rag.retriever.embeddings_available', lambda: True
        )
        monkeypatch.setattr(
            'ai_assistant.rag.retriever.ensure_index',
            lambda **kwargs: {'rebuilt': False, 'fingerprint': 'x', 'chunk_count': 1},
        )
        monkeypatch.setattr(
            'ai_assistant.rag.retriever.embed_query',
            lambda query: [0.1, 0.2, 0.3],
        )
        monkeypatch.setattr(
            'ai_assistant.rag.retriever.search_index',
            lambda query_embedding, n_results=8, persist_dir=None: [{
                'chunk_id': glossary.chunk_id,
                'source': glossary.source,
                'title': glossary.title,
                'heading': glossary.heading,
                'content': glossary.content,
                'score': 0.92,
            }],
        )
        from django.conf import settings
        monkeypatch.setattr(settings, 'RAG_MODE', 'hybrid', raising=False)
        monkeypatch.setattr(settings, 'OPENAI_API_KEY', 'sk-test', raising=False)

        from ai_assistant.rag.retriever import retrieve_vector_context

        out = retrieve_vector_context(
            'What does PSI mean?',
            lexical_fallback=retrieve_knowledge_context_lexical,
        )
        assert out['results']
        assert out['results'][0]['chunk_id'] == glossary.chunk_id
        assert '[KB1]' in out['context']
        assert 'Population Stability Index' in out['context']


@pytest.mark.unit
class TestKnowledgeBankIndexer:
    """Fingerprint-driven Chroma index rebuild."""

    def test_corpus_fingerprint_changes_with_content(self, tmp_path):
        from ai_assistant.rag.indexer import corpus_fingerprint

        docs = tmp_path / 'kb'
        docs.mkdir()
        (docs / 'a.md').write_text('# A\n\nhello\n', encoding='utf-8')
        first = corpus_fingerprint(docs)
        (docs / 'a.md').write_text('# A\n\nhello world\n', encoding='utf-8')
        second = corpus_fingerprint(docs)
        assert first != second

    def test_ensure_index_rebuilds_when_fingerprint_stale(self, tmp_path, monkeypatch):
        docs = tmp_path / 'kb'
        docs.mkdir()
        (docs / 'glossary.md').write_text(
            '# Glossary\n\n## PSI\n\nPopulation Stability Index.\n',
            encoding='utf-8',
        )
        persist = tmp_path / 'chroma'

        def fake_embed(texts, **kwargs):
            # Deterministic low-dim vectors for Chroma upsert/query.
            vectors = []
            for idx, text in enumerate(texts):
                vectors.append([float(idx + 1), float(len(text) % 7), 0.5])
            return vectors

        monkeypatch.setattr(
            'ai_assistant.rag.indexer.embed_texts', fake_embed
        )
        monkeypatch.setattr(
            'ai_assistant.rag.embeddings.embeddings_available',
            lambda: True,
        )

        from ai_assistant.rag.indexer import ensure_index
        from ai_assistant.rag.chroma_store import get_collection, stored_fingerprint

        first = ensure_index(persist_dir=persist, knowledge_dir=docs)
        assert first['rebuilt'] is True
        assert first['chunk_count'] >= 1

        second = ensure_index(persist_dir=persist, knowledge_dir=docs)
        assert second['rebuilt'] is False

        (docs / 'glossary.md').write_text(
            '# Glossary\n\n## PSI\n\nPopulation Stability Index updated.\n',
            encoding='utf-8',
        )
        third = ensure_index(persist_dir=persist, knowledge_dir=docs)
        assert third['rebuilt'] is True
        collection = get_collection(persist, reset=False)
        assert stored_fingerprint(collection) == third['fingerprint']


@pytest.mark.unit
class TestKnowledgeBankRagWorkflow:
    """When intent includes R, _chat_workflow retrieves and injects docs."""

    def test_rag_intent_injects_knowledge_bank_context(self, monkeypatch):
        from django.conf import settings

        # Force lexical fallback so the workflow test never calls OpenAI embeddings.
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)
        monkeypatch.setattr(settings, 'OPENAI_API_KEY', '')
        monkeypatch.setattr(settings, 'RAG_MODE', 'hybrid')

        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            user_message='What does PSI mean in the DeclarAI platform?',
            call_llm=lambda idx, messages, tools: _text_response('PSI means stability.'),
        )

        assert out['result']['intent_labels'] == ['A', 'R']
        assert out['result']['rag_sources']
        joined = '\n'.join(m.get('content') or ''
                           for m in out['llm_calls'][0]['messages'])
        assert 'Knowledge bank context retrieved for this turn.' in joined
        assert '[KB1]' in joined
        assert 'Population Stability Index' in joined

    def test_non_rag_turn_does_not_inject_knowledge_bank_context(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            user_message='Set max_features to 20 and then start SFS.',
            call_llm=lambda idx, messages, tools: _text_response('Prepared.'),
        )

        assert out['result']['intent_labels'] == ['D', 'E']
        assert 'rag_sources' not in out['result']
        joined = '\n'.join(m.get('content') or ''
                           for m in out['llm_calls'][0]['messages'])
        assert 'Knowledge bank context retrieved for this turn.' not in joined

@pytest.mark.unit
class TestSkillAutoInjectionProviderAware:
    """The FE skill playbook is pre-loaded into the system prompt only for
    cloud models; engine models skip it (it overflows their small context
    window) and pull it on demand via the invoke_skill tool."""

    def test_engine_model_does_not_preload_skill_body(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='engine',
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        # The auto-router still matched (loader would be reachable), but the
        # body must NOT have been loaded or injected for an engine model.
        assert out['skill_calls'] == []
        joined = ' '.join(m.get('content') or '' for m in out['llm_calls'][0]['messages'])
        assert 'SKILL_PLAYBOOK_BODY' not in joined
        assert 'playbook has been pre-loaded' not in joined

    def test_cloud_model_preloads_skill_body(self, monkeypatch):
        out = _run_chat_workflow(
            monkeypatch, provider='openai',
            call_llm=lambda idx, messages, tools: _text_response('done'),
        )
        assert out['skill_calls'] == ['feature-engineering']
        joined = ' '.join(m.get('content') or '' for m in out['llm_calls'][0]['messages'])
        assert 'SKILL_PLAYBOOK_BODY' in joined
        assert 'playbook has been pre-loaded' in joined

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
        from ai_assistant import prometa_config
        captured = {}

        def fake_set(key, value):
            captured[key] = value

        monkeypatch.setattr(te, 'set_span_attr', fake_set)
        monkeypatch.setattr(prometa_config, 'set_span_attr', fake_set)
        result = te._load_skill_file_traced(
            'feature-engineering',
            'references/feature_engineering_best_practices.md',
        )
        assert 'BEGIN FILE CONTENT' in result
        assert captured.get('mcp.server.name') == 'declarai'
        assert captured.get('mcp.tool.name') == 'declarai.get_skill_file'
        assert captured.get('gen_ai.tool.name') == 'skill-file-read'
        assert captured.get('prometa.tool_name') == 'skill-file-read'
        assert captured.get('declarai.skill.name') == 'feature-engineering'
        assert captured.get('declarai.skill.file_path') == \
            'references/feature_engineering_best_practices.md'
        assert captured.get('declarai.skill.file_found') is True
        assert isinstance(captured.get('declarai.skill.file_chars'), int)
        assert captured['declarai.skill.file_chars'] > 100
