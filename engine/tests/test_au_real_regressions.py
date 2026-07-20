from __future__ import annotations

from pathlib import Path

import pytest

from packages.extractors.epub_act import parse_epub_act
from packages.extractors.pdf_align import align_to_pdf

RAW = Path("data/raw/au")


def _units(register: str, act: str):
    epub = RAW / f"{register}.epub"
    if not epub.is_file():
        pytest.skip("archived official AU fixture is not present")
    return parse_epub_act(epub.read_bytes(), "Australia", act, register, "https://www.legislation.gov.au")


def _aligned(register: str, act: str, citations: set[str], volumes: int):
    units = [u for u in _units(register, act) if u.article_section in citations]
    paths = ([str(RAW / f"{register}.pdf")] if volumes == 1 else
             [str(RAW / f"{register}_vol{i}.pdf") for i in range(1, volumes + 1)])
    if not all(Path(p).is_file() for p in paths):
        pytest.skip("authorised AU PDF fixture volumes are not present")
    aligned, total = align_to_pdf(units, paths)
    return units, aligned, total


def test_privacy_33d_real_structure_and_pdf_pages():
    units, aligned, total = _aligned("C2026C00227", "Privacy Act 1988",
        {"s. 33D(1)", "s. 33D(2)"}, 1)
    assert total == 2 and aligned == 2
    assert {u.metadata["alignment_start_page"] for u in units} == {267}
    assert "(a)" in units[0].text and "(b)" in units[0].text


def test_tia_187a_note_does_not_create_false_section_and_187b_is_genuine():
    all_units = _units("C2026C00209", "Telecommunications (Interception and Access) Act 1979")
    section_187b = [u for u in all_units
                    if u.article_section == "s. 187B" or u.article_section.startswith("s. 187B(")]
    assert section_187b and all(u.metadata["section_number"] == "187B" for u in section_187b)
    one = next(u for u in all_units if u.article_section == "s. 187A(1)")
    assert "Note 2: Section 187B removes" in one.text
    targets = [u for u in all_units if u.article_section in {"s. 187A(1)", "s. 187B(1)"}]
    aligned, total = align_to_pdf(targets,
        [str(RAW / "C2026C00209_vol1.pdf"), str(RAW / "C2026C00209_vol2.pdf")])
    assert total == 2 and aligned == 2
    assert all(u.location_reference.startswith("vol 2, page") for u in targets)


def test_telecommunications_317zh_never_creates_printed_page_102_section():
    units = _units("C2026C00224", "Telecommunications Act 1997")
    assert not any(u.article_section == "s. 102" and u.metadata.get("heading", "").startswith("Telecommunications")
                   for u in units)
    target = [u for u in units if u.article_section == "s. 317ZH(1)"]
    aligned, total = align_to_pdf(target, [str(RAW / f"C2026C00224_vol{i}.pdf") for i in range(1, 4)])
    assert total == 1 and aligned == 1
    assert target[0].location_reference.startswith("vol 2, page 130")
    # paragraph-closed binding (20 Jul) widens the evidence window to include the
    # subsection's child paragraphs; the citation start page is unchanged.
    assert 131 <= target[0].metadata["alignment_end_page"] <= 134


def test_criminal_code_decimal_and_roman_item_are_preserved_and_aligned():
    units = _units("C2026C00243", "Criminal Code Act 1995")
    target = next(u for u in units if u.article_section == "s. 474.17A(3)")
    assert "(iii)" in target.text and target.metadata["section_number"] == "474.17A"
    aligned, total = align_to_pdf([target],
        [str(RAW / f"C2026C00243_vol{i}.pdf") for i in range(1, 4)])
    assert (aligned, total) == (1, 1)
    assert target.location_reference.startswith("vol 3, page 110")


def test_compilation_bundle_rejects_mixed_register_files(tmp_path):
    from scripts.build_au_corpus import validate_compilation_bundle
    bad = {"register_id": "C2026C00001", "compilation_date": "2026-01-01",
           "epub": str(tmp_path / "C2026C99999.epub"),
           "pdfs": [(0, str(tmp_path / "C2026C00001.pdf"))]}
    with pytest.raises(ValueError, match="register ID"):
        validate_compilation_bundle(bad)
