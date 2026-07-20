from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


JsonDict = dict[str, Any]
LegalStatus = Literal[
    "draft", "not_yet_effective", "in_force", "amended", "repealed",
    "superseded", "unknown",
]
ExtractionRoute = Literal[
    "NATIVE_SIMPLE", "NATIVE_COMPLEX", "SCANNED", "MIXED", "REVIEW",
]


class StatusEvidence(BaseModel):
    status: LegalStatus
    fact_url: str = Field(min_length=1)
    fact_text: str = Field(min_length=1)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_date: str | None = None
    end_date: str | None = None
    resolution_rule: str = Field(min_length=1)
    conflicting: bool = False


class SourceArtifact(BaseModel):
    """Immutable identity and authority record for one archived source."""

    id: str
    original_url: str
    retrieved_url: str
    source_type: str
    mime_type: str
    byte_length: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accessed_at: datetime
    official_domain: str
    official: bool
    local_path: str
    register_id: str | None = None
    version_id: str | None = None
    status_evidence: StatusEvidence
    metadata: JsonDict = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class TextSpan(BaseModel):
    id: str
    source_artifact_id: str
    page_number: int = Field(ge=1)
    text: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    bbox: tuple[float, float, float, float]
    reading_order: int = Field(ge=0)
    extraction_method: str
    engine_version: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = ConfigDict(frozen=True)


class PageArtifact(BaseModel):
    id: str
    source_artifact_id: str
    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    route: ExtractionRoute
    route_reasons: list[str]
    raw_text: str
    searchable_text: str
    page_image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    span_ids: list[str]
    quality_signals: JsonDict = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class CitationProof(BaseModel):
    source_artifact_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int | None = Field(default=None, ge=1)
    anchor: str | None = None
    article_path: list[str]
    span_ids: list[str]
    bboxes: list[tuple[float, float, float, float]]
    exact_snippet: str
    normalized_snippet: str
    source_start_char: int | None = Field(default=None, ge=0)
    source_end_char: int | None = Field(default=None, ge=0)
    alignment_status: Literal["exact", "anchor", "unaligned", "ambiguous"]
    alignment_score: float = Field(ge=0.0, le=1.0)
    gate_results: list[JsonDict] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchCoverageManifest(BaseModel):
    economy: str
    indicator_id: str
    portals: list[str]
    instruments: list[str]
    queries: list[str]
    searched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exclusions: list[str] = Field(default_factory=list)
    caps: list[str] = Field(default_factory=list)
    unresolved_failures: list[str] = Field(default_factory=list)
    # One record per governing/search instrument.  A list of names alone does
    # not prove that each instrument was actually acquired and searched.
    instrument_results: list[JsonDict] = Field(default_factory=list)
    query_result_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def complete(self) -> bool:
        if not self.portals or not self.instruments or not self.queries:
            return False
        if self.unresolved_failures:
            return False
        searched = {str(r.get("instrument", "")) for r in self.instrument_results
                    if r.get("searched") is True and r.get("source_artifact_id")}
        return bool(searched) and all(i in searched for i in self.instruments)


class ReviewDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer_name: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewed_at: datetime
    citation_checked: bool
    mapping_checked: bool
    status_checked: bool
    correction_note: str | None = None
    citation_reviewer_name: str | None = None
    mapping_reviewer_name: str | None = None
    status_reviewer_name: str | None = None

    @property
    def complete_approval(self) -> bool:
        return self.decision == "approved" and all(
            (self.citation_checked, self.mapping_checked, self.status_checked)
        )


class OCRToken(BaseModel):
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bbox: list[float] | None = None
    page_number: int | None = Field(default=None, ge=1)


class SourceDocument(BaseModel):
    id: str
    title: str
    economy: str
    authority: str
    source_url: str
    content_hash: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: JsonDict = Field(default_factory=dict)


class ExtractedPage(BaseModel):
    document_id: str
    page_number: int = Field(ge=1)
    text: str
    source_url: str
    location_reference: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tokens: list[OCRToken] = Field(default_factory=list)
    metadata: JsonDict = Field(default_factory=dict)


class RuleUnit(BaseModel):
    id: str
    document_id: str
    economy: str
    law_name: str
    law_number_ref: str | None = None
    last_amended: str | None = None
    article_section: str
    text: str
    source_url: str
    location_reference: str
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: JsonDict = Field(default_factory=dict)
    source_artifact_id: str | None = None
    raw_context: str | None = None
    linked_span_ids: list[str] = Field(default_factory=list)


class PredicateTuple(BaseModel):
    actor: str | None = None
    action: str | None = None
    object: str | None = None
    destination: str | None = None
    modality: str | None = None
    condition: str | None = None
    exception: str | None = None
    source_status: str | None = None
    metadata: JsonDict = Field(default_factory=dict)


class CandidateFinding(BaseModel):
    economy: str
    law_name: str
    law_number_ref: str | None = None
    last_amended: str | None = None
    indicator_id: str
    article_section: str
    discovery_tag: Literal["NEW", "KNOWN", "UNCLEAR"]
    location_reference: str
    verbatim_snippet: str
    mapping_rationale: str
    source_url: str
    confidence: float = Field(ge=0.0, le=1.0)
    graph_path: list[str] = Field(default_factory=list)
    verifier_risks: list[str] = Field(default_factory=list)


class MappedFinding(BaseModel):
    economy: str = Field(alias="Economy")
    law_name: str = Field(alias="Law Name")
    law_number_ref: str | None = Field(default=None, alias="Law Number / Ref")
    last_amended: str | None = Field(default=None, alias="Last Amended")
    indicator_id: str = Field(alias="Indicator ID")
    article_section: str = Field(alias="Article / Section")
    discovery_tag: Literal["NEW", "KNOWN"] = Field(alias="Discovery Tag")
    location_reference: str = Field(alias="Location Reference")
    verbatim_snippet: str = Field(alias="Verbatim Snippet")
    mapping_rationale: str = Field(alias="Mapping Rationale")
    source_url: str = Field(alias="Source URL")
    confidence: float = Field(alias="Confidence", ge=0.0, le=1.0)
    notes: str | None = Field(default=None, alias="Notes")
    # Appended-after-the-13 columns (allowed per the 15-Jun Q&A); kept after the required set.
    coverage: str | None = Field(default=None, alias="Coverage")
    verbatim_snippet_en: str | None = Field(default=None, alias="Verbatim Snippet (English)")
    status: LegalStatus | None = Field(default=None, alias="Status")
    model_version: str | None = None  # JSON-only provenance (which model produced the row)
    graph_path: list[str] = Field(default_factory=list)
    verifier_risks: list[str] = Field(default_factory=list)
    # JSON-only provenance/curation fields (EUI 12-field spec + P2' envelope contract)
    archived_copy: str | None = None
    access_date: str | None = None
    # R6 (P3.5): mean OCR recognition confidence is NOT a character error rate.
    # ocr_quality_cer is populated ONLY from true CER vs human-transcribed gold.
    mean_ocr_confidence: float | None = None   # None = native text (no OCR involved)
    ocr_quality_cer: float | None = None       # true CER only; else None
    status_evidence: str | None = None         # what backs the Status field (A2)
    status_evidence_record: StatusEvidence | None = None
    citation_tier: str | None = None           # [settled] / [verify] / [verify-pinpoint]
    reviewer_decision: str = "pending"          # pending / approved / rejected (Legal HITL)
    source_artifact_id: str | None = None
    citation_proof: CitationProof | None = None
    search_coverage_manifest: SearchCoverageManifest | None = None
    review: ReviewDecision | None = None
    raw_context: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator(
        "economy",
        "law_name",
        "indicator_id",
        "article_section",
        "location_reference",
        "verbatim_snippet",
        "mapping_rationale",
        "source_url",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be non-empty")
        return value


class GateResult(BaseModel):
    gate_id: str
    status: Literal["PASS", "FAIL", "WARN", "NOT_RUN"]
    reason: str
    evidence_reference: str | None = None
    metadata: JsonDict = Field(default_factory=dict)


class RunEnvelope(BaseModel):
    run_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    country: str
    pillar: int
    provider_profile: str
    findings: list[MappedFinding]
    gates: list[GateResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: JsonDict = Field(default_factory=dict)
