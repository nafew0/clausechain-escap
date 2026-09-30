"""Reconcile the optional Neo4j mirror from the authoritative SQLite graph.

This is an operator-only script, not an API. It uses fixed Cypher, archives
stale provision records before removal, and never changes engine source files.
Run it with the engine Python environment so the Neo4j driver is available.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


LABELS = ("Instrument", "Section", "Provision")


def neo4j_properties(props: dict) -> dict:
    output = {}
    for key, value in props.items():
        if isinstance(value, dict):
            output[f"{key}_json"] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, list):
            if all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
                output[key] = [item for item in value if item is not None]
            else:
                output[f"{key}_json"] = json.dumps(value, ensure_ascii=False)
        elif value is None or isinstance(value, (str, int, float, bool)):
            output[key] = value
        else:
            output[key] = str(value)
    return output


def batches(rows, size=500):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_root", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.engine_root.resolve()
    sys.path.insert(0, str(root))
    from packages.core.envfile import load_env_file
    from neo4j import GraphDatabase, READ_ACCESS

    load_env_file(root / ".env")
    credentials = (os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    if not all(credentials):
        raise RuntimeError("Neo4j configuration is incomplete")
    db = sqlite3.connect(f"file:{root / 'data/graph_v2.db'}?mode=ro&immutable=1", uri=True)
    driver = GraphDatabase.driver(credentials[0], auth=credentials[1:])
    desired_ids = {
        label: {row[0] for row in db.execute("SELECT id FROM nodes WHERE label=?", (label,))}
        for label in LABELS
    }
    with driver.session(default_access_mode=READ_ACCESS) as session:
        current_ids = {
            label: {row["id"] for row in session.run(f"MATCH (n:{label}) RETURN n.id AS id")}
            for label in LABELS
        }
    report = {
        label: {
            "desired": len(desired_ids[label]),
            "current": len(current_ids[label]),
            "missing": len(desired_ids[label] - current_ids[label]),
            "stale": len(current_ids[label] - desired_ids[label]),
        }
        for label in LABELS
    }
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "nodes": report}, indent=2))
    if not args.apply:
        driver.close()
        return 0

    with driver.session() as session:
        for label in LABELS:
            cursor = db.execute("SELECT id,props FROM nodes WHERE label=?", (label,))
            for batch in batches(
                ({"id": node_id, "props": neo4j_properties(json.loads(raw))} for node_id, raw in cursor)
            ):
                session.run(
                    f"UNWIND $rows AS row MERGE (n:{label} {{id:row.id}}) SET n += row.props",
                    rows=batch,
                ).consume()

        for rel, source_label, target_label in (
            ("HAS_SECTION", "Instrument", "Section"),
            ("HAS_PROVISION", "Section", "Provision"),
        ):
            cursor = db.execute("SELECT src,dst FROM edges WHERE rel=?", (rel,))
            for batch in batches(({"src": src, "dst": dst} for src, dst in cursor), 800):
                session.run(
                    f"UNWIND $rows AS row MATCH (a:{source_label} {{id:row.src}}) "
                    f"MATCH (b:{target_label} {{id:row.dst}}) MERGE (a)-[:{rel}]->(b)",
                    rows=batch,
                ).consume()

        for batch in batches(
            ({"id": source_id, "props": neo4j_properties(json.loads(raw)), "payload": raw}
             for source_id, raw in db.execute("SELECT id,payload FROM source_artifacts"))
        ):
            for row in batch:
                row["props"]["payload_json"] = row.pop("payload")
            session.run(
                "UNWIND $rows AS row MERGE (n:SourceArtifact {id:row.id}) SET n += row.props",
                rows=batch,
            ).consume()

        stale_provisions = sorted(current_ids["Provision"] - desired_ids["Provision"])
        if stale_provisions:
            backup = []
            for batch in batches(({"id": value} for value in stale_provisions)):
                backup.extend(dict(row) for row in session.run(
                    "UNWIND $rows AS row MATCH (p:Provision {id:row.id}) "
                    "RETURN p.id AS id, properties(p) AS properties",
                    rows=batch,
                ))
            backup_dir = root.parent / "backend" / "var" / "neo4j_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            (backup_dir / f"stale-provisions-{stamp}.json").write_text(
                json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for batch in batches(({"id": value} for value in stale_provisions)):
                session.run(
                    "UNWIND $rows AS row MATCH (p:Provision {id:row.id}) DETACH DELETE p",
                    rows=batch,
                ).consume()

    driver.close()
    print(json.dumps({"status": "synchronized", "stale_provisions_archived": report["Provision"]["stale"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
