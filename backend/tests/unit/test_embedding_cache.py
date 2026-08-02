"""Embedding Redis cache + OpenAI embeddings SDK instrumentation smoke tests."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestOpenAIEmbeddingsInstrumentation:
    def test_openai_install_patches_embeddings_create(self):
        """SDK #80: install() must expose embeddings request attrs (git pin)."""
        from prometa.integrations import openai as prometa_openai

        assert hasattr(prometa_openai, "_embeddings_request_attrs"), (
            "prometa-sdk missing embeddings instrumentation. Install the "
            "git pin from requirements.txt (SDK #80) and rebuild the "
            "backend image if needed."
        )

        # Force re-install path if a prior test already installed.
        if getattr(prometa_openai, "_INSTALLED", False):
            prometa_openai._INSTALLED = False  # type: ignore[attr-defined]

        ok = prometa_openai.install()
        assert ok is True

        attrs = prometa_openai._embeddings_request_attrs({
            "model": "text-embedding-3-small",
            "input": ["hello", "world"],
        })
        assert attrs.get("gen_ai.operation.name") == "embeddings"
        assert attrs.get("gen_ai.request.model") == "text-embedding-3-small"
        assert attrs.get("gen_ai.request.embedding.input_count") == 2


@pytest.mark.unit
class TestEmbeddingRedisCache:
    def test_cache_hit_skips_openai(self, monkeypatch):
        from ai_assistant.rag import embeddings as emb

        model = "text-embedding-3-small"
        text = "What does PSI mean?"
        key = emb._embedding_cache_key(model, text)
        vector = [0.1, 0.2, 0.3]

        fake_redis = MagicMock()
        fake_redis.get.return_value = json.dumps(vector)

        monkeypatch.setattr(emb, "_get_redis", lambda: fake_redis)
        monkeypatch.setattr(emb, "_api_key", lambda: "sk-test")
        monkeypatch.setattr(emb, "_embedding_model", lambda: model)

        openai_called = {"n": 0}

        class _BoomClient:
            @property
            def embeddings(self):
                openai_called["n"] += 1
                raise AssertionError("OpenAI should not be called on cache hit")

        monkeypatch.setattr(
            "openai.OpenAI", lambda api_key=None: _BoomClient()
        )

        out = emb.embed_texts([text], model=model)
        assert out == [vector]
        assert openai_called["n"] == 0
        fake_redis.get.assert_called_with(key)

    def test_cache_miss_calls_openai_and_writes_back(self, monkeypatch):
        from ai_assistant.rag import embeddings as emb

        model = "text-embedding-3-small"
        text = "Explain SFS"
        vector = [0.5, 0.6]

        fake_redis = MagicMock()
        fake_redis.get.return_value = None

        monkeypatch.setattr(emb, "_get_redis", lambda: fake_redis)
        monkeypatch.setattr(emb, "_api_key", lambda: "sk-test")
        monkeypatch.setattr(emb, "_embedding_model", lambda: model)
        monkeypatch.setattr(emb, "_cache_ttl", lambda: 123)

        class _Resp:
            data = [SimpleNamespace(index=0, embedding=vector)]

        class _Embeddings:
            def create(self, model, input):  # noqa: A002
                assert model == "text-embedding-3-small"
                assert input == [text]
                return _Resp()

        class _Client:
            embeddings = _Embeddings()

        monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _Client())

        out = emb.embed_texts([text], model=model)
        assert out == [vector]
        fake_redis.setex.assert_called()
        args, _kwargs = fake_redis.setex.call_args
        assert args[0] == emb._embedding_cache_key(model, text)
        assert args[1] == 123
        assert json.loads(args[2]) == vector

    def test_cache_lookup_kind_embedding_used(self, monkeypatch):
        from ai_assistant.rag import embeddings as emb
        from contextlib import contextmanager

        calls: list = []

        class _Handle:
            def hit(self, **kwargs):
                calls.append(("hit", kwargs))

            def miss(self):
                calls.append(("miss", {}))

        @contextmanager
        def _recording(kind, *, key):
            calls.append(("enter", kind, key))
            try:
                yield _Handle()
            finally:
                calls.append(("exit", kind, key))

        monkeypatch.setattr(emb, "cache_lookup", _recording)
        monkeypatch.setattr(emb, "_get_redis", lambda: None)
        monkeypatch.setattr(emb, "_api_key", lambda: "sk-test")
        monkeypatch.setattr(emb, "_embedding_model", lambda: "text-embedding-3-small")

        class _Resp:
            data = [SimpleNamespace(index=0, embedding=[1.0])]

        class _Client:
            class embeddings:
                @staticmethod
                def create(model, input):  # noqa: A002
                    return _Resp()

        monkeypatch.setattr("openai.OpenAI", lambda api_key=None: _Client())

        emb.embed_texts(["hello"])
        enters = [c for c in calls if c[0] == "enter"]
        assert enters
        assert enters[0][1] == "embedding"
        assert enters[0][2].startswith("ai:embedding:")
        assert any(c[0] == "miss" for c in calls)

    def test_embed_texts_source_uses_cache_lookup_embedding(self):
        import inspect
        from ai_assistant.rag import embeddings as emb

        source = inspect.getsource(emb)
        assert "cache_lookup" in source
        assert "ai:embedding:" in inspect.getsource(emb._embedding_cache_key)
        assert "embedding" in inspect.getsource(emb._cache_get_vector)
