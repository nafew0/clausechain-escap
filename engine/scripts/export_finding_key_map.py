"""Export finding_key_map.json — the UI↔engine join table (App Dev Plan C3).

For every finding across the six runs: the canonical finding_key (same sha256
as submission_replay/decisions.json), human identifiers for joining payload
rows, the matching proof-bundle asset (if any), and the blocked flag.

Usage: .venv/bin/python scripts/export_finding_key_map.py [--out finding_key_map.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RUNS = ["final_si_p6", "final_si_p7", "final_ma_p6", "final_ma_p7",
        "final_au_p6", "final_au_p7"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="finding_key_map.json")
    args = parser.parse_args()

    from packages.core.finalization import finding_key
    from packages.core.schemas import MappedFinding

    # the bundle names proof pages assets/{finding_key}.png (build_review_bundle.py)
    assets_dir = Path("submission/review/assets")

    rows = []
    for run in RUNS:
        env = json.loads(Path(f"outputs/{run}/output.json").read_text())
        for raw in env.get("findings", []):
            finding = MappedFinding.model_validate(raw)
            key = finding_key(finding)
            proof = finding.citation_proof
            proof_status = getattr(proof, "alignment_status", None) if proof else None
            blocked = (finding.verbatim_snippet == "NO_EVIDENCE_FOUND_PENDING_REVIEW"
                       or str(proof_status or "").startswith("unaligned"))
            rows.append({
                "finding_key": key,
                "run": run,
                "economy": finding.economy,
                "indicator": finding.indicator_id,
                "law": finding.law_name,
                "article": finding.article_section,
                "discovery_tag": finding.discovery_tag,
                "is_absence": finding.verbatim_snippet == "NO_EVIDENCE_FOUND_PENDING_REVIEW",
                "blocked": bool(blocked),
                "alignment_status": proof_status,
                "proof_asset": (f"assets/{key}.png"
                                if (assets_dir / f"{key}.png").is_file() else None),
            })

    dup = len(rows) - len({r["finding_key"] for r in rows})
    Path(args.out).write_text(json.dumps(
        {"rows": rows, "total": len(rows), "duplicate_keys": dup}, indent=1))
    print(f"wrote {args.out} — {len(rows)} findings, "
          f"{sum(1 for r in rows if r['proof_asset'])} with proof assets, "
          f"{sum(1 for r in rows if r['blocked'])} blocked, {dup} duplicate keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
