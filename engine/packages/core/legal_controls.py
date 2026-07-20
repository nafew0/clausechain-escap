from __future__ import annotations

import re
from datetime import datetime, timezone

from packages.core.schemas import LegalStatus, StatusEvidence


INELIGIBLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("BILL_OR_DRAFT", re.compile(r"\b(bill|draft|exposure draft)\b", re.I)),
    ("CONSULTATION", re.compile(r"\bconsultation|discussion paper\b", re.I)),
    ("INTERNATIONAL_AGREEMENT", re.compile(r"\b(agreement|treaty|rcep)\b", re.I)),
    ("SECONDARY_COMMENTARY", re.compile(r"\b(commentary|client alert|legal update|blog)\b", re.I)),
    ("COMPANY_POLICY", re.compile(r"\b(company|corporate) policy\b", re.I)),
)

ELIGIBLE_SOURCE_TYPES = {"act", "statute", "regulation", "official_code", "official_instrument",
                         "treaty"}
INELIGIBLE_SOURCE_TYPES = {
    "bill": "BILL_OR_DRAFT", "draft": "BILL_OR_DRAFT",
    "consultation": "CONSULTATION", "international_agreement": "INTERNATIONAL_AGREEMENT",
    "commentary": "SECONDARY_COMMENTARY", "company_policy": "COMPANY_POLICY",
}


def evidence_eligibility(law_name: str, source_type: str = "statute",
                         legal_status: LegalStatus = "unknown") -> tuple[bool, str | None]:
    source_type = source_type.strip().lower()
    if source_type in INELIGIBLE_SOURCE_TYPES:
        return False, INELIGIBLE_SOURCE_TYPES[source_type]
    for reason, pattern in INELIGIBLE_PATTERNS:
        # A seed that DECLARES source_type "treaty" (official state register, P6-I5
        # rubric's own primary source) is not disqualified by treaty words in its
        # name; the name heuristic exists for undeclared/defaulted source types.
        if reason == "INTERNATIONAL_AGREEMENT" and source_type == "treaty":
            continue
        if pattern.search(law_name):
            return False, reason
    if legal_status != "in_force":
        return False, f"STATUS_{legal_status.upper()}"
    if source_type not in ELIGIBLE_SOURCE_TYPES:
        return False, "UNSUPPORTED_SOURCE_TYPE"
    return True, None


def content_eligibility(page_texts: list[str]) -> tuple[bool, str | None]:
    """Reject documents whose contents—not merely filenames—identify them as drafts."""
    if not page_texts:
        return False, "EMPTY_DOCUMENT"
    draft_pages = sum(bool(re.search(r"(?im)^\s*(?:exposure\s+)?draft\s*$", text))
                      for text in page_texts)
    # A repeated page watermark is decisive. A single occurrence can be a quoted
    # amendment history or contents entry and therefore is not enough by itself.
    if draft_pages >= 2 and draft_pages / len(page_texts) >= 0.10:
        return False, "BILL_OR_DRAFT_CONTENT"
    return True, None


def resolve_status(*, fact_url: str, fact_text: str, current_as_at: str | None = None,
                   effective_date: str | None = None, end_date: str | None = None,
                   explicit_status: LegalStatus | None = None) -> StatusEvidence:
    text = fact_text.lower()
    status: LegalStatus
    rule: str
    if explicit_status:
        status, rule = explicit_status, "official structured status field"
    elif re.search(r"\brepealed|ceased to be in force\b", text):
        status, rule = "repealed", "official fact contains repeal marker"
    elif re.search(r"\bsuperseded|replaced by\b", text):
        status, rule = "superseded", "official fact contains supersession marker"
    elif re.search(r"\bnot yet (in force|commenced)|commences on\b", text):
        status, rule = "not_yet_effective", "official fact contains future-commencement marker"
    elif re.search(r"\b(bill|draft)\b", text):
        status, rule = "draft", "official fact identifies a bill/draft"
    elif current_as_at and re.search(r"\b(current|latest|in force|compilation)\b", text):
        status, rule = "in_force", "official current/latest compilation assertion plus date"
    else:
        status, rule = "unknown", "no sufficient official legal-status assertion"
    conflict = bool(
        status == "in_force" and re.search(r"\brepealed|superseded|ceased to be in force\b", text)
    )
    return StatusEvidence(
        status=status, fact_url=fact_url, fact_text=fact_text, effective_date=effective_date,
        end_date=end_date, resolution_rule=rule, checked_at=datetime.now(timezone.utc),
        conflicting=conflict,
    )


def status_allows_final(status: StatusEvidence | None) -> bool:
    return bool(status and status.status == "in_force" and not status.conflicting
                and status.fact_url and status.fact_text)
