from __future__ import annotations

from packages.ingest.known_index import (classify_ref_mentions, expected_anchors, extract_refs,
                                         indicator_code, master_anchor_expected,
                                         normalize_law_name)


def test_extract_refs_articles_and_sections() -> None:
    text = (
        "Article 18 of the amended Patent Law establishes ... and under s. 245(2) "
        "and Section 17 records must be kept; Code Section 3.5.14 applies; "
        "see also Regulation 5 and Schedule 1."
    )
    refs = extract_refs(text)
    assert "Art. 18" in refs
    assert "s. 245(2)" in refs
    assert "s. 17" in refs
    assert "s. 3.5.14" in refs
    assert "reg. 5" in refs
    assert "Sch. 1" in refs


def test_extract_refs_empty() -> None:
    assert extract_refs("") == []
    assert extract_refs("No provisions are mentioned here.") == []


def test_indicator_code_from_number_and_name() -> None:
    assert indicator_code("6.4") == "P6-I4"
    assert indicator_code("Indicator 7.3 (minimum retention)") == "P7-I3"
    assert indicator_code("Conditional flow regimes") == "P6-I4"
    assert indicator_code("Lack of dedicated legal framework for cybersecurity") == "P7-I2"
    assert indicator_code("Ban & local processing requirements") == "P6-I1"
    assert indicator_code("not an indicator") is None


def test_normalize_law_name() -> None:
    assert normalize_law_name("Personal Data Protection Act 2012 (PDPA)") == \
        normalize_law_name("personal data protection act 2012")
    assert normalize_law_name("Cyber Security Act (Act 854) 2024") == "cyber security act 2024"


def test_score_zero_presence_indicator_does_not_force_positive_anchor() -> None:
    assert not master_anchor_expected("P7-I3", "0")
    assert not master_anchor_expected("P6-I1", "0")
    # Framework indicators are reverse-polarity: score 0 means the framework exists.
    assert master_anchor_expected("P7-I1", "0")
    assert master_anchor_expected("P7-I2", "0")


def test_master_definition_reference_is_not_an_operative_anchor() -> None:
    impact = (
        "According to Section 199, every company must keep accounting records for 5 years. "
        "Accounting records refers to working papers and documents (Section 4)."
    )
    mentions = classify_ref_mentions(impact, "Companies Act 1967", "P7-I3", "1")
    roles = {m["ref"]: m["role"] for m in mentions}
    assert roles["s. 199"] == "operative"
    assert roles["s. 4"] == "definition"
    entry = {"indicator_code": "P7-I3", "score": "1", "ref_mentions": mentions}
    assert [a["ref"] for a in expected_anchors(entry)] == ["s. 199"]


def test_regulations_year_is_an_instrument_title_not_a_provision() -> None:
    mentions = classify_ref_mentions(
        "The Telecommunications Regulations 2021 enables provider cooperation.",
        "Telecommunications Regulations 2021", "P7-I5", "1")
    assert mentions[0]["ref"] == "reg. 2021"
    assert mentions[0]["role"] == "instrument_title"


def test_combined_act_reference_gets_nearby_instrument_hint() -> None:
    acts = ("Australian Security Intelligence Organisation Act 1979; "
            "Surveillance Legislation Amendment (Identify and Disrupt) Act 2021")
    impact = ("The Australian Security Intelligence Organisation Act 1979 includes a computer "
              "access warrant under Section 25A. The Surveillance Legislation Amendment "
              "(Identify and Disrupt) Act 2021 creates data disruption powers in Schedule 3.")
    mentions = classify_ref_mentions(impact, acts, "P7-I5", "1")
    by_ref = {m["ref"]: m for m in mentions}
    assert by_ref["s. 25A"]["laws_norm"] == [
        normalize_law_name("Australian Security Intelligence Organisation Act 1979")]
    # amendment-first, principal appended (consolidation fallback, 15 Jul): the
    # corpus holds consolidated acts, so an amendment-only binding never matches.
    sch3 = by_ref["Sch. 3"]["laws_norm"]
    assert sch3[0] == normalize_law_name(
        "Surveillance Legislation Amendment (Identify and Disrupt) Act 2021")
    assert normalize_law_name(
        "Australian Security Intelligence Organisation Act 1979") in sch3


def test_law_hint_prefers_specific_instrument_over_shared_name_prefix() -> None:
    acts = ("Telecommunications Act 1997; "
            "Telecommunications (Interception and Access) Act 1979; "
            "Telecommunications Regulations 2021")
    impact = ("The Telecommunications (Interception and Access) Act 1979 permits access "
              "under Section 10 by authorised officers.")
    mention = classify_ref_mentions(impact, acts, "P7-I5", "1")[0]
    assert mention["laws_norm"] == [
        normalize_law_name("Telecommunications (Interception and Access) Act 1979")]


def test_conditional_transfer_if_colon_is_an_operative_anchor() -> None:
    impact = ("Section 129 (Cross-border data transfers) prescribes that personal data "
              "shall be transferred to any location outside Malaysia if: safeguards apply.")
    mention = classify_ref_mentions(
        impact, "Personal Data Protection Act 2010", "P6-I4", "1")[0]
    assert mention["role"] == "operative"


def test_amendment_only_hint_retains_principal_act():
    """The s. 26 trap (15 Jul regression): an anchor bound ONLY to an Amendment
    Act can never match the corpus — amendments consolidate into the principal.
    """
    from packages.ingest.known_index import classify_ref_mentions

    cell = "Personal Data Protection Act 2012;\n\nPersonal Data Protection (Amendment) Act 2020"
    prose = ("s. 26 provides that an organisation must not transfer personal data outside "
             "Singapore except in accordance with prescribed requirements. This section was "
             "updated by the Personal Data Protection (Amendment) Act 2020.")
    mentions = classify_ref_mentions(prose, cell, "P6-I4", "1")
    anchor = next(m for m in mentions if m["ref"] == "s. 26")
    assert "personal data protection act 2012" in anchor["laws_norm"], anchor["laws_norm"]
