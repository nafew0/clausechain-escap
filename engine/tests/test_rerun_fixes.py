"""19 Jul rerun fixes: snippet extension, Malay refs, treaty grammar, screen cap."""
from __future__ import annotations

from packages.core.schemas import ExtractedPage
from packages.extractors.pdf_act import (TREATY_SECTION_PATTERNS,
                                         _repair_ocr_section_labels,
                                         parse_act_text)
from packages.ingest.known_index import extract_refs
from packages.verifier.gates import extend_to_clause_boundary
from packages.providers.ocr_provider import _tesseract_lines


def test_snippet_extends_to_operative_object_phrase():
    """The N012 case: span stopped at '...search to be made' — must extend."""
    source = ("A police officer investigating an arrestable offence may, without a "
              "search warrant, search or cause a search to be made for a document or "
              "other thing in any place where he or she has reason to believe the "
              "document or thing is located; and such search must be recorded. "
              "(2) The police officer must conduct the search in person.")
    cut = ("A police officer investigating an arrestable offence may, without a "
           "search warrant, search or cause a search to be made")
    extended = extend_to_clause_boundary(cut, source)
    assert "for a document or other thing" in extended
    assert extended.endswith("such search must be recorded.")
    # already-complete snippets are untouched
    done = "The record must be retained for 3 years."
    assert extend_to_clause_boundary(done, done + " (2) More text.") == done


def test_malay_citation_forms_extract():
    refs = extract_refs("Menurut Seksyen 12A(1), dan Perkara 5 serta peraturan 4 ...")
    assert "s. 12A(1)" in refs
    assert "Art. 5" in refs
    assert "reg. 4" in refs


def test_tesseract_preserves_layout_lines_for_section_parser():
    data = {
        "text": ["Search", "by", "police", "116.", "(1)", "Whenever"],
        "block_num": [1, 1, 1, 2, 2, 2],
        "par_num": [1, 1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1, 2],
    }
    assert _tesseract_lines(data) == "Search by police\n116. (1)\nWhenever"


def test_ocr_section_suffix_repair_uses_neighbour_sequence():
    lines = [(1, "116a. First"), (2, "116s. Middle"), (3, "116c. Third")]
    assert [line for _, line in _repair_ocr_section_labels(lines)] == [
        "116A. First", "116B. Middle", "116C. Third"
    ]


def test_treaty_article_grammar_parses():
    page = ExtractedPage(
        document_id="t", page_number=1, source_url="https://x", location_reference="page 1",
        text=("Article 14.11: Cross-Border Transfer of Information by Electronic Means\n"
              "Each Party shall allow the cross-border transfer of information by electronic "
              "means, including personal information, when this activity is for the conduct "
              "of the business of a covered person.\n"
              "Article 14.12: Location of Computing Facilities\n"
              "No Party shall require a covered person to use or locate computing facilities "
              "in that Party's territory as a condition for conducting business there."))
    units = parse_act_text([page], "Singapore", "CPTPP Chapter 14", "CPTPP14", "https://x",
                           extra_section_patterns=TREATY_SECTION_PATTERNS,
                           citation_template="Art. {label}")
    cites = {u.article_section for u in units}
    assert "Art. 14.11" in cites and "Art. 14.12" in cites


def test_treaty_grammar_accepts_bare_heading_and_rejects_wrapped_cross_reference():
    page = ExtractedPage(
        document_id="t", page_number=1, source_url="https://x", location_reference="page 1",
        text=("Article 12.3: Scope\nThe Chapter applies to electronic commerce.\n"
              "Article 12.14 (Location of Computing Facilities) and Article 12.15\n"
              "shall not apply to government information.\n"
              "Article 12.14: Location of Computing Facilities\n"
              "A Party shall not require local computing facilities.\n"
              "Article 12A.1: Annex application\n"
              "This Annex applies to the listed procedures.\n"
              "ARTICLE 13\nExpress Shipments\n"
              "Each Party shall maintain expedited procedures."),
    )
    units = parse_act_text(
        [page], "Singapore", "Digital agreement", "DA", "https://x",
        extra_section_patterns=TREATY_SECTION_PATTERNS,
        citation_template="Art. {label}",
    )
    citations = [unit.article_section for unit in units]
    assert citations == ["Art. 12.3", "Art. 12.14", "Art. 12A.1", "Art. 13"]
    article = next(unit for unit in units if unit.article_section == "Art. 12.14")
    assert article.text.startswith("Article 12.14: Location")


def test_screen_cap_default_raised():
    from packages.rdtii.mapper import SCREEN_CAP_PER_INDICATOR

    assert SCREEN_CAP_PER_INDICATOR >= 200


def test_zone3_gold_tripwire():
    """Any det-vs-master-gold divergence must auto-flag (the Z005 lesson: even a
    unanimous persona panel can be wrong; the answer key is the tripwire)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.zone3_score import deterministic_score, master_gold_scores

    gold = master_gold_scores("Australia")
    assert gold.get("P7-I1") == 0.0  # AU has the Privacy Act — master agrees
    det, _ = deterministic_score("P7-I1", [])  # thin evidence -> det claims 1
    assert abs(det - gold["P7-I1"]) > 0.01  # divergence detected -> would flag
