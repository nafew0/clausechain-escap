"""Pillar 2 (public procurement): rubric, gold codes, parser and gate fixes."""
from __future__ import annotations

from pathlib import Path

import yaml

from packages.core import review_layout
from packages.core.schemas import ExtractedPage
from packages.extractors.pdf_act import SECTION_GRAMMARS, parse_act_text
from packages.ingest.known_index import indicator_code
from packages.rdtii.mapper import GOLDEN_RULES, golden_rules
from packages.verifier.gates import finalize_snippet_result


def _Page(number: int, text: str) -> ExtractedPage:
    return ExtractedPage(document_id="d", page_number=number, text=text,
                         source_url="file://d", location_reference=f"page {number}",
                         confidence=1.0)


def test_float_indicator_cells_resolve_to_real_codes():
    # xlsx numeric cells: 2.2 and 2.3 arrive as binary-float strings.
    assert indicator_code("2.2000000000000002", "2") == "P2-I2"
    assert indicator_code("2.2999999999999998", "2") == "P2-I3"
    assert indicator_code("2.1", "2") == "P2-I1"
    assert indicator_code("6.4") == "P6-I4"


def test_pillar2_rubric_is_regulatory_for_three_indicators_with_own_rules():
    rubric = yaml.safe_load(Path("configs/rdtii/pillar_2.yaml").read_text())
    indicators = rubric["indicators"]
    regulatory = [i for i, cfg in indicators.items() if cfg.get("regulatory") is not False]
    assert regulatory == ["P2-I1", "P2-I2", "P2-I3"]
    for code in regulatory:
        rules = golden_rules(indicators[code])
        assert "PROCUREMENT" in rules.upper() and "6.4" not in rules
    assert golden_rules({}) == GOLDEN_RULES.strip()     # P6/P7 unchanged


def test_russian_article_grammar_beats_part_numbering():
    # 223-FZ shape: few "Статья N." headings, many "1." parts -> the generic
    # grammar used to win on yield and label parts as articles.
    lines = []
    for article in (1, 2, 3):
        lines.append(f"Статья {article}. Заголовок статьи {article}")
        for part in range(1, 6):
            lines.append(f"{part}. Текст части {part} статьи {article} о закупках.")
    units = parse_act_text([_Page(1, "\n".join(lines))], economy="Russian Federation",
                           act_name="Federal Law No. 223-FZ", act_ref="t", source_url="u",
                           extra_section_patterns=SECTION_GRAMMARS["russian"],
                           citation_template="Art. {label}")
    assert {u.article_section.split("(")[0] for u in units} == {"Art. 1", "Art. 2", "Art. 3"}


def test_stray_keyword_mentions_do_not_override_numbered_paragraphs():
    lines = [f"{n}. Paragraph {n} of the overview sets out the regime." for n in range(1, 21)]
    lines.insert(5, "Artigo 5.º Remissão")
    lines.insert(12, "Artigo 9.º Remissão")
    units = parse_act_text([_Page(1, "\n".join(lines))], economy="Timor-Leste",
                           act_name="Overview", act_ref="t", source_url="u",
                           extra_section_patterns=SECTION_GRAMMARS["portuguese"],
                           citation_template="para. {label}")
    assert len(units) >= 15


def test_russian_list_markers_do_not_block_structural_closure():
    source = ("2. Правительство Российской Федерации:\n"
              "1) вправе принимать меры, устанавливающие:\n"
              "а) запрет закупок товаров, происходящих из иностранных государств;\n"
              "б) ограничение закупок товаров;\n"
              "2) определяет перечень документов.\n\n3. Следующая часть.")
    result = finalize_snippet_result(source[:60], source)
    assert result.closure_code.startswith("PASS")


def test_pillar2_runs_join_both_modes_but_not_the_round1_baseline(tmp_path):
    for run in ("final_r2_si_p2", "local_ru_p2"):
        (tmp_path / "outputs" / run).mkdir(parents=True)
        (tmp_path / "outputs" / run / "output.json").write_text("{}")
    assert "final_r2_si_p2" in review_layout.hybrid_runs(tmp_path)
    assert "local_ru_p2" in review_layout.local_runs(tmp_path)
    layout = review_layout.Layout(mode="hybrid", runs=("final_si_p6", "final_r2_si_p2"),
                                  provider_profile="hybrid_accuracy",
                                  submission_dir=tmp_path, review_dir=tmp_path,
                                  zone3_dir=tmp_path, reports_dir=tmp_path)
    assert layout.round1_runs == ["final_si_p6"]


def test_thai_inserted_clauses_parse_as_their_own_units():
    # MR on Promoted Supplies (No. 2) B.E. 2563 inserts "ข้อ ๒๗/๑".."ข้อ ๒๗/๓"; the
    # base "thai" grammar folded them all into one "cl. 27".
    # The amending instruction wraps its list of inserted clauses onto a line that
    # starts "ข้อ ๒๗/๒ และข้อ ๒๗/๓": a cross-reference, not the 27/2 heading.
    text = ("ข้อ ๒๗ หน่วยงานของรัฐต้องดำเนินการจัดซื้อจัดจ้างตามที่กำหนดในหมวดนี้\n"
            "ให้เพิ่มความต่อไปนี้เป็นหมวด ๗/๑ พัสดุส่งเสริมการผลิตภายในประเทศ ข้อ ๒๗/๑\n"
            "ข้อ ๒๗/๒ และข้อ ๒๗/๓ แห่งกฎกระทรวงกำหนดพัสดุ\n"
            "ข้อ ๒๗/๑ ในหมวดนี้ พัสดุที่ผลิตภายในประเทศ หมายความว่า พัสดุที่ได้รับการรับรอง\n"
            "ข้อ ๒๗/๒ ให้พัสดุที่ผลิตภายในประเทศเป็นพัสดุที่รัฐต้องการส่งเสริมหรือสนับสนุน\n"
            "ข้อ ๒๗/๓ ให้หน่วยงานของรัฐดำเนินการจัดซื้อจัดจ้างพัสดุที่ผลิตภายในประเทศ\n"
            "ข้อ ๒๘ บทเฉพาะกาลสำหรับการจัดซื้อจัดจ้างที่ดำเนินการอยู่ก่อนวันที่กฎกระทรวงนี้ใช้บังคับ\n")
    units = parse_act_text([_Page(1, text)], economy="Thailand", act_name="MR No. 2",
                           act_ref="t", source_url="u",
                           extra_section_patterns=SECTION_GRAMMARS["thai_inserted_clause"]
                           + SECTION_GRAMMARS["thai"],
                           citation_template="cl. {label}")
    assert [u.article_section for u in units] == [
        "cl. ๒๗", "cl. ๒๗/๑", "cl. ๒๗/๒", "cl. ๒๗/๓", "cl. ๒๘"]
