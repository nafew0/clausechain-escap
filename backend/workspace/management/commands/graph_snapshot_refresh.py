import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from workspace.importer import (
    SnapshotImportError,
    _json_document,
    _run_json,
    _serialized_document,
    import_snapshot,
)
from workspace.models import EngineSnapshot


class Command(BaseCommand):
    help = "Refresh only the read-only Neo4j artifact from the active immutable evidence snapshot."

    def handle(self, *args, **options):
        active = EngineSnapshot.objects.filter(active=True).prefetch_related("artifacts").first()
        if active is None:
            raise CommandError("No active engine snapshot exists")
        by_key = {artifact.key: artifact for artifact in active.artifacts.all()}
        required = {"legal-review-payload", "finding-key-map", "consolidated"}
        missing = sorted(required - set(by_key))
        if missing:
            raise CommandError(f"Active snapshot is missing: {', '.join(missing)}")

        payload = by_key["legal-review-payload"].parsed_json
        key_map = by_key["finding-key-map"].parsed_json
        consolidated = by_key["consolidated"].parsed_json
        key_rows = {
            (
                str(row.get("economy") or "").casefold(),
                str(row.get("indicator") or "").casefold(),
                " ".join(str(row.get("law") or "").split()).casefold(),
                " ".join(str(row.get("article") or "").split()).casefold(),
            ): row.get("finding_key")
            for row in key_map.get("rows", [])
        }
        graph_findings = []
        for row in consolidated.get("rows") or []:
            copy = dict(row)
            identity = (
                str(row.get("Economy") or "").casefold(),
                str(row.get("Indicator ID") or "").casefold(),
                " ".join(str(row.get("Law Name") or "").split()).casefold(),
                " ".join(str(row.get("Article / Section") or "").split()).casefold(),
            )
            copy["finding_key"] = key_rows.get(identity)
            graph_findings.append(copy)

        root = Path(settings.ENGINE_ROOT).resolve()
        validation_path = root / "reports" / "graph_validation.json"
        with tempfile.TemporaryDirectory(prefix="clausechain-graph-refresh-") as temp_dir:
            findings_path = Path(temp_dir) / "findings.json"
            findings_path.write_text(json.dumps(graph_findings, ensure_ascii=False), encoding="utf-8")
            try:
                graph_snapshot = _run_json(
                    [
                        str(settings.ENGINE_PYTHON),
                        str(Path(__file__).resolve().parents[2] / "neo4j_snapshot_export.py"),
                        str(root),
                        str(findings_path),
                        str(validation_path),
                    ],
                    cwd=root,
                )
            except SnapshotImportError as exc:
                raise CommandError(str(exc)) from exc

        documents = []
        for artifact in by_key.values():
            if artifact.key == "neo4j-graph-snapshot":
                documents.append(_serialized_document(
                    "neo4j-graph-snapshot", "validation",
                    "generated:neo4j-read-only-snapshot", graph_snapshot,
                ))
            elif artifact.key == "graph-validation":
                documents.append(_json_document(
                    validation_path, key="graph-validation", category="validation",
                    source_path="reports/graph_validation.json",
                ))
            else:
                documents.append({
                    "key": artifact.key,
                    "category": artifact.category,
                    "source_path": artifact.source_path,
                    "media_type": artifact.media_type,
                    "byte_size": artifact.byte_size,
                    "sha256": artifact.sha256,
                    "raw_text": artifact.raw_text,
                    "parsed_json": artifact.parsed_json,
                })

        runs = {
            key.removeprefix("run-"): artifact.parsed_json
            for key, artifact in by_key.items() if key.startswith("run-")
        }
        configs = {
            "jurisdictions": {
                key.removeprefix("jurisdiction-").upper(): artifact.parsed_json
                for key, artifact in by_key.items() if key.startswith("jurisdiction-")
            },
            "seeds": by_key.get("seeds").parsed_json if by_key.get("seeds") else None,
        }
        artifacts = {
            "payload": payload,
            "key_map": key_map,
            "consolidated": consolidated,
            "champion": by_key["champion-validation"].parsed_json,
            "costs": by_key["cost-report"].parsed_json,
            "runs": runs,
            "ops_stats": by_key["ops-stats"].parsed_json,
            "configs": configs,
            "graph_snapshot": graph_snapshot,
            "snapshot_artifacts": documents,
        }
        snapshot, created = import_snapshot(artifacts)
        self.stdout.write(json.dumps({
            "snapshot_id": str(snapshot.pk),
            "source_hash": snapshot.source_hash,
            "created": created,
            "graph_status": graph_snapshot.get("status"),
            "checks": graph_snapshot.get("checks"),
            "resolved_findings": graph_snapshot.get("resolved_findings"),
            "expected_findings": graph_snapshot.get("expected_findings"),
        }, sort_keys=True))
