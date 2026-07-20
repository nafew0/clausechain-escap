"""EPUB/XHTML act extractor tests + the frozen unit-id contract.

The synthetic EPUB mirrors legislation.gov.au markup (ActHead1-5 heading
classes, CharSectno section numbers). The id-contract tests pin the three
id schemes stored corpora / zone-3 scores / refutation files depend on —
they must never change silently.
"""
from __future__ import annotations

import io
import zipfile

from packages.extractors.epub_act import parse_epub_act


def _epub(body_html: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("OEBPS/document_1/document_1.html",
                   f"<html><body>{body_html}</body></html>")
    return buf.getvalue()


def _head(level: int, inner: str) -> str:
    return f'<p id="nav" class="ActHead{level}">{inner}</p>'


def _section(number: str, heading: str, body: str) -> str:
    return (_head(5, f'<a><span class="CharSectno">{number}</span>'
                     f"<span>&#xa0; </span><span>{heading}</span></a>")
            + f"<p class='subsection'>{body}</p>")


def test_acthead5_split_and_subsection_pieces():
    html = (_head(2, "Part 1—Preliminary")
            + _head(5, '<a><span class="CharSectno">5</span><span> Interpretation</span></a>')
            + '<p class="subsection">(1) In this Act, data means recorded information that has meaning.</p>'
            + '<p class="subsection">(2) A reference to a person includes a body corporate for all purposes.</p>')
    units = parse_epub_act(_epub(html), "Australia", "Test Act 2020", "REF", "https://x")
    labels = {u.article_section for u in units}
    assert labels == {"s. 5(1)", "s. 5(2)"}
    u1 = next(u for u in units if u.article_section == "s. 5(1)")
    assert u1.id == "au:REF:s5-1"
    assert u1.metadata["extraction"] == "xhtml_oracle"
    assert u1.metadata["heading"] == "Interpretation"


def test_semantic_subsection_class_prevents_cross_reference_false_split():
    html = (_head(5, '<a><span class="CharSectno">187B</span><span> Scope</span></a>')
            + '<p class="subsection">(1) This rule applies subject to a declaration under subsection (2).</p>'
            + '<p class="paragraph">(a) The service is a relevant service for this purpose.</p>'
            + '<p class="subsection">(3) The decision maker must consider national security.</p>')
    units = parse_epub_act(_epub(html), "Australia", "Test Act", "REF", "https://x")
    assert [u.article_section for u in units] == ["s. 187B(1)", "s. 187B(3)"]
    assert "under subsection (2)" in units[0].text
    assert "(a) The service" in units[0].text


def test_schedule_clause_gets_schedule_citation():
    html = (_section("90", "Final body section",
                     "A body section with enough text to pass the length filter easily.")
            + _head(1, "Schedule&#xa0;1—International production orders")
            + _section("5", "Clause five heading",
                       "A schedule clause with enough operative text to form a unit."))
    units = parse_epub_act(_epub(html), "Australia", "Test Act 2020", "REF", "https://x")
    sch = next(u for u in units if "schedule" in u.metadata)
    assert sch.article_section == "Sch 1, cl. 5"
    assert sch.id == "au:REF:sch1-cl5"
    assert sch.metadata["schedule"] == "1"
    body = next(u for u in units if u.metadata.get("section_number") == "90")
    assert body.article_section == "s. 90"  # body section untouched


def test_decimal_code_sections_stay_plain_inside_schedule():
    """Criminal Code style: the Schedule IS the Code — decimals cite as s. N."""
    html = (_head(1, "Schedule&#xa0;1—The Criminal Code")
            + _section("474.17", "Using a carriage service to menace",
                       "A person commits an offence if the person uses a carriage service "
                       "in a way that reasonable persons would regard as menacing."))
    units = parse_epub_act(_epub(html), "Australia", "Criminal Code Act 1995", "REF", "https://x")
    assert [u.article_section for u in units] == ["s. 474.17"]
    assert units[0].id == "au:REF:s474.17"


def test_schedule_resets_on_same_or_higher_heading():
    html = (_head(1, "Schedule&#xa0;2—Forms")
            + _section("3", "A schedule clause",
                       "Clause text inside schedule two with sufficient length to keep.")
            + _head(1, "Chapter 2—Other provisions")
            + _section("7", "After the schedule",
                       "This section follows a non-schedule level-1 heading and is body text."))
    units = parse_epub_act(_epub(html), "Australia", "Test Act 2020", "REF", "https://x")
    by_no = {u.metadata["section_number"]: u for u in units}
    assert by_no["3"].article_section == "Sch 2, cl. 3"
    assert by_no["7"].article_section == "s. 7"


def test_hierarchy_anchor_and_endnotes_are_distinguished_from_law():
    html = (_head(1, "Chapter 2—Controls") + _head(2, "Part 3—Duties")
            + _head(3, "Division 4—Retention")
            + _section("12", "Keep records",
                       "A person must keep records for seven years after the transaction.")
            + _head(1, "Endnotes")
            + _section("99", "Amendment history",
                       "This endnote is navigation metadata and is not operative law."))
    units = parse_epub_act(_epub(html), "Australia", "Test Act", "REF", "https://x")
    assert [u.article_section for u in units] == ["s. 12"]
    assert units[0].metadata["part"] == "Part 3—Duties"
    assert units[0].metadata["division"] == "Division 4—Retention"
    assert units[0].metadata["hierarchy_path"][-1] == "Keep records"
    assert units[0].metadata["xhtml_anchor"] == "nav"


def test_toc_is_navigation_hint_not_an_operative_unit():
    html = ('<p class="TOC5"><span>12</span><span> Keep records</span></p>'
            + _section("12", "Keep records",
                       "A person must keep the official records for seven years."))
    units = parse_epub_act(_epub(html), "Australia", "Test Act", "REF", "https://x")
    assert len(units) == 1 and units[0].article_section == "s. 12"
    assert units[0].metadata["toc_hint"] == "Keep records"


def test_unit_id_contract_frozen_prefixes():
    """Stored corpora, zone-3 scores, and refutation files reference these ids."""
    # epub path -> "au:" hardcoded
    html = _section("9", "Heading", "Enough text for one unit to be emitted here today.")
    epub_unit = parse_epub_act(_epub(html), "Australia", "X", "REF", "https://x")[0]
    assert epub_unit.id.startswith("au:REF:")

    # statute-PDF path -> economy[:2].lower() ("ma:", NOT "my:" — frozen as-is)
    from packages.core.schemas import ExtractedPage
    from packages.extractors.pdf_act import parse_act_text

    page = ExtractedPage(document_id="d", page_number=1, source_url="https://x",
                         location_reference="page 1",
                         text="9. Heading\nA section body long enough to be kept as a unit.")
    pdf_unit = parse_act_text([page], "Malaysia", "X Act", "REF", "https://x")[0]
    assert pdf_unit.id.startswith("ma:REF:")

    # SSO-HTML path -> economy.lower() full name
    from packages.core.rule_units import build_rule_units
    from packages.extractors.html_act import parse_sso_act

    fixture = open("tests/fixtures/sso_pdpa_s25_26.html", encoding="utf-8").read()
    doc = parse_sso_act(fixture, "https://sso.agc.gov.sg/Act/PDPA2012")
    sso_unit = build_rule_units(doc, economy="Singapore", act_ref="PDPA2012")[0]
    assert sso_unit.id.startswith("singapore:PDPA2012:")
