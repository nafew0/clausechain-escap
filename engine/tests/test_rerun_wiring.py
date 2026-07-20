"""Sol-review blockers (19 Jul): the deep-research evidence must GENUINELY flow
through the engine. These tests pin each wiring point at the builder level:
treaty eligibility + scoping, grammar profiles used by real builders, manifest
reconciliation, SG subsidiary legislation, snippet-before-gates ordering, and
the recorded (not silent) retrieval union cap.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.core.legal_controls import evidence_eligibility
from packages.ingest.seed_profiles import seed_parse_profile
from packages.extractors.pdf_act import parse_act_text
from packages.verifier.gates import finalize_snippet, g1_span_exists, g5_whole_rule


class FakePage(SimpleNamespace):
    pass


def _pages(text: str) -> list:
    return [FakePage(page_number=1, text=text, confidence=1.0,
                     metadata={"extraction": "native_text"})]


# ---------------------------------------------------------------- eligibility
def test_declared_treaty_is_eligible_in_force():
    ok, reason = evidence_eligibility(
        "CPTPP Chapter 14 (Malaysia MITI text)", "treaty", "in_force")
    assert ok, reason


def test_undeclared_agreement_name_still_rejected():
    ok, reason = evidence_eligibility(
        "Some Trade Agreement Commentary", "act", "in_force")
    assert not ok and reason == "INTERNATIONAL_AGREEMENT"


def test_draft_treaty_still_rejected():
    ok, reason = evidence_eligibility("Draft CPTPP Bill", "treaty", "in_force")
    assert not ok  # bill/draft patterns still apply to declared treaties


def test_treaty_requires_in_force():
    ok, _ = evidence_eligibility("CPTPP Chapter 14", "treaty", "unknown")
    assert not ok


# ----------------------------------------------------------- grammar profiles
def test_treaty_profile_parses_dfat_style_chapter():
    profile = seed_parse_profile({"source_type": "treaty"})
    assert profile["citation_template"] == "Art. {label}"
    text = (
        "Article 14.11: Cross-Border Transfer of Information by Electronic Means\n"
        "1. The Parties recognise that each Party may have its own regulatory "
        "requirements concerning the transfer of information by electronic means.\n"
        "Article 14.13: Location of Computing Facilities\n"
        "1. No Party shall require a covered person to use or locate computing "
        "facilities in that Party's territory as a condition for conducting "
        "business in that territory.\n"
    )
    units = parse_act_text(_pages(text), economy="Australia",
                           act_name="CPTPP Chapter 14", act_ref="cptpp14",
                           source_url="https://example.gov.au/cptpp.pdf",
                           extra_section_patterns=profile["extra_section_patterns"],
                           citation_template=profile["citation_template"])
    cites = {u.article_section for u in units}
    assert any(c.startswith("Art. 14.11") for c in cites), cites
    assert any(c.startswith("Art. 14.13") for c in cites), cites


def test_malay_profile_parses_seksyen_headings():
    profile = seed_parse_profile({"source_type": "act"}, ["malay"])
    assert profile["citation_template"] == "s. {label}"
    text = (
        "Seksyen 12A. Pemprosesan data peribadi\n"
        "Tiada seorang pun boleh memproses data peribadi melainkan mengikut "
        "peruntukan Akta ini dan apa-apa syarat yang ditetapkan.\n"
        "Seksyen 13. Perlindungan data\n"
        "Pengguna data hendaklah mengambil langkah praktik untuk melindungi "
        "data peribadi daripada apa-apa kehilangan atau penyalahgunaan.\n"
    )
    units = parse_act_text(_pages(text), economy="Malaysia",
                           act_name="Akta Perlindungan Data Peribadi 2010",
                           act_ref="a709ms", source_url="https://example.gov.my/709.pdf",
                           extra_section_patterns=profile["extra_section_patterns"],
                           citation_template=profile["citation_template"])
    cites = {u.article_section for u in units}
    assert "s. 12A" in cites and "s. 13" in cites, cites


def test_my_research_pdf_regulation_profile():
    """MY deep-research seeds (circulars/regulations) parse via the generic path."""
    profile = seed_parse_profile({"source_type": "regulation"}, ["malay"])
    assert profile["source_type"] == "regulation"
    ok, reason = evidence_eligibility(
        "Personal Data Protection (Class of Data Users) Regulations 2013",
        profile["source_type"], "in_force")
    assert ok, reason


# ---------------------------------------------------- SG subsidiary legislation
def test_sg_sl_print_view_parses_with_same_parser():
    from packages.extractors.html_act import parse_sso_act

    html = (
        '<title>Personal Data Protection Regulations 2021 - Singapore Statutes Online</title>'
        'Current version as at 19 Jul 2026'
        '<div class="prov1"><td class="prov1Hdr" id="pr3-"><span>Transfer of personal data</span></td>'
        '<td class="prov1Txt"><strong>3.</strong>'
        '<a name="pr3-ps1-"></a>(1) A transferring organisation must not transfer personal data '
        'outside Singapore except in accordance with these Regulations.'
        '<a name="pr3-ps2-"></a>(2) This regulation applies to every transferring organisation.'
        '</td></div>'
    )
    doc = parse_sso_act(html, "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021")
    assert doc.sections and doc.sections[0].number == "3"
    assert len(doc.sections[0].subsections) == 2
    assert "must not transfer personal data" in doc.sections[0].text


def test_sg_builder_recognizes_sl_urls():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_sg_corpus", Path(__file__).resolve().parents[1] / "scripts/build_sg_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._sso_ref("https://sso.agc.gov.sg/SL/PDPA2012-S63-2021?x=1") == (
        "SL", "PDPA2012-S63-2021")
    assert mod._sso_ref("https://sso.agc.gov.sg/Act/PDPA2012") == ("Act", "PDPA2012")
    assert mod._sso_ref("https://example.com/other") is None


# ------------------------------------------------------ snippet-before-gates
def test_final_snippet_constructed_first_then_gated():
    source = ("(1) A person must not disclose any protected information to a "
              "foreign authority unless the disclosure is authorised by an order "
              "of the court; and any such disclosure must be recorded. "
              "(2) Subsection (1) does not apply to anonymised statistics.")
    claimed = "must not disclose any protected information to a foreign"
    final = finalize_snippet(claimed, source)
    # extended to the genuine sentence boundary, never a semicolon/list fragment
    assert final.endswith("any such disclosure must be recorded.")
    # the SAME final text passes verbatim + whole-rule gates
    assert g1_span_exists(final, source).status == "PASS"
    assert g5_whole_rule("P7-I1", final, source).status != "FAIL"
    # idempotent: gating text IS the exported text
    assert finalize_snippet(final, source) == final


def test_finalize_snippet_soft_limit_never_cuts_selected_legal_text():
    clause = "The data user shall protect the personal data from loss. "
    source = clause * 30  # 58 chars * 30 >> 700
    # source-exact but over-long claim: finish the selected sentence; 700 is soft
    final = finalize_snippet(source[:720], source)
    assert len(final) > 700
    assert final.endswith(".")
    assert g1_span_exists(final, source).status == "PASS"
    # a claim that is NOT source-exact comes back unchanged so G1 rejects the
    # exact text that would have been exported (no silent repair)
    fabricated = source[:100] + " fabricated tail"
    assert finalize_snippet(fabricated, source) == fabricated
    assert g1_span_exists(fabricated, source).status == "FAIL"


def test_orchestrator_has_no_post_gate_snippet_mutation():
    src = (Path(__file__).resolve().parents[1] /
           "packages/core/orchestrator.py").read_text()
    gate_pos = src.index("gate_results, ok = run_gates")
    assert "finalize_snippet" in src[:gate_pos], "snippet must be final before gates"
    assert "extend_to_clause_boundary" not in src[gate_pos:], \
        "no snippet mutation is allowed after gating"


# ------------------------------------------------------------- retrieval caps
def test_union_cap_recorded_not_silent(monkeypatch):
    from packages.retrieval import hybrid

    monkeypatch.setattr(hybrid, "UNION_CAP_PER_INDICATOR", 5)

    class StubStore:
        def search_provisions(self, *a, **k):
            return []

    class StubCache:
        def ensure(self, *a, **k):
            pass

        def dense_top(self, *a, **k):
            return []

    corpus = [{"provision_id": f"p{i}", "text": "transfer of personal data rules",
               "props": {"evidence_eligible": True, "legal_status": "in_force"}}
              for i in range(20)]
    caps: list = []
    out = hybrid.retrieve_for_indicator(
        StubStore(), StubCache(), corpus, "P6-I4",
        {"positive_cues": ["transfer of personal data"]}, "Singapore", caps_out=caps)
    assert len(out) == 5
    assert caps and caps[0]["stage"] == "retrieval_union"
    assert caps[0]["input_count"] == 20 and caps[0]["limit"] == 5


def test_union_cap_env_overridable():
    import importlib
    import os

    os.environ["UNION_CAP_PER_INDICATOR"] = "777"
    try:
        from packages.retrieval import hybrid
        importlib.reload(hybrid)
        assert hybrid.UNION_CAP_PER_INDICATOR == 777
    finally:
        del os.environ["UNION_CAP_PER_INDICATOR"]
        from packages.retrieval import hybrid
        importlib.reload(hybrid)


# ------------------------------------------------------------- treaty scoping
def test_treaty_candidates_scoped_to_optin_indicators():
    import yaml

    rubric = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "configs/rdtii/pillar_6.yaml").read_text())
    assert rubric["indicators"]["P6-I5"].get("allowed_source_types") == ["treaty"]
    assert not rubric["indicators"]["P6-I1"].get("allowed_source_types")
    for pillar in ("6", "7"):
        r = yaml.safe_load((Path(__file__).resolve().parents[1] /
                            f"configs/rdtii/pillar_{pillar}.yaml").read_text())
        optins = [k for k, v in r["indicators"].items() if v.get("allowed_source_types")]
        assert optins == (["P6-I5"] if pillar == "6" else [])


def test_source_type_filter_applies_before_ranking_and_caps():
    from packages.retrieval import hybrid

    class StubStore:
        def search_provisions(self, *a, **k):
            return []

    class StubCache:
        def ensure(self, *a, **k):
            pass

        def dense_top(self, *a, **k):
            return []

    corpus = (
        [{"provision_id": f"d{i}", "text": "cross-border transfer of information",
          "props": {"evidence_eligible": True, "legal_status": "in_force",
                    "source_type": "act"}} for i in range(3)]
        + [{"provision_id": f"t{i}", "text": "cross-border transfer of information",
            "props": {"evidence_eligible": True, "legal_status": "in_force",
                      "source_type": "treaty"}} for i in range(3)]
    )
    cue = {"positive_cues": ["cross-border transfer of information"]}
    # domestic indicator (no allowlist): treaties never enter, even before caps
    got = hybrid.retrieve_for_indicator(StubStore(), StubCache(), corpus,
                                        "P6-I1", cue, "Singapore")
    assert {c.provision_id for c in got} == {"d0", "d1", "d2"}
    # treaty-only indicator: ONLY treaty units — a domestic statute cannot reach P6-I5
    got = hybrid.retrieve_for_indicator(
        StubStore(), StubCache(), corpus, "P6-I5",
        {**cue, "allowed_source_types": ["treaty"]}, "Singapore")
    assert {c.provision_id for c in got} == {"t0", "t1", "t2"}
    # ZERO units of the allowed class (AU while DFAT is blocked): empty result,
    # no dense-leg crash on an empty matrix (20 Jul AU P6 AxisError)
    domestic_only = [r for r in corpus if r["props"]["source_type"] == "act"]
    got = hybrid.retrieve_for_indicator(
        StubStore(), StubCache(), domestic_only, "P6-I5",
        {**cue, "allowed_source_types": ["treaty"]}, "Australia")
    assert got == []


# ------------------------------------------------- manifest reconciliation
def test_fetch_seeds_reconciles_metadata_without_refetch(tmp_path, monkeypatch):
    from packages.connectors import seeds_fetch

    monkeypatch.chdir(tmp_path)
    seeds = {"economies": {"Malaysia": [
        {"act": "Test Act", "url": "https://example.gov.my/a.pdf",
         "indicator_code": "P6-I5", "policy": "x", "coverage": "y",
         "source_type": "treaty", "cluster": "Data governance"},
    ]}}
    (tmp_path / "data").mkdir()
    (tmp_path / "data/seeds.json").write_text(json.dumps(seeds))
    raw = tmp_path / "data/raw/my"
    raw.mkdir(parents=True)
    # prior manifest entry: ok but WITHOUT source_type (pre-research state)
    (raw / "seeds_manifest.json").write_text(json.dumps({
        "https://example.gov.my/a.pdf": {"act": "Test Act", "status": "ok",
                                         "file": "data/raw/my/seed_x.pdf"}}))

    class StubClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get(self, url):
            raise AssertionError("cached-ok row must not be refetched")

    monkeypatch.setattr(seeds_fetch.httpx, "Client", StubClient)
    manifest = seeds_fetch.fetch_seeds("Malaysia", ("P6",))
    entry = manifest["https://example.gov.my/a.pdf"]
    assert entry["source_type"] == "treaty"          # metadata refreshed
    assert entry["status"] == "ok"                    # never refetched
    recon = json.loads((raw / "seeds_reconciliation.json").read_text())
    assert recon["already_ok"] == 1 and recon["refreshed_metadata"] == 1


# ----------------------------------------------------------- restamp guard
def test_restamp_requires_full_processing_fingerprint(tmp_path):
    from packages.core.fingerprint import processing_fingerprint
    from packages.core.schemas import RuleUnit
    from packages.graph.sqlite_graph import SqliteGraphStore

    store = SqliteGraphStore(db_path=str(tmp_path / "g.db"))
    fp = processing_fingerprint("abc123", "act", ["malay"], ("ocr:hybrid_accuracy",))
    unit = RuleUnit(
        id="my:test:s1", document_id="my:test", economy="Malaysia",
        law_name="Test Act", article_section="s. 1",
        text="A person must not process personal data without consent under this Act.",
        source_url="https://example.gov.my/a.pdf", location_reference="page 1",
        metadata={"content_sha256": "abc123", "processing_fingerprint": fp,
                  "build_generation": "g1", "legal_status": "in_force",
                  "evidence_eligible": True},
    )
    store.upsert_rule_unit(unit)
    # identical fingerprint (same bytes + extraction version + profile) -> reuse
    assert store.restamp_artifact_generation("Malaysia", fp, "g2") == 1
    assert store.prune_economy_generation("Malaysia", "g2") == 0  # survived
    # SAME source bytes but changed parser profile -> fingerprint miss -> rebuild
    fp_other_profile = processing_fingerprint("abc123", "act", [], ("ocr:hybrid_accuracy",))
    assert fp_other_profile != fp
    assert store.restamp_artifact_generation("Malaysia", fp_other_profile, "g3") == 0
    assert store.prune_economy_generation("Malaysia", "g3") == 1  # stale parse pruned


def test_fingerprint_binds_version_profile_and_grammars():
    import packages.core.fingerprint as fpm

    base = fpm.processing_fingerprint("sha", "act", ["malay"])
    assert fpm.processing_fingerprint("sha", "act", ["malay"]) == base
    assert fpm.processing_fingerprint("sha2", "act", ["malay"]) != base   # bytes
    assert fpm.processing_fingerprint("sha", "treaty", ["malay"]) != base  # profile
    assert fpm.processing_fingerprint("sha", "act", []) != base            # grammars
    old = fpm.EXTRACTION_VERSION
    try:
        fpm.EXTRACTION_VERSION = "9999-01-01.0"
        assert fpm.processing_fingerprint("sha", "act", ["malay"]) != base  # version
    finally:
        fpm.EXTRACTION_VERSION = old


def test_fingerprint_binds_fail_closed_seed_expectations():
    from packages.core.fingerprint import processing_fingerprint
    from packages.ingest.seed_profiles import seed_fingerprint_config

    chapter_14 = {"source_type": "treaty",
                  "expected_citations": ["Art. 14.11"],
                  "expected_phrases": ["cross-border transfer of information"]}
    chapter_12 = {**chapter_14, "expected_citations": ["Art. 12.15"]}
    first = processing_fingerprint(
        "same-source-sha", "treaty", config=seed_fingerprint_config(chapter_14))
    second = processing_fingerprint(
        "same-source-sha", "treaty", config=seed_fingerprint_config(chapter_12))
    assert first != second


# ---------------------------------------------- acquisition/absence integrity
def _write_acquisition_fixture(root: Path) -> None:
    seeds = {"economies": {"Australia": [
        {"act": "CPTPP Chapter 14", "url": "https://dfat.example/cptpp.pdf",
         "indicator_code": "P6-I5", "source_type": "treaty"},
        {"act": "Cybersecurity Act", "url": "https://register.example/cyber.pdf",
         "indicator_code": "P7-I2", "source_type": "act"},
    ]}}
    (root / "data/raw/au").mkdir(parents=True)
    (root / "data/seeds.json").write_text(json.dumps(seeds))
    (root / "data/raw/au/seeds_manifest.json").write_text(json.dumps({
        "https://dfat.example/cptpp.pdf": {
            "act": "CPTPP Chapter 14", "indicator_code": "P6-I5",
            "status": "dead", "http_status": 403, "error": "TLS refused",
        },
        "https://register.example/cyber.pdf": {
            "act": "Cybersecurity Act", "indicator_code": "P7-I2",
            "status": "dead", "http_status": 503,
        },
    }))


def test_dead_seed_is_indicator_scoped_unresolved_coverage(tmp_path, monkeypatch):
    import packages.core.orchestrator as orchestrator

    _write_acquisition_fixture(tmp_path)
    monkeypatch.setattr(orchestrator, "ENGINE_ROOT", tmp_path)
    coverage = orchestrator._coverage_manifest(
        "Australia", "P6-I5",
        {"question": "Has the economy joined no binding transfer agreement?"},
        {"official_sources": [{"name": "DFAT", "domain": "dfat.example"}]},
        [], [], [],
    )
    assert any("ACQUISITION_UNRESOLVED P6-I5" in failure
               and "CPTPP Chapter 14" in failure
               and "http_status=403" in failure
               for failure in coverage.unresolved_failures)
    assert not any("Cybersecurity Act" in failure
                   for failure in coverage.unresolved_failures)
    assert coverage.complete is False


def test_missing_seed_inventory_fails_closed(tmp_path, monkeypatch):
    import packages.core.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "ENGINE_ROOT", tmp_path)
    coverage = orchestrator._coverage_manifest(
        "Australia", "P6-I5", {"question": "binding agreement?"},
        {"official_sources": [{"name": "DFAT", "domain": "dfat.example"}]},
        [], [], [],
    )
    assert any("seed inventory" in failure and "inventory_unavailable" in failure
               for failure in coverage.unresolved_failures)
    assert coverage.complete is False


def test_loaded_official_copy_satisfies_failed_seed_url(tmp_path, monkeypatch):
    import packages.core.orchestrator as orchestrator

    _write_acquisition_fixture(tmp_path)
    monkeypatch.setattr(orchestrator, "ENGINE_ROOT", tmp_path)
    corpus = [{
        "provision_id": "p1", "text": "Each Party shall allow cross-border transfer.",
        "props": {"law_name": "CPTPP Chapter 14", "source_artifact_id": "artifact-1",
                  "legal_status": "in_force", "evidence_eligible": True,
                  "source_type": "treaty"},
    }]
    coverage = orchestrator._coverage_manifest(
        "Australia", "P6-I5",
        {"question": "Has the economy joined no binding transfer agreement?"},
        {"official_sources": [{"name": "DFAT", "domain": "dfat.example"}]},
        [], corpus, [],
    )
    assert not any("ACQUISITION_UNRESOLVED" in failure
                   for failure in coverage.unresolved_failures)
    assert coverage.complete is True


def test_expected_evidence_fails_closed():
    from packages.ingest.seed_profiles import missing_expectations

    profile = seed_parse_profile({"source_type": "treaty"})
    text = ("Article 1: Definitions\nFor the purposes of this Chapter the term "
            "covered person means a person of a Party as defined in this agreement.\n")
    units = parse_act_text(_pages(text), economy="Australia",
                           act_name="Wrong Chapter", act_ref="wrong",
                           source_url="https://example.gov.au/ch1.pdf",
                           extra_section_patterns=profile["extra_section_patterns"],
                           citation_template=profile["citation_template"])
    entry = {"expected_citations": ["Art. 14.11"],
             "expected_phrases": ["cross-border transfer of information"]}
    missing = missing_expectations(entry, units)
    assert "Art. 14.11" in missing and "cross-border transfer of information" in missing
    # the right chapter satisfies both declarations
    good = ("Article 14.11: Cross-Border Transfer of Information by Electronic Means\n"
            "1. Each Party shall allow the cross-border transfer of information by "
            "electronic means, including personal information, for business.\n")
    good_units = parse_act_text(_pages(good), economy="Australia",
                                act_name="CPTPP Chapter 14", act_ref="c14",
                                source_url="https://example.gov.au/ch14.pdf",
                                extra_section_patterns=profile["extra_section_patterns"],
                                citation_template=profile["citation_template"])
    assert missing_expectations(entry, good_units) == []


def test_long_span_flagged_not_truncated():
    from packages.verifier.gates import finalize_snippet_result, g9_structural_closure

    # one giant clause with NO internal boundary: kept whole + WARN flag
    source = "the data user shall " + "and ".join(f"obligation {i} " for i in range(80))
    final = finalize_snippet_result(source, source)
    assert len(final.text) > 700  # never character-truncated
    flag = g9_structural_closure(final)
    assert flag.status == "FAIL"
    assert "FAIL_" in flag.reason
