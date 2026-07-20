from __future__ import annotations

from datetime import datetime, timezone

import fitz
import pytest

from packages.core.citations import citation_path
from packages.core.evidence import SourceValidationError, source_artifact_from_file, verify_artifact
from packages.core.finalization import FinalizationError, validate_final_finding
from packages.core.legal_controls import content_eligibility, evidence_eligibility, resolve_status
from packages.core.schemas import (CitationProof, MappedFinding, ReviewDecision, RuleUnit,
                                   SearchCoverageManifest, StatusEvidence)
from packages.extractors.pdf import extract_pdf, materialize_page_evidence
from packages.extractors.pdf_align import align_to_pdf
from packages.graph.sqlite_graph import SqliteGraphStore


def _pdf(path, text="33D Exact PDF source characters for a qualifying legal provision."):
    doc = fitz.open(); page = doc.new_page(); page.insert_text((72, 72), text); doc.save(path); doc.close()


def _status(status="in_force"):
    return StatusEvidence(status=status, fact_url="https://official.example/status",
                          fact_text="Official current in force compilation",
                          resolution_rule="official structured status field")


def test_source_hash_and_mislabeled_download_guards(tmp_path):
    bad = tmp_path / "bad.pdf"; bad.write_text("<html>Access denied login</html>")
    with pytest.raises(SourceValidationError):
        source_artifact_from_file(bad, original_url="https://official.example/x",
            source_type="act", status_evidence=_status(), official_domains={"official.example"},
            expected_mime="application/pdf")
    pdf = tmp_path / "x.pdf"; _pdf(pdf)
    artifact = source_artifact_from_file(pdf, original_url="https://official.example/x",
        source_type="act", status_evidence=_status(), official_domains={"official.example"},
        expected_mime="application/pdf")
    verify_artifact(artifact)
    pdf.write_bytes(pdf.read_bytes() + b"changed")
    with pytest.raises(SourceValidationError): verify_artifact(artifact)


def test_lossless_graph_roundtrip_and_page_spans(tmp_path):
    pdf = tmp_path / "x.pdf"; _pdf(pdf)
    artifact = source_artifact_from_file(pdf, original_url="https://official.example/x",
        source_type="act", status_evidence=_status(), official_domains={"official.example"},
        expected_mime="application/pdf")
    pages = extract_pdf(str(pdf)); page_records, spans = materialize_page_evidence(pages, artifact.id)
    unit = RuleUnit(id="au:x:s33D", document_id="au:x", economy="Australia", law_name="X Act",
        article_section="s. 33D", text=pages[0].text, source_url=artifact.retrieved_url,
        location_reference="page 1", source_artifact_id=artifact.id, raw_context=pages[0].text,
        linked_span_ids=[s.id for s in spans], metadata={"archived_copy": str(pdf),
        "content_sha256": artifact.sha256, "evidence_eligible": True,
        "legal_status": "in_force", "status_evidence": _status().model_dump(mode="json")})
    store = SqliteGraphStore(tmp_path / "g.db"); store.upsert_source_artifact(artifact)
    store.upsert_page_artifacts(page_records); store.upsert_text_spans(spans); store.upsert_rule_unit(unit)
    props = store.search_provisions("qualifying legal", "Australia", 1)[0]["props"]
    assert props["source_artifact_id"] == artifact.id
    assert props["content_sha256"] == artifact.sha256 and props["linked_span_ids"]
    assert store._connect().execute("select count(*) from text_spans").fetchone()[0] > 0


def test_sqlite_stores_full_finding_and_immutable_review(tmp_path):
    store = SqliteGraphStore(tmp_path / "g.db")
    finding = MappedFinding(Economy="Singapore", **{"Law Name":"X Act","Indicator ID":"P7-I1",
        "Article / Section":"s. 1","Discovery Tag":"KNOWN","Location Reference":"#s1",
        "Verbatim Snippet":"Exact source text","Mapping Rationale":"framework evidence",
        "Source URL":"https://official.example/x","Confidence":.9,"Status":"in_force"})
    store.upsert_finding("f1", "run1", finding)
    assert store._connect().execute("select count(*) from findings").fetchone()[0] == 1
    decision = ReviewDecision(decision="rejected", reviewer_name="User", reviewer_role="Legal",
        reviewed_at=datetime.now(timezone.utc), citation_checked=True, mapping_checked=True,
        status_checked=True)
    store.record_review_decision("f1", decision)
    changed = decision.model_copy(update={"correction_note": "changed"})
    with pytest.raises(ValueError, match="immutable ReviewDecision"):
        store.record_review_decision("f1", changed)


def test_au_alignment_replaces_xhtml_text_with_exact_pdf_characters(tmp_path):
    pdf = tmp_path / "au.pdf"; exact = "Exact PDF source characters for a qualifying legal provision."
    _pdf(pdf, exact)
    unit = RuleUnit(id="u", document_id="d", economy="Australia", law_name="X Act",
                    article_section="s. 33D", text=exact.replace("  ", " "),
                    source_url="https://official.example", location_reference="unaligned")
    aligned, total = align_to_pdf([unit], [str(pdf)])
    assert (aligned, total) == (1, 1)
    assert unit.text in fitz.open(pdf)[0].get_text() and unit.metadata["pdf_alignment"] == "exact"


def test_citation_hierarchy_and_ineligible_sources():
    assert citation_path("Sch 1, cl. 474.17A(1)(c)(iii)") == [
        "Schedule 1", "clause 474.17A", "item (1)", "item (c)", "item (iii)"]
    assert evidence_eligibility("RCEP Agreement - Malaysia", "act", "in_force")[0] is False
    assert evidence_eligibility("Personal Data Protection Bill 2024", "act", "unknown")[0] is False
    assert evidence_eligibility("Privacy Act 1988", "act", "in_force") == (True, None)
    assert evidence_eligibility("Privacy Act 1988", "act", "unknown") == (False, "STATUS_UNKNOWN")
    assert evidence_eligibility("Privacy Act 1988", "international_agreement", "in_force") == (
        False, "INTERNATIONAL_AGREEMENT")
    conflict = resolve_status(fact_url="https://official.example", fact_text="repealed",
                              explicit_status="in_force")
    assert conflict.conflicting is True


def test_finalization_requires_proof_status_hash_and_named_approval(tmp_path):
    pdf = tmp_path / "x.pdf"; snippet = "Exact PDF source characters"; _pdf(pdf, snippet)
    artifact = source_artifact_from_file(pdf, original_url="https://official.example/x",
        source_type="act", status_evidence=_status(), official_domains={"official.example"},
        expected_mime="application/pdf")
    review = ReviewDecision(decision="approved", reviewer_name="User", reviewer_role="Legal reviewer",
        reviewed_at=datetime.now(timezone.utc), citation_checked=True, mapping_checked=True,
        status_checked=True)
    proof = CitationProof(source_artifact_id=artifact.id, source_sha256=artifact.sha256,
        page_number=1, article_path=["section 1"], span_ids=["s1"], bboxes=[(1, 1, 2, 2)],
        exact_snippet=snippet, normalized_snippet=snippet.lower(), alignment_status="exact",
        alignment_score=1, gate_results=[{"gate_id": "G1", "status": "PASS"}])
    finding = MappedFinding(Economy="Australia", **{"Law Name": "X Act", "Indicator ID": "P7-I1",
        "Article / Section": "s. 1", "Discovery Tag": "KNOWN", "Location Reference": "page 1",
        "Verbatim Snippet": snippet, "Mapping Rationale": "Maps exactly", "Source URL": artifact.retrieved_url,
        "Confidence": .9, "Status": "in_force"}, source_artifact_id=artifact.id,
        status_evidence_record=_status(), citation_proof=proof, review=review,
        reviewer_decision="approved")
    validate_final_finding(finding, {artifact.id: artifact})
    finding.review = None; finding.reviewer_decision = "pending"
    with pytest.raises(FinalizationError, match="human approval"):
        validate_final_finding(finding, {artifact.id: artifact})


@pytest.mark.parametrize(("mutation", "message"), [
    (lambda f: setattr(f, "status", "unknown"), "legal status"),
    (lambda f: setattr(f.citation_proof, "alignment_status", "unaligned"), "unresolved"),
    (lambda f: setattr(f, "source_artifact_id", None), "missing SourceArtifact"),
])
def test_end_to_end_final_gate_blocks_unsafe_rows(tmp_path, mutation, message):
    pdf = tmp_path / "x.pdf"; snippet = "Exact source text"; _pdf(pdf, snippet)
    artifact = source_artifact_from_file(pdf, original_url="https://official.example/x",
        source_type="act", status_evidence=_status(), official_domains={"official.example"},
        expected_mime="application/pdf")
    review = ReviewDecision(decision="approved", reviewer_name="User", reviewer_role="Legal",
        reviewed_at=datetime.now(timezone.utc), citation_checked=True, mapping_checked=True,
        status_checked=True)
    proof = CitationProof(source_artifact_id=artifact.id, source_sha256=artifact.sha256,
        page_number=1, article_path=["section 1"], span_ids=["s1"], bboxes=[(1,1,2,2)],
        exact_snippet=snippet, normalized_snippet=snippet.lower(), alignment_status="exact",
        alignment_score=1, gate_results=[])
    finding = MappedFinding(Economy="Australia", **{"Law Name":"X Act","Indicator ID":"P7-I1",
        "Article / Section":"s. 1","Discovery Tag":"KNOWN","Location Reference":"page 1",
        "Verbatim Snippet":snippet,"Mapping Rationale":"exact","Source URL":artifact.retrieved_url,
        "Confidence":.9,"Status":"in_force"}, source_artifact_id=artifact.id,
        status_evidence_record=_status(), citation_proof=proof, review=review,
        reviewer_decision="approved")
    mutation(finding)
    with pytest.raises(FinalizationError, match=message):
        validate_final_finding(finding, {artifact.id: artifact})


def test_absence_without_governing_artifact_stays_valid_but_blocked():
    from packages.core.orchestrator import _absence_row
    from packages.core.schemas import SearchCoverageManifest

    coverage = SearchCoverageManifest(economy="Malaysia", indicator_id="P6-I1",
        portals=["AGC"], instruments=["PDPA"], queries=["localization"])
    finding = _absence_row("Malaysia", "P6-I1", "PDPA", "https://official.example",
                           "model", coverage, {})
    assert finding.status == "unknown" and finding.source_artifact_id is None
    assert finding.reviewer_decision == "pending"


def test_absence_manifest_requires_proof_every_instrument_was_searched():
    manifest = SearchCoverageManifest(economy="Australia", indicator_id="P6-I1",
        portals=["Federal Register"], instruments=["Privacy Act", "TIA"],
        queries=["local storage"], instrument_results=[{
            "instrument": "Privacy Act", "searched": True, "source_artifact_id": "a1"}])
    assert manifest.complete is False
    complete = manifest.model_copy(update={"instrument_results": manifest.instrument_results + [{
        "instrument": "TIA", "searched": True, "source_artifact_id": "a2"}]})
    assert complete.complete is True


def test_named_approval_cannot_finalize_absence_with_failed_acquisition(tmp_path):
    pdf = tmp_path / "governing.pdf"
    _pdf(pdf, "Official governing instrument")
    artifact = source_artifact_from_file(
        pdf, original_url="https://official.example/governing.pdf",
        source_type="act", status_evidence=_status(),
        official_domains={"official.example"}, expected_mime="application/pdf")
    coverage = SearchCoverageManifest(
        economy="Australia", indicator_id="P6-I5", portals=["DFAT"],
        instruments=["Governing Act"], queries=["binding data transfer agreement"],
        instrument_results=[{"instrument": "Governing Act", "searched": True,
                             "source_artifact_id": artifact.id}],
        unresolved_failures=[
            "ACQUISITION_UNRESOLVED P6-I5: CPTPP Chapter 14 | status=dead"
        ],
    )
    review = ReviewDecision(
        decision="approved", reviewer_name="Named Reviewer", reviewer_role="Legal",
        reviewed_at=datetime.now(timezone.utc), citation_checked=True,
        mapping_checked=True, status_checked=True)
    finding = MappedFinding(
        Economy="Australia", **{
            "Law Name": "Governing Act", "Indicator ID": "P6-I5",
            "Article / Section": "n/a", "Discovery Tag": "KNOWN",
            "Location Reference": "n/a",
            "Verbatim Snippet": "NO_EVIDENCE_FOUND_PENDING_REVIEW",
            "Mapping Rationale": "No evidence found after configured search.",
            "Source URL": artifact.retrieved_url, "Confidence": 0.6,
            "Status": "in_force",
        },
        source_artifact_id=artifact.id, status_evidence_record=_status(),
        search_coverage_manifest=coverage, review=review,
        reviewer_decision="approved")
    with pytest.raises(FinalizationError, match="complete SearchCoverageManifest"):
        validate_final_finding(finding, {artifact.id: artifact})


def test_sparse_retrieval_cannot_leak_ineligible_nodes():
    from packages.retrieval.hybrid import retrieve_for_indicator

    class Store:
        def search_provisions(self, *args, **kwargs):
            return [{"provision_id": "bill", "text": "must store locally", "score": 9,
                     "props": {"evidence_eligible": False, "legal_status": "draft"}}]
    class Cache:
        def ensure(self, items): pass
        def dense_top(self, *args, **kwargs): return []
    assert retrieve_for_indicator(Store(), Cache(), [], "P6-I1",
        {"positive_cues": ["store locally"]}, "Australia") == []


def test_defined_term_exact_leg_survives_without_sparse_or_dense_hits():
    from packages.retrieval.hybrid import retrieve_for_indicator
    class Store:
        def search_provisions(self, *args, **kwargs): return []
    class Cache:
        def ensure(self, items): pass
        def dense_top(self, *args, **kwargs): return []
    corpus = [{"provision_id": "p1", "text": "An authorised officer may inspect data.",
               "props": {"evidence_eligible": True, "legal_status": "in_force"}}]
    hits = retrieve_for_indicator(Store(), Cache(), corpus, "P7-I5",
        {"defined_terms": ["authorised officer"]}, "Australia")
    assert [h.provision_id for h in hits] == ["p1"]
    assert hits[0].matched_queries == ["exact-phrase:authorised officer"]


def test_repeated_draft_watermark_is_content_ineligible():
    pages = ["Section 1\nDRAFT\noperative text"] * 8 + ["final-looking page"] * 2
    assert content_eligibility(pages) == (False, "BILL_OR_DRAFT_CONTENT")
    assert content_eligibility(["The history mentions a draft bill once.", "Section 2"])[0]


def test_my_builder_matches_gold_title_despite_inserted_act_number():
    from scripts.build_my_corpus import is_relevant_act

    assert is_relevant_act(
        {"indicator_code": None}, "Criminal Procedure Code (Act 593) 2018",
        {"criminal procedure code 2018"},
    )


def test_pdf_validation_allows_nul_padding_but_not_trailing_payload():
    from packages.core.evidence import SourceValidationError, validate_source_bytes

    valid = b"%PDF-1.7\nobject data\n%%EOF" + (b"\x00" * 5000)
    assert validate_source_bytes(valid, "application/pdf") == "application/pdf"
    prefix = b"%PDF-1.7\nobject data\n%%EOF" + (b"\x00" * 5000)
    offset_marked = prefix + str(len(prefix)).encode()
    assert validate_source_bytes(offset_marked, "application/pdf") == "application/pdf"
    with pytest.raises(SourceValidationError, match="non-padding"):
        validate_source_bytes(valid + b"appended payload", "application/pdf")
    with pytest.raises(SourceValidationError, match="non-padding"):
        validate_source_bytes(valid + b"1234", "application/pdf")


def test_screen_bypass_is_limited_to_current_indicator_anchor_ids():
    from types import SimpleNamespace
    from packages.core.orchestrator import _partition_current_anchors

    candidates = [SimpleNamespace(provision_id="current"),
                  SimpleNamespace(provision_id="known-under-other-indicator")]
    anchors, rest = _partition_current_anchors(candidates, {"current"})
    assert [item.provision_id for item in anchors] == ["current"]
    assert [item.provision_id for item in rest] == ["known-under-other-indicator"]
