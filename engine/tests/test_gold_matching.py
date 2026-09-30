"""ESCAP master (gold) matching for the final-round packs: nothing missed, nothing
mis-attributed, and unchanged behaviour for economies without the new pack keys."""
from __future__ import annotations

import json

from packages.discovery.diff import KnownIndex, laws_match, section_base, section_matches


def test_registration_numbers_keep_different_laws_apart():
    gold = "federal law no 152 fz on personal data"
    assert laws_match(gold, "Federal Law No. 152-FZ of 27.07.2006 On Personal Data (consolidated)")
    # Title overlap alone once matched 152-FZ gold anchors to 572-FZ provisions.
    assert not laws_match(gold, "Federal Law No. 572-FZ of 29.12.2022 On identification and "
                                "authentication using biometric personal data")
    assert not laws_match("law on electronic transactions no 20 na 2010",
                          "Amended Law on Electronic Transactions No. 31/NA (2022)")
    assert laws_match("law on electronic data protection no 25 na 2017",
                      "Law on Electronic Data Protection No. 25/NA (2017)")


def _index(tmp_path, pack: dict, rows: list[dict]) -> KnownIndex:
    (tmp_path / "configs/jurisdictions").mkdir(parents=True)
    (tmp_path / "configs/jurisdictions/tt.yaml").write_text(json.dumps(pack))  # JSON is YAML
    (tmp_path / "data").mkdir()
    (tmp_path / "data/index.json").write_text(json.dumps({"economies": {pack["name"]: rows}}))
    return KnownIndex(tmp_path / "data/index.json")


LAW = "Federal Law No. 152-FZ On Personal Data (consolidated)"
UNITS = [{"law_name": LAW, "article_section": label} for label in
         ("Art. 12", "Art. 12(4)", "Art. 12(7)", "Art. 22", "Art. 22(1)", "Art. 22.1", "Art. 22.1(1)")]


def test_decimal_gold_refs_read_as_inserted_article_or_part(tmp_path):
    index = _index(tmp_path, {"name": "Testland", "gold_ref_style": "decimal_parts"}, [])
    index.register_corpus("Testland", UNITS)
    match = lambda ref, label: index.gold_ref_matches("Testland", LAW, ref, label)  # noqa: E731
    # "12.7" = part 7 of Art. 12 (no article 12.7 exists)...
    assert match("Art. 12.7", "Art. 12(7)") and not match("Art. 12.7", "Art. 12(4)")
    # ...while "22.1" is the inserted article 22¹, never Art. 22 part 1.
    assert match("Art. 22.1", "Art. 22.1(1)") and not match("Art. 22.1", "Art. 22(1)")
    assert match("Art. 12", "Art. 12(4)") and not match("Art. 22", "Art. 22.1(1)")


def test_aliases_and_amending_law_crosswalk_come_from_the_pack(tmp_path):
    amending = "Federal Law No. 208-FZ On Amendments to the Federal Law On Information"
    principal = "Federal Law No. 149-FZ On Information (consolidated)"
    index = _index(tmp_path, {
        "name": "Testland", "gold_ref_style": "decimal_parts",
        "gold_aliases": {amending: principal},
        "gold_ref_crosswalk": {amending: {"Art. 1.10": "Art. 10.4"}},
    }, [{"acts_norm": ["federal law no 208 fz on amendments to the federal law on information"],
         "articles": ["Art. 1.10"], "indicator_code": "P7-I3"}])
    index.register_corpus("Testland", [{"law_name": principal, "article_section": label}
                                       for label in ("Art. 10.4(1)", "Art. 1(1)")])
    assert index.tag("Testland", principal, "Art. 10.4(1)")[0] == "KNOWN"
    assert index.tag("Testland", principal, "Art. 1(1)")[0] == "NEW"


def test_economies_without_the_pack_keys_keep_exact_matching(tmp_path):
    index = _index(tmp_path, {"name": "Testland"}, [])
    index.register_corpus("Testland", [{"law_name": "Criminal Code", "article_section": "s. 474"}])
    for gold, candidate in [("s. 474.17", "s. 474"), ("s. 3.5", "s. 3.5.14"), ("s. 26", "s. 26(1)")]:
        assert index.gold_ref_matches("Testland", "Criminal Code", gold, candidate) == \
            section_matches(section_base(gold), section_base(candidate))
