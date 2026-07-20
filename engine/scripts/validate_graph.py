from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.core.evidence import verify_artifact  # noqa: E402
from packages.core.legal_controls import evidence_eligibility  # noqa: E402
from packages.core.schemas import SourceArtifact  # noqa: E402
from packages.graph.sqlite_graph import GRAPH_SCHEMA_VERSION, SqliteGraphStore  # noqa: E402


def main() -> int:
    db = Path(sys.argv[1] if len(sys.argv) > 1 else "data/graph_v2.db")
    # Apply the supported additive v2 -> v3 migration before raw SQL validation.
    SqliteGraphStore(db).schema_version()
    conn = sqlite3.connect(db); errors = []
    version_row = conn.execute(
        "select value from graph_metadata where key='schema_version'"
    ).fetchone()
    schema_version = int(version_row[0]) if version_row else None
    if schema_version != GRAPH_SCHEMA_VERSION:
        errors.append(f"graph schema version {schema_version} != {GRAPH_SCHEMA_VERSION}")
    artifacts = {r[0]: SourceArtifact.model_validate_json(r[1])
                 for r in conn.execute("select id,payload from source_artifacts")}
    for artifact in artifacts.values():
        try:
            verify_artifact(artifact)
        except Exception as error:
            errors.append(f"artifact {artifact.id}: {error}")
    au_bundles: dict[str, set[str]] = {}
    for artifact in artifacts.values():
        bundle = artifact.metadata.get("compilation_bundle_id")
        role = artifact.metadata.get("authority_role")
        if bundle:
            au_bundles.setdefault(str(bundle), set()).add(str(role))
    for bundle, roles in au_bundles.items():
        if roles != {"quotation_authority", "structure_oracle"}:
            errors.append(f"AU compilation bundle {bundle} has incomplete authority roles: {sorted(roles)}")
    counts = {}
    rows = conn.execute("select json_extract(props,'$.economy'),props from nodes where label='Provision'")
    for economy, props_json in rows:
        props = json.loads(props_json); counts[economy] = counts.get(economy, 0) + 1
        eligible, reason = evidence_eligibility(props.get("law_name", ""),
                                                props.get("source_type") or "act",
                                                props.get("legal_status", "unknown"))
        if not eligible:
            errors.append(f"ineligible provision {props.get('id')}: {reason}")
        if props.get("evidence_eligible") is not True:
            errors.append(f"provision {props.get('id')} is present but not evidence eligible")
        if not props.get("source_artifact_id") or props.get("source_artifact_id") not in artifacts:
            errors.append(f"provision {props.get('id')} lacks SourceArtifact")
        if not props.get("content_sha256"):
            errors.append(f"provision {props.get('id')} lacks source hash")
        if economy == "Australia":
            # Source-class-aware contract (Sol review #4b, 19 Jul): the EPUB+PDF
            # compilation-bundle requirement applies to Federal Register
            # compilations only. State-register acts and treaty PDFs are direct
            # official PDFs — their integrity contract is exact PDF alignment.
            artifact = artifacts.get(props.get("source_artifact_id"))
            source_host = ""
            if artifact is not None:
                from urllib.parse import urlparse
                source_host = (urlparse(getattr(artifact, "retrieved_url", "")
                                        or getattr(artifact, "original_url", "")).hostname or "")
            federal = source_host.endswith("legislation.gov.au")
            if federal:
                if not props.get("structure_artifact_id") or props.get("structure_artifact_id") not in artifacts:
                    errors.append(f"AU provision {props.get('id')} lacks structure SourceArtifact")
                if not props.get("compilation_bundle_id"):
                    errors.append(f"AU provision {props.get('id')} lacks compilation bundle")
            elif props.get("pdf_alignment") != "exact":
                errors.append(f"AU non-federal provision {props.get('id')} lacks exact PDF alignment")
    report = {"status": "FAIL" if errors else "PASS", "provisions": counts,
              "source_artifacts": len(artifacts), "schema_version": schema_version,
              "errors": errors}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/graph_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({**report, "errors": errors[:20]}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__": raise SystemExit(main())
