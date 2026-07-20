from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.core.finalization import finding_key, validate_final_finding  # noqa: E402
from packages.core.schemas import MappedFinding, SourceArtifact, TextSpan  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--submission", default="submission")
    p.add_argument("--graph", default="data/graph_v2.db"); args = p.parse_args()
    root = Path(args.submission)
    payload = json.loads((root / "consolidated_final.json").read_text())
    findings = [MappedFinding.model_validate(r) for r in payload["rows"]]
    conn = sqlite3.connect(args.graph)
    artifacts = {r[0]: SourceArtifact.model_validate_json(r[1])
                 for r in conn.execute("SELECT id,payload FROM source_artifacts")}
    spans = {r[0]: TextSpan.model_validate_json(r[1])
             for r in conn.execute("SELECT id,payload FROM text_spans")}
    for finding in findings:
        validate_final_finding(finding, artifacts, spans)
    csv_rows = list(csv.DictReader((root / "consolidated_final.csv").open()))
    json_projection = {(f.economy, f.indicator_id, f.law_name, f.article_section) for f in findings}
    csv_projection = {(r["Economy"], r["Indicator ID"], r["Law Name"], r["Article / Section"]) for r in csv_rows}
    if json_projection != csv_projection or len(csv_rows) != len(findings):
        raise SystemExit("CSV/JSON row identity mismatch")
    keys = [finding_key(f) for f in findings]
    if len(keys) != len(set(keys)):
        raise SystemExit("duplicate final finding identity")
    manifest = payload.get("replay_manifest") or {}
    if manifest.get("approved_finding_keys") != keys:
        raise SystemExit("replay manifest row identities/order do not match final JSON")
    print(json.dumps({"status": "PASS", "rows": len(findings),
                      "finding_keys": [finding_key(f) for f in findings]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
