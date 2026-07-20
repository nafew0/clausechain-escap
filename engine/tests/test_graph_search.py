from __future__ import annotations

from pathlib import Path

from packages.core.rule_units import build_rule_units
from packages.extractors.html_act import parse_sso_act
from packages.graph.sqlite_graph import SqliteGraphStore

FIXTURE = Path(__file__).parent / "fixtures" / "sso_pdpa_s25_26.html"


def _load_store(tmp_path) -> SqliteGraphStore:
    store = SqliteGraphStore(tmp_path / "graph.db")
    doc = parse_sso_act(FIXTURE.read_text(encoding="utf-8"),
                        "https://sso.agc.gov.sg/Act/PDPA2012")
    for unit in build_rule_units(doc, economy="Singapore", act_ref="PDPA2012"):
        store.upsert_rule_unit(unit)
    return store


def test_rule_units_have_paragraph_depth_citations(tmp_path):
    doc = parse_sso_act(FIXTURE.read_text(encoding="utf-8"),
                        "https://sso.agc.gov.sg/Act/PDPA2012")
    units = build_rule_units(doc, economy="Singapore", act_ref="PDPA2012")
    labels = [u.article_section for u in units]
    assert "s. 26(1)" in labels           # never bare "s. 26"
    unit = next(u for u in units if u.article_section == "s. 26(1)")
    assert unit.source_url.endswith("#pr26-")
    assert unit.metadata["heading"] == "Transfer of personal data outside Singapore"


def test_fts5_search_finds_transfer_provision(tmp_path):
    store = _load_store(tmp_path)
    hits = store.search_provisions("transfer personal data outside Singapore",
                                   economy="Singapore")
    assert hits, "FTS5 search returned nothing"
    top = hits[0]
    assert "must not transfer" in top["text"]
    assert top["score"] >= hits[-1]["score"]  # best-first ordering
    # economy filter respected
    assert store.search_provisions("transfer", economy="Narnia") == []


def test_fts5_search_is_broad_or_semantics(tmp_path):
    store = _load_store(tmp_path)
    # one matching term is enough to surface a hit (OR, broad recall)
    hits = store.search_provisions("nonexistentterm retention", economy="Singapore")
    assert any("etention" in h["text"] for h in hits)
