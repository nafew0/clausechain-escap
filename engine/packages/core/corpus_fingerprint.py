from __future__ import annotations

import hashlib
import json


def corpus_fingerprint(corpus: list[dict]) -> str:
    """Content identity for the exact evidence corpus consumed by a run."""
    rows = []
    for unit in corpus:
        props = unit.get("props") or {}
        rows.append({
            "id": unit.get("provision_id") or props.get("id"),
            "law": props.get("law_name"),
            "citation": props.get("article_section"),
            "source_sha256": props.get("content_sha256"),
            "text_sha256": hashlib.sha256(
                str(unit.get("text") or props.get("text") or "").encode("utf-8")
            ).hexdigest(),
        })
    payload = json.dumps(sorted(rows, key=lambda row: str(row["id"])),
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
