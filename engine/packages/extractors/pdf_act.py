"""Statute-PDF extractor: Commonwealth/gazette-style act PDFs -> RuleUnits, any economy.

Input PDFs come from the seeds fetcher (ministry/gazette copies). Text arrives
via the PDF router (native text layer; docling opt-in; scanned -> OCR VM).
New economies with different section grammars pass `extra_section_patterns`
(e.g. "Pasal N", "Статья N", "มาตรา N") and a `citation_template` ("Art. {label}")
— defaults preserve the Commonwealth "s. N" behavior exactly.

Section detection: lines starting with "N." (optionally N letters, e.g. 116B.)
are section starts ONLY if the number is >= the previous section number
(monotonic filter — kills numbered-list false positives). Subsections split on
top-level "(n)" markers. Citations: "s. 129(1)"; Location Reference: "page N".
"""
from __future__ import annotations

import re

from packages.core.schemas import RuleUnit
from packages.extractors.pdf import extract_pdf
from packages.core.rule_units import classify_rule_components

# Observed statute layouts: "Section 22. Heading" (pdp.gov.my), bare "22. text"
# (gazette), AU "13  Heading" (no dot), and AU Schedule decimals "474.17A  Heading".
# Parsed with each; the richer result wins.
_SECTION_PATTERNS = [
    re.compile(r"^\s{0,6}Section\s+(\d{1,3}[A-Z]{0,2})\.?\s+(.{0,120})", re.IGNORECASE),
    # Schedule decimals (474.17A) and official-code hierarchy (3.5.14).
    re.compile(r"^\s{0,6}(\d{1,3}(?:\.\d{1,2}){1,2}[A-Z]{0,2})\s+(\S.{0,110})"),
    re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\.\s+(.{0,120})"),
    # AU Commonwealth compilations: "13  Interferences with privacy" (no dot, 2+ spaces)
    re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\s{2,}(\S.{0,110})"),
]

# R5 (P3.5) heading-plausibility guards — the user-verified failure modes:
#  (a) note/body sentences: "Section 187B removes..." — heading text starting with a
#      lowercase continuation verb is prose, not a heading;
#  (b) page footers: "102  Telecommunications (Interception and Access) Act 1979" —
#      heading text that is (or starts like) the act's own name is page furniture.
_LOWERCASE_CONTINUATION = re.compile(r"^[a-z]")


def _plausible_heading(heading_text: str, act_name: str) -> bool:
    text = heading_text.strip()
    if not text:
        return True
    if _LOWERCASE_CONTINUATION.match(text):
        return False  # "removes...", "of this Act..." = sentence continuation, not a heading
    from packages.discovery.diff import law_tokens

    head_tokens = law_tokens(text[:80])
    act_tokens = law_tokens(act_name)
    # Footer test: the "heading" contains essentially the ENTIRE act title (at most
    # one act-title token missing). Sharing common words like "personal data" is fine.
    if len(act_tokens) >= 3 and len(act_tokens - head_tokens) <= 1:
        return False  # running header/footer (page number + act name)
    return True
# Treaty/agreement grammar (rerun-fix #4): "Article 14.11  Cross-Border Transfer..."
# Use via parse_act_text(extra_section_patterns=TREATY_SECTION_PATTERNS,
#                        citation_template="Art. {label}") — data-driven, no per-row code.
TREATY_SECTION_PATTERNS = [
    re.compile(r"^\s{0,6}Article\s+(\d{1,3}(?:\.\d{1,2})?[A-Z]?(?:-[A-Z])?)\s*[:.\-\u2013\u2014]?\s+(\S.{0,110})", re.I),
]

# Malay-language statute grammar (rerun-fix #6 wiring): official Malaysian acts print
# bilingual or Malay-only compilations ("Seksyen 12A.", "Perkara 5."). Citations stay
# in the Commonwealth "s. N" convention the known index and gold data use.
MALAY_SECTION_PATTERNS = [
    re.compile(r"^\s{0,6}Seksyen\s+(\d{1,3}[A-Z]{0,2})\.?\s+(\S.{0,110})", re.I),
    re.compile(r"^\s{0,6}Perkara\s+(\d{1,3}[A-Z]{0,2})\.?\s+(\S.{0,110})", re.I),
]

# Named grammar registry: jurisdiction packs / seed profiles select by name \u2014 the
# engine stays generic, target-specific knowledge lives in data (yaml/seeds).
SECTION_GRAMMARS: dict[str, list[re.Pattern]] = {
    "treaty": TREATY_SECTION_PATTERNS,
    "malay": MALAY_SECTION_PATTERNS,
}
CITATION_TEMPLATES: dict[str, str] = {"treaty": "Art. {label}"}

_SUBSECTION = re.compile(r"\((\d{1,2})\)\s")


def _sec_sort_key(num: str) -> tuple[int, int, int, str]:
    """Sortable body/schedule/code path, including nested clause 4.10.3."""
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?([A-Z]*)", num)
    if not match:
        return (0, -1, -1, "")
    return (int(match.group(1)), int(match.group(2) or -1),
            int(match.group(3) or -1), match.group(4))


def parse_act_text(pages: list, economy: str, act_name: str, act_ref: str,
                   source_url: str, law_number_ref: str | None = None,
                   extra_section_patterns: list[re.Pattern] | None = None,
                   citation_template: str = "s. {label}") -> list[RuleUnit]:
    """pages = ExtractedPage list; returns paragraph-depth RuleUnits."""
    # Build (page_number, line) stream
    lines: list[tuple[int, str]] = []
    for page in pages:
        for line in page.text.splitlines():
            lines.append((page.page_number, line))

    # Consolidated Acts commonly put a complete numbered table of contents before
    # the enacting text. Feeding both copies to the monotonic parser makes the TOC
    # win and causes the real provisions (including gaps not printed in the TOC
    # extract) to be rejected as backwards duplicates. Start at the formal long
    # title when present; non-Act instruments/codes without that marker are unchanged.
    enactment_starts = [i for i, (_, line) in enumerate(lines)
                        if re.match(r"^\s*An Act to\b", line, re.I)]
    if enactment_starts:
        lines = lines[enactment_starts[-1]:]

    # Pass 1: find section starts with the monotonic filter; adaptive layout —
    # every pattern is tried and the one yielding more sections wins. A declared
    # profile grammar (extra_section_patterns) is tried FIRST so equal-yield ties
    # resolve to the declared grammar, not the Commonwealth default.
    best: list[dict] = []
    for pattern in (extra_section_patterns or []) + _SECTION_PATTERNS:
        sections: list[dict] = []
        last_key = (0, -1, -1, "")
        for index, (page_no, line) in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            # R5 guards: prose continuations ("Section 187B removes...") and
            # running headers/footers (page number + act name) are not headings.
            if not _plausible_heading(match.group(2) or "", act_name):
                continue
            key = _sec_sort_key(match.group(1))
            if sections:
                same_base_sibling = key[:-1] == last_key[:-1] and key[-1] != last_key[-1]
                if not same_base_sibling and (key <= last_key or key[0] > last_key[0] + 40):
                    continue  # non-monotonic or absurd jump = list item / page artifact
                # letter-suffix siblings (25 -> 25AA -> 25A) may print out of order
                # in multi-column compilations; accept any order within one base number
                if same_base_sibling and any(s["number"] == match.group(1) for s in sections[-6:]):
                    continue  # exact duplicate
            elif key[0] == 0:
                continue
            sections.append({"number": match.group(1), "page": page_no, "line_index": index})
            last_key = max(last_key, key)
        if len(sections) > len(best):
            best = sections
    sections = best

    units: list[RuleUnit] = []
    for pos, sec in enumerate(sections):
        end = sections[pos + 1]["line_index"] if pos + 1 < len(sections) else len(lines)
        body = "\n".join(line for _, line in lines[sec["line_index"]:end])
        body = re.sub(r"\s+", " ", body).strip()
        body = re.sub(rf"^{re.escape(sec['number'])}\.\s*", "", body)
        number = sec["number"]

        # split on top-level (1) (2) ... markers, in increasing order
        markers = []
        expected = 1
        for m in _SUBSECTION.finditer(body):
            if int(m.group(1)) == expected:
                markers.append((m.start(), m.group(1)))
                expected += 1
        pieces: list[tuple[str, str]] = []
        if len(markers) >= 2:
            head = body[: markers[0][0]].strip()
            if head:
                pieces.append((number, head))
            for j, (start, label) in enumerate(markers):
                stop = markers[j + 1][0] if j + 1 < len(markers) else len(body)
                pieces.append((f"{number}({label})", body[start:stop].strip()))
        else:
            pieces.append((number, body))

        for label, text in pieces:
            if len(text) < 30:
                continue
            # ID SCHEME (FROZEN — stored corpora depend on this): economy[:2]
            # gives "ma:"/"au:"; do not change without a full corpus regeneration.
            units.append(RuleUnit(
                id=f"{economy[:2].lower()}:{act_ref}:s{label.replace('(', '-').replace(')', '')}",
                document_id=f"{economy[:2].lower()}:{act_ref}",
                economy=economy,
                law_name=act_name,
                law_number_ref=law_number_ref,
                article_section=citation_template.format(label=label),
                text=text[:20000],
                raw_context=body[:20000],
                source_url=source_url,
                location_reference=f"page {sec['page']}",
                extraction_confidence=pages[0].confidence if pages else None,
                metadata={"section_number": number,
                          "extraction": (pages[0].metadata.get("extraction", "native_text")
                                         if pages else "native_text"),
                          "rule_components": classify_rule_components(body[:20000])},
            ))
    return units


def extract_act_pdf(pdf_path: str, economy: str, act_name: str, act_ref: str,
                    source_url: str, law_number_ref: str | None = None,
                    ocr_engine=None,
                    extra_section_patterns: list[re.Pattern] | None = None,
                    citation_template: str = "s. {label}") -> list[RuleUnit]:
    pages = extract_pdf(pdf_path, ocr_engine=ocr_engine)
    return parse_act_text(pages, economy, act_name, act_ref, source_url, law_number_ref,
                          extra_section_patterns=extra_section_patterns,
                          citation_template=citation_template)
