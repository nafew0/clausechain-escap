"""Regression suite from DoDont §13's worked-example bank (P3-F).

Every ❌ trap ESCAP demonstrated becomes a deterministic test against our gates —
these are the exact failures the judges showed teams missing.
"""
from __future__ import annotations

from packages.core.schemas import MappedFinding
from packages.discovery.diff import section_matches
from packages.verifier.gates import (g1_span_exists, g5_whole_rule, g7_ban_vs_conditional,
                                     g7_indicator_fit)


def _finding(indicator: str, law: str = "Personal Data Protection Act 2012",
             article: str = "s. 26(1)") -> MappedFinding:
    return MappedFinding(
        economy="Singapore", law_name=law, indicator_id=indicator,
        article_section=article, discovery_tag="KNOWN", location_reference="#pr26-",
        verbatim_snippet="x", mapping_rationale="x", source_url="https://sso.agc.gov.sg/x",
        confidence=0.9)


def test_w2_hallucinated_quote_fails_g1():
    """§13 W2: 'IT Act s.70B(1)' text that does not exist in the source."""
    source = "70B. The agency shall serve as the national nodal agency."
    fake = "70B(4) may impose penalties for non-compliance with directions"
    assert g1_span_exists(fake, source).status == "FAIL"
    assert g1_span_exists("national nodal agency", source).status == "PASS"


def test_w6_lost_exception_kills_the_false_ban():
    """§13 W6: dropping the 'unless' turns 6.4 into a false 6.1 — two layers catch it."""
    full = "must not transfer personal data outside Singapore unless prescribed requirements are met"
    snippet = "must not transfer personal data outside Singapore"
    # layer 1: G5 whole-rule fails the ban row
    assert g5_whole_rule("P6-I1", snippet, full).status == "FAIL"
    # layer 2: if both mappings exist, the 6.1 row is dropped deterministically
    kept, gates = g7_ban_vs_conditional([_finding("P6-I1"), _finding("P6-I4")])
    assert [f.indicator_id for f in kept] == ["P6-I4"]
    assert gates and gates[0].gate_id == "G7"


def test_w4_style_business_transfer_never_a_data_transfer():
    """P2 scale-regression trap: bank BUSINESS transfers leaked into P6-I4."""
    text = ("The transferor must transfer the whole or any part of its business to the "
            "transferee under a scheme approved by the Minister.")
    assert g7_indicator_fit("P6-I4", text[:120], text, "Banking Act 1970").status == "FAIL"


def test_gold_parent_code_clause_matches_nested_provision_only():
    assert section_matches("3", "3.5.14")
    assert section_matches("4.10", "4.10.3")
    assert not section_matches("3", "30.1")


def test_bill_as_measure_hard_fails():
    """DoDont §4: drafts/bills are never recordable (MY inventory cites one)."""
    r = g7_indicator_fit("P6-I4", "transfer outside Malaysia", "x",
                         "Personal Data Protection Bill 2024")
    assert r.status == "FAIL"


def test_w5_confidentiality_is_not_localization():
    """§13 W5: a banking confidentiality duty is not a transfer ban/condition."""
    text = ("An officer of the bank must not disclose customer information to any "
            "other person except as expressly provided in this Act.")
    # no cross-border transfer language -> the P6 fit gate rejects it
    assert g7_indicator_fit("P6-I1", text[:100], text, "Banking Act 1970").status == "FAIL"


def test_e4_consolidation_preserves_provenance(tmp_path, monkeypatch):
    """P3.5 E4: consolidated JSON must retain JSON-only provenance/reviewer fields."""
    import csv as _csv
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path as _P

    run = tmp_path / "run1"
    run.mkdir()
    finding = {"Economy": "Singapore", "Indicator ID": "P6-I4", "Law Name": "X Act",
               "Article / Section": "s. 1(1)", "Discovery Tag": "KNOWN",
               "Location Reference": "#pr1-", "Verbatim Snippet": "text",
               "Mapping Rationale": "r", "Source URL": "https://x", "Confidence": 0.9,
               "Notes": "", "archived_copy": "data/raw/x.html", "access_date": "2026-07-10",
               "status_evidence": "portal asserts current", "reviewer_decision": "pending",
               "citation_tier": "[verify-pinpoint]", "source_artifact_id": "sha256:" + "a" * 64,
               "citation_proof": {"source_artifact_id": "sha256:" + "a" * 64,
                    "source_sha256": "a" * 64, "page_number": 1, "anchor": None,
                    "article_path": ["section 1", "item (1)"], "span_ids": ["span-1"],
                    "bboxes": [[1, 2, 3, 4]], "exact_snippet": "text",
                    "normalized_snippet": "text", "alignment_status": "exact",
                    "alignment_score": 1.0, "gate_results": [],
                    "verified_at": "2026-07-10T00:00:00Z"}}
    (run / "output.json").write_text(_json.dumps({"findings": [finding]}))
    with (run / "output.csv").open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=[k for k in finding if k[0].isupper()])
        w.writeheader()
        w.writerow({k: v for k, v in finding.items() if k[0].isupper()})
    (run / "final_output.csv").write_text((run / "output.csv").read_text())

    monkeypatch.chdir(tmp_path)
    engine_root = _P(__file__).resolve().parents[1]
    subprocess.run([_sys.executable, str(engine_root / "scripts/consolidate_submission.py"),
                    str(run)], check=True, cwd=tmp_path)
    data = _json.loads((tmp_path / "submission/consolidated.json").read_text())
    row = data["rows"][0]
    for field in ("archived_copy", "access_date", "status_evidence",
                  "reviewer_decision", "citation_tier", "source_artifact_id",
                  "citation_proof"):
        assert field in row, f"consolidation dropped {field}"
