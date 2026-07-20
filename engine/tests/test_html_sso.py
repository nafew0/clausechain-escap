from __future__ import annotations

from pathlib import Path

from packages.extractors.html_act import parse_sso_act
from packages.extractors.textutil import clean_text

FIXTURE = Path(__file__).parent / "fixtures" / "sso_pdpa_s25_26.html"


def test_parse_real_sso_fixture_sections_and_subsections():
    doc = parse_sso_act(FIXTURE.read_text(encoding="utf-8"),
                        "https://sso.agc.gov.sg/Act/PDPA2012")

    assert doc.law_name == "Personal Data Protection Act 2012"
    assert doc.current_as_at == "07 Jul 2026"

    s26 = next(s for s in doc.sections if s.sec_id == "pr26-")
    assert s26.heading == "Transfer of personal data outside Singapore"
    assert [x.label for x in s26.subsections][:2] == ["26(1)", "26(2)"]
    # the verbatim text is the CURRENT consolidated wording ("must not", not "shall not")
    assert "must not transfer any personal data" in s26.subsections[0].text
    assert "except in accordance with requirements prescribed" in s26.subsections[0].text
    assert s26.anchor_url(doc.source_url).endswith("#pr26-")


def test_clean_text_preserves_legal_characters():
    assert clean_text("s&#160;26(1) &#8212; the rule") == "s 26(1) — the rule"
