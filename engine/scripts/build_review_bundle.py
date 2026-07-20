"""Build a static source-to-row review bundle and unsigned decision template."""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.core.finalization import finding_key  # noqa: E402
from packages.core.schemas import MappedFinding, SourceArtifact  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--candidates", default="submission/consolidated.json")
    p.add_argument("--graph", default="data/graph_v2.db"); p.add_argument("--out", default="submission/review")
    args = p.parse_args(); out = Path(args.out); assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    findings = [MappedFinding.model_validate(r) for r in json.loads(Path(args.candidates).read_text())["rows"]]
    conn = sqlite3.connect(args.graph)
    artifacts = {r[0]: SourceArtifact.model_validate_json(r[1])
                 for r in conn.execute("SELECT id,payload FROM source_artifacts")}
    cards, decisions = [], []
    expected_assets: set[Path] = set()
    for i, finding in enumerate(findings, 1):
        key = finding_key(finding); proof = finding.citation_proof; artifact = artifacts.get(finding.source_artifact_id or "")
        image_rel = None
        if artifact and proof and proof.page_number and Path(artifact.local_path).suffix.lower() == ".pdf":
            with fitz.open(artifact.local_path) as doc:
                page = doc[proof.page_number - 1]
                shape = page.new_shape()
                for box in proof.bboxes:
                    shape.draw_rect(fitz.Rect(box)); shape.finish(color=(1, 0, 0), width=1.5)
                shape.commit()
                image_rel = f"assets/{key}.png"
                image_path = out / image_rel
                expected_assets.add(image_path)
                page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(image_path)
        status = finding.status_evidence_record.model_dump(mode="json") if finding.status_evidence_record else None
        gates = proof.gate_results if proof else []
        coverage = (finding.search_coverage_manifest.model_dump(mode="json")
                    if finding.search_coverage_manifest else None)
        cards.append(f"""<article><h2>{i}. {html.escape(finding.indicator_id)} · {html.escape(finding.article_section)}</h2>
<p><b>Finding key:</b> <code>{key}</code></p><p><b>Law:</b> {html.escape(finding.law_name)} · <b>Tag:</b> {finding.discovery_tag}</p>
<p><a href="{html.escape(finding.source_url)}">Official source</a> · <b>Status:</b> {finding.status}</p>
<blockquote>{html.escape(finding.verbatim_snippet)}</blockquote>
<p><b>Context:</b> {html.escape(finding.raw_context or '')}</p><p><b>Rationale:</b> {html.escape(finding.mapping_rationale)}</p>
<p><b>Discovery comparison:</b> {html.escape(finding.discovery_tag)} · <b>Citation path:</b> {html.escape(' › '.join(proof.article_path) if proof else 'unresolved')}</p>
{f'<img src="{image_rel}" alt="Highlighted source page">' if image_rel else '<p><b>No page highlight:</b> anchor/absence/unresolved proof.</p>'}
<details><summary>Status evidence</summary><pre>{html.escape(json.dumps(status, indent=2))}</pre></details>
<details><summary>Search coverage / absence proof</summary><pre>{html.escape(json.dumps(coverage, indent=2))}</pre></details>
<details><summary>Deterministic gates</summary><pre>{html.escape(json.dumps(gates, indent=2))}</pre></details></article>""")
        decisions.append({"finding_key": key, "review": {"decision": "rejected",
            "reviewer_name": "", "reviewer_role": "", "reviewed_at": "",
            "citation_checked": False, "mapping_checked": False, "status_checked": False,
            "citation_reviewer_name": "", "mapping_reviewer_name": "",
            "status_reviewer_name": "",
            "correction_note": "UNSIGNED TEMPLATE — change only after human review"}})
    (out / "index.html").write_text("<!doctype html><meta charset=utf-8><title>ClauseChain Review</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:auto}article{border-bottom:2px solid #ddd;padding:24px 0}"
        "img{max-width:100%;border:1px solid #999}blockquote{background:#f5f5f5;padding:16px}pre{white-space:pre-wrap}</style>"
        + "".join(cards), encoding="utf-8")
    (out / "decisions.template.json").write_text(json.dumps(decisions, indent=2) + "\n")
    # Review images are a derived, content-addressed cache. Remove images that
    # no longer correspond to the current candidate set while leaving any
    # non-generated files in the assets directory untouched.
    for image_path in assets.glob("*.png"):
        if image_path not in expected_assets:
            image_path.unlink()
    print(f"review bundle: {len(findings)} rows -> {out / 'index.html'}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
