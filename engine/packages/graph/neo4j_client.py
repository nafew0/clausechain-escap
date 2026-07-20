from __future__ import annotations

from dataclasses import dataclass
import json
import os

from packages.core.schemas import (MappedFinding, PageArtifact, ReviewDecision, RuleUnit,
                                   SourceArtifact, TextSpan)
from packages.graph.sqlite_graph import GRAPH_SCHEMA_VERSION


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str | None
    user: str | None
    password: str | None

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        return cls(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD"),
        )

    @property
    def is_complete(self) -> bool:
        return bool(self.uri and self.user and self.password)


class Neo4jGraphStore:
    """Neo4j-backed GraphStore (Path B / live-demo). Lazy connection; same node
    and edge model as SqliteGraphStore. Sparse search uses Neo4j's built-in
    Lucene full-text index (the Neo4j answer to SQLite's FTS5)."""

    FULLTEXT_INDEX = "provision_text"

    def __init__(self, config: Neo4jConfig | None = None) -> None:
        self.config = config or Neo4jConfig.from_env()
        self._driver = None
        self._schema_ready = False

    def _connect(self):
        if self._driver is None:
            if not self.config.is_complete:
                raise RuntimeError(
                    "GRAPH_BACKEND=neo4j but NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD are not all set."
                )
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.config.uri, auth=(self.config.user, self.config.password)
            )
        return self._driver

    def _ensure_schema(self, session) -> None:
        if self._schema_ready:
            return
        session.run(
            "CREATE CONSTRAINT node_id IF NOT EXISTS "
            "FOR (n:Provision) REQUIRE n.id IS UNIQUE"
        )
        session.run(
            f"CREATE FULLTEXT INDEX {self.FULLTEXT_INDEX} IF NOT EXISTS "
            "FOR (p:Provision) ON EACH [p.text]"
        )
        version_row = session.run(
            "MERGE (m:GraphMetadata {id: 'clausechain-schema'}) "
            "ON CREATE SET m.version = $version "
            "RETURN m.version AS version",
            version=GRAPH_SCHEMA_VERSION,
        ).single()
        if not version_row or int(version_row["version"]) != GRAPH_SCHEMA_VERSION:
            found = version_row["version"] if version_row else "missing"
            raise RuntimeError(
                f"Neo4j graph schema version {found} is incompatible with {GRAPH_SCHEMA_VERSION}"
            )
        self._schema_ready = True

    def schema_version(self) -> int:
        with self._connect().session() as session:
            self._ensure_schema(session)
            row = session.run(
                "MATCH (m:GraphMetadata {id:'clausechain-schema'}) RETURN m.version AS version"
            ).single()
            return int(row["version"])

    def upsert_source_artifact(self, artifact: SourceArtifact) -> None:
        payload = artifact.model_dump(mode="json")
        with self._connect().session() as session:
            self._ensure_schema(session)
            session.run(
                """
                MERGE (a:SourceArtifact {id:$id})
                SET a.sha256=$sha256, a.original_url=$original_url,
                    a.retrieved_url=$retrieved_url, a.official=$official,
                    a.official_domain=$official_domain, a.register_id=$register_id,
                    a.version_id=$version_id, a.local_path=$local_path,
                    a.payload_json=$payload_json
                """,
                id=artifact.id, sha256=artifact.sha256,
                original_url=artifact.original_url, retrieved_url=artifact.retrieved_url,
                official=artifact.official, official_domain=artifact.official_domain,
                register_id=artifact.register_id, version_id=artifact.version_id,
                local_path=artifact.local_path,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )

    def upsert_page_artifacts(self, pages: list[PageArtifact], batch_size: int = 300) -> None:
        rows = [{"id": p.id, "source_id": p.source_artifact_id,
                 "page_number": p.page_number, "route": p.route,
                 "payload_json": p.model_dump_json()} for p in pages]
        with self._connect().session() as session:
            self._ensure_schema(session)
            for start in range(0, len(rows), batch_size):
                session.run(
                    """
                    UNWIND $rows AS r
                    MATCH (a:SourceArtifact {id:r.source_id})
                    MERGE (p:PageArtifact {id:r.id})
                    SET p.source_artifact_id=r.source_id, p.page_number=r.page_number,
                        p.route=r.route, p.payload_json=r.payload_json
                    MERGE (a)-[:HAS_PAGE]->(p)
                    """, rows=rows[start:start + batch_size])

    def upsert_text_spans(self, spans: list[TextSpan], batch_size: int = 800) -> None:
        rows = [{"id": s.id, "source_id": s.source_artifact_id,
                 "page_id": f"{s.source_artifact_id}:p{s.page_number}",
                 "page_number": s.page_number, "text": s.text,
                 "bbox_json": json.dumps(s.bbox), "payload_json": s.model_dump_json()}
                for s in spans]
        with self._connect().session() as session:
            self._ensure_schema(session)
            for start in range(0, len(rows), batch_size):
                session.run(
                    """
                    UNWIND $rows AS r
                    MATCH (a:SourceArtifact {id:r.source_id})
                    MATCH (p:PageArtifact {id:r.page_id})
                    MERGE (s:TextSpan {id:r.id})
                    SET s.source_artifact_id=r.source_id, s.page_number=r.page_number,
                        s.text=r.text, s.bbox_json=r.bbox_json,
                        s.payload_json=r.payload_json
                    MERGE (a)-[:HAS_SPAN]->(s)
                    MERGE (p)-[:HAS_SPAN]->(s)
                    """, rows=rows[start:start + batch_size])

    def get_text_spans(self, span_ids: list[str]) -> list[TextSpan]:
        if not span_ids:
            return []
        with self._connect().session() as session:
            records = session.run(
                "UNWIND range(0,size($ids)-1) AS pos "
                "MATCH (s:TextSpan {id:$ids[pos]}) "
                "RETURN pos,s.payload_json AS payload ORDER BY pos",
                ids=span_ids,
            )
            return [TextSpan.model_validate_json(record["payload"])
                    for record in records]

    def add_discovery_lead(self, lead_id: str, reason_code: str, payload: dict) -> None:
        with self._connect().session() as session:
            self._ensure_schema(session)
            session.run(
                "MERGE (d:DiscoveryLead {id:$id}) SET d.reason_code=$reason, d.payload_json=$payload",
                id=lead_id, reason=reason_code,
                payload=json.dumps(payload, ensure_ascii=False),
            )

    def prune_economy_generation(self, economy: str, generation: str) -> int:
        with self._connect().session() as session:
            self._ensure_schema(session)
            row = session.run(
                """
                MATCH (p:Provision {economy:$economy})
                WHERE coalesce(p.build_generation,'') <> $generation
                WITH collect(p) AS stale, count(p) AS removed
                FOREACH (p IN stale | DETACH DELETE p)
                RETURN removed
                """, economy=economy, generation=generation).single()
            return int(row["removed"] if row else 0)

    def upsert_rule_unit(self, rule_unit: RuleUnit) -> str:
        instrument_id = f"instrument:{rule_unit.economy}:{rule_unit.law_name}"
        section_id = f"section:{rule_unit.economy}:{rule_unit.law_name}:{rule_unit.article_section}"
        provision_id = f"provision:{rule_unit.id}"
        with self._connect().session() as session:
            self._ensure_schema(session)
            session.run(
                """
                MERGE (i:Instrument {id: $instrument_id})
                  SET i.law_name = $law_name, i.economy = $economy,
                      i.law_number_ref = $law_number_ref, i.last_amended = $last_amended
                MERGE (s:Section {id: $section_id})
                  SET s.article_section = $article_section, s.source_url = $source_url
                MERGE (p:Provision {id: $provision_id})
                  SET p.text = $text, p.economy = $economy,
                      p.location_reference = $location_reference,
                      p.source_url = $source_url,
                      p.article_section = $article_section,
                      p.law_name = $law_name,
                      p.heading = $heading, p.part = $part,
                      p.metadata_json = $metadata_json,
                      p.source_artifact_id = $source_artifact_id,
                      p.structure_artifact_id = $structure_artifact_id,
                      p.compilation_bundle_id = $compilation_bundle_id,
                      p.raw_context = $raw_context,
                      p.linked_span_ids = $linked_span_ids,
                      p.legal_status = $legal_status,
                      p.evidence_eligible = $evidence_eligible,
                      p.status_evidence_json = $status_evidence_json,
                      p.archived_copy = $archived_copy,
                      p.access_date = $access_date,
                      p.content_sha256 = $content_sha256,
                      p.extraction = $extraction,
                      p.extraction_confidence = $extraction_confidence,
                      p.pdf_alignment = $pdf_alignment,
                      p.alignment_score = $alignment_score,
                      p.ocr_citation_disagreement = $ocr_citation_disagreement,
                      p.build_generation = $build_generation
                MERGE (i)-[:HAS_SECTION]->(s)
                MERGE (s)-[:HAS_PROVISION]->(p)
                """,
                instrument_id=instrument_id,
                section_id=section_id,
                provision_id=provision_id,
                law_name=rule_unit.law_name,
                economy=rule_unit.economy,
                law_number_ref=rule_unit.law_number_ref,
                last_amended=rule_unit.last_amended,
                article_section=rule_unit.article_section,
                source_url=rule_unit.source_url,
                location_reference=rule_unit.location_reference,
                text=rule_unit.text,
                heading=str(rule_unit.metadata.get("heading", "")),
                part=str(rule_unit.metadata.get("part", "")),
                metadata_json=json.dumps(rule_unit.metadata, ensure_ascii=False),
                source_artifact_id=rule_unit.source_artifact_id,
                structure_artifact_id=rule_unit.metadata.get("structure_artifact_id"),
                compilation_bundle_id=rule_unit.metadata.get("compilation_bundle_id"),
                raw_context=rule_unit.raw_context,
                linked_span_ids=rule_unit.linked_span_ids,
                legal_status=rule_unit.metadata.get("legal_status", "unknown"),
                evidence_eligible=bool(rule_unit.metadata.get("evidence_eligible", False)),
                status_evidence_json=json.dumps(rule_unit.metadata.get("status_evidence"), ensure_ascii=False),
                archived_copy=rule_unit.metadata.get("archived_copy"),
                access_date=rule_unit.metadata.get("access_date"),
                content_sha256=rule_unit.metadata.get("content_sha256"),
                extraction=rule_unit.metadata.get("extraction"),
                extraction_confidence=rule_unit.extraction_confidence,
                pdf_alignment=rule_unit.metadata.get("pdf_alignment"),
                alignment_score=rule_unit.metadata.get("alignment_score"),
                ocr_citation_disagreement=bool(rule_unit.metadata.get("ocr_citation_disagreement", False)),
                build_generation=rule_unit.metadata.get("build_generation"),
            )
            session.run(
                "MATCH (p:Provision {id: $pid}) SET p.current_as_at = $current",
                pid=provision_id,
                current=str(rule_unit.metadata.get("current_as_at") or ""),
            )
        return f"neo4j://rule-unit/{rule_unit.id}"

    def upsert_rule_units(self, rule_units: list[RuleUnit], batch_size: int = 400) -> int:
        """Batched load via UNWIND — one round-trip per batch instead of per unit."""
        rows = []
        for u in rule_units:
            rows.append({
                "instrument_id": f"instrument:{u.economy}:{u.law_name}",
                "section_id": f"section:{u.economy}:{u.law_name}:{u.article_section}",
                "provision_id": f"provision:{u.id}",
                "law_name": u.law_name, "economy": u.economy,
                "law_number_ref": u.law_number_ref, "last_amended": u.last_amended,
                "article_section": u.article_section, "source_url": u.source_url,
                "location_reference": u.location_reference, "text": u.text,
                "heading": str(u.metadata.get("heading", "")),
                "part": str(u.metadata.get("part", "")),
                "current_as_at": str(u.metadata.get("current_as_at") or ""),
                "metadata_json": json.dumps(u.metadata, ensure_ascii=False),
                "source_artifact_id": u.source_artifact_id,
                "structure_artifact_id": u.metadata.get("structure_artifact_id"),
                "compilation_bundle_id": u.metadata.get("compilation_bundle_id"),
                "raw_context": u.raw_context,
                "linked_span_ids": u.linked_span_ids,
                "legal_status": u.metadata.get("legal_status", "unknown"),
                "evidence_eligible": bool(u.metadata.get("evidence_eligible", False)),
                "status_evidence_json": json.dumps(u.metadata.get("status_evidence"), ensure_ascii=False),
                "archived_copy": u.metadata.get("archived_copy"),
                "access_date": u.metadata.get("access_date"),
                "content_sha256": u.metadata.get("content_sha256"),
                "extraction": u.metadata.get("extraction"),
                "extraction_confidence": u.extraction_confidence,
                "pdf_alignment": u.metadata.get("pdf_alignment"),
                "alignment_score": u.metadata.get("alignment_score"),
                "ocr_citation_disagreement": bool(u.metadata.get("ocr_citation_disagreement", False)),
                "build_generation": u.metadata.get("build_generation"),
            })
        with self._connect().session() as session:
            self._ensure_schema(session)
            for start in range(0, len(rows), batch_size):
                session.run(
                    """
                    UNWIND $rows AS r
                    MERGE (i:Instrument {id: r.instrument_id})
                      SET i.law_name = r.law_name, i.economy = r.economy,
                          i.law_number_ref = r.law_number_ref, i.last_amended = r.last_amended
                    MERGE (s:Section {id: r.section_id})
                      SET s.article_section = r.article_section, s.source_url = r.source_url
                    MERGE (p:Provision {id: r.provision_id})
                      SET p.text = r.text, p.economy = r.economy,
                          p.location_reference = r.location_reference,
                          p.source_url = r.source_url, p.article_section = r.article_section,
                          p.law_name = r.law_name, p.heading = r.heading, p.part = r.part,
                          p.current_as_at = r.current_as_at,
                          p.metadata_json = r.metadata_json,
                          p.source_artifact_id = r.source_artifact_id,
                          p.structure_artifact_id = r.structure_artifact_id,
                          p.compilation_bundle_id = r.compilation_bundle_id,
                          p.raw_context = r.raw_context,
                          p.linked_span_ids = r.linked_span_ids,
                          p.legal_status = r.legal_status,
                          p.evidence_eligible = r.evidence_eligible,
                          p.status_evidence_json = r.status_evidence_json,
                          p.archived_copy = r.archived_copy,
                          p.access_date = r.access_date,
                          p.content_sha256 = r.content_sha256,
                          p.extraction = r.extraction,
                          p.extraction_confidence = r.extraction_confidence,
                          p.pdf_alignment = r.pdf_alignment,
                          p.alignment_score = r.alignment_score,
                          p.ocr_citation_disagreement = r.ocr_citation_disagreement,
                          p.build_generation = r.build_generation,
                          p.law_number_ref = r.law_number_ref, p.last_amended = r.last_amended
                    MERGE (i)-[:HAS_SECTION]->(s)
                    MERGE (s)-[:HAS_PROVISION]->(p)
                    """,
                    rows=rows[start:start + batch_size],
                )
        return len(rows)

    def search_provisions(
        self, query: str, economy: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Sparse leg of hybrid retrieval: Neo4j Lucene full-text (OR semantics)."""
        import re as _re

        # strip every Lucene syntax character; lowercase so AND/OR/NOT/TO in the
        # query text are plain terms, not operators; OR-join for broad recall
        terms = [t.lower() for t in _re.sub(r"[^0-9A-Za-zÀ-￿ ]+", " ", query).split()
                 if len(t.strip()) > 1]
        if not terms:
            return []
        lucene = " OR ".join(terms)
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{self.FULLTEXT_INDEX}', $q) "
            "YIELD node, score "
            + ("WHERE node.economy = $economy " if economy else "")
            + "RETURN node, score ORDER BY score DESC LIMIT $limit"
        )
        with self._connect().session() as session:
            self._ensure_schema(session)
            params = {"q": lucene, "limit": limit}
            if economy:
                params["economy"] = economy
            records = session.run(cypher, **params)
            output = []
            for r in records:
                props = dict(r["node"])
                try:
                    props["metadata"] = json.loads(props.get("metadata_json") or "{}")
                    props["status_evidence"] = json.loads(
                        props.get("status_evidence_json") or "null")
                except json.JSONDecodeError:
                    props["metadata"] = {}
                output.append({
                    "provision_id": r["node"].get("id"),
                    "text": r["node"].get("text", ""),
                    "score": float(r["score"]),
                    "props": props,
                })
            return output

    def upsert_edges(self, edges: list[dict], batch_size: int = 500) -> int:
        """Generic typed-edge batch: [{'src','rel','dst','src_label','dst_label','props'}].
        Relationship types are validated against the GraphRAG §5 schema."""
        allowed = {"CROSS_REFERENCES", "MAPS_TO", "EVIDENCED_BY", "KNOWN_AS",
                   "NEW_RELATIVE_TO", "AMENDS", "REPEALS", "SUPERSEDES",
                   "EXCEPTION_TO", "QUALIFIES"}
        with self._connect().session() as session:
            self._ensure_schema(session)
            for rel in {e["rel"] for e in edges}:
                if rel not in allowed:
                    raise ValueError(f"edge type {rel!r} not in the legal-graph schema")
                batch = [e for e in edges if e["rel"] == rel]
                for start in range(0, len(batch), batch_size):
                    session.run(
                        f"""
                        UNWIND $rows AS r
                        MERGE (a {{id: r.src}})
                        MERGE (b {{id: r.dst}})
                        MERGE (a)-[rel:{rel}]->(b)
                          SET rel += r.props
                        """,
                        rows=[{"src": e["src"], "dst": e["dst"], "props": e.get("props", {})}
                              for e in batch],
                    )
        return len(edges)

    def count_nodes(self) -> int:
        with self._connect().session() as session:
            return int(session.run("MATCH (n) RETURN count(n) AS c").single()["c"])

    def quarantine_unaligned_provisions(self, economy: str | None = None) -> int:
        """Mirror the judged-path fail-closed alignment policy in Neo4j."""
        where = "p.pdf_alignment = 'unaligned-review' AND p.evidence_eligible = true"
        if economy:
            where += " AND p.economy = $economy"
        with self._connect().session() as session:
            record = session.run(
                f"MATCH (p:Provision) WHERE {where} "
                "SET p.evidence_eligible = false, "
                "p.quarantine_reason = 'ALIGNMENT_UNRESOLVED' "
                "RETURN count(p) AS changed",
                economy=economy,
            ).single()
            return int(record["changed"] if record else 0)

    def mark_artifact_build_complete(self, economy: str, fingerprint: str,
                                     generation: str, unit_count: int) -> None:
        if unit_count <= 0:
            return
        with self._connect().session() as session:
            session.run(
                "MERGE (b:ArtifactBuild {id:$id}) "
                "SET b.economy=$economy,b.fingerprint=$fingerprint,"
                "b.generation=$generation,b.unit_count=$unit_count,"
                "b.completed_at=datetime()",
                id=f"{economy}:{fingerprint}", economy=economy,
                fingerprint=fingerprint, generation=generation, unit_count=unit_count,
            )

    def upsert_finding(self, finding_id: str, run_id: str, finding: MappedFinding) -> None:
        with self._connect().session() as session:
            session.run("MERGE (f:Finding {id:$id}) SET f.run_id=$run_id, f.payload=$payload",
                        id=finding_id, run_id=run_id,
                        payload=finding.model_dump_json(by_alias=True))
            if finding.citation_proof:
                session.run("MERGE (p:CitationProof {id:$id}) SET p.payload=$payload "
                            "WITH p MATCH (f:Finding {id:$id}) MERGE (f)-[:EVIDENCED_BY]->(p)",
                            id=finding_id, payload=finding.citation_proof.model_dump_json())

    def record_review_decision(self, finding_id: str, decision: ReviewDecision) -> None:
        payload = decision.model_dump_json()
        with self._connect().session() as session:
            existing = session.run("MATCH (r:ReviewDecision {id:$id}) RETURN r.payload AS p",
                                   id=finding_id).single()
            if existing and existing["p"] != payload:
                raise ValueError(f"immutable ReviewDecision already exists for {finding_id}")
            session.run("MERGE (r:ReviewDecision {id:$id}) ON CREATE SET r.payload=$payload "
                        "WITH r MATCH (f:Finding {id:$id}) MERGE (f)-[:REVIEWED_BY]->(r)",
                        id=finding_id, payload=payload)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
