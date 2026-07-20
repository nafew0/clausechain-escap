"""Hybrid broad-recall retrieval: graph full-text (sparse) + embedding cosine (dense).

Design rules (12-Jun, Dev Plan §0): BROAD RECALL, NOT top-k — evidence dropped
early can never be recovered downstream; the gates cut later. Union of both
legs, generous caps, per-indicator query packs generated from the rubric YAML.

Dense embeddings are precomputed once per corpus and cached on disk keyed by a
hash of (provision_id, text), so re-runs cost zero embedding calls.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import os as _os

# generous caps that bound LLM cost without behaving like top-k relevance cuts;
# the union cap is env-tunable and every truncation is recorded in run stats
# (Sol review, 19 Jul: no silent recall limits).
SPARSE_LIMIT_PER_QUERY = 40
DENSE_LIMIT_PER_QUERY = 40
DENSE_MIN_SIMILARITY = 0.25
UNION_CAP_PER_INDICATOR = int(_os.getenv("UNION_CAP_PER_INDICATOR", "400"))


def build_query_pack(indicator_id: str, indicator_cfg: dict) -> list[str]:
    """Turn a rubric-YAML indicator into a set of search queries (concept + statutory phrasings)."""
    queries: list[str] = []
    question = indicator_cfg.get("question")
    if question:
        queries.append(str(question))
    name = indicator_cfg.get("name")
    if name:
        queries.append(str(name))
    for cue in indicator_cfg.get("positive_cues", []) or []:
        queries.append(str(cue))
    hunt = indicator_cfg.get("hunt_in", []) or []
    queries.extend(str(h) for h in hunt)
    return [q for q in queries if q.strip()]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingCache:
    """Disk-cached corpus embeddings: embed each provision text at most once, ever."""

    def __init__(self, embedder, cache_path: str | Path = "data/cache/embeddings.json") -> None:
        self._embedder = embedder
        self._path = Path(cache_path)
        self._cache: dict[str, list[float]] = {}
        if self._path.is_file():
            self._cache = json.loads(self._path.read_text())

    @staticmethod
    def _key(provision_id: str, text: str) -> str:
        return f"{provision_id}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"

    MAX_CHARS = 20000   # ~5k tokens, well under the 8192-token embedding limit
    BATCH = 96

    @classmethod
    def _sanitize(cls, text: str) -> str:
        text = text.strip() or "(empty provision)"
        return text[: cls.MAX_CHARS]

    def ensure(self, items: list[tuple[str, str]]) -> None:
        """items = [(provision_id, text)]; embeds only the missing ones, in chunked batches."""
        missing = [(pid, text) for pid, text in items if self._key(pid, text) not in self._cache]
        if not missing:
            return
        for start in range(0, len(missing), self.BATCH):
            chunk = missing[start:start + self.BATCH]
            vectors = self._embedder.embed([self._sanitize(text) for _, text in chunk])
            for (pid, text), vec in zip(chunk, vectors):
                self._cache[self._key(pid, text)] = vec
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._cache))

    def vector(self, provision_id: str, text: str) -> list[float] | None:
        return self._cache.get(self._key(provision_id, text))

    @staticmethod
    def _query_key(query: str) -> str:
        return "__query__:" + hashlib.sha256(query.strip().encode()).hexdigest()

    def ensure_queries(self, queries: list[str]) -> None:
        """Persist query embeddings and request all missing queries in one call.

        Query packs are deterministic configuration data. Caching them is both
        cheaper and substantially faster than making one HTTP request per cue on
        every economy/pillar run.
        """
        unique = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
        missing = [query for query in unique if self._query_key(query) not in self._cache]
        if not missing:
            return
        vectors = self._embedder.embed([self._sanitize(query) for query in missing])
        for query, vector in zip(missing, vectors, strict=True):
            self._cache[self._query_key(query)] = vector
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._cache))

    def embed_query(self, query: str) -> list[float]:
        self.ensure_queries([query])
        return self._cache[self._query_key(query)]

    def matrix(self, corpus: list[dict]):
        """Normalized numpy matrix over the corpus vectors (built once, reused per run)."""
        import numpy as np

        key = (len(corpus), corpus[0]["provision_id"] if corpus else "",
               corpus[-1]["provision_id"] if corpus else "")
        if getattr(self, "_matrix_key", None) == key:
            return self._matrix, self._matrix_rows
        rows, vectors = [], []
        for row in corpus:
            vec = self.vector(row["provision_id"], row["text"])
            if vec is not None:
                rows.append(row)
                vectors.append(vec)
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms
        self._matrix_rows = rows
        self._matrix_key = key
        return self._matrix, self._matrix_rows

    def dense_top(self, query: str, corpus: list[dict], limit: int, min_sim: float):
        """[(similarity, corpus_row)] for one query — vectorized cosine."""
        import numpy as np

        matrix, rows = self.matrix(corpus)
        if not len(rows):
            return []
        qvec = np.asarray(self.embed_query(query), dtype=np.float32)
        qnorm = np.linalg.norm(qvec) or 1.0
        sims = matrix @ (qvec / qnorm)
        order = np.argsort(-sims)[:limit]
        return [(float(sims[i]), rows[i]) for i in order if sims[i] >= min_sim]


@dataclass
class Candidate:
    provision_id: str
    text: str
    props: dict
    sparse_score: float = 0.0
    dense_score: float = 0.0
    matched_queries: list[str] = field(default_factory=list)

    @property
    def combined(self) -> float:
        return self.dense_score + min(self.sparse_score, 10.0) / 10.0


def retrieve_for_indicator(
    store,
    cache: EmbeddingCache,
    corpus: list[dict],
    indicator_id: str,
    indicator_cfg: dict,
    economy: str,
    caps_out: list | None = None,
) -> list[Candidate]:
    """Union of sparse (graph full-text) and dense (cosine) hits for one indicator.

    `corpus` = [{'provision_id', 'text', 'props'}] — the full loaded corpus for
    the economy (dense leg scans it all; it is small by design).
    """
    # Source-type scoping BEFORE any ranking or cap (Sol review #5, 19 Jul): an
    # indicator sees only its allowed evidence classes, so excluded classes can
    # never consume union-cap capacity. Rubric YAML declares
    # `allowed_source_types: [treaty]` (P6-I5); absent -> all domestic classes,
    # never treaties.
    allowed = indicator_cfg.get("allowed_source_types")
    allowed = {str(s).strip().lower() for s in allowed} if allowed else None

    def _source_ok(props: dict | None) -> bool:
        props = props or {}
        stype = (props.get("source_type")
                 or (props.get("metadata") or {}).get("source_type") or "act")
        return stype in allowed if allowed is not None else stype != "treaty"

    corpus = [row for row in corpus if _source_ok(row.get("props"))]
    if not corpus:
        # No unit of an allowed source class exists for this economy (e.g. AU
        # P6-I5 while every treaty acquisition is blocked): zero candidates —
        # the absence path + ACQUISITION_UNRESOLVED coverage take over.
        return []
    queries = build_query_pack(indicator_id, indicator_cfg)
    by_id: dict[str, Candidate] = {}

    # Deterministic exact-phrase/defined-term leg.  This is deliberately
    # independent of FTS ranking and embeddings so statutory terms cannot be
    # lost through tokenization or semantic drift.
    exact_phrases = [str(v).strip() for v in (
        list(indicator_cfg.get("positive_cues", []) or [])
        + list(indicator_cfg.get("defined_terms", []) or [])) if str(v).strip()]
    for phrase in exact_phrases:
        needle = phrase.casefold()
        for row in corpus:
            if needle not in row["text"].casefold():
                continue
            cand = by_id.setdefault(row["provision_id"], Candidate(
                row["provision_id"], row["text"], row.get("props", {})))
            cand.sparse_score = max(cand.sparse_score, 10.0)
            cand.matched_queries.append(f"exact-phrase:{phrase}")

    # sparse leg — graph-backed full-text (FTS5 / Lucene), one query at a time
    for query in queries:
        for hit in store.search_provisions(query, economy=economy, limit=SPARSE_LIMIT_PER_QUERY):
            # The FTS index intentionally retains historical/ineligible nodes for
            # audit, but the evidence retriever must never surface them.
            if not hit.get("props", {}).get("evidence_eligible", False):
                continue
            if hit.get("props", {}).get("legal_status") != "in_force":
                continue
            if not _source_ok(hit.get("props")):
                continue
            cand = by_id.setdefault(
                hit["provision_id"],
                Candidate(hit["provision_id"], hit["text"], hit.get("props", {})),
            )
            cand.sparse_score = max(cand.sparse_score, float(hit.get("score", 0.0)))
            cand.matched_queries.append(query)

    # dense leg — vectorized cosine over the cached corpus matrix (numpy, A3)
    cache.ensure([(c["provision_id"], c["text"]) for c in corpus])
    if hasattr(cache, "ensure_queries"):
        cache.ensure_queries(queries)
    for query in queries:
        for sim, row in cache.dense_top(query, corpus, DENSE_LIMIT_PER_QUERY,
                                        DENSE_MIN_SIMILARITY):
            cand = by_id.setdefault(
                row["provision_id"],
                Candidate(row["provision_id"], row["text"], row.get("props", {})),
            )
            cand.dense_score = max(cand.dense_score, sim)
            cand.matched_queries.append(query)

    candidates = sorted(by_id.values(), key=lambda c: c.combined, reverse=True)
    if len(candidates) > UNION_CAP_PER_INDICATOR and caps_out is not None:
        caps_out.append({"stage": "retrieval_union", "limit": UNION_CAP_PER_INDICATOR,
                         "input_count": len(candidates)})
    return candidates[:UNION_CAP_PER_INDICATOR]


def load_corpus(store, economy: str) -> list[dict]:
    """Pull every provision for an economy out of the graph store (for the dense leg)."""
    if hasattr(store, "_connect") and hasattr(store, "db_path"):  # SqliteGraphStore
        rows = store._connect().execute(
            "SELECT provision_id, economy, text FROM provisions_fts WHERE economy = ?",
            (economy,),
        ).fetchall()
        out = []
        for provision_id, _econ, text in rows:
            node = store._connect().execute(
                "SELECT props FROM nodes WHERE id = ?", (provision_id,)
            ).fetchone()
            props = json.loads(node[0]) if node else {}
            if (not props.get("evidence_eligible", False)
                    or props.get("legal_status") != "in_force"):
                continue
            out.append({"provision_id": provision_id, "text": text, "props": props})
        return out
    # Neo4j
    with store._connect().session() as session:
        records = session.run(
            "MATCH (p:Provision) WHERE p.economy = $economy RETURN p", economy=economy
        )
        out = []
        for record in records:
            node = record["p"]
            props = dict(node)
            try:
                props["metadata"] = json.loads(props.get("metadata_json") or "{}")
                props["status_evidence"] = json.loads(
                    props.get("status_evidence_json") or "null")
            except json.JSONDecodeError:
                props["metadata"] = {}
            if (props.get("evidence_eligible", False)
                    and props.get("legal_status") == "in_force"):
                out.append({"provision_id": node.get("id"),
                            "text": node.get("text", ""), "props": props})
        return out
