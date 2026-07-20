from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from packages.core.schemas import (MappedFinding, PageArtifact, ReviewDecision, RuleUnit,
                                   SourceArtifact, TextSpan)

GRAPH_SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_metadata (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
    id    TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    props TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS edges (
    src   TEXT NOT NULL,
    rel   TEXT NOT NULL,
    dst   TEXT NOT NULL,
    props TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (src, rel, dst)
);
CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(rel);
CREATE VIRTUAL TABLE IF NOT EXISTS provisions_fts USING fts5(
    provision_id UNINDEXED, economy UNINDEXED, text
);
CREATE TABLE IF NOT EXISTS source_artifacts (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS page_artifacts (
    id TEXT PRIMARY KEY, source_artifact_id TEXT NOT NULL, page_number INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS text_spans (
    id TEXT PRIMARY KEY, source_artifact_id TEXT NOT NULL, page_number INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_leads (
    id TEXT PRIMARY KEY, reason_code TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citation_proofs (
    finding_id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coverage_manifests (
    finding_id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_decisions (
    finding_id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
"""


class SqliteGraphStore:
    """Default judged-path graph store: same node/edge model, zero extra services.

    Implements the `GraphStore` protocol. Neo4j (`GRAPH_BACKEND=neo4j`) is the
    optional swap for the live-demo graph view — see configs/graph.yaml.
    Connection is lazy so constructing the store never touches disk.
    """

    def __init__(self, db_path: str | Path = "data/graph_v2.db") -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute(
                "SELECT value FROM graph_metadata WHERE key='schema_version'"
            ).fetchone()
            if row and int(row[0]) not in {2, GRAPH_SCHEMA_VERSION}:
                raise RuntimeError(
                    f"graph schema version {row[0]} is incompatible with {GRAPH_SCHEMA_VERSION}"
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO graph_metadata(key,value) VALUES ('schema_version',?)",
                (str(GRAPH_SCHEMA_VERSION),),
            )
            self._conn.commit()
        return self._conn

    def schema_version(self) -> int:
        row = self._connect().execute(
            "SELECT value FROM graph_metadata WHERE key='schema_version'"
        ).fetchone()
        return int(row[0])

    def upsert_node(self, node_id: str, label: str, props: dict | None = None) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO nodes (id, label, props) VALUES (?, ?, ?)",
            (node_id, label, json.dumps(props or {}, ensure_ascii=False)),
        )
        conn.commit()

    def upsert_edge(self, src: str, rel: str, dst: str, props: dict | None = None) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO edges (src, rel, dst, props) VALUES (?, ?, ?, ?)",
            (src, rel, dst, json.dumps(props or {}, ensure_ascii=False)),
        )
        conn.commit()

    def upsert_rule_unit(self, rule_unit: RuleUnit) -> str:
        instrument_id = f"instrument:{rule_unit.economy}:{rule_unit.law_name}"
        section_id = f"section:{rule_unit.economy}:{rule_unit.law_name}:{rule_unit.article_section}"
        provision_id = f"provision:{rule_unit.id}"

        self.upsert_node(
            instrument_id,
            "Instrument",
            {"law_name": rule_unit.law_name, "economy": rule_unit.economy,
             "law_number_ref": rule_unit.law_number_ref, "last_amended": rule_unit.last_amended},
        )
        self.upsert_node(
            section_id, "Section",
            {"article_section": rule_unit.article_section, "source_url": rule_unit.source_url},
        )
        self.upsert_node(
            provision_id, "Provision",
            {"text": rule_unit.text, "location_reference": rule_unit.location_reference,
             "start_char": rule_unit.start_char, "end_char": rule_unit.end_char,
             "source_url": rule_unit.source_url,
             "article_section": rule_unit.article_section,
             "law_name": rule_unit.law_name, "economy": rule_unit.economy,
             "law_number_ref": rule_unit.law_number_ref,
             "last_amended": rule_unit.last_amended,
             "heading": str(rule_unit.metadata.get("heading", "")),
             "part": str(rule_unit.metadata.get("part", "")),
             "current_as_at": rule_unit.metadata.get("current_as_at"),
             "legal_status": rule_unit.metadata.get("legal_status", "unknown"),
             "evidence_eligible": bool(rule_unit.metadata.get("evidence_eligible", False)),
             "status_evidence": rule_unit.metadata.get("status_evidence"),
             "source_artifact_id": rule_unit.source_artifact_id,
             "structure_artifact_id": rule_unit.metadata.get("structure_artifact_id"),
             "compilation_bundle_id": rule_unit.metadata.get("compilation_bundle_id"),
             "raw_context": rule_unit.raw_context,
             "linked_span_ids": rule_unit.linked_span_ids,
             "archived_copy": rule_unit.metadata.get("archived_copy"),
             "access_date": rule_unit.metadata.get("access_date"),
             "content_sha256": rule_unit.metadata.get("content_sha256"),
             "processing_fingerprint": rule_unit.metadata.get("processing_fingerprint"),
             "source_type": rule_unit.metadata.get("source_type"),
             "extraction": rule_unit.metadata.get("extraction"),
             "confidence": rule_unit.extraction_confidence,
             "pdf_alignment": rule_unit.metadata.get("pdf_alignment"),
             "alignment_score": rule_unit.metadata.get("alignment_score"),
             "ocr_citation_disagreement": rule_unit.metadata.get("ocr_citation_disagreement", False),
             "build_generation": rule_unit.metadata.get("build_generation"),
             "metadata": rule_unit.metadata,
             "id": provision_id},
        )
        self.upsert_edge(instrument_id, "HAS_SECTION", section_id)
        self.upsert_edge(section_id, "HAS_PROVISION", provision_id)

        conn = self._connect()
        conn.execute("DELETE FROM provisions_fts WHERE provision_id = ?", (provision_id,))
        conn.execute(
            "INSERT INTO provisions_fts (provision_id, economy, text) VALUES (?, ?, ?)",
            (provision_id, rule_unit.economy, rule_unit.text),
        )
        conn.commit()
        return f"sqlite://rule-unit/{rule_unit.id}"

    def upsert_source_artifact(self, artifact: SourceArtifact) -> None:
        self._connect().execute(
            "INSERT OR REPLACE INTO source_artifacts(id,payload) VALUES (?,?)",
            (artifact.id, artifact.model_dump_json()),
        )
        self._connect().commit()

    def upsert_page_artifacts(self, pages: list[PageArtifact]) -> None:
        self._connect().executemany(
            "INSERT OR REPLACE INTO page_artifacts(id,source_artifact_id,page_number,payload) VALUES (?,?,?,?)",
            [(p.id, p.source_artifact_id, p.page_number, p.model_dump_json()) for p in pages],
        )
        self._connect().commit()

    def upsert_text_spans(self, spans: list[TextSpan]) -> None:
        self._connect().executemany(
            "INSERT OR REPLACE INTO text_spans(id,source_artifact_id,page_number,payload) VALUES (?,?,?,?)",
            [(s.id, s.source_artifact_id, s.page_number, s.model_dump_json()) for s in spans],
        )
        self._connect().commit()

    def upsert_finding(self, finding_id: str, run_id: str, finding: MappedFinding) -> None:
        conn = self._connect()
        conn.execute("INSERT OR REPLACE INTO findings(id,run_id,payload) VALUES (?,?,?)",
                     (finding_id, run_id, finding.model_dump_json(by_alias=True)))
        if finding.citation_proof:
            conn.execute("INSERT OR REPLACE INTO citation_proofs(finding_id,payload) VALUES (?,?)",
                         (finding_id, finding.citation_proof.model_dump_json()))
        if finding.search_coverage_manifest:
            conn.execute("INSERT OR REPLACE INTO coverage_manifests(finding_id,payload) VALUES (?,?)",
                         (finding_id, finding.search_coverage_manifest.model_dump_json()))
        conn.commit()

    def record_review_decision(self, finding_id: str, decision: ReviewDecision) -> None:
        """Append-once decision record: changed decisions require a new finding identity."""
        conn = self._connect(); payload = decision.model_dump_json()
        existing = conn.execute("SELECT payload FROM review_decisions WHERE finding_id=?",
                                (finding_id,)).fetchone()
        if existing and existing[0] != payload:
            raise ValueError(f"immutable ReviewDecision already exists for {finding_id}")
        conn.execute("INSERT OR IGNORE INTO review_decisions(finding_id,payload) VALUES (?,?)",
                     (finding_id, payload)); conn.commit()

    def add_discovery_lead(self, lead_id: str, reason_code: str, payload: dict) -> None:
        self._connect().execute(
            "INSERT OR REPLACE INTO discovery_leads(id,reason_code,payload) VALUES (?,?,?)",
            (lead_id, reason_code, json.dumps(payload, ensure_ascii=False)),
        )
        self._connect().commit()

    def purge_ineligible_provisions(self, economy: str | None = None) -> int:
        """Remove derived evidence nodes while retaining a deterministic lead record."""
        from packages.core.legal_controls import evidence_eligibility

        conn = self._connect()
        rows = conn.execute("SELECT id,props FROM nodes WHERE label='Provision'").fetchall()
        doomed: list[tuple[str, str, dict]] = []
        for node_id, raw in rows:
            props = json.loads(raw)
            if economy and props.get("economy") != economy:
                continue
            eligible, reason = evidence_eligibility(
                props.get("law_name", ""), props.get("metadata", {}).get("source_type", "act"),
                props.get("legal_status", "unknown"))
            if not eligible:
                doomed.append((node_id, reason or "INELIGIBLE", props))
        if not doomed:
            return 0
        conn.execute("BEGIN")
        for node_id, reason, props in doomed:
            conn.execute("INSERT OR REPLACE INTO discovery_leads(id,reason_code,payload) VALUES (?,?,?)",
                         (f"lead:{node_id}", reason, json.dumps(props, ensure_ascii=False)))
            conn.execute("DELETE FROM provisions_fts WHERE provision_id=?", (node_id,))
            conn.execute("DELETE FROM edges WHERE src=? OR dst=?", (node_id, node_id))
            conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        conn.commit()
        return len(doomed)

    def purge_instrument_provisions(self, economy: str, law_name: str,
                                    reason: str = "TARGETED_REBUILD_REPLACED") -> int:
        """Remove a derived instrument atomically while retaining quarantine leads."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT id,props FROM nodes WHERE label='Provision' "
            "AND json_extract(props,'$.economy')=? "
            "AND json_extract(props,'$.law_name')=?", (economy, law_name)).fetchall()
        if not rows:
            return 0
        conn.execute("BEGIN")
        for node_id, raw in rows:
            conn.execute(
                "INSERT OR REPLACE INTO discovery_leads(id,reason_code,payload) VALUES (?,?,?)",
                (f"lead:{node_id}", reason, raw),
            )
            conn.execute("DELETE FROM provisions_fts WHERE provision_id=?", (node_id,))
            conn.execute("DELETE FROM edges WHERE src=? OR dst=?", (node_id, node_id))
            conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        conn.commit()
        return len(rows)

    def restamp_artifact_generation(self, economy: str, fingerprint: str,
                                    generation: str) -> int:
        """Incremental-processing guard (19 Jul): provisions are reused ONLY on a
        full processing-fingerprint match (source sha + extraction version + parse
        profile — see packages/core/fingerprint.py); the builder then skips
        re-extraction/OCR and this restamps them into the current generation so the
        end-of-build prune retains them. A parser/grammar change bumps the version,
        misses the match, and forces a fresh extraction."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, props FROM nodes WHERE label='Provision' "
            "AND json_extract(props,'$.economy')=? "
            "AND json_extract(props,'$.processing_fingerprint')=?",
            (economy, fingerprint),
        ).fetchall()
        if not rows:
            return 0
        import json as _json
        conn.execute("BEGIN")
        for node_id, props_raw in rows:
            props = _json.loads(props_raw)
            props["build_generation"] = generation
            conn.execute("UPDATE nodes SET props=? WHERE id=?",
                         (_json.dumps(props, ensure_ascii=False), node_id))
        conn.commit()
        return len(rows)

    def prune_economy_generation(self, economy: str, generation: str) -> int:
        """Atomically remove stale derived provisions only after a complete rebuild."""
        conn = self._connect()
        stale = [row[0] for row in conn.execute(
            "SELECT id FROM nodes WHERE label='Provision' "
            "AND json_extract(props,'$.economy')=? "
            "AND COALESCE(json_extract(props,'$.build_generation'),'')<>?",
            (economy, generation),
        )]
        if not stale:
            return 0
        conn.execute("BEGIN")
        conn.executemany("DELETE FROM provisions_fts WHERE provision_id=?", [(i,) for i in stale])
        conn.executemany("DELETE FROM edges WHERE src=? OR dst=?", [(i, i) for i in stale])
        conn.executemany("DELETE FROM nodes WHERE id=?", [(i,) for i in stale])
        conn.commit()
        return len(stale)

    def search_provisions(
        self, query: str, economy: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Sparse leg of hybrid retrieval: SQLite FTS5 (BM25 ranking, built-in)."""
        # FTS5 query syntax: quote each term to avoid operator interpretation; OR them
        # for broad recall (union of term hits, ranked) rather than implicit AND.
        terms = [t for t in query.replace('"', " ").split() if t.strip()]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        sql = (
            "SELECT provision_id, economy, text, bm25(provisions_fts) AS rank "
            "FROM provisions_fts WHERE provisions_fts MATCH ?"
        )
        params: list = [match]
        if economy:
            sql += " AND economy = ?"
            params.append(economy)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        rows = self._connect().execute(sql, params).fetchall()
        results = []
        for provision_id, econ, text, rank in rows:
            node = self._connect().execute(
                "SELECT props FROM nodes WHERE id = ?", (provision_id,)
            ).fetchone()
            props = json.loads(node[0]) if node else {}
            results.append(
                {"provision_id": provision_id, "text": text,
                 "score": -float(rank), "props": props}  # bm25() is lower-is-better
            )
        return results

    def count_nodes(self) -> int:
        row = self._connect().execute("SELECT COUNT(*) FROM nodes").fetchone()
        return int(row[0])

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
