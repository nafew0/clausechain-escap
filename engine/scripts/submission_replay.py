"""Deterministically build final CSV/JSON from named human approvals only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.finalization import (apply_decision, finding_key, review_subject_hash,
                                        validate_final_finding)  # noqa: E402
from packages.core.schemas import MappedFinding, ReviewDecision, SourceArtifact, TextSpan  # noqa: E402
from packages.export.csv_writer import write_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", default="submission/consolidated.json")
    parser.add_argument("--decisions", default="data/review/decisions.json")
    parser.add_argument("--bundle", help="Rev C recovery: a data/review/bundles/<id>/ dir — "
                        "decisions are read from it instead of the live file")
    parser.add_argument("--graph", default="data/graph_v2.db")
    parser.add_argument("--out", default="submission")
    args = parser.parse_args()
    candidate_path, decision_path = Path(args.candidates), Path(args.decisions)
    if args.bundle:  # deterministic rebuild from an immutable bundle (server-loss recovery)
        decision_path = Path(args.bundle) / "decisions.json"
    candidate_bytes, decision_bytes = candidate_path.read_bytes(), decision_path.read_bytes()
    candidates = [MappedFinding.model_validate(r) for r in json.loads(candidate_bytes)["rows"]]
    decision_items = json.loads(decision_bytes)
    decisions = {
        d["finding_key"]: (d.get("review_subject_hash"),
                           ReviewDecision.model_validate(d["review"]))
        for d in decision_items
    }
    candidate_keys = {finding_key(f) for f in candidates}
    unknown = sorted(set(decisions) - candidate_keys)
    if unknown:
        raise SystemExit(f"decision file contains {len(unknown)} unknown/stale finding key(s)")
    conn = sqlite3.connect(args.graph)
    artifacts = {row[0]: SourceArtifact.model_validate_json(row[1])
                 for row in conn.execute("SELECT id,payload FROM source_artifacts")}
    spans = {row[0]: TextSpan.model_validate_json(row[1])
             for row in conn.execute("SELECT id,payload FROM text_spans")}
    approved = []
    for finding in candidates:
        decision_item = decisions.get(finding_key(finding))
        if not decision_item:
            continue
        subject_hash, decision = decision_item
        current_subject_hash = review_subject_hash(finding)
        if subject_hash != current_subject_hash:
            raise SystemExit(
                f"stale approval subject for {finding_key(finding)}: proof/status/rationale changed"
            )
        if decision.decision != "approved":
            continue
        finding = apply_decision(finding, decision)
        validate_final_finding(finding, artifacts, spans)
        immutable_review_id = f"{finding_key(finding)}:{current_subject_hash}"
        existing = conn.execute("SELECT payload FROM review_decisions WHERE finding_id=?",
                                (immutable_review_id,)).fetchone()
        payload_json = decision.model_dump_json()
        if existing and existing[0] != payload_json:
            raise SystemExit(f"immutable ReviewDecision conflict for {finding_key(finding)}")
        conn.execute("INSERT OR IGNORE INTO review_decisions(finding_id,payload) VALUES (?,?)",
                     (immutable_review_id, payload_json))
        approved.append(finding)
    conn.commit()
    approved.sort(key=lambda f: (f.economy, f.indicator_id, f.law_name, f.article_section,
                                 finding_key(f)))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    write_csv(approved, out / "consolidated_final.csv")
    payload = {"replay_manifest": {
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "decisions_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        "approved_finding_keys": [finding_key(f) for f in approved],
        "approved_review_subject_hashes": [review_subject_hash(f) for f in approved],
    }, "rows": [f.model_dump(mode="json", by_alias=True) for f in approved]}
    (out / "consolidated_final.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"submission replay: {len(approved)} explicitly approved rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
