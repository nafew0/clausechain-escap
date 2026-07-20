from __future__ import annotations

from packages.core.curation import curate_new_findings
from packages.core.schemas import CitationProof, MappedFinding


def _finding(article: str, rationale: str, confidence: float = 0.8,
             tag: str = "NEW") -> MappedFinding:
    proof = CitationProof(
        source_artifact_id="sha256:" + "a" * 64,
        source_sha256="a" * 64,
        anchor="#pr1-",
        article_path=["section 1"],
        span_ids=["span-1"],
        bboxes=[],
        exact_snippet="cyber security incident response requirement",
        normalized_snippet="cyber security incident response requirement",
        alignment_status="anchor",
        alignment_score=1.0,
        gate_results=[],
    )
    return MappedFinding(
        economy="Singapore", law_name="Cybersecurity Act 2018",
        indicator_id="P7-I2", article_section=article,
        discovery_tag=tag, location_reference="#pr1-",
        verbatim_snippet="cyber security incident response requirement",
        mapping_rationale=rationale,
        source_url="https://sso.agc.gov.sg/Act/CA2018", confidence=confidence,
        citation_proof=proof,
    )


def test_new_curation_caps_redundant_framework_evidence_and_audits_exclusions():
    rows = [
        _finding("s. 3", "The object establishes a cybersecurity framework", 0.9),
        _finding("s. 5", "The Commissioner responds to incidents", 0.88),
        _finding("s. 6", "The Commissioner reports another incident", 0.7),
    ]
    kept, excluded = curate_new_findings(rows)
    assert len(kept) == 2
    assert len(excluded) == 1
    assert excluded[0]["reason"].startswith("redundant NEW evidence")


def test_curation_never_removes_known_rows():
    known = _finding("s. 3", "framework", tag="KNOWN")
    kept, excluded = curate_new_findings([known])
    assert kept == [known]
    assert excluded == []
