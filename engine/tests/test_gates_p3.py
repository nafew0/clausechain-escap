from __future__ import annotations

from packages.verifier.gates import (citation_tier, g2_location, g5_whole_rule,
                                     g4_currentness, g6_meaning_support, g7_indicator_fit,
                                     g8_counter_and_dangling)

BAN_WITH_EXCEPTION = ("An organisation must not transfer any personal data outside Singapore "
                      "unless the prescribed requirements are met.")


def test_g2_anchor_must_match_section():
    assert g2_location("s. 26(1)", "#pr26-").status == "PASS"
    assert g2_location("s. 27(1)", "#pr26-").status == "FAIL"
    assert g2_location("s. 129(1)", "page 42").status == "PASS"


def test_g5_ban_with_exception_outside_snippet_fails():
    snippet = "An organisation must not transfer any personal data outside Singapore"
    assert g5_whole_rule("P6-I1", snippet, BAN_WITH_EXCEPTION).status == "FAIL"
    # snippet that carries the exception passes
    assert g5_whole_rule("P6-I1", BAN_WITH_EXCEPTION, BAN_WITH_EXCEPTION).status == "PASS"
    # non-ban indicators only warn
    assert g5_whole_rule("P6-I4", snippet, BAN_WITH_EXCEPTION).status == "WARN"


def test_g6_permissive_may_misread_as_mandate_warns():
    r = g6_meaning_support("This section requires operators to retain records",
                           "An operator may keep records of calls", "An operator may keep records.")
    assert r.status == "WARN"
    assert g6_meaning_support("This section requires retention",
                              "An operator must retain records", "").status == "PASS"


def test_g8_dangling_reference_warns():
    text = "Nothing in this section limits the powers under section 999 of this Act."
    r = g8_counter_and_dangling("snippet", text, "X Act", {"25", "26"})
    assert r.status == "WARN" and "999" in r.reason
    ok = g8_counter_and_dangling("snippet", "see section 25 for details", "X Act", {"25"})
    assert ok.status == "PASS"


def test_g7_bill_names_hard_fail():
    r = g7_indicator_fit("P7-I1", "any", "any text", "Personal Data Protection Bill 2024")
    assert r.status == "FAIL" and "Bill" in r.reason


def test_citation_tiers():
    assert citation_tier("s. 26(1)") == "[verify-pinpoint]"
    assert citation_tier("s. 26") == "[verify]"


def test_g4_accepts_iso_compilation_dates():
    result = g4_currentness("2026-06-04", "in_force")
    assert result.status == "PASS"
    assert "2026-06-04" in result.reason


def test_g7_understands_without_first_obtaining_warrant():
    text = ("An authorized officer may enter and search computer data without first "
            "obtaining a warrant if delay creates risk.")
    assert g7_indicator_fit("P7-I5", text, text, "Services Tax Act 2018").status == "PASS"
    gated = ("An authorized officer may search computer data only under a warrant "
             "issued by a magistrate.")
    assert g7_indicator_fit("P7-I5", gated, gated, "Services Tax Act 2018").status == "WARN"
    executive = ("The Director-General may, by warrant under his own hand, authorise "
                 "interception of communications.")
    assert g7_indicator_fit("P7-I5", executive, executive, "Security Act").status == "PASS"
    attorney = "The Attorney-General may issue a warrant authorising access to computer data."
    assert g7_indicator_fit("P7-I5", attorney, attorney, "Security Act").status == "PASS"


def test_g7_local_infrastructure_requires_domestic_mandatory_condition():
    false_designation = (
        "The Commissioner may designate a computer system located wholly outside Singapore."
    )
    assert g7_indicator_fit(
        "P6-I3", false_designation, false_designation, "Cybersecurity Act 2018"
    ).status == "FAIL"
    true_requirement = (
        "A provider must maintain its service infrastructure and servers within the country "
        "as a condition of its licence."
    )
    assert g7_indicator_fit(
        "P6-I3", true_requirement, true_requirement, "Digital Services Act"
    ).status == "PASS"


def test_g7_retention_minimum_rejects_ceiling_or_permission():
    ceiling = "The Registrar need only keep a former name in the register for 5 years."
    assert g7_indicator_fit("P7-I3", ceiling, ceiling, "Companies Act").status == "FAIL"
    duty = "The company must retain every record for a period of at least 5 years."
    assert g7_indicator_fit("P7-I3", duty, duty, "Companies Act").status == "PASS"


def test_g7_records_mandatory_retention_without_duration_for_score_zero_review():
    text = "An employer must make and keep employee records for the period prescribed."
    result = g7_indicator_fit("P7-I3", text, text, "Employment Act")
    assert result.status == "WARN"
    assert "score 0" in result.reason


def test_g7_cross_border_indicators_require_the_correct_legal_effect():
    transfer_only = "An organisation may transfer personal data outside the country."
    assert g7_indicator_fit("P6-I1", transfer_only, transfer_only, "Privacy Act").status == "FAIL"
    conditional = "An organisation may transfer data outside the country only if consent is obtained."
    assert g7_indicator_fit("P6-I4", conditional, conditional, "Privacy Act").status == "PASS"


def test_g7_accepts_statutory_in_accordance_condition_wording():
    text = ("An organisation must not transfer any personal data to a country or territory "
            "outside Singapore except in accordance with requirements prescribed under this Act.")
    assert g7_indicator_fit("P6-I4", text, text,
                            "Personal Data Protection Act 2012").status == "PASS"
