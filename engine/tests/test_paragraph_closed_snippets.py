from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.verifier.gates import (finalize_snippet_result,
                                     g9_structural_closure)
from packages.core.finalization import review_subject_hash
from packages.core.schemas import MappedFinding
from packages.ingest.expected_anchors import citation_refs


def test_sg_cpc_s34_regression_closes_complete_a_to_c_rule():
    source = (
        "(1) A police officer may issue an order in writing requiring the person "
        "to produce the document or thing, but if the police officer has reason to "
        "believe that the document or thing is likely to be removed, an oral order "
        "may be issued with an order to search where — ( a ) the document is "
        "reasonably suspected of relating to an arrestable offence; ( b ) the "
        "police officer has reason to believe that the document or thing, which he "
        "or she considers to be necessary for his or her investigation, is likely "
        "to be removed; or ( c ) it is not known who possesses the document or "
        "thing which he or she considers to be necessary for his or her investigation. "
        "Explanation 1.—This explanation must not be partially exported."
    )
    claimed = source[:source.index("oral order") + len("oral or")]
    result = finalize_snippet_result(claimed, source)
    assert result.passed
    assert result.text.endswith("necessary for his or her investigation.")
    assert "Explanation" not in result.text
    assert not result.text.endswith("an or")


def test_colon_introduced_list_follows_all_children():
    source = (
        "The record must be retained for the period: (a) seven years for an adult; "
        "(b) until age 25 for a child; and (c) any longer period required by a court. "
        "A separate rule follows."
    )
    result = finalize_snippet_result("The record must be retained for the period:", source)
    assert result.text.endswith("required by a court.")
    assert "(c)" in result.text
    assert result.closure_code == "PASS_CLOSED"


def test_nested_list_does_not_close_at_first_child_sentence():
    source = (
        "The controller must ensure that: (a) where consent applies: (i) consent is "
        "recorded. (ii) consent can be withdrawn. (b) every exception is recorded. "
        "The next subsection begins."
    )
    result = finalize_snippet_result("The controller must ensure that:", source)
    assert result.text.endswith("every exception is recorded.")
    assert "(ii)" in result.text and "(b)" in result.text


@pytest.mark.parametrize("ending", ["and", "or"])
def test_dangling_connector_follows_to_full_stop(ending):
    source = f"The officer may inspect records {ending} copy the records for the investigation."
    result = finalize_snippet_result(f"The officer may inspect records {ending}", source)
    assert result.passed and result.text.endswith("investigation.")


def test_unmatched_structure_is_blocked():
    source = "The officer may inspect (records and copy data"
    result = finalize_snippet_result(source, source)
    assert result.closure_code == "FAIL_UNBALANCED_STRUCTURE"
    assert g9_structural_closure(result).status == "FAIL"


def test_legislative_abbreviations_and_decimals_are_not_sentence_stops():
    source = (
        "Under s. 474.17 and Art. 2.1, No. 8 applies to the regulated person. "
        "The next sentence is outside the rule."
    )
    result = finalize_snippet_result("Under s. 474.17", source)
    assert result.text.endswith("regulated person.")


def test_fragment_expands_to_containing_labelled_paragraph():
    source = (
        "Section heading without punctuation (1) The authorised officer may inspect "
        "the complete record for an investigation. (2) A separate power applies."
    )
    result = finalize_snippet_result("officer may inspect", source)
    assert result.passed
    assert result.text.startswith("(1) The authorised officer")
    assert result.text.endswith("for an investigation.")
    assert "Section heading" not in result.text


def test_closed_passage_between_soft_and_hard_limits_passes_long():
    source = "The controller must " + ("retain every audit record and " * 35) + "finish the audit."
    result = finalize_snippet_result("The controller must", source)
    assert 700 < len(result.text) < 3000
    assert result.closure_code == "PASS_LONG_BUT_CLOSED"
    assert g9_structural_closure(result).status == "PASS"


def test_closed_passage_over_hard_limit_is_blocked_without_truncation():
    source = "The controller must " + ("retain every audit record and " * 120) + "finish the audit."
    result = finalize_snippet_result("The controller must", source)
    assert len(result.text) > 3000 and result.text == source
    assert result.closure_code == "FAIL_CLOSURE_OVER_HARD_LIMIT"


def test_review_subject_changes_when_mapping_rationale_changes():
    finding = MappedFinding(Economy="Singapore", **{
        "Law Name": "Example Act", "Indicator ID": "P7-I1",
        "Article / Section": "s. 1", "Discovery Tag": "NEW",
        "Location Reference": "#s1", "Verbatim Snippet": "The duty applies.",
        "Mapping Rationale": "Establishes the duty.",
        "Source URL": "https://official.example/act", "Confidence": 0.9,
        "Status": "in_force",
    })
    first = review_subject_hash(finding)
    finding.mapping_rationale = "Establishes a materially different duty."
    assert review_subject_hash(finding) != first


def test_expected_anchor_citation_lists_expand_without_parenthetical_range_noise():
    assert citation_refs("ss. 245(3), 341(2), 531(2)") == [
        "s. 245(3)", "s. 341(2)", "s. 531(2)"
    ]
    assert citation_refs("Sch. 1, cl. 14(a)–(h)") == ["Sch 1, cl. 14(a)"]


def test_current_run_artifacts_never_emit_open_snippets():
    root = Path(__file__).resolve().parents[1]
    for path in sorted((root / "outputs").glob("final_*/output.json")):
        payload = json.loads(path.read_text())
        for row in payload.get("findings", []):
            snippet = row.get("Verbatim Snippet", "")
            if "NO_EVIDENCE_FOUND" in snippet:
                continue
            proof = row.get("citation_proof") or {}
            gates = [gate for gate in proof.get("gate_results", [])
                     if gate.get("gate_id") == "G9"]
            assert gates, f"{path}: {row.get('Article / Section')} lacks G9"
            assert gates[-1].get("metadata", {}).get("closure_code") in {
                "PASS_CLOSED", "PASS_LONG_BUT_CLOSED"
            }
            assert snippet.rstrip().endswith((".", "!", "?"))
