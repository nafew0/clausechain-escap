"""Graph enrichment (P3-D): deterministic edges only (GraphRAG §3 guardrail).

1. CROSS_REFERENCES: regex same-act section references from every provision's
   text -> edge Provision -> Section (powers G8 dangling-reference + the demo
   traversal "provision -> exception -> cross-ref").
2. MAPS_TO / EVIDENCED_BY / KNOWN_AS|NEW_RELATIVE_TO: written back from a run's
   output.json for every exported row — the graph then CONTAINS the audit trail
   (GraphRAG §10 win condition).

Usage:
  .venv/bin/python scripts/enrich_graph.py cross-refs
  .venv/bin/python scripts/enrich_graph.py findings outputs/p3_au_p7 [more run dirs]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

import os  # noqa: E402

from packages.discovery.diff import normalize_law, section_base  # noqa: E402
from packages.graph.sqlite_graph import SqliteGraphStore  # noqa: E402
from packages.verifier.gates import _CROSS_REF  # noqa: E402


def stores():
    from packages.graph.store import get_graph_store

    out = [get_graph_store()]
    if (os.getenv("GRAPH_BACKEND") or "sqlite").lower() != "sqlite":
        out.append(SqliteGraphStore())
    return out


def all_provisions(sq: SqliteGraphStore) -> list[dict]:
    rows = sq._connect().execute("SELECT id, props FROM nodes WHERE label='Provision'").fetchall()
    return [{"id": node_id, **json.loads(props)} for node_id, props in rows]


def push_edges(edges: list[dict]) -> None:
    for store in stores():
        if hasattr(store, "upsert_edges"):
            store.upsert_edges(edges)
        else:
            for e in edges:
                store.upsert_edge(e["src"], e["rel"], e["dst"], e.get("props", {}))


def build_cross_refs() -> int:
    provisions = all_provisions(SqliteGraphStore())
    edges = []
    for p in provisions:
        text = p.get("text", "")[:3000]
        law, economy = p.get("law_name", ""), p.get("economy", "")
        for match in _CROSS_REF.finditer(text):
            other = match.group(2)
            if other and other.strip().lower().startswith(("this ", "that ", "the said")):
                other = None
            if other:
                continue  # cross-act edges need instrument resolution — later
            target = f"section:{economy}:{law}:s. {match.group(1).upper()}"
            edges.append({"src": p["id"], "rel": "CROSS_REFERENCES", "dst": target,
                          "props": {"provenance": "regex_text", "raw": match.group(0)[:60]}})
    push_edges(edges)
    return len(edges)


def write_back_findings(run_dirs: list[Path]) -> int:
    count = 0
    edges = []
    for run in run_dirs:
        env = json.loads((run / "output.json").read_text())
        for i, f in enumerate(env.get("findings", [])):
            if f.get("Article / Section", f.get("article_section", "n/a")) in ("n/a", ""):
                continue
            economy = f.get("Economy", f.get("economy"))
            law = f.get("Law Name", f.get("law_name"))
            article = f.get("Article / Section", f.get("article_section"))
            indicator = f.get("Indicator ID", f.get("indicator_id"))
            tag = f.get("Discovery Tag", f.get("discovery_tag"))
            base = section_base(article)
            provision_glob = f"provision-ref:{economy}:{normalize_law(law)}:{base}"
            section_id = f"section:{economy}:{law}:s. {base}"
            finding_id = f"finding:{env.get('run_id','run')}:{i}"
            for store in stores():
                store.upsert_node(finding_id, "VerifiedFinding",
                                  {"indicator": indicator, "article": article,
                                   "law": law, "economy": economy, "tag": tag,
                                   "run": env.get("run_id")}) if hasattr(store, "upsert_node") else None
            edges.append({"src": section_id, "rel": "MAPS_TO", "dst": f"indicator:{indicator}",
                          "props": {"run": env.get("run_id"), "tag": tag}})
            edges.append({"src": finding_id, "rel": "EVIDENCED_BY", "dst": section_id,
                          "props": {"article": article}})
            edges.append({"src": section_id,
                          "rel": "KNOWN_AS" if tag == "KNOWN" else "NEW_RELATIVE_TO",
                          "dst": f"baseline:{economy}:master-db", "props": {}})
            count += 1
    push_edges(edges)
    return count


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "cross-refs"
    if mode == "cross-refs":
        print("CROSS_REFERENCES edges:", build_cross_refs())
    else:
        print("finding write-backs:", write_back_findings([Path(a) for a in sys.argv[2:]]))
