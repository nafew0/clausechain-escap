from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from packages.providers.llm_providers import (
    FallbackLLM,
    GeminiChatProvider,
    OllamaProvider,
    OpenAIChatProvider,
    build_llm,
)
from packages.providers.model_router import get_profile, resolve_embedding, resolve_llm


class Ping(BaseModel):
    ok: bool


class FakeLLM:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        if self.fail:
            raise RuntimeError("primary down")
        return schema(ok=True)


def test_profiles_load_and_expand(monkeypatch) -> None:
    monkeypatch.delenv("HYBRID_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("HYBRID_LLM_MODEL", raising=False)
    profile = get_profile("hybrid_accuracy")  # Path B default
    assert profile["bulk"]["primary"] == "openai:gpt-6-luna"  # OpenAI API direct (30 Sep)
    # Path B embeddings = cloud OpenAI (decided 4 Jul); EMBEDDING_PROVIDER can override
    assert profile["embedding"]["provider"] in {"openai", "bge_m3"}
    assert profile["embedding"]["model"] in {"text-embedding-3-small", "BAAI/bge-m3"}
    assert profile["graph"]["provider"] in {"sqlite", "neo4j"}
    # Path A fallback exists and is key-free (ollama + sqlite + local bge_m3)
    fallback = get_profile("local_fallback")
    assert fallback["bulk"]["primary"].startswith("ollama:")
    assert fallback["graph"]["provider"] == "sqlite"
    assert fallback["embedding"]["provider"] == "bge_m3"


def test_build_llm_parses_specs() -> None:
    assert isinstance(build_llm("openai:gpt-5.4-nano"), OpenAIChatProvider)
    assert isinstance(build_llm("google:gemini-3-flash-preview"), GeminiChatProvider)
    assert isinstance(build_llm("ollama:qwen2.5:7b"), OllamaProvider)
    with pytest.raises(ValueError):
        build_llm("mystery-model")


def test_fallback_used_when_primary_fails() -> None:
    primary, fallback = FakeLLM(fail=True), FakeLLM()
    result = FallbackLLM(primary, fallback).complete("ping", Ping)
    assert result.ok is True
    assert primary.calls == 1 and fallback.calls == 1


def test_fallback_raises_without_fallback() -> None:
    with pytest.raises(RuntimeError):
        FallbackLLM(FakeLLM(fail=True), None).complete("ping", Ping)


def test_resolve_llm_and_embedding_construct_offline(monkeypatch) -> None:
    monkeypatch.delenv("HYBRID_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("HYBRID_LLM_MODEL", raising=False)
    llm = resolve_llm("hybrid_accuracy", tier="high_reasoning")
    assert isinstance(llm, FallbackLLM)
    assert llm.primary.model == "gpt-6-luna"
    assert llm.primary.base_url == "https://api.openai.com/v1"
    escalation = resolve_llm("hybrid_accuracy", tier="legal_escalation")
    assert escalation.primary.model == "gpt-6-luna"  # Luna-only hybrid (29 Sep)
    # Path B: cloud OpenAI embeddings (construction is offline-safe — no network until embed())
    embedder = resolve_embedding("hybrid_accuracy")
    assert embedder.model == "text-embedding-3-small"
    assert embedder.dimensions == 1536
    # Path A stays local BGE-M3, constructed without loading the model
    fallback_embedder = resolve_embedding("local_fallback")
    assert fallback_embedder.model == "BAAI/bge-m3"


def test_engine_a_can_route_through_openrouter_by_setting(monkeypatch) -> None:
    monkeypatch.setenv("HYBRID_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("HYBRID_LLM_MODEL", "openai/gpt-6-luna")
    llm = resolve_llm("hybrid_accuracy", tier="bulk")
    assert llm.primary.model == "openai/gpt-6-luna"
    assert llm.primary.base_url == "https://openrouter.ai/api/v1"
    assert llm.primary.api_key_env == "OPENROUTER_API_KEY"


def test_temperature_dropped_once_the_model_rejects_it(monkeypatch) -> None:
    import httpx

    from packages.providers import http_client
    from packages.providers.llm_providers import OpenAIChatProvider

    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {
                "message": "Unsupported value: 'temperature' does not support 0 with this model.",
                "param": "temperature", "code": "unsupported_value"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 3}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(http_client, "client", lambda base_url, timeout: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = OpenAIChatProvider("gpt-6-luna")
    assert llm._call("ping") == '{"ok": true}'
    assert llm._call("ping again") == '{"ok": true}'
    assert ["temperature" in body for body in bodies] == [True, False, False]


def test_both_names_of_text_embedding_3_small_share_the_newest_cache(tmp_path, monkeypatch) -> None:
    import os
    from types import SimpleNamespace

    from packages.retrieval.hybrid import embedding_cache_path

    monkeypatch.chdir(tmp_path)
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True)
    direct, routed = SimpleNamespace(model="text-embedding-3-small"), SimpleNamespace(model="openai/text-embedding-3-small")
    assert embedding_cache_path("RU", direct) == "data/cache/embeddings_ru.json"
    (cache / "embeddings_ru__openai-text-embedding-3-small.json").write_text("{}")
    assert embedding_cache_path("RU", direct) == "data/cache/embeddings_ru__openai-text-embedding-3-small.json"
    (cache / "embeddings_ru.json").write_text("{}")
    os.utime(cache / "embeddings_ru.json", (1, 1))
    assert embedding_cache_path("RU", routed) == "data/cache/embeddings_ru__openai-text-embedding-3-small.json"
    assert embedding_cache_path("RU", SimpleNamespace(model="bge-m3")) == "data/cache/embeddings_ru__bge-m3.json"
