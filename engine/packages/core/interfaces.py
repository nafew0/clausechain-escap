from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from packages.core.schemas import ExtractedPage, RuleUnit


class LLMProvider(Protocol):
    def complete(self, prompt: str, schema: type[BaseModel], *,
                 prompt_cache_key: str | None = None) -> BaseModel: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OCREngine(Protocol):
    def extract(self, file_path: str) -> list[ExtractedPage]: ...


class GraphStore(Protocol):
    def upsert_rule_unit(self, rule_unit: RuleUnit) -> str: ...

    def search_provisions(
        self, query: str, economy: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Sparse full-text search over Provision nodes (FTS5 in SQLite, Lucene in Neo4j).

        Returns [{'provision_id', 'text', 'score', 'props'}], best first. This is
        the sparse leg of hybrid retrieval — a GraphStore capability, not a
        separate system, so it swaps with the backend.
        """
        ...
