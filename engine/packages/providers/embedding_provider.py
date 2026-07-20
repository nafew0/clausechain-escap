from __future__ import annotations

import os

import httpx


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
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.last_usage: dict | None = None

    RETRY_BACKOFFS_S = (5.0, 20.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        import time as _time

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        body: dict = {"model": self.model, "input": texts}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        last_error: Exception | None = None
        for attempt in range(1 + len(self.RETRY_BACKOFFS_S)):
            try:
                response = httpx.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                    timeout=self.timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(f"retryable {response.status_code}",
                                                request=response.request, response=response)
                break
            except (httpx.HTTPStatusError, httpx.TransportError) as error:
                last_error = error
                if attempt < len(self.RETRY_BACKOFFS_S):
                    _time.sleep(self.RETRY_BACKOFFS_S[attempt])
                else:
                    raise last_error
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
    if provider in {"bge_m3", "bge-m3", "local"}:
        return BgeM3EmbeddingProvider(
            model=config.get("model", "BAAI/bge-m3"),
            dimensions=int(config.get("dimensions", 1024)),
        )
    if provider == "stub":
        return StubEmbeddingProvider(dimensions=int(config.get("dimensions", 1536)))
    raise ValueError(f"Unknown embedding provider: {provider!r}")
