from __future__ import annotations

import os

import httpx

from packages.providers import http_client


class StubEmbeddingProvider:
    """Deterministic P0 embedding stub with no network calls."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimensions for _ in texts]


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 60.0,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.last_usage: dict | None = None

    RETRY_BACKOFFS_S = (5.0, 20.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        import time as _time

        api_key = os.getenv(self.api_key_env)
        # OpenAI proper needs a key; a self-hosted server may run without auth.
        if not api_key and self.base_url == "https://api.openai.com/v1":
            raise RuntimeError(f"{self.api_key_env} is not set")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # Token-safety truncation: Thai/CJK tokenize near 1 token/char, so a long
        # unit can blow the 8192-token embedding limit (400 Bad Request — hit on
        # the Thai corpus, 1 Aug). 6000 chars stays safe in every script; only
        # over-limit texts are cut, so existing cached embeddings stay valid.
        max_chars = int(os.getenv("EMBED_MAX_CHARS", "6000"))
        texts = [t if len(t) <= max_chars else t[:max_chars] for t in texts]
        body: dict = {"model": self.model, "input": texts}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        connect_failures = other_failures = 0
        while True:
            try:
                response = http_client.client(self.base_url, self.timeout).post(
                    f"{self.base_url}/embeddings",
                    headers=headers,
                    json=body,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(f"retryable {response.status_code}",
                                                request=response.request, response=response)
                break
            except http_client.CONNECT_ERRORS:
                # Never reached the server: safe to resend, on the longer schedule.
                if connect_failures >= len(http_client.CONNECT_BACKOFFS_S):
                    raise
                _time.sleep(http_client.CONNECT_BACKOFFS_S[connect_failures])
                connect_failures += 1
            except (httpx.HTTPStatusError, httpx.TransportError):
                if other_failures >= len(self.RETRY_BACKOFFS_S):
                    raise
                _time.sleep(self.RETRY_BACKOFFS_S[other_failures])
                other_failures += 1
        response.raise_for_status()
        payload = response.json()
        self.last_usage = payload.get("usage")
        if self.last_usage:
            from packages.providers import cost

            cost.record(self.model, self.last_usage.get("prompt_tokens", 0))
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]


class BgeM3EmbeddingProvider:
    """Local multilingual embeddings (BAAI/bge-m3) via sentence-transformers.

    Lazy: the heavy model loads on first embed(), so construction is offline-safe.
    """

    def __init__(self, model: str = "BAAI/bge-m3", dimensions: int = 1024) -> None:
        self.model = model
        self.dimensions = dimensions
        self._st = None

    def _load(self):
        if self._st is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:  # pragma: no cover
                raise RuntimeError(
                    "BGE-M3 needs sentence-transformers — run: uv sync --group embed"
                ) from error
            self._st = SentenceTransformer(self.model)
        return self._st

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        return [v.tolist() for v in model.encode(texts, normalize_embeddings=True)]


def build_embedding(config: dict):
    """Build an embedding provider from a models.yaml `embedding:` block."""
    provider = (config.get("provider") or "stub").strip().lower()
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            model=config.get("model", "text-embedding-3-small"),
            dimensions=config.get("dimensions"),
        )
    if provider in {"openai_compatible", "openweights"}:
        # Open-weights embedding model on a self-hosted OpenAI-compatible server.
        base_url = config.get("base_url") or os.getenv("LOCALAI_EMBED_ENDPOINT", "")
        if not base_url:
            raise RuntimeError("LOCALAI_EMBED_ENDPOINT is not set")
        return OpenAIEmbeddingProvider(
            model=config.get("model") or os.getenv("LOCALAI_EMBED_MODEL", "bge-m3"),
            dimensions=None,
            # Same key as the LLM server unless a separate one is configured.
            api_key_env=("LOCALAI_EMBED_API_KEY" if os.getenv("LOCALAI_EMBED_API_KEY")
                         else "LOCALAI_API_KEY"),
            base_url=base_url,
        )
    if provider in {"bge_m3", "bge-m3", "local"}:
        return BgeM3EmbeddingProvider(
            model=config.get("model", "BAAI/bge-m3"),
            dimensions=int(config.get("dimensions", 1024)),
        )
    if provider == "stub":
        return StubEmbeddingProvider(dimensions=int(config.get("dimensions", 1536)))
    raise ValueError(f"Unknown embedding provider: {provider!r}")
