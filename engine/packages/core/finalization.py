from __future__ import annotations

import hashlib
import json

from packages.core.evidence import verify_artifact
from packages.core.legal_controls import evidence_eligibility
from packages.core.schemas import MappedFinding, ReviewDecision, SourceArtifact, TextSpan


class FinalizationError(ValueError):
    pass


def finding_key(finding: MappedFinding) -> str:
    payload = "\x1f".join((finding.economy, finding.indicator_id, finding.law_name,
                            finding.article_section, finding.source_artifact_id or "",
                            finding.verbatim_snippet))
    return hashlib.sha256(payload.encode()).hexdigest()


def review_subject_payload(finding: MappedFinding) -> dict:
    """Material facts a legal approval actually attests to.

    Finding keys identify rows; this payload additionally binds approval to the
    complete proof, status fact, rationale and absence coverage.  Volatile model
    object formatting is removed by canonical JSON serialization, but evidence
    timestamps remain material: refreshed currentness/coverage requires review.
    """
    proof = (finding.citation_proof.model_dump(mode="json", exclude={"verified_at"})
             if finding.citation_proof else None)
    return {
        "contract": "clausechain-review-subject-v1",
        "finding_key": finding_key(finding),
        "economy": finding.economy,
        "indicator_id": finding.indicator_id,
        "law_name": finding.law_name,
        "article_section": finding.article_section,
        "verbatim_snippet": finding.verbatim_snippet,
        "mapping_rationale": finding.mapping_rationale,
        "source_url": finding.source_url,
        "source_artifact_id": finding.source_artifact_id,
        "citation_proof": proof,
        "status_evidence": (finding.status_evidence_record.model_dump(mode="json")
                            if finding.status_evidence_record else None),
        "search_coverage_manifest": (
            finding.search_coverage_manifest.model_dump(mode="json")
            if finding.search_coverage_manifest else None
        ),
    }


def review_subject_hash(finding: MappedFinding) -> str:
    encoded = json.dumps(
        review_subject_payload(finding), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_final_finding(finding: MappedFinding,
                           artifacts: dict[str, SourceArtifact],
                           spans: dict[str, TextSpan] | None = None) -> None:
    errors: list[str] = []
    review = finding.review
    if not review or not review.complete_approval:
        errors.append("missing complete named human approval")
    if finding.reviewer_decision != "approved":
        errors.append("reviewer_decision is not approved")
    if finding.discovery_tag == "NEW" and review:
        if not review.citation_reviewer_name or not review.mapping_reviewer_name:
            errors.append("NEW row lacks named independent citation and mapping checks")
        elif review.citation_reviewer_name == review.mapping_reviewer_name:
            errors.append("NEW row citation and mapping checks are not independent")
    status = finding.status_evidence_record
    if finding.status != "in_force" or not status or status.status != "in_force" or status.conflicting:
        errors.append("legal status is not evidence-backed in_force")
    artifact = artifacts.get(finding.source_artifact_id or "")
    if not artifact:
        errors.append("missing SourceArtifact")
    else:
        if not artifact.official:
            errors.append("source artifact is not official")
        eligible, reason = evidence_eligibility(
            finding.law_name, artifact.source_type,
            status.status if status else "unknown")
        if not eligible:
            errors.append(f"source is not final-evidence eligible: {reason}")
        try:
            verify_artifact(artifact)
        except (OSError, ValueError) as error:
            errors.append(f"source artifact integrity failed: {error}")
    is_absence = "NO_EVIDENCE_FOUND" in finding.verbatim_snippet
    proof = finding.citation_proof
    if is_absence:
        manifest = finding.search_coverage_manifest
        if not manifest or not manifest.complete:
            errors.append("absence lacks a complete SearchCoverageManifest")
    else:
        if not proof:
            errors.append("missing CitationProof")
        else:
            if proof.source_artifact_id != finding.source_artifact_id:
                errors.append("CitationProof source does not match finding")
            if artifact and proof.source_sha256 != artifact.sha256:
                errors.append("CitationProof hash does not match SourceArtifact")
            if proof.exact_snippet != finding.verbatim_snippet:
                errors.append("CitationProof exact snippet differs from export")
            if proof.source_start_char is None or proof.source_end_char is None:
                errors.append("CitationProof lacks canonical source offsets")
            elif proof.source_end_char <= proof.source_start_char:
                errors.append("CitationProof source offsets are invalid")
            elif not finding.raw_context:
                errors.append("finding lacks canonical raw_context for proof replay")
            elif finding.raw_context[proof.source_start_char:proof.source_end_char] != proof.exact_snippet:
                errors.append("CitationProof offsets do not reproduce the exact export snippet")
            if proof.alignment_status not in {"exact", "anchor"}:
                errors.append("citation is unresolved")
            if not proof.page_number and not proof.anchor:
                errors.append("citation has neither page nor anchor")
            if proof.page_number and (not proof.span_ids or not proof.bboxes):
                errors.append("page citation lacks stored span IDs or highlight boxes")
            if not proof.span_ids:
                errors.append("citation lacks immutable source span IDs")
            elif spans is not None:
                selected = [spans.get(span_id) for span_id in proof.span_ids]
                if any(span is None for span in selected):
                    errors.append("CitationProof references missing TextSpan")
                else:
                    parts = [span.text for span in selected if span]
                    source_forms = ("".join(parts), " ".join(parts), "\n".join(parts))
                    if not any(proof.exact_snippet in source_text for source_text in source_forms):
                        # A snippet may cross adjacent layout spans; whitespace-only
                        # differences are location aids, never exported replacements.
                        errors.append("exported snippet is not an exact stored TextSpan slice")
            if any(g.get("status") == "FAIL" for g in proof.gate_results):
                errors.append("CitationProof contains a failed gate")
            closure_gates = [g for g in proof.gate_results if g.get("gate_id") == "G9"]
            if not closure_gates:
                errors.append("CitationProof lacks structural closure gate G9")
            elif closure_gates[-1].get("metadata", {}).get("closure_code") not in {
                    "PASS_CLOSED", "PASS_LONG_BUT_CLOSED"}:
                errors.append("CitationProof does not prove a structurally closed snippet")
            if not proof.exact_snippet.rstrip().endswith((".", "!", "?")):
                errors.append("exported snippet does not end at a sentence/paragraph boundary")
    if errors:
        raise FinalizationError(f"{finding_key(finding)}: " + "; ".join(errors))


def load_artifacts(path) -> dict[str, SourceArtifact]:
    data = json.loads(path.read_text())
    return {item["id"]: SourceArtifact.model_validate(item) for item in data}


def apply_decision(finding: MappedFinding, decision: ReviewDecision) -> MappedFinding:
    updated = finding.model_copy(deep=True)
    updated.review = decision
    updated.reviewer_decision = decision.decision
    return updated
