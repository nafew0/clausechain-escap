"""W4: export ops_stats.json — real data for the pipeline screens (Crawl/Harvest/Extraction).

Sections:
  acquisition  — every immutable SourceArtifact (portal, url, sha256, fetched, kind)
  eligibility  — per economy: instruments with legal_status / evidence_eligible /
                 quarantine reason (Harvest Review -> Corpus Eligibility)
  extraction   — per economy+law: unit count, extraction methods, alignment
                 breakdown, mean OCR confidence where present

Read-only over data/graph_v2.db. Usage:
  .venv/bin/python scripts/export_ops_stats.py [--out ops_stats.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="ops_stats.json")
    parser.add_argument("--db", default="data/graph_v2.db")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)

    acquisition = []
    for (payload,) in conn.execute("SELECT payload FROM source_artifacts"):
        a = json.loads(payload)
        acquisition.append({
            "id": a.get("id"), "source_url": a.get("original_url"),
            "retrieved_url": a.get("retrieved_url"), "domain": a.get("official_domain"),
            "official": a.get("official"), "source_type": a.get("source_type"),
            "mime_type": a.get("mime_type"), "bytes": a.get("byte_length"),
            "sha256": a.get("sha256"), "accessed_at": a.get("accessed_at"),
            "local_path": a.get("local_path"),
            "status_evidence": (a.get("status_evidence") or {}).get("fact_text")
                               if isinstance(a.get("status_evidence"), dict)
                               else a.get("status_evidence")})

    eligibility: dict[str, dict] = defaultdict(dict)
    extraction: dict[str, dict] = defaultdict(dict)
    rows = conn.execute("""SELECT json_extract(props,'$.economy'),
                                  json_extract(props,'$.law_name'), props
                           FROM nodes WHERE label='Provision'""")
    for economy, law, props in rows:
        if not economy or not law:
            continue
        p = json.loads(props)
        meta = p.get("metadata") or {}
        el = eligibility[economy].setdefault(law, {
            "instrument": law, "units": 0, "evidence_eligible": 0,
            "legal_status": Counter(), "ineligible_reasons": Counter()})
        el["units"] += 1
        el["legal_status"][str(p.get("legal_status", "unknown"))] += 1
        if p.get("evidence_eligible"):
            el["evidence_eligible"] += 1
        elif p.get("ineligible_reason") or p.get("quarantine_reason"):
            el["ineligible_reasons"][str(p.get("ineligible_reason")
                                         or p.get("quarantine_reason"))[:80]] += 1
        ex = extraction[economy].setdefault(law, {
            "instrument": law, "units": 0, "methods": Counter(),
            "alignment": Counter(), "ocr_confidences": []})
        ex["units"] += 1
        ex["methods"][str(meta.get("extraction", "native_text"))] += 1
        ex["alignment"][str(meta.get("pdf_alignment")
                            or ("anchor" if str(p.get("location_reference", "")).startswith("#")
                                else "n/a"))] += 1
        if p.get("extraction_confidence") is not None:
            ex["ocr_confidences"].append(p["extraction_confidence"])

    def finalize(block: dict) -> list[dict]:
        out = []
        for economy, laws in sorted(block.items()):
            for law, rec in sorted(laws.items()):
                rec = dict(rec)
                for key in ("legal_status", "ineligible_reasons", "methods", "alignment"):
                    if key in rec:
                        rec[key] = dict(rec[key])
                if "ocr_confidences" in rec:
                    vals = rec.pop("ocr_confidences")
                    rec["mean_ocr_confidence"] = (round(sum(vals) / len(vals), 4)
                                                  if vals else None)
                rec["economy"] = economy
                out.append(rec)
        return out

    for record in acquisition:  # economy from the archive path (data/raw/<cc>/)
        path = str(record.get("local_path") or "")
        record["economy"] = {"sg": "Singapore", "my": "Malaysia", "au": "Australia"}.get(
            path.split("/")[2] if path.count("/") >= 2 else "", None)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "acquisition": sorted(acquisition, key=lambda a: (str(a.get("economy")),
                                                          str(a.get("source_url") or ""))),
        "eligibility": finalize(eligibility),
        "extraction": finalize(extraction),
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"wrote {args.out} — {len(acquisition)} artifacts, "
          f"{len(payload['eligibility'])} instruments, "
          f"{sum(1 for _ in payload['extraction'])} extraction rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
