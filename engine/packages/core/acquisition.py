"""Acquisition-failure facts used by absence coverage manifests.

The immutable seed configuration declares which official source was supposed to
be acquired for each indicator.  The reconciled per-economy manifest records
whether that acquisition actually succeeded.  Absence reasoning must consume
both: a missing/dead seed is an unresolved search failure, never evidence that a
measure does not exist.
"""
from __future__ import annotations

import json
from pathlib import Path


ECONOMY_CODES = {"Singapore": "sg", "Malaysia": "my", "Australia": "au"}


def _json_object(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def unresolved_seed_acquisitions(
    economy: str,
    indicator_id: str,
    engine_root: str | Path,
) -> list[dict]:
    """Return deterministic acquisition failures for one economy/indicator.

    A configured URL is unresolved when it is absent from the reconciled
    manifest or its manifest status is not ``ok``.  Returned records contain no
    local archive path and are safe to embed in review/validation artifacts.
    """
    root = Path(engine_root)
    code = ECONOMY_CODES.get(economy)
    if not code:
        return [{
            "economy": economy,
            "indicator_id": indicator_id,
            "act": "seed inventory",
            "url": "",
            "status": "unsupported_economy",
            "reason_code": "ACQUISITION_UNRESOLVED",
            "detail": (f"status=unsupported_economy; no seed-manifest mapping "
                       f"configured for {economy}"),
        }]

    seeds_path = root / "data/seeds.json"
    configured_payload = _json_object(seeds_path)
    economies = configured_payload.get("economies")
    if not seeds_path.is_file() or not isinstance(economies, dict) \
            or not isinstance(economies.get(economy), list):
        return [{
            "economy": economy,
            "indicator_id": indicator_id,
            "act": "seed inventory",
            "url": "",
            "status": "inventory_unavailable",
            "reason_code": "ACQUISITION_UNRESOLVED",
            "detail": (f"status=inventory_unavailable; missing or malformed seed "
                       f"inventory for {economy}"),
        }]
    configured = economies[economy]
    rows = [row for row in configured
            if str(row.get("indicator_code") or "") == indicator_id
            and str(row.get("url") or "").startswith("http")]
    manifest = _json_object(root / f"data/raw/{code}/seeds_manifest.json")

    failures: list[dict] = []
    for row in rows:
        url = str(row.get("url") or "").strip()
        entry = manifest.get(url)
        if isinstance(entry, dict) and entry.get("status") == "ok":
            continue
        status = str(entry.get("status") if isinstance(entry, dict) else "not_attempted")
        http_status = entry.get("http_status") if isinstance(entry, dict) else None
        error = str(entry.get("error") or "") if isinstance(entry, dict) else ""
        detail_parts = [f"status={status}"]
        if http_status not in (None, 0, ""):
            detail_parts.append(f"http_status={http_status}")
        if error:
            detail_parts.append(f"error={error[:180]}")
        failures.append({
            "economy": economy,
            "indicator_id": indicator_id,
            "act": str(row.get("act") or "unnamed configured source"),
            "url": url,
            "status": status,
            "reason_code": "ACQUISITION_UNRESOLVED",
            "detail": "; ".join(detail_parts),
        })
    return sorted(failures, key=lambda item: (item["act"], item["url"]))


def format_acquisition_failure(failure: dict) -> str:
    """Stable human/machine-readable SearchCoverageManifest failure line."""
    return (
        f"ACQUISITION_UNRESOLVED {failure.get('indicator_id', '')}: "
        f"{failure.get('act', 'unnamed source')} | {failure.get('detail', '')} | "
        f"{failure.get('url', '')}"
    ).rstrip(" |")
