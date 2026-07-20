from __future__ import annotations

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


def test_profiles_load_and_expand() -> None:
    profile = get_profile("hybrid_accuracy")  # Path B default
    assert profile["bulk"]["primary"] == "openai:gpt-5.4-nano"
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


def test_resolve_llm_and_embedding_construct_offline() -> None:
    llm = resolve_llm("hybrid_accuracy", tier="high_reasoning")
    assert isinstance(llm, FallbackLLM)
    assert llm.primary.model == "gpt-5.4-nano"
    escalation = resolve_llm("hybrid_accuracy", tier="legal_escalation")
    assert escalation.primary.model == "gpt-5.4-mini"
    # Path B: cloud OpenAI embeddings (construction is offline-safe — no network until embed())
    embedder = resolve_embedding("hybrid_accuracy")
    assert embedder.model == "text-embedding-3-small"
    assert embedder.dimensions == 1536
    # Path A stays local BGE-M3, constructed without loading the model
    fallback_embedder = resolve_embedding("local_fallback")
    assert fallback_embedder.model == "BAAI/bge-m3"
