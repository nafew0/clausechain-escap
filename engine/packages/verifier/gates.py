"""Deterministic verification gates (P1 scope: G1 span, G3 authority, G4 currentness).

Gates are CODE, not LLM judgment (TH2OECD boundary rule). A row ships only when
every applicable gate passes; failures reject the row (never silently emitted).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlparse

from packages.core.schemas import GateResult

_WS = re.compile(r"\s+")
SNIPPET_SOFT_LIMIT = 700
SNIPPET_HARD_LIMIT = 3_000


@dataclass(frozen=True)
class FinalizedSnippet:
    """A source-exact snippet plus the mechanically proven closure result."""

    text: str
    source_start: int | None
    source_end: int | None
    closure_code: str
    reason: str

    @property
    def passed(self) -> bool:
        return self.closure_code in {"PASS_CLOSED", "PASS_LONG_BUT_CLOSED"}


def _normalize(text: str) -> str:
    """Whitespace/unicode-tolerant normalization for span comparison (OCR/entity noise)."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return _WS.sub(" ", text).strip().lower()


_LEGISLATIVE_ABBREVIATION = re.compile(
    r"(?:^|\s)(?:s|ss|art|arts|no|nos|cl|cls|reg|regs|sch|para|paras|pt|vol|ch)\.$",
    re.IGNORECASE,
)
_DANGLING_CONNECTOR = re.compile(r"\b(?:and|or)\s*$", re.IGNORECASE)
_INCOMPLETE_REFERENCE = re.compile(
    r"\b(?:section|subsection|paragraph|subparagraph|article|regulation|schedule|clause|part)\s*$",
    re.IGNORECASE,
)


def _is_real_sentence_stop(source: str, index: int) -> bool:
    """Return true only for a sentence-closing full stop, not legal notation."""
    if source[index] not in ".!?":
        return False
    if source[index] == ".":
        if index and index + 1 < len(source):
            if source[index - 1].isdigit() and source[index + 1].isdigit():
                return False  # 474.17, 2.1, etc.
        prefix = source[max(0, index - 16):index + 1]
        if _LEGISLATIVE_ABBREVIATION.search(prefix):
            return False
        token = re.search(r"(?:^|\s)([A-Z])\.$", prefix)
        if token:
            return False  # an initial such as "A. Smith"
    suffix = source[index + 1:index + 8]
    return not suffix or bool(re.match(r"^[\]\)\}\"'’”]*\s", suffix))


def _balanced_structure(text: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in text:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def _open_ending_code(text: str) -> str | None:
    stripped = text.rstrip().rstrip('"\'’”)]}')
    if stripped.endswith(":") or stripped.endswith(("—", "–")):
        return "FAIL_OPEN_LIST"
    if _DANGLING_CONNECTOR.search(stripped) or _INCOMPLETE_REFERENCE.search(stripped):
        return "FAIL_DANGLING_CONNECTOR"
    if not _balanced_structure(text):
        return "FAIL_UNBALANCED_STRUCTURE"
    return None


_LIST_CHILD = re.compile(r"\(\s*(?:[a-z]|[ivxlcdm]{1,6})\s*\)", re.IGNORECASE)


def _list_has_later_child(source: str, start: int, stop: int) -> bool:
    """Do not close at an early child sentence of a colon-introduced list."""
    passage = source[start:stop]
    colon = passage.find(":")
    if colon < 0 or not _LIST_CHILD.search(passage[colon + 1:]):
        return False
    lookahead = source[stop:stop + 800]
    if re.match(r"\s*(?:Explanation|Note|Example)\b", lookahead, re.IGNORECASE):
        return False
    return bool(_LIST_CHILD.search(lookahead))


def _semantic_child_end(
    claimed: str, source: str, claimed_end: int, semantic_blocks: list[dict] | None
) -> int:
    """Return the minimum source offset needed to include immediate child blocks."""
    if not semantic_blocks:
        return claimed_end
    normalized_claim = _normalize(claimed)
    ranks = {"section": 0, "subsection": 1, "paragraph": 2,
             "subparagraph": 3, "subsubparagraph": 4, "item": 2}
    owner = None
    for index, block in enumerate(semantic_blocks):
        text = str(block.get("text") or "")
        if normalized_claim in _normalize(text) or _normalize(text) in normalized_claim:
            owner = index
            break
    if owner is None:
        return claimed_end
    owner_block = semantic_blocks[owner]
    owner_text = str(owner_block.get("text") or "")
    if ":" not in owner_text and not claimed.rstrip().endswith(":"):
        return claimed_end
    owner_rank = ranks.get(str(owner_block.get("class") or "").casefold(), 1)
    children: list[dict] = []
    for block in semantic_blocks[owner + 1:]:
        css = str(block.get("class") or "").casefold()
        rank = ranks.get(css)
        text = str(block.get("text") or "")
        if rank is not None and rank <= owner_rank:
            break
        if rank is None and not _LIST_CHILD.match(text.strip()):
            break
        children.append(block)
    if not children:
        return claimed_end
    tail = source[claimed_end:]
    last_text = str(children[-1].get("text") or "")
    located = source_exact_span(last_text, tail)
    return claimed_end + located[2] if located else claimed_end


def finalize_snippet_result(
    claimed: str,
    source_text: str,
    *,
    soft_limit: int = SNIPPET_SOFT_LIMIT,
    hard_limit: int = SNIPPET_HARD_LIMIT,
    semantic_blocks: list[dict] | None = None,
) -> FinalizedSnippet:
    """Close a mapper quote at a genuine source sentence/paragraph boundary.

    The soft limit is presentation guidance only.  A colon/list introduction,
    dangling connector, unmatched structure, or partial word is followed through
    its immediate children until a real sentence stop.  The returned characters
    always come from ``source_text``.  Unprovable/over-limit passages are marked
    FAIL so they can never enter an export.
    """
    located = source_exact_span(claimed, source_text)
    if located is None:
        return FinalizedSnippet(
            claimed, None, None, "FAIL_UNBALANCED_STRUCTURE",
            "mapper quote is not source-locatable; structural closure cannot be proven",
        )
    _, start, claimed_end = located
    minimum_end = _semantic_child_end(
        claimed, source_text, claimed_end, semantic_blocks
    )

    # A mapper may stop in the middle of a word (the CPC "an or" failure).  We
    # deliberately begin the boundary search at its exact end and only accept a
    # real sentence stop, so the rest of that word and all list children travel.
    stop: int | None = None
    for index in range(max(start, minimum_end - 1), len(source_text)):
        if _is_real_sentence_stop(source_text, index):
            candidate = source_text[start:index + 1]
            if (_balanced_structure(candidate)
                    and not _list_has_later_child(source_text, start, index + 1)):
                stop = index + 1
                break

    if stop is None:
        remainder = source_text[start:].rstrip()
        code = _open_ending_code(remainder) or "FAIL_UNBALANCED_STRUCTURE"
        return FinalizedSnippet(
            remainder, start, start + len(remainder), code,
            "no genuine closed sentence/paragraph boundary can be proven in canonical context",
        )

    text = source_text[start:stop]
    open_code = _open_ending_code(text)
    if open_code:
        return FinalizedSnippet(
            text, start, stop, open_code,
            "candidate boundary leaves an open statutory structure",
        )
    if len(text) > hard_limit:
        return FinalizedSnippet(
            text, start, stop, "FAIL_CLOSURE_OVER_HARD_LIMIT",
            f"shortest proven closed source passage is {len(text)} characters (hard limit {hard_limit})",
        )
    code = "PASS_LONG_BUT_CLOSED" if len(text) > soft_limit else "PASS_CLOSED"
    return FinalizedSnippet(
        text, start, stop, code,
        (f"source-exact passage closes at a genuine sentence boundary ({len(text)} chars; "
         f"soft target {soft_limit}, hard limit {hard_limit})"),
    )


def extend_to_clause_boundary(snippet: str, source: str, max_extra: int = 300) -> str:
    """Compatibility wrapper; closure is now paragraph-aware and never stops at ``:``/``;``."""
    del max_extra
    return finalize_snippet_result(snippet, source).text


def finalize_snippet(claimed: str, source_text: str, max_len: int = 700) -> str:
    """Compatibility wrapper returning the exact finalized text."""
    return finalize_snippet_result(claimed, source_text, soft_limit=max_len).text


def g9_structural_closure(result: FinalizedSnippet) -> GateResult:
    return GateResult(
        gate_id="G9",
        status="PASS" if result.passed else "FAIL",
        reason=f"{result.closure_code}: {result.reason}",
        metadata={
            "closure_code": result.closure_code,
            "source_start": result.source_start,
            "source_end": result.source_end,
            "snippet_length": len(result.text),
        },
    )


def g9_span_length(snippet: str, max_len: int = 700) -> GateResult:
    """Deprecated compatibility check for callers without canonical context.

    New engine code must call :func:`g9_structural_closure`; length alone can no
    longer prove a legal passage complete.
    """
    open_code = _open_ending_code(snippet)
    closed = bool(snippet.rstrip().endswith((".", "!", "?"))) and open_code is None
    code = (open_code or ("PASS_LONG_BUT_CLOSED" if len(snippet) > max_len
                          else "PASS_CLOSED")) if closed or open_code else "FAIL_DANGLING_CONNECTOR"
    return GateResult(
        gate_id="G9", status="PASS" if code.startswith("PASS") else "FAIL",
        reason=f"{code}: compatibility structural check ({len(snippet)} chars)",
        metadata={"closure_code": code, "snippet_length": len(snippet)},
    )


def source_exact_span(snippet: str, source_text: str) -> tuple[str, int, int] | None:
    """E3-lite (P3.5): return the SOURCE's own characters for a claimed snippet.

    The LLM copies quotes imperfectly (punctuation/whitespace drift). We locate the
    snippet under normalization, then slice the ORIGINAL source text — the exported
    quotation is constructed from stored source characters, never from LLM output.
    """
    if not snippet.strip():
        return None
    # Build normalized source with an offset map back to original indices.
    norm_chars: list[str] = []
    offset_map: list[int] = []
    prev_space = True
    for index, ch in enumerate(source_text):
        c = unicodedata.normalize("NFKC", ch)
        c = {"‑": "-", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"'}.get(c, c)
        if c.isspace():
            if prev_space:
                continue
            norm_chars.append(" ")
            offset_map.append(index)
            prev_space = True
        else:
            norm_chars.append(c.lower())
            offset_map.append(index)
            prev_space = False
    norm_source = "".join(norm_chars)
    target = _normalize(snippet)
    pos = norm_source.find(target)
    if pos < 0:
        return None
    start = offset_map[pos]
    end_index = pos + len(target) - 1
    end = offset_map[end_index] + 1
    return source_text[start:end], start, end


def source_exact_slice(snippet: str, source_text: str) -> str | None:
    located = source_exact_span(snippet, source_text)
    return located[0] if located else None


def g1_span_exists(snippet: str, source_text: str) -> GateResult:
    """The quote must literally exist in the extracted source (the anti-hallucination gate)."""
    ok = bool(snippet.strip()) and _normalize(snippet) in _normalize(source_text)
    return GateResult(
        gate_id="G1",
        status="PASS" if ok else "FAIL",
        reason="verbatim snippet found in extracted source text" if ok
        else "snippet NOT found in source — hallucinated or edited quote",
    )


def g3_authority(source_url: str, whitelist_domains: set[str]) -> GateResult:
    host = (urlparse(source_url).hostname or "").lower()
    ok = any(host == d or host.endswith("." + d) for d in whitelist_domains)
    return GateResult(
        gate_id="G3",
        status="PASS" if ok else "FAIL",
        reason=f"source domain {host!r} is on the official whitelist" if ok
        else f"source domain {host!r} is NOT an official source",
    )


def g4_currentness(current_as_at: str | None, status: str = "in_force") -> GateResult:
    """P1 basic check: the portal's own 'Current version as at <date>' assertion.

    (Repeal/supersession graph checks land with G8 in P3'.)
    """
    if status == "unknown":
        return GateResult(gate_id="G4", status="WARN",
                          reason="legal currentness is unknown; candidate may be reviewed but cannot be final")
    if status != "in_force":
        return GateResult(gate_id="G4", status="FAIL",
                          reason=f"instrument status is {status!r}, not in force")
    if not current_as_at:
        return GateResult(gate_id="G4", status="WARN",
                          reason="no current-version assertion found on the source page")
    try:
        try:
            as_at = datetime.strptime(current_as_at, "%d %b %Y").date()
        except ValueError:
            as_at = date.fromisoformat(current_as_at)
        reason = f"official portal asserts current version as at {as_at.isoformat()}"
        return GateResult(gate_id="G4", status="PASS", reason=reason)
    except ValueError:
        return GateResult(gate_id="G4", status="WARN",
                          reason=f"unparseable current-version date: {current_as_at!r}")


# Deterministic legal-fit validators (reviewer feedback, 9 Jul): G1/G3/G4 prove
# quote/source/currentness but NOT legal fit — these lexical gates do, per indicator.
_XBORDER = re.compile(r"outside|abroad|cross[- ]border|foreign|another country|other countr|place outside|out of", re.I)
_TRANSFER = re.compile(r"transfer|transmit|send|disclos\w+ to .{0,40}(outside|abroad|foreign)", re.I)
_RETAIN = re.compile(r"retain|keep|preserve|maintain|stor\w+", re.I)
_DURATION = re.compile(r"(period of|not less than|at least|minimum of)?\s*\w*\s*(year|month|day|week)s?", re.I)
_RECORDS = re.compile(r"record|data|document|book|information|register", re.I)
_INFRASTRUCTURE = re.compile(r"server|data cent(?:re|er)|comput(?:er|ing) (?:system|facility)|infrastructure|facility", re.I)
_DOMESTIC_LOCATION = re.compile(
    r"\b(?:local|domestic(?:ally)?)\b|\b(?:located|established|maintained|hosted)\b"
    r".{0,35}\b(?:in|within)\b(?!\s+(?:another|other|foreign))|"
    r"\b(?:server|data cent(?:re|er)|facility|infrastructure)\b.{0,35}"
    r"\b(?:in|within)\b(?!\s+(?:another|other|foreign))",
    re.I,
)
_PROHIBITION = re.compile(r"\b(?:must not|shall not|may not|is prohibited|are prohibited|prohibit(?:s|ed)?)\b", re.I)
# Statutory conditional vocabulary. Real acts phrase the condition as
# "except in accordance with requirements prescribed" (SG PDPA s. 26(1)) at
# least as often as the textbook "unless" — both families must count.
_CONDITION = re.compile(
    r"\b(?:if|unless|only if|consent|adequacy|adequate|approval|condition|safeguard"
    r"|contract|except|subject to|in accordance with|prescribed|standard of protection)\b",
    re.I)
_MINIMUM_DUTY = re.compile(r"\b(?:must|shall|required to|not less than|at least|minimum(?: period)? of)\b", re.I)
_RETENTION_CEILING = re.compile(r"\b(?:need only|may (?:retain|keep)|up to|not more than|no longer than|maximum(?: period)? of)\b", re.I)
_WARRANT = re.compile(r"warrant|court order|order of (a|the) court|judge|magistrate|judicial", re.I)
_WITHOUT_JUDICIAL = re.compile(
    r"\b(?:without|no need for|does not require|not required to obtain)\b"
    r".{0,35}\b(?:warrant|court order|judicial authori[sz]ation)\b|\bwarrantless\b",
    re.I,
)


def g7_indicator_fit(indicator_id: str, snippet: str, full_text: str, law_name: str) -> GateResult:
    """Hard post-map legal-fit checks. FAIL = the row cannot ship; WARN = flag for review."""
    blob = f"{snippet} {full_text[:2000]}"
    if "bill" in re.sub(r"[^a-z ]", " ", law_name.lower()).split():
        return GateResult(gate_id="G7", status="FAIL",
                          reason=f"law name contains 'Bill' ({law_name[:60]}) — drafts are never recordable")
    if indicator_id in ("P6-I1", "P6-I4"):
        if not (_XBORDER.search(blob) and _TRANSFER.search(blob)):
            return GateResult(gate_id="G7", status="FAIL",
                              reason=f"{indicator_id} requires CROSS-BORDER data transfer language; "
                                     "generic processing/disclosure does not qualify")
    if indicator_id == "P6-I1" and not _PROHIBITION.search(blob):
        return GateResult(gate_id="G7", status="FAIL",
                          reason="P6-I1 requires an operative prohibition on cross-border transfer")
    if indicator_id == "P6-I2":
        if not (_RETAIN.search(blob) and _RECORDS.search(blob)
                and _DOMESTIC_LOCATION.search(blob) and _MINIMUM_DUTY.search(blob)):
            return GateResult(gate_id="G7", status="FAIL",
                              reason="P6-I2 requires a mandatory domestic-copy/storage duty")
    if indicator_id == "P6-I3":
        if not (_INFRASTRUCTURE.search(blob) and _DOMESTIC_LOCATION.search(blob)
                and (_MINIMUM_DUTY.search(blob)
                     or re.search(r"\b(?:condition|precondition)\b", blob, re.I))):
            return GateResult(gate_id="G7", status="FAIL",
                              reason="P6-I3 requires local infrastructure as a mandatory service condition")
    if indicator_id == "P6-I4" and not _CONDITION.search(blob):
        return GateResult(gate_id="G7", status="FAIL",
                          reason="P6-I4 requires an operative condition or safeguard for transfer")
    if indicator_id == "P7-I3":
        if not (_RETAIN.search(blob) and _DURATION.search(blob) and _RECORDS.search(blob)):
            return GateResult(gate_id="G7", status="FAIL",
                              reason="P7-I3 requires retention verb + records/data object + a minimum duration")
        if re.search(r"licen[cs]e|permit", snippet, re.I) and not re.search(r"record|data", snippet, re.I):
            return GateResult(gate_id="G7", status="FAIL",
                              reason="P7-I3: licence-duration provisions are not data retention")
        if _RETENTION_CEILING.search(blob) or not _MINIMUM_DUTY.search(blob):
            return GateResult(gate_id="G7", status="FAIL",
                              reason="P7-I3 requires a mandatory minimum; permissive or maximum retention does not qualify")
    if indicator_id == "P7-I5":
        if _WARRANT.search(blob) and not _WITHOUT_JUDICIAL.search(blob):
            return GateResult(gate_id="G7", status="WARN",
                              reason="P7-I5: access appears COURT-GATED (warrant/judicial language) — "
                                     "court-order test says this supports score 0; flag for legal review")
    return GateResult(gate_id="G7", status="PASS", reason=f"{indicator_id} legal-fit checks passed")


_EXCEPTION_TOKENS = re.compile(r"\bunless\b|\bexcept\b|subject to|provided that|notwithstanding", re.I)
_MANDATORY = re.compile(r"\bmust\b|\bshall\b|is required|are required", re.I)
_CROSS_REF = re.compile(r"section\s+(\d{1,3}[A-Z]{0,2})(?:\s+of\s+(?:the\s+)?([A-Z][\w() ]{4,60}?(?:Act|Code|Regulations)[\w ]{0,12}))?", re.I)


def g2_location(article_section: str, location_reference: str) -> GateResult:
    """The location pointer must be consistent with the cited section (anchor
    contains the section number, or is an explicit page/vol reference)."""
    from packages.discovery.diff import section_base

    base = section_base(article_section)
    loc = (location_reference or "").lower()
    if loc.startswith("#pr") or loc.startswith("#sc"):
        ok = bool(base) and base.lower() in loc
        return GateResult(gate_id="G2", status="PASS" if ok else "FAIL",
                          reason=f"anchor {location_reference!r} {'matches' if ok else 'does NOT match'} s. {base}")
    if "page" in loc or "vol" in loc:
        return GateResult(gate_id="G2", status="PASS",
                          reason=f"page-level location {location_reference!r} recorded from the source parse")
    return GateResult(gate_id="G2", status="WARN", reason=f"unrecognized location format {location_reference!r}")


def g5_whole_rule(indicator_id: str, snippet: str, full_text: str) -> GateResult:
    """Rule + exception must travel together (DoDont §5): a 'ban' whose section
    carries an exception outside the quoted snippet is the classic 6.1 trap."""
    outside = _EXCEPTION_TOKENS.search(full_text) and not _EXCEPTION_TOKENS.search(snippet)
    if not outside:
        return GateResult(gate_id="G5", status="PASS", reason="rule and exception captured together")
    if indicator_id == "P6-I1":
        return GateResult(gate_id="G5", status="FAIL",
                          reason="section contains an exception (unless/except/subject to) OUTSIDE the snippet — "
                                 "a ban with a compliance path is conditional (6.4), not 6.1")
    return GateResult(gate_id="G5", status="WARN",
                      reason="exception language exists outside the snippet — reviewer should read the full section")


def g6_meaning_support(rationale: str, snippet: str, full_text: str) -> GateResult:
    """The rationale's modality claims must be supported by the text (may ≠ shall)."""
    claims_mandate = re.search(r"prohibit|require|mandate|must|ban", rationale or "", re.I)
    text = f"{snippet} {full_text[:1500]}"
    if claims_mandate and not (_MANDATORY.search(text) or re.search(r"\bmay not\b|\bshall not\b|\bmust not\b", text, re.I)):
        return GateResult(gate_id="G6", status="WARN",
                          reason="rationale claims a mandatory rule but the text shows no must/shall modality "
                                 "(permissive 'may' misread as mandatory?)")
    return GateResult(gate_id="G6", status="PASS", reason="rationale modality supported by the text")


def g8_counter_and_dangling(snippet: str, full_text: str, law_name: str,
                            corpus_sections: set[str]) -> GateResult:
    """Counter-evidence + dangling-reference (DoDont §12.8): every section this
    provision cross-references (same act) must exist in the parsed corpus."""
    dangling = []
    for match in _CROSS_REF.finditer(full_text[:3000]):
        ref_base, other_act = match.group(1).upper(), match.group(2)
        if other_act and other_act.strip().lower().startswith(("this ", "that ", "the said")):
            other_act = None  # "of this Act" = same-act reference (re.I fooled [A-Z])
        if other_act:  # genuine cross-act reference — checked at corpus level, skip here
            continue
        if corpus_sections and ref_base not in corpus_sections:
            dangling.append(ref_base)
    if dangling:
        return GateResult(gate_id="G8", status="WARN",
                          reason=f"references section(s) {sorted(set(dangling))[:4]} not found in the parsed act "
                                 "— possible repealed/renumbered target (dangling reference); reviewer check")
    return GateResult(gate_id="G8", status="PASS",
                      reason="no dangling same-act references; no repeal language detected")


def citation_tier(article_section: str) -> str:
    """Claude-for-Legal tiering: pinpoint cites carry the highest fabrication risk."""
    return "[verify-pinpoint]" if "(" in (article_section or "") else "[verify]"


def g7_ban_vs_conditional(findings: list) -> tuple[list, list[GateResult]]:
    """Deterministic 6.1-vs-6.4 disambiguation (the #1 warned confusion, DoDont §6).

    A ban (6.1) and a conditional-flow regime (6.4) are mutually exclusive for the
    SAME provision: if a provision maps to both, the conditional reading wins (a
    compliance path exists, so it is not a ban) and the 6.1 row is dropped.
    """
    from packages.discovery.diff import normalize_law, section_base

    conditional_keys = {
        (normalize_law(f.law_name), section_base(f.article_section))
        for f in findings if f.indicator_id == "P6-I4"
    }
    kept, gates = [], []
    for f in findings:
        key = (normalize_law(f.law_name), section_base(f.article_section))
        if f.indicator_id == "P6-I1" and key in conditional_keys:
            gates.append(GateResult(
                gate_id="G7",
                status="FAIL",
                reason=(f"{f.law_name} {f.article_section}: also maps to P6-I4 — a provision "
                        "with a compliance path is a CONDITIONAL regime, not a ban; "
                        "6.1 row dropped (DoDont §6 disambiguation, applied as code)"),
                evidence_reference=f"P6-I1 {f.article_section}",
            ))
            continue
        kept.append(f)
    return kept, gates


def run_gates(
    snippet: str,
    source_text: str,
    source_url: str,
    whitelist_domains: set[str],
    current_as_at: str | None,
    legal_status: str = "unknown",
) -> tuple[list[GateResult], bool]:
    gates = [
        g1_span_exists(snippet, source_text),
        g3_authority(source_url, whitelist_domains),
        g4_currentness(current_as_at, legal_status),
    ]
    all_ok = all(g.status in ("PASS", "WARN") for g in gates)
    return gates, all_ok
