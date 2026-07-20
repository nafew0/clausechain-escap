#!/usr/bin/env python3
"""Build the development-only D2 fixture from the real ui_export.zip contract."""

import hashlib
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ui_export.zip"
TARGET = ROOT / "frontend" / "src" / "lib" / "workspace" / "fixtures" / "current.json"
SHEETS = {
    "new": "NEW Findings",
    "absence": "Absence Review",
    "recall": "Recall Misses",
    "zone3": "Zone-3 Scores",
    "known": "KNOWN Findings",
}


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalized(value):
    return " ".join(str(value or "").split()).casefold()


def stable_key(*values):
    return hashlib.sha256("|".join(normalized(value) for value in values).encode()).hexdigest()


def row_record(headers, row):
    return dict(zip(headers, row)) if isinstance(row, list) else row


def read_json(archive, name):
    return json.loads(archive.read(name))


def main():
    if not SOURCE.is_file():
        sys.exit(f"Missing real fixture source: {SOURCE}")
    with zipfile.ZipFile(SOURCE) as archive:
        payload = read_json(archive, "review_payload.json")
        key_map = read_json(archive, "finding_key_map.json")
        consolidated = read_json(archive, "consolidated.json")
        champion = read_json(archive, "champion_validation.json")
        costs = read_json(archive, "runs/cost_report.json")
        run_names = [
            "final_si_p6", "final_si_p7", "final_ma_p6",
            "final_ma_p7", "final_au_p6", "final_au_p7",
        ]
        runs = {name: read_json(archive, f"runs/{name}/output.json") for name in run_names}

    keys = {item["finding_key"]: item for item in key_map["rows"]}
    lookup = {
        tuple(normalized(item[field]) for field in ("economy", "indicator", "law", "article")): item
        for item in key_map["rows"]
    }
    artifact_hashes = payload.get("artifact_hashes", {})
    bundle_hash = content_hash(artifact_hashes)
    fingerprint_payload = dict(payload)
    fingerprint_payload.pop("generated_at", None)
    source_hash = content_hash({
        "payload": fingerprint_payload,
        "key_map": key_map,
        "consolidated": consolidated,
        "champion": champion,
        "costs": costs,
        "runs": runs,
    })
    generated_at = payload["generated_at"]

    empty_review = {
        "decision": None,
        "correction_pending": False,
        "citation_checked": False,
        "mapping_checked": False,
        "status_checked": False,
        "citation_reviewer_name": "",
        "mapping_reviewer_name": "",
        "status_reviewer_name": "",
        "stages": {},
    }
    queues = {}
    next_id = 1
    for queue, sheet_name in SHEETS.items():
        sheet = payload["sheets"][sheet_name]
        headers = sheet["headers"]
        results = []
        for position, row in enumerate(sheet["rows"]):
            record = row_record(headers, row)
            if queue in ("new", "known", "absence"):
                key = str(record.get("Finding key") or "")
            elif queue == "recall":
                key = str(record.get("Recall key") or stable_key(
                    record.get("Economy"), record.get("Indicator"),
                    record.get("Master act/instrument"), record.get("Master citation"),
                ))
            else:
                key = stable_key(record.get("Economy"), record.get("Indicator"))

            key_item = keys.get(key, {})
            guidance = str(record.get("Legal-review guidance") or "")
            warnings = str(record.get("Gate warnings") or "")
            reason = guidance if guidance.startswith("TECHNICAL BLOCK") else ""
            if queue != "absence" and key_item.get("blocked") and not reason:
                reason = warnings or "Engine citation proof marks this finding as blocked."
            item = {
                "id": next_id,
                "position": position,
                "row": row,
                "stable_key": key,
                "finding_key": key if queue in ("new", "known", "absence") else None,
                "blocked": bool(reason),
                "block_reason": reason,
                "source_hash": content_hash(row),
            }
            if queue in ("new", "known", "absence"):
                item.update(
                    review_state=empty_review,
                    latest_correction=None,
                    approval_eligibility={"eligible": not bool(reason), "reason": reason},
                )
            else:
                item.update(latest_decision=None)
            results.append(item)
            next_id += 1
        queues[queue] = {
            "queue": queue,
            "headers": headers,
            "snapshot_id": f"fixture-{bundle_hash[:12]}",
            "snapshot_hash": source_hash,
            "count": len(results),
            "next": None,
            "previous": None,
            "results": results,
        }

    evidence = []
    for row in consolidated["rows"]:
        identity = tuple(normalized(row[field]) for field in (
            "Economy", "Indicator ID", "Law Name", "Article / Section"
        ))
        item = lookup[identity]
        proof_asset = item.get("proof_asset")
        evidence.append({
            "finding_key": item["finding_key"],
            "row": row,
            "blocked": bool(item.get("blocked")),
            "proof_asset_url": f"/proof/{proof_asset.removeprefix('assets/')}" if proof_asset else None,
            "source_hash": content_hash(row),
        })

    def run_cost(envelope):
        economy = {"SG": "Singapore", "MY": "Malaysia", "MA": "Malaysia", "AU": "Australia"}.get(
            str(envelope.get("country", "")).upper(), envelope.get("country", "")
        )
        matches = [item for item in costs if normalized(item.get("economy")) == normalized(economy)
                   and str(item.get("pillar")) == str(envelope.get("pillar"))]
        return matches[-1] if matches else {}

    fixture = {
        "summary": {
            "snapshot": {
                "id": f"fixture-{bundle_hash[:12]}",
                "schema_version": str(payload["schema_version"]),
                "generated_at": generated_at,
                "imported_at": generated_at,
                "source_hash": source_hash,
                "bundle_hash": bundle_hash,
                "engine_git_sha": payload.get("engine_git_sha", ""),
                "stale": False,
            },
            "counts": payload["counts"],
            "refuter_status": payload["refuter_status"],
            "champion": champion,
            "progress": {queue: {"decided": 0, "total": data["count"]} for queue, data in queues.items()},
            "reviewer_roles": ["citation_reviewer", "mapping_reviewer", "status_reviewer"],
        },
        "queues": queues,
        "evidence": evidence,
        "runs": {
            "results": [{
                "run_name": name,
                "envelope": envelope,
                "cost": run_cost(envelope),
                "source_hash": content_hash(envelope),
            } for name, envelope in runs.items()]
        },
        "references": {
            "indicator_criteria": payload["sheets"]["Indicator Criteria"],
            "master_known": payload["sheets"]["Master Known"],
        },
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
