"""Targeted, generic PDF realignment for one already-ingested instrument.

This is a safe remediation route for a typography/alignment-engine upgrade: it
loads only evidence-ineligible ``unaligned-review`` units, reconstructs exact
page/span proof from the archived PDFs, and promotes only newly exact matches.
It never performs fuzzy matching and never changes units that remain unaligned.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.schemas import RuleUnit
from packages.extractors.pdf import extract_pdf, materialize_page_evidence
from packages.extractors.pdf_align import align_and_bind_pdf_evidence
from packages.graph.sqlite_graph import SqliteGraphStore


def _unit(props: dict) -> RuleUnit:
    metadata = dict(props.get("metadata") or {})
    return RuleUnit(
        id=str(props["id"]).removeprefix("provision:"),
        document_id=str(metadata.get("compilation") or props.get("compilation_bundle_id") or "document"),
        economy=props["economy"], law_name=props["law_name"],
        law_number_ref=props.get("law_number_ref"), last_amended=props.get("last_amended"),
        article_section=props["article_section"], text=props["text"],
        source_url=props["source_url"], location_reference=props["location_reference"],
        start_char=props.get("start_char"), end_char=props.get("end_char"),
        extraction_confidence=props.get("confidence"), metadata=metadata,
        source_artifact_id=props.get("source_artifact_id"),
        raw_context=props.get("raw_context") or props["text"],
        linked_span_ids=list(props.get("linked_span_ids") or []),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--economy", required=True)
    parser.add_argument("--law", required=True)
    parser.add_argument("--pdf", action="append", required=True,
                        help="Archived PDF in volume order; repeat for multiple volumes")
    parser.add_argument("--alignment-version", default="2026-07-20.10")
    args = parser.parse_args()

    store = SqliteGraphStore()
    conn = store._connect()
    rows = conn.execute(
        "SELECT props FROM nodes WHERE label='Provision' "
        "AND json_extract(props,'$.economy')=? AND json_extract(props,'$.law_name')=? "
        "AND COALESCE(json_extract(props,'$.pdf_alignment'),"
        "json_extract(props,'$.metadata.pdf_alignment'),'')<>'exact'",
        (args.economy, args.law),
    ).fetchall()
    units = [_unit(json.loads(row[0])) for row in rows]
    if not units:
        print("0 unresolved units; nothing to realign")
        return 0

    pages_by_volume = []
    page_records_by_volume = []
    spans_by_volume = []
    artifact_by_volume = []
    for pdf_arg in args.pdf:
        pdf = str(Path(pdf_arg))
        artifact_row = conn.execute(
            "SELECT payload FROM source_artifacts "
            "WHERE json_extract(payload,'$.local_path')=?",
            (pdf,),
        ).fetchone()
        if not artifact_row:
            raise RuntimeError(f"No immutable SourceArtifact for {pdf}")
        artifact = json.loads(artifact_row[0])
        pages = extract_pdf(pdf)
        page_records, spans = materialize_page_evidence(pages, artifact["id"])
        pages_by_volume.append(pages)
        page_records_by_volume.append(page_records)
        spans_by_volume.append(spans)
        artifact_by_volume.append(artifact)

    aligned, total = align_and_bind_pdf_evidence(
        units, args.pdf, spans_by_volume, pages_by_volume,
    )
    promoted = []
    for unit in units:
        if unit.metadata.get("pdf_alignment") != "exact":
            continue
        volume = int(unit.metadata.get("alignment_volume") or 1)
        artifact = artifact_by_volume[volume - 1]
        unit.source_artifact_id = artifact["id"]
        unit.metadata.update({
            "archived_copy": artifact["local_path"],
            "content_sha256": artifact["sha256"],
            "alignment_engine_version": args.alignment_version,
            "evidence_eligible": unit.metadata.get("legal_status") == "in_force",
        })
        promoted.append(unit)

    for records, spans in zip(page_records_by_volume, spans_by_volume, strict=True):
        store.upsert_page_artifacts(records)
        store.upsert_text_spans(spans)
    store.upsert_rule_units(promoted)
    print(f"{args.law}: {aligned}/{total} unresolved units realigned; "
          f"{len(promoted)} promoted to exact page/span proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
