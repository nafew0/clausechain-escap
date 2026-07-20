"""Read-only Neo4j snapshot exporter used by the Django importer.

This module is intentionally executed with the engine interpreter. It performs
only fixed Cypher reads and never returns credentials or unrestricted payloads.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_LABELS = {
    "Instrument", "Section", "Provision", "SourceArtifact", "VerifiedFinding",
    "Indicator", "Baseline", "CitationProof",
}
ALLOWED_RELS = {
    "HAS_SECTION", "HAS_PROVISION", "MAPS_TO", "EVIDENCED_BY", "KNOWN_AS",
    "NEW_RELATIVE_TO", "CROSS_REFERENCES", "AMENDS", "REPEALS", "SUPERSEDES",
    "EXCEPTION_TO", "QUALIFIES",
}
SAFE_PROPERTIES = {
    "id", "law_name", "economy", "law_number_ref", "last_amended",
    "article_section", "source_url", "location_reference", "heading", "part",
    "legal_status", "evidence_eligible", "current_as_at", "indicator", "article",
    "law", "tag", "run", "official", "official_domain", "register_id",
    "version_id", "sha256", "text",
}


def clean_properties(props: dict) -> dict:
    output = {key: props[key] for key in SAFE_PROPERTIES if key in props}
    if "text" in output:
        output["text"] = str(output["text"])[:320]
    return output


def main() -> int:
    engine_root = Path(sys.argv[1]).resolve()
    findings_path = Path(sys.argv[2]).resolve()
    validation_path = Path(sys.argv[3]).resolve()
    sys.path.insert(0, str(engine_root))
    from packages.core.envfile import load_env_file
    from neo4j import GraphDatabase, READ_ACCESS

    load_env_file(engine_root / ".env")
    uri, user, password = (os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    if not all((uri, user, password)):
        raise RuntimeError("Neo4j configuration is incomplete")

    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    refs = [
        {
            "economy": row.get("Economy"),
            "law": row.get("Law Name"),
            "article": row.get("Article / Section"),
            "finding_key": row.get("finding_key") or row.get("Finding key"),
        }
        for row in findings
        if row.get("Article / Section") not in (None, "", "n/a")
    ]
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            schema_row = session.run(
                "MATCH (m:GraphMetadata {id:'clausechain-schema'}) RETURN m.version AS version"
            ).single()
            schema_version = int(schema_row["version"]) if schema_row else None
            label_counts = {
                row["label"]: int(row["count"])
                for row in session.run(
                    "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count ORDER BY label"
                )
                if row["label"] in ALLOWED_LABELS
            }
            relationship_counts = {
                row["type"]: int(row["count"])
                for row in session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY type"
                )
                if row["type"] in ALLOWED_RELS
            }
            economy_counts = {
                str(row["economy"]): int(row["count"])
                for row in session.run(
                    "MATCH (p:Provision) WHERE p.economy IS NOT NULL "
                    "RETURN p.economy AS economy, count(*) AS count ORDER BY economy"
                )
            }
            matched = list(session.run(
                "UNWIND $refs AS ref "
                "MATCH (i:Instrument)-[:HAS_SECTION]->(s:Section)-[:HAS_PROVISION]->(p:Provision) "
                "WHERE p.economy = ref.economy AND p.law_name = ref.law "
                "AND p.article_section = ref.article "
                "RETURN DISTINCT ref.finding_key AS finding_key, i, s, p LIMIT 500",
                refs=refs,
            ))
            for row in matched:
                for name in ("i", "s", "p"):
                    node = row[name]
                    node_id = str(node.get("id"))
                    labels = [label for label in node.labels if label in ALLOWED_LABELS]
                    if node_id and labels:
                        props = clean_properties(dict(node))
                        if name == "p" and row["finding_key"]:
                            props["finding_key"] = row["finding_key"]
                        nodes[node_id] = {"id": node_id, "labels": labels, "properties": props}

            selected_ids = list(nodes)[:500]
            if selected_ids:
                related = session.run(
                    "MATCH (a)-[r]->(b) WHERE a.id IN $ids "
                    "AND type(r) IN $rels RETURN a, r, b LIMIT 1000",
                    ids=selected_ids,
                    rels=sorted(ALLOWED_RELS),
                )
                for row in related:
                    rel = row["r"]
                    rel_type = rel.type
                    if rel_type not in ALLOWED_RELS:
                        continue
                    for name in ("a", "b"):
                        node = row[name]
                        node_id = str(node.get("id"))
                        labels = [label for label in node.labels if label in ALLOWED_LABELS]
                        if node_id and labels and len(nodes) < 500:
                            nodes.setdefault(node_id, {"id": node_id, "labels": labels, "properties": clean_properties(dict(node))})
                    source, target = str(row["a"].get("id")), str(row["b"].get("id"))
                    if source in nodes and target in nodes:
                        edge_id = f"{source}:{rel_type}:{target}"
                        edges[edge_id] = {
                            "id": edge_id, "source": source, "target": target,
                            "type": rel_type, "properties": clean_properties(dict(rel)),
                        }

            # Structural edges for every selected evidence path.
            structural = session.run(
                "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids "
                "AND type(r) IN $rels RETURN a.id AS source, b.id AS target, type(r) AS type LIMIT 1000",
                ids=list(nodes), rels=sorted(ALLOWED_RELS),
            )
            for row in structural:
                edge_id = f"{row['source']}:{row['type']}:{row['target']}"
                edges.setdefault(edge_id, {"id": edge_id, "source": row["source"], "target": row["target"], "type": row["type"], "properties": {}})
    finally:
        driver.close()

    expected_schema = int(validation.get("schema_version") or 0)
    expected_economies = validation.get("provisions") or {}
    resolved = len({row["finding_key"] for row in matched if row["finding_key"]})
    checks = {
        "schema": schema_version == expected_schema,
        "source_artifacts": label_counts.get("SourceArtifact", 0) == int(validation.get("source_artifacts") or 0),
        "economy_provisions": all(economy_counts.get(key) == int(value) for key, value in expected_economies.items()),
        "finding_resolution": resolved == len({ref["finding_key"] for ref in refs if ref["finding_key"]}),
    }
    payload = {
        "status": "verified" if all(checks.values()) else "parity_failed",
        "origin": "neo4j",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": schema_version,
        "checks": checks,
        "counts": {"labels": label_counts, "relationships": relationship_counts, "economies": economy_counts},
        "expected": validation,
        "resolved_findings": resolved,
        "expected_findings": len({ref["finding_key"] for ref in refs if ref["finding_key"]}),
        "nodes": list(nodes.values())[:500],
        "edges": list(edges.values())[:1000],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
