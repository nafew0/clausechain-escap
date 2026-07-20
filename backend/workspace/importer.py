import json
import hashlib
import subprocess
import tempfile
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import yaml

from .keys import content_hash, recall_key, zone3_key
from .models import EngineSnapshot, EvidenceRow, ReviewItem, RunRecord, SnapshotArtifact


RUN_NAMES = (
    "final_si_p6",
    "final_si_p7",
    "final_ma_p6",
    "final_ma_p7",
    "final_au_p6",
    "final_au_p7",
)
SHEETS = {
    ReviewItem.Queue.NEW: "NEW Findings",
    ReviewItem.Queue.ABSENCE: "Absence Review",
    ReviewItem.Queue.RECALL: "Recall Misses",
    ReviewItem.Queue.ZONE3: "Zone-3 Scores",
    ReviewItem.Queue.KNOWN: "KNOWN Findings",
}
REFERENCE_SHEETS = {
    "indicator_criteria": "Indicator Criteria",
    "master_known": "Master Known",
}


class SnapshotImportError(RuntimeError):
    pass


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SnapshotImportError(
            f"Required engine artifact is missing: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SnapshotImportError(
            f"Invalid JSON in engine artifact: {path}: {exc}"
        ) from exc


def _json_document(path, *, key, category, source_path=None):
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SnapshotImportError(f"Required engine artifact is unavailable: {path}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SnapshotImportError(f"Invalid JSON in engine artifact: {path}: {exc}") from exc
    return _artifact_document(
        key=key,
        category=category,
        source_path=source_path or str(path),
        media_type="application/json",
        raw=raw,
        parsed=parsed,
    )


def _artifact_document(*, key, category, source_path, media_type, raw, parsed):
    encoded = raw.encode("utf-8")
    return {
        "key": key,
        "category": category,
        "source_path": source_path,
        "media_type": media_type,
        "byte_size": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "raw_text": raw,
        "parsed_json": parsed,
    }


def _serialized_document(key, category, source_path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return _artifact_document(
        key=key,
        category=category,
        source_path=source_path,
        media_type="application/json",
        raw=raw,
        parsed=value,
    )


def _run_json(command, *, cwd):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        stderr = getattr(locals().get("result", None), "stderr", "")
        raise SnapshotImportError(
            f"Engine export failed: {exc}. {stderr}".strip()
        ) from exc


def load_engine_artifacts(engine_root=None):
    root = Path(engine_root or settings.ENGINE_ROOT).resolve()
    python = str(settings.ENGINE_PYTHON)
    payload = _run_json(
        [
            python,
            "-c",
            (
                "import json; "
                "from scripts.export_legal_review_payload import build_payload; "
                "print(json.dumps(build_payload(), ensure_ascii=False))"
            ),
        ],
        cwd=root,
    )

    with tempfile.TemporaryDirectory(prefix="clausechain-map-") as temp_dir:
        map_path = Path(temp_dir) / "finding_key_map.json"
        try:
            subprocess.run(
                [python, "scripts/export_finding_key_map.py", "--out", str(map_path)],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SnapshotImportError(f"finding_key map export failed: {exc}") from exc
        key_map_doc = _json_document(
            map_path,
            key="finding-key-map",
            category="review_payload",
            source_path="generated:finding_key_map.json",
        )

    documents = [
        _serialized_document("legal-review-payload", "review_payload", "generated:legal-review-payload", payload),
        key_map_doc,
    ]

    consolidated_doc = _json_document(root / "submission" / "consolidated.json", key="consolidated", category="evidence", source_path="submission/consolidated.json")
    champion_doc = _json_document(root / "reports" / "champion_validation.json", key="champion-validation", category="validation", source_path="reports/champion_validation.json")
    costs_doc = _json_document(root / "logs" / "cost_report.json", key="cost-report", category="runs", source_path="logs/cost_report.json")
    documents.extend((consolidated_doc, champion_doc, costs_doc))
    runs = {}
    for name in RUN_NAMES:
        document = _json_document(root / "outputs" / name / "output.json", key=f"run-{name}", category="runs", source_path=f"outputs/{name}/output.json")
        documents.append(document)
        runs[name] = document["parsed_json"]

    with tempfile.TemporaryDirectory(prefix="clausechain-ops-") as temp_dir:
        ops_path = Path(temp_dir) / "ops_stats.json"
        try:
            subprocess.run(
                [python, "scripts/export_ops_stats.py", "--out", str(ops_path)],
                cwd=root, check=True, capture_output=True, text=True, timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SnapshotImportError(f"ops stats export failed: {exc}") from exc
        ops_doc = _json_document(ops_path, key="ops-stats", category="operations", source_path="generated:ops_stats.json")
        documents.append(ops_doc)

    configs = {"jurisdictions": {}, "seeds": None}
    for code in ("sg", "my", "au"):
        path = root / "configs" / "jurisdictions" / f"{code}.yaml"
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(raw)
        except (OSError, yaml.YAMLError) as exc:
            raise SnapshotImportError(f"Invalid jurisdiction config {path}: {exc}") from exc
        if not isinstance(parsed, dict) or str(parsed.get("jurisdiction", "")).lower() != code:
            raise SnapshotImportError(f"Jurisdiction config {path} has the wrong jurisdiction code")
        document = _artifact_document(key=f"jurisdiction-{code}", category="configuration", source_path=f"configs/jurisdictions/{code}.yaml", media_type="application/yaml", raw=raw, parsed=parsed)
        documents.append(document)
        configs["jurisdictions"][code.upper()] = document
    seeds_doc = _json_document(root / "data" / "seeds.json", key="seeds", category="configuration", source_path="data/seeds.json")
    documents.append(seeds_doc)
    configs["seeds"] = seeds_doc

    manifest_doc = _serialized_document("engine-manifest", "manifests", "generated:engine-manifest", payload.get("manifest") or {"artifact_hashes": payload.get("artifact_hashes") or {}})
    documents.append(manifest_doc)
    graph_validation_doc = _json_document(root / "reports" / "graph_validation.json", key="graph-validation", category="validation", source_path="reports/graph_validation.json")
    documents.append(graph_validation_doc)

    consolidated = consolidated_doc["parsed_json"]
    key_rows = {(
        str(row.get("economy") or "").casefold(), str(row.get("indicator") or "").casefold(),
        " ".join(str(row.get("law") or "").split()).casefold(), " ".join(str(row.get("article") or "").split()).casefold(),
    ): row.get("finding_key") for row in documents[1]["parsed_json"].get("rows", [])}
    graph_findings = []
    for row in consolidated.get("rows") or []:
        copy = dict(row)
        identity = (
            str(row.get("Economy") or "").casefold(), str(row.get("Indicator ID") or "").casefold(),
            " ".join(str(row.get("Law Name") or "").split()).casefold(), " ".join(str(row.get("Article / Section") or "").split()).casefold(),
        )
        copy["finding_key"] = key_rows.get(identity)
        graph_findings.append(copy)
    with tempfile.TemporaryDirectory(prefix="clausechain-graph-") as temp_dir:
        findings_path = Path(temp_dir) / "findings.json"
        findings_path.write_text(json.dumps(graph_findings, ensure_ascii=False), encoding="utf-8")
        try:
            graph_snapshot = _run_json(
                [python, str(Path(__file__).with_name("neo4j_snapshot_export.py")), str(root), str(findings_path), str(root / "reports" / "graph_validation.json")],
                cwd=root,
            )
        except SnapshotImportError as exc:
            graph_snapshot = {"status": "unavailable", "origin": "neo4j", "reason": str(exc), "nodes": [], "edges": []}
    graph_doc = _serialized_document("neo4j-graph-snapshot", "validation", "generated:neo4j-read-only-snapshot", graph_snapshot)
    documents.append(graph_doc)

    return {
        "payload": payload,
        "key_map": documents[1]["parsed_json"],
        "consolidated": consolidated,
        "champion": champion_doc["parsed_json"],
        "costs": costs_doc["parsed_json"],
        "runs": runs,
        "ops_stats": ops_doc["parsed_json"],
        "configs": configs,
        "graph_snapshot": graph_snapshot,
        "snapshot_artifacts": documents,
    }


def _parse_generated_at(value):
    parsed = parse_datetime(str(value or ""))
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise SnapshotImportError(
                f"Payload generated_at is invalid: {value!r}"
            ) from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def _header_index(headers):
    return {str(header): index for index, header in enumerate(headers)}


def _cell(row, indexes, name):
    index = indexes.get(name)
    return row[index] if index is not None and index < len(row) else ""


def _finding_lookup(key_map):
    lookup = {}
    absence_lookup = {}
    by_key = {}
    for item in key_map.get("rows", []):
        finding_key = str(item.get("finding_key") or "")
        if not finding_key or finding_key in by_key:
            raise SnapshotImportError(
                f"Missing or duplicate finding_key: {finding_key!r}"
            )
        by_key[finding_key] = item
        identity = tuple(
            " ".join(str(item.get(key) or "").split()).casefold()
            for key in ("economy", "indicator", "law", "article")
        )
        if identity in lookup:
            raise SnapshotImportError(f"Ambiguous finding-key identity: {identity}")
        lookup[identity] = item
        if item.get("is_absence"):
            absence_identity = identity[:3]
            if absence_identity in absence_lookup:
                raise SnapshotImportError(
                    f"Ambiguous absence finding identity: {absence_identity}"
                )
            absence_lookup[absence_identity] = item
    return lookup, absence_lookup, by_key


def _match_finding(row, headers, queue, lookup, absence_lookup):
    indexes = _header_index(headers)
    economy = _cell(row, indexes, "Economy")
    indicator = _cell(row, indexes, "Indicator")
    law = _cell(row, indexes, "Law/instrument") or _cell(
        row, indexes, "Configured governing instrument"
    )
    article = _cell(row, indexes, "Article/section")
    normalized = tuple(
        " ".join(str(item or "").split()).casefold()
        for item in (economy, indicator, law, article)
    )
    if queue == ReviewItem.Queue.ABSENCE:
        return absence_lookup.get(normalized[:3])
    return lookup.get(normalized)


def _block_reason(row, headers, key_item, queue):
    indexes = _header_index(headers)
    guidance = str(_cell(row, indexes, "Legal-review guidance") or "")
    warnings = str(_cell(row, indexes, "Gate warnings") or "")
    if guidance.startswith("TECHNICAL BLOCK"):
        return guidance
    if queue != ReviewItem.Queue.ABSENCE and key_item and key_item.get("blocked"):
        return warnings or "Engine citation proof marks this finding as blocked."
    return ""


def _cost_for_run(costs, envelope):
    if not isinstance(costs, list):
        return {}
    country = str(envelope.get("country") or "").upper()
    economy_alias = {
        "SG": "Singapore",
        "MY": "Malaysia",
        "MA": "Malaysia",
        "AU": "Australia",
    }
    economy = economy_alias.get(country, country)
    pillar = str(envelope.get("pillar") or "")
    matches = [
        item
        for item in costs
        if str(item.get("economy") or "").casefold() == economy.casefold()
        and str(item.get("pillar") or "") == pillar
    ]
    return matches[-1] if matches else {}


def _snapshot_documents(artifacts):
    documents = artifacts.get("snapshot_artifacts")
    if documents:
        return documents
    # Tests and programmatic callers may provide parsed artifacts directly.
    documents = [
        _serialized_document("legal-review-payload", "review_payload", "generated:legal-review-payload", artifacts["payload"]),
        _serialized_document("finding-key-map", "review_payload", "generated:finding_key_map.json", artifacts["key_map"]),
        _serialized_document("consolidated", "evidence", "submission/consolidated.json", artifacts["consolidated"]),
        _serialized_document("champion-validation", "validation", "reports/champion_validation.json", artifacts["champion"]),
        _serialized_document("cost-report", "runs", "logs/cost_report.json", artifacts["costs"]),
    ]
    for name, envelope in artifacts["runs"].items():
        documents.append(_serialized_document(f"run-{name}", "runs", f"outputs/{name}/output.json", envelope))
    documents.extend(
        [
            _serialized_document("ops-stats", "operations", "generated:ops_stats.json", artifacts.get("ops_stats") or {"schema_version": 1, "generated_at": artifacts["payload"].get("generated_at"), "acquisition": [], "eligibility": [], "extraction": []}),
            _serialized_document("engine-manifest", "manifests", "generated:engine-manifest", artifacts["payload"].get("manifest") or {}),
            _serialized_document("neo4j-graph-snapshot", "validation", "generated:neo4j-read-only-snapshot", artifacts.get("graph_snapshot") or {"status": "unavailable", "origin": "neo4j", "nodes": [], "edges": []}),
        ]
    )
    for code, config in (artifacts.get("configs") or {}).get("jurisdictions", {}).items():
        if "raw_text" in config:
            documents.append(config)
        else:
            documents.append(_serialized_document(f"jurisdiction-{code.lower()}", "configuration", f"configs/jurisdictions/{code.lower()}.yaml", config))
    seeds = (artifacts.get("configs") or {}).get("seeds")
    if seeds:
        documents.append(seeds if "raw_text" in seeds else _serialized_document("seeds", "configuration", "data/seeds.json", seeds))
    return documents


def _validate_ops_stats(payload):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SnapshotImportError("ops_stats.json must use schema_version 1")
    for key in ("acquisition", "eligibility", "extraction"):
        if not isinstance(payload.get(key), list):
            raise SnapshotImportError(f"ops_stats.json field {key!r} must be an array")


def import_snapshot(artifacts=None, *, keep=5):
    artifacts = artifacts or load_engine_artifacts()
    payload = artifacts["payload"]
    sheets = payload.get("sheets") or {}
    required_sheets = [*SHEETS.values(), *REFERENCE_SHEETS.values()]
    missing_sheets = [name for name in required_sheets if name not in sheets]
    if missing_sheets:
        raise SnapshotImportError(
            f"Review payload is missing sheets: {', '.join(missing_sheets)}"
        )

    documents = _snapshot_documents(artifacts)
    ops_document = next((item for item in documents if item["key"] == "ops-stats"), None)
    if ops_document is None:
        raise SnapshotImportError("The immutable ops-stats artifact is missing")
    _validate_ops_stats(ops_document["parsed_json"])

    fingerprint_artifacts = dict(artifacts)
    fingerprint_artifacts.pop("snapshot_artifacts", None)
    fingerprint_artifacts.pop("graph_snapshot", None)
    stable_hashes = {}
    for item in documents:
        if item["key"] == "neo4j-graph-snapshot":
            continue
        if item["key"] in {"legal-review-payload", "ops-stats"} and isinstance(item["parsed_json"], dict):
            stable_value = dict(item["parsed_json"])
            stable_value.pop("generated_at", None)
            stable_hashes[item["key"]] = content_hash(stable_value)
        else:
            stable_hashes[item["key"]] = item["sha256"]
    fingerprint_artifacts["artifact_hashes"] = stable_hashes
    graph_document = next((item for item in documents if item["key"] == "neo4j-graph-snapshot"), None)
    if graph_document:
        graph_stable = dict(graph_document["parsed_json"])
        graph_stable.pop("extracted_at", None)
        graph_stable.pop("nodes", None)
        graph_stable.pop("edges", None)
        fingerprint_artifacts["graph_snapshot"] = graph_stable
    fingerprint_payload = dict(payload)
    fingerprint_payload.pop("generated_at", None)
    fingerprint_artifacts["payload"] = fingerprint_payload
    # A contract salt prevents a pre-D3 snapshot (whose source artifacts are
    # identical but whose reference sheets were not stored) from being reused.
    fingerprint_artifacts["workspace_contract"] = "d6r-artifact-graph-v1"
    source_hash = content_hash(fingerprint_artifacts)
    existing = EngineSnapshot.objects.filter(source_hash=source_hash).first()
    if existing:
        if not existing.active:
            with transaction.atomic():
                EngineSnapshot.objects.filter(active=True).update(
                    active=False, stale=True
                )
                EngineSnapshot.objects.filter(pk=existing.pk).update(
                    active=True, stale=False
                )
                existing.refresh_from_db()
        return existing, False

    lookup, absence_lookup, key_lookup = _finding_lookup(artifacts["key_map"])
    headers_json = {
        queue: list((sheets[name] or {}).get("headers") or [])
        for queue, name in SHEETS.items()
    }
    reference_json = {
        key: {
            "headers": list((sheets[name] or {}).get("headers") or []),
            "rows": list((sheets[name] or {}).get("rows") or []),
        }
        for key, name in REFERENCE_SHEETS.items()
    }
    generated_at = _parse_generated_at(
        payload.get("generated_at") or payload.get("manifest", {}).get("generated_at")
    )

    with transaction.atomic():
        EngineSnapshot.objects.filter(active=True).update(active=False, stale=True)
        snapshot = EngineSnapshot.objects.create(
            schema_version=str(payload.get("schema_version") or "1"),
            generated_at=generated_at,
            source_hash=source_hash,
            bundle_hash=str(
                payload.get("bundle_hash")
                or content_hash(payload.get("artifact_hashes") or fingerprint_artifacts)
            ),
            engine_git_sha=str(payload.get("engine_git_sha") or ""),
            counts_json=payload.get("counts") or {},
            headers_json=headers_json,
            reference_json=reference_json,
            refuter_status=str(payload.get("refuter_status") or ""),
            champion_status=str(artifacts["champion"].get("status") or ""),
            champion_json=artifacts["champion"],
            manifest_json=(
                payload.get("manifest")
                or {"artifact_hashes": payload.get("artifact_hashes") or {}}
            ),
            active=True,
        )

        SnapshotArtifact.objects.bulk_create(
            [
                SnapshotArtifact(
                    snapshot=snapshot,
                    key=document["key"],
                    category=document["category"],
                    source_path=document.get("source_path", ""),
                    media_type=document.get("media_type", "application/json"),
                    byte_size=document.get("byte_size", len(document.get("raw_text", "").encode("utf-8"))),
                    sha256=document["sha256"],
                    raw_text=document.get("raw_text", ""),
                    parsed_json=document.get("parsed_json"),
                    generated_at=generated_at,
                )
                for document in documents
            ]
        )

        review_items = []
        for queue, sheet_name in SHEETS.items():
            sheet = sheets[sheet_name] or {}
            headers = list(sheet.get("headers") or [])
            for position, row in enumerate(sheet.get("rows") or []):
                key_item = None
                stable_key = ""
                finding_key = ""
                if queue in (
                    ReviewItem.Queue.NEW,
                    ReviewItem.Queue.KNOWN,
                    ReviewItem.Queue.ABSENCE,
                ):
                    indexes = _header_index(headers)
                    embedded_key = (
                        row.get("finding_key") or row.get("Finding key")
                        if isinstance(row, dict)
                        else _cell(row, indexes, "Finding key")
                    )
                    key_item = (
                        _match_finding(row, headers, queue, lookup, absence_lookup)
                        if not embedded_key
                        else key_lookup.get(str(embedded_key))
                    )
                    if embedded_key and key_item is None:
                        raise SnapshotImportError(
                            f"Payload finding_key is absent from the proof map: {embedded_key}"
                        )
                    finding_key = str(
                        embedded_key or (key_item or {}).get("finding_key") or ""
                    )
                    stable_key = finding_key
                    if not finding_key:
                        raise SnapshotImportError(
                            f"Could not resolve finding_key for {sheet_name} row {position + 1}"
                        )
                else:
                    indexes = _header_index(headers)
                    if queue == ReviewItem.Queue.RECALL:
                        stable_key = str(_cell(row, indexes, "Recall key") or "")
                        if not stable_key:
                            stable_key = recall_key(
                                _cell(row, indexes, "Economy"),
                                _cell(row, indexes, "Indicator"),
                                _cell(row, indexes, "Master act/instrument"),
                                _cell(row, indexes, "Master citation"),
                            )
                    else:
                        stable_key = zone3_key(
                            _cell(row, indexes, "Economy"),
                            _cell(row, indexes, "Indicator"),
                        )
                reason = _block_reason(row, headers, key_item, queue)
                review_items.append(
                    ReviewItem(
                        snapshot=snapshot,
                        queue=queue,
                        position=position,
                        row_json=row,
                        stable_key=stable_key,
                        finding_key=finding_key,
                        blocked=bool(reason),
                        block_reason=reason,
                        source_hash=content_hash(row),
                    )
                )
        ReviewItem.objects.bulk_create(review_items)

        evidence_rows = []
        for position, row in enumerate(artifacts["consolidated"].get("rows") or []):
            identity = tuple(
                " ".join(str(row.get(key) or "").split()).casefold()
                for key in ("Economy", "Indicator ID", "Law Name", "Article / Section")
            )
            key_item = lookup.get(identity)
            if not key_item:
                raise SnapshotImportError(
                    f"Could not resolve consolidated finding_key: {identity}"
                )
            evidence_rows.append(
                EvidenceRow(
                    snapshot=snapshot,
                    position=position,
                    row_json=row,
                    finding_key=key_item["finding_key"],
                    proof_asset=str(key_item.get("proof_asset") or ""),
                    blocked=bool(key_item.get("blocked")),
                    source_hash=content_hash(row),
                )
            )
        EvidenceRow.objects.bulk_create(evidence_rows)

        RunRecord.objects.bulk_create(
            [
                RunRecord(
                    snapshot=snapshot,
                    run_name=name,
                    envelope_json=envelope,
                    cost_json=_cost_for_run(artifacts["costs"], envelope),
                    source_hash=content_hash(envelope),
                )
                for name, envelope in artifacts["runs"].items()
            ]
        )

        retained_ids = list(
            EngineSnapshot.objects.order_by("-imported_at").values_list(
                "pk", flat=True
            )[:keep]
        )
        EngineSnapshot.objects.exclude(pk__in=retained_ids).filter(
            releases__isnull=True
        ).delete()
    return snapshot, True
