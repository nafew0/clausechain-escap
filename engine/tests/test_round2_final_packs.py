"""Final-round economies (RU/MN/LA/TL): grammars, per-seed scope and run wiring."""
from __future__ import annotations

import json

from packages.core import acquisition, review_layout
from packages.core.orchestrator import CODE_BY_NAME, ECONOMY_NAMES
from packages.core.schemas import ExtractedPage
from packages.extractors.pdf_act import SECTION_GRAMMARS, parse_act_text
from packages.ingest.seed_profiles import seed_fingerprint_config, seed_parse_profile


def _page(number: int, text: str) -> ExtractedPage:
    return ExtractedPage(document_id="d", page_number=number, text=text,
                         source_url="file://d", location_reference=f"page {number}",
                         confidence=1.0)


def _labels(text: str, grammar: str, act: str = "Test instrument") -> list[str]:
    units = parse_act_text([_page(1, text)], "Test", act, "t", "https://x",
                           extra_section_patterns=SECTION_GRAMMARS[grammar],
                           citation_template="Art. {label}")
    return [unit.article_section for unit in units]


RUSSIAN = """Статья 18. Обязанности оператора при сборе персональных данных
1. При сборе персональных данных оператор обязан предоставить субъекту информацию.
Статья 18¹. Меры, направленные на обеспечение выполнения оператором обязанностей
1. Оператор обязан принимать меры, предусмотренные статьей 18 настоящего закона.
Статья 19. Меры по обеспечению безопасности персональных данных при их обработке
1. Оператор при обработке персональных данных обязан принимать необходимые меры.
Статья 22¹. Лица, ответственные за организацию обработки персональных данных
1. Оператор, являющийся юридическим лицом, назначает лицо, ответственное за обработку.
"""


def test_russian_superscript_articles_cite_as_decimal_labels():
    labels = _labels(RUSSIAN, "russian", "Federal Law No. 152-FZ On Personal Data")
    assert labels == ["Art. 18", "Art. 18.1", "Art. 19", "Art. 22.1"]


def test_russian_parts_and_inserted_parts_become_their_own_units():
    text = """Статья 64. Обязанности операторов связи
1. Операторы связи обязаны хранить на территории Российской Федерации информацию о фактах приема.
1¹. Операторы связи обязаны предоставлять уполномоченным государственным органам информацию.
2. Операторы связи обязаны обеспечивать реализацию установленных требований к сетям связи.
Статья 65. Порядок ввода в действие
1. Настоящий закон вступает в силу по истечении шести месяцев после дня опубликования.
"""
    assert _labels(text, "russian") == ["Art. 64", "Art. 64(1)", "Art. 64(1.1)", "Art. 64(2)",
                                        "Art. 65"]


def test_long_russian_part_splits_into_list_items():
    items = "\n".join(f"{n}) требовать от граждан и должностных лиц прекращения нарушения "
                      f"номер {n}; " + "подробное описание полномочия " * 12 for n in range(1, 30))
    text = (f"Статья 13. Права полиции\n1. Полиции предоставляются следующие права:\n{items}\n"
            "2. Полиции могут быть предоставлены иные права федеральными законами.\n"
            "Статья 14. Задержание\n1. Полиция имеет право задерживать лиц в случаях, "
            "предусмотренных федеральным законом.\n"
            "Статья 15. Проникновение в жилые помещения\n1. Сотрудники полиции вправе "
            "входить в жилые помещения в случаях, установленных законом.\n")
    labels = _labels(text, "russian")
    # The bare heading "Статья 13. Права полиции" is under the 30-char unit floor.
    assert labels[:3] == ["Art. 13(1)", "Art. 13(1)(1)", "Art. 13(1)(2)"]
    assert labels[-4:] == ["Art. 13(1)(29)", "Art. 13(2)", "Art. 14", "Art. 15"]


MONGOLIAN = """1 дүгээр зүйл.Хуулийн зорилт
1.1.Энэ хуулийн зорилт нь хүний хувийн мэдээллийг хамгаалахтай холбогдсон харилцааг зохицуулахад оршино.
4 дүгээр зүйл.Хуулийн нэр томьёоны тодорхойлолт
4.1.5.Иргэний хуулийн 17, 18,
19 дүгээр зүйлд заасан, хуульд өөрөөр заагаагүй бол хууль ёсны төлөөлөгчийг ойлгоно.
5 дугаар зүйл.Мэдээлэл цуглуулах, боловсруулах, ашиглахад тавих шаардлага
5.1.Мэдээлэл хариуцагч нь мэдээлэл цуглуулах, боловсруулах, ашиглахдаа хуулийг баримтална.
14 дүгээр зүйл.Мэдээллийг гадаад улс дахь хүнд дамжуулах
14.1.Хууль, олон улсын гэрээнд зааснаас бусад тохиолдолд мэдээллийг дамжуулахыг хориглоно.
"""


def test_mongolian_dative_cross_reference_does_not_start_an_article():
    # "19 дүгээр зүйлд заасан" (dative: "in article 19") once swallowed Arts. 5-18.
    assert _labels(MONGOLIAN, "mongolian") == ["Art. 1", "Art. 4", "Art. 5", "Art. 14"]


def test_flattened_superscript_article_is_recovered_from_its_neighbours():
    # legalinfo.mn's PDF export prints "4¹ дүгээр зүйл" as "41 дүгээр зүйл"; read
    # literally, "41" swallowed Arts. 5-40 of the Accounting Law.
    text = "\n".join(
        f"{n} дүгээр зүйл.Гарчиг {n}\n{n}.1.Энэ зүйлийн агуулга хангалттай урт текст байна гэж үзнэ."
        for n in ("3", "4", "41", "5", "6"))
    assert _labels(text, "mongolian") == ["Art. 3", "Art. 4", "Art. 4.1", "Art. 5", "Art. 6"]


def test_mongolian_regulation_clauses_keep_sub_clauses_inside():
    text = """Гурав.Технологийн аюулгүй байдлын шаардлага
3.1.Мэдээлэл боловсруулахад технологийн аюулгүй байдлын дараах шаардлагыг хангаж ажиллана. Үүнд: мэдээлэл хариуцагч нь дотоод журам баталж мөрдөнө.
3.2.Мэдээлэл боловсруулах сервер нь дараах нөхцөл шаардлагыг хангасан байна. Үүнд:
3.2.1.Монгол Улсын нутаг дэвсгэрт байршдаг байх;
3.2.2.зөвхөн Монгол Улсаас нэвтрэх /хандах/ боломжтой байх;
"""
    units = parse_act_text([_page(1, text)], "Test", "A/90 regulation", "t", "https://x",
                           extra_section_patterns=SECTION_GRAMMARS["mongolian_regulation"],
                           citation_template="cl. {label}")
    assert [unit.article_section for unit in units] == ["cl. 3.1", "cl. 3.2"]
    assert "3.2.1.Монгол Улсын нутаг дэвсгэрт байршдаг байх" in units[1].text


PORTUGUESE = """Artigo 14.º
Conservação de documentos
1. As entidades mantêm os registos pelo período mínimo previsto na presente lei, nos termos do
artigo 3.º e demais disposições aplicáveis.
Artigo 15.º Arquivo de registos
1. As entidades referidas no artigo 3.º mantêm arquivos pelo período de, pelo menos, cinco anos.
"""


def test_portuguese_artigo_headings_and_lowercase_references():
    assert _labels(PORTUGUESE, "portuguese") == ["Art. 14", "Art. 15"]


def test_portuguese_letter_ordinal_headings_parse():
    # JR 2012 prints "Artigo 10.o" once numbers reach two digits (DL 15/2012).
    text = ("Artigo 9.º\nCompetências da autoridade reguladora nos termos do presente diploma.\n"
            "Artigo 10.o\nRegisto dos operadores de redes e serviços de telecomunicações.\n"
            "Artigo 11.o\nLicenças de espectro de radiofrequência atribuídas pela autoridade.\n")
    assert _labels(text, "portuguese") == ["Art. 9", "Art. 10", "Art. 11"]


LAO = """ມາດຕາ ໑໖ ການເກັບຮັກສາຂໍ້ມູນ
ຜູ້ຄຸ້ມຄອງຂໍ້ມູນ ຕ້ອງເກັບຮັກສາຂໍ້ມູນເອເລັກໂຕຣນິກ ໃຫ້ປອດໄພ ຕາມທີ່ໄດ້ກຳນົດໄວ້ໃນກົດໝາຍສະບັບນີ້.
ມາດຕາ ໑໗ ການສົ່ງ ຫຼື ໂອນຂໍ້ມູນ
ການສົ່ງ ຫຼື ໂອນຂໍ້ມູນສ່ວນບຸກຄົນ ໄປຕ່າງປະເທດ ຕ້ອງໄດ້ຮັບການອະນຸຍາດຈາກເຈົ້າຂອງຂໍ້ມູນ.
"""


def test_lao_article_grammar_orders_lao_digits():
    # Labels keep Lao digits here; build_seeds_corpus normalises them to Arabic.
    assert _labels(LAO, "lao") == ["Art. ໑໖", "Art. ໑໗"]


def test_seed_opt_in_grammar_parses_bare_numbered_clauses():
    text = """3
Requirement for Registration
3.1
A service provider who supplies a prepaid mobile service must register the subscriber.
3.2
A service provider must not supply a prepaid mobile service to an unregistered subscriber.
"""
    profile = seed_parse_profile({"section_grammars": ["numbered_clause"]}, ["portuguese"])
    units = parse_act_text([_page(1, text)], "Test", "ANC Guidelines", "t", "https://x",
                           extra_section_patterns=profile["extra_section_patterns"],
                           citation_template="cl. {label}")
    assert [unit.article_section for unit in units] == ["cl. 3", "cl. 3.1", "cl. 3.2"]
    assert "must register the subscriber" in units[1].text


def test_fingerprint_config_is_unchanged_unless_a_seed_declares_scope():
    plain = {"act": "Personal Data Protection Act", "url": "https://x"}
    assert set(seed_fingerprint_config(plain)) == {"expected_citations", "expected_phrases",
                                                   "citation_template"}
    scoped = dict(plain, page_range=[21, 40], section_grammars=["numbered_clause"])
    assert seed_fingerprint_config(scoped)["page_range"] == [21, 40]
    assert seed_fingerprint_config(scoped)["section_grammars"] == ["numbered_clause"]


def test_final_round_economies_resolve_by_un_name_and_common_spelling():
    assert ECONOMY_NAMES["TL"] == "Timor-Leste" and ECONOMY_NAMES["LA"] == "Lao PDR"
    for name, code in [("RUSSIAN FEDERATION", "RU"), ("RUSSIA", "RU"), ("MONGOLIA", "MN"),
                       ("LAO PDR", "LA"), ("LAOS", "LA"), ("TIMOR-LESTE", "TL"),
                       ("EAST TIMOR", "TL")]:
        assert CODE_BY_NAME[name] == code


def test_optional_hybrid_runs_join_only_once_they_have_output(tmp_path):
    assert review_layout.hybrid_runs(tmp_path) == review_layout.HYBRID_RUNS
    run = tmp_path / "outputs/final_r2_tl_p6"
    run.mkdir(parents=True)
    (run / "output.json").write_text("{}")
    assert review_layout.hybrid_runs(tmp_path) == [*review_layout.HYBRID_RUNS, "final_r2_tl_p6"]
    assert review_layout.ECONOMY_BY_CODE[review_layout.run_code("final_r2_tl_p6")] == "Timor-Leste"


def test_round_two_acquisition_reads_the_round_two_seed_inventory(tmp_path):
    url = "https://www.mj.gov.tl/jornal/public/docs/2011/serie_1/SERIE1_NO_46.pdf#page=3"
    (tmp_path / "data/raw/tl").mkdir(parents=True)
    (tmp_path / "data/seeds_r2.json").write_text(json.dumps({"economies": {"Timor-Leste": [
        {"act": "Lei n.º 17/2011", "url": url, "indicator_code": "P7-I3"}]}}))
    (tmp_path / "data/raw/tl/seeds_manifest.json").write_text(json.dumps({url: {"status": "ok"}}))
    assert acquisition.unresolved_seed_acquisitions("Timor-Leste", "P7-I3", tmp_path) == []
    (tmp_path / "data/raw/tl/seeds_manifest.json").write_text(json.dumps({url: {"status": "dead"}}))
    [failure] = acquisition.unresolved_seed_acquisitions("Timor-Leste", "P7-I3", tmp_path)
    assert failure["status"] == "dead" and failure["reason_code"] == "ACQUISITION_UNRESOLVED"


def test_vision_ocr_retries_transient_errors_then_fails_closed(monkeypatch):
    import httpx

    from packages.providers.ocr_provider import GoogleVisionOCR

    ocr = GoogleVisionOCR(api_key="test-key")
    monkeypatch.setattr(GoogleVisionOCR, "RETRY_DELAYS_S", (0.0, 0.0))
    request = httpx.Request("POST", GoogleVisionOCR.ENDPOINT)
    replies = [httpx.Response(502, request=request),
               httpx.Response(200, request=request, json={"responses": [
                   {"fullTextAnnotation": {"text": "Artigo 56.º", "pages": []}}]})]
    monkeypatch.setattr(httpx, "post", lambda *a, **k: replies.pop(0))
    assert ocr.ocr_image(b"png", 3, "cpp").text == "Artigo 56.º"

    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(503, request=request))
    try:
        ocr.ocr_image(b"png", 3, "cpp")
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("a persistent 5xx must still fail closed")


def test_lao_legacy_font_text_layer_is_not_readable_lao():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "build_seeds_corpus", Path(__file__).resolve().parents[1] / "scripts/build_seeds_corpus.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    genuine = "ມາດຕາ 17 ຂໍ້ຫ້າມສໍາລັບບໍລິສັດຫຼັກຊັບ ການເກັບຮັກສາຂໍ້ມູນ ແລະ ລະບົບຂອງບໍລິສັດ ທີ່ຢູ່ໃນ ສປປ ລາວ. " * 20
    legacy = "ຓາຈຉາ  17 ຂ ໇ນ ໇າຓຘ າຖັຍຍ ຖິຘັຈນ ັກຆັຍ ກາຌເກັຍປັກຘາຂ ໇ຓູຌ ແຖະ ຖະຍົຍຂບຄຍ ຖິຘັຈ. " * 20
    assert builder.readable_lao(genuine)
    assert not builder.readable_lao(legacy)
