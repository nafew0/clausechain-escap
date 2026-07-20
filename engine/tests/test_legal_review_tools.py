from scripts.build_legal_workbook import (
    _alignment_label,
    _official_urls,
    _recall_rationale,
    _surrounding_context,
)
from scripts.refute_new import _panel_prompt


def test_workbook_uses_canonical_provenance_fields():
    finding = {
        "raw_context": "full source context",
        "Notes": "discovery note only",
        "citation_proof": {"alignment_status": "exact", "alignment_score": 1.0},
    }
    assert _alignment_label(finding) == "exact (1.0)"
    assert _surrounding_context(finding) == "full source context"


def test_master_known_urls_use_reference_list():
    assert _official_urls({
        "references": ["https://official.example/a", "https://official.example/b"],
    }) == "https://official.example/a\nhttps://official.example/b"


def test_recall_rationale_is_human_readable():
    miss = {
        "class": "MAPPING",
        "proposed_verdict": "LEGAL_MAPPING_REVIEW",
        "evidence": {"technical_class": "IN_CORPUS_NOT_EMITTED"},
    }
    rationale = _recall_rationale(miss)
    assert "exists in the corpus" in rationale
    assert not rationale.startswith("{")


def test_refuter_prompt_contains_full_rubric_context_and_source_context():
    cfg = {
        "name": "Minimum period of data retention requirements",
        "question": "Must data be kept for at least a specified period?",
        "scoring": {"1": "A minimum period is specified."},
        "exclusions": ["No-longer-than-necessary is a ceiling."],
        "hunt_in": ["Sectoral law: tax, companies, health."],
    }
    finding = {
        "Indicator ID": "P7-I3",
        "Law Name": "Companies Act",
        "Article / Section": "s. 1",
        "Verbatim Snippet": "retain the records for 7 years",
        "raw_context": "A company shall retain the records for 7 years after closure.",
        "Mapping Rationale": "Minimum retention duty.",
        "citation_proof": {
            "alignment_status": "exact",
            "alignment_score": 1.0,
            "gate_results": [],
        },
    }
    prompt = _panel_prompt(finding, cfg)
    assert "Sectoral law: tax, companies, health." in prompt
    assert "A minimum period is specified." in prompt
    assert finding["raw_context"] in prompt
    assert "Sectoral evidence is NOT a defect" in prompt
