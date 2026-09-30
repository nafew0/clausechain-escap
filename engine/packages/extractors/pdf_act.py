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
    # Heading text may follow on the same line or start on the next one
    # ("Section 29" alone on its line, as in the Thai PDPA official translation).
    re.compile(r"^\s{0,6}Section\s+(\d{1,3}[A-Z]{0,2})\.?(?:\s+(.{0,120})|\s*$)", re.IGNORECASE),
    # Schedule decimals (474.17A) and official-code hierarchy (3.5.14).
    re.compile(r"^\s{0,6}(\d{1,3}(?:\.\d{1,2}){1,2}[A-Z]{0,2})\s+(\S.{0,110})"),
    re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\.\s+(.{0,120})", re.I),
    # AU Commonwealth compilations: "13  Interferences with privacy" (no dot, 2+ spaces)
    re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\s{2,}(\S.{0,110})", re.I),
    CLAUSE_PATTERN := re.compile(r"^\s{0,6}Clause\s+(\d{1,3}[A-Z]?)\.?(?:\s+(.{0,120})|\s*$)", re.I),
]
# Notifications/regulations number provisions "Clause 4." (PDPC cross-border
# notifications); cited "cl. 4" as in ESCAP gold, unless a caller set a template.

# R5 (P3.5) heading-plausibility guards — the user-verified failure modes:
#  (a) note/body sentences: "Section 187B removes..." — heading text starting with a
#      lowercase continuation verb is prose, not a heading;
#  (b) page footers: "102  Telecommunications (Interception and Access) Act 1979" —
#      heading text that is (or starts like) the act's own name is page furniture.
_LOWERCASE_CONTINUATION = re.compile(r"^[a-z]")
# Words that continue a sentence after a wrapped cross-reference
# ("... under\nSection 29\nof this Act", "... dalam\nPasal 20\nayat (1)").
# Deliberately a word list, not "any lowercase": text-layer glitches ("l,embaga"
# for "Lembaga") and page-footer URLs also start lowercase after real headings.
_REFERENCE_CONTINUATION = re.compile(
    r"^(?:of|and|or|to|in|is|are|shall|may|applies|apply|does|has|have|as|by|under|"
    r"with|for|ayat|huruf|angka|dan|atau|sampai|jo|juncto|sebagaimana)\b")


def _plausible_heading(heading_text: str, act_name: str) -> bool:
    text = heading_text.strip()
    if not text:
        return True
    if _LOWERCASE_CONTINUATION.match(text):
        return False  # "removes...", "of this Act..." = sentence continuation, not a heading
    if re.search(r"\b(?:Section|Article|Regulation|Clause)\s+\d", text, re.I):
        return False  # a body cross-reference wrapped onto a new line is not a heading
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
    # One grammar covers both ``Article 12.14: Title`` and a standalone
    # ``ARTICLE 13`` whose title is printed on the following line. Anchoring to
    # the full line prevents a body sentence from being accepted by prefix only.
    re.compile(
        r"^\s{0,6}Article\s+(\d{1,3}[A-Z]?(?:\.\d{1,2}[A-Z]?){0,2}(?:-[A-Z])?)"
        r"\s*(?:[:.\-\u2013\u2014]\s*)?(.*?)\s*$",
        re.I,
    ),
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
    # Thai statutes: มาตรา = section (acts); ข้อ = clause (subordinate
    # notifications). Thai digits ๐-๙ appear in gazette text; the R2 builder
    # normalises captured labels to Arabic (text/spans untouched).
    "thai": [
        re.compile(r"^\s{0,6}มาตรา\s+([๐-๙0-9]{1,4}(?:/[๐-๙0-9]{1,3})?)\s*(\S.{0,110})?"),
        re.compile(r"^\s{0,6}ข้อ\s+([๐-๙0-9]{1,3})\s*(\S.{0,110})?"),
    ],
    # Thai amending regulations that insert clauses ("ข้อ ๒๗/๓", MR on Promoted
    # Supplies No. 2 / No. 4). Also matches plain "ข้อ N" so it can out-yield the
    # "thai" grammar. Opt-in per seed: rebuilding already-reviewed Thai instruments
    # with it would split their clauses and change finding keys. A number followed
    # by "และ" (and) / "ถึง" (to) is the amending instruction's wrapped list of the
    # clauses it inserts ("ข้อ ๒๗/๒ และข้อ ๒๗/๓ ..."), not a heading.
    "thai_inserted_clause": [
        re.compile(r"^\s{0,6}ข้อ\s+([๐-๙0-9]{1,3}(?:/[๐-๙0-9]{1,3})?)(?!\s*(?:และ|ถึง))"
                   r"\s*(\S.{0,110})?"),
    ],
    # Indonesian statutes/regulations: Pasal N (ayat handled at paragraph depth).
    "indonesian": [
        # A heading is "Pasal N" alone on its line, or followed by a capital or
        # "(" when the text layer glues the first sentence on. Lines like
        # "Pasal 20, Pasal 21, ... ayat (1)" (the "Mengingat" preamble),
        # "Pasal 20 ayat (1) ..." (a wrapped cross-reference) and "Pasal 11 . . ."
        # (the page-turn catchword) are not headings: accepting the preamble one
        # made the monotonic filter reject Articles 2-19 of whole Acts.
        # "Pasal 1 1" is a text-layer spacing glitch for "Pasal 11" (the label is
        # de-spaced in parse_act_text).
        re.compile(r"^\s{0,6}(?i:pasal)\s+(\d{1,4}(?: \d{1,2})?[A-Z]?)(?:\s*|\s+([A-Z(][^,]{0,110}))$"),
    ],
    # English translations of civil-law instruments (Lao, Mongolian, Timorese
    # UNTAET-era and treaty texts): "Article 17  Title" / "ARTICLE 17".
    "article": TREATY_SECTION_PATTERNS,
    # Russian statutes/codes: "Статья 12. Title". Inserted articles print as a
    # superscript ("Статья 18¹"); the html_render acquisition keeps them as Unicode
    # superscript digits and parse_act_text normalises the label to "18.1". The dot
    # after the number is required: body cross-references are lowercase "статьей 12".
    "russian": [
        re.compile(r"^\s{0,6}Статья\s+(\d{1,4}[¹²³⁰-⁹]{0,3})\.\s*(\S.{0,400})?$"),
    ],
    # Mongolian laws: "14 дүгээр зүйл.Title" (ordinal suffix follows vowel harmony:
    # дүгээр/дугаар); inserted articles "6.1 дүгээр зүйл" or "6¹ дүгээр зүйл". A
    # heading ends "зүйл." (or the line); a wrapped cross-reference continues in the
    # dative ("...17, 18,\n19 дүгээр зүйлд заасан") and must not start a section.
    "mongolian": [
        re.compile(r"^\s{0,6}(\d{1,3}(?:\.\d{1,2})?[¹²³⁰-⁹]{0,3})\s*"
                   r"(?:дүгээр|дугаар|дүгаар|дугээр)\s+зүйл(?:\.\s*(\S.{0,400})?|\s*$)", re.I),
    ],
    # Lao laws/decisions: ມາດຕາ N (Arabic or Lao digits ໐-໙; the R2 builder
    # normalises Lao digits in labels to Arabic, text/spans untouched).
    "lao": [
        re.compile(r"^\s{0,6}ມາດຕາ\s*([0-9໐-໙]{1,3})\s*(\S.{0,400})?$"),
    ],
    # Mongolian regulations (журам): chapters in words ("Нэг.", "ГУРАВ."), clauses
    # "3.2.Text" (or "1.1." with the text on the next line); sub-clauses "3.2.1."
    # stay inside their clause. Opt-in per seed with citation "cl. {label}".
    # (Round-2 grammars capture up to 400 heading chars: clause text often runs on
    # the heading line, and "$" is what rejects lowercase cross-references.)
    "mongolian_regulation": [
        re.compile(r"^\s{0,6}(\d{1,2}\.\d{1,2})\.(?!\d)\s*(\S.{0,400})?$"),
    ],
    # Regulator guidelines whose clause numbers stand alone on their line with the
    # title on the next ("3" / "Requirement for Registration" / "3.1" / text) —
    # e.g. ANC SIM-registration guidelines. Opt-in per seed (too broad as a default).
    "numbered_clause": [
        re.compile(r"^\s{0,6}(\d{1,2}(?:\.\d{1,2})?)()\s*$"),
    ],
    # India General Financial Rules 2017: "Rule 161 Advertised Tender Enquiry".
    "india_rule": [
        re.compile(r"^\s{0,6}Rule\s+(\d{1,3}[A-Z]?)\s+(\S.{0,110})$"),
    ],
    # Singapore SSO PDF export: "6.—(1) The Minister may ..." / "2. In this Act ..."
    # (the em dash + "(1)" form the default grammar misses). Seed-declared only.
    "sg_emdash": [
        re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\.(?:\s+(\S.{0,120})|\s*[—–]\s*(?=\(\d))"),
    ],
    # Malaysian LOM reprints printing the section number alone on its line ("2.").
    "bare_number_dot": [
        re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\.(?:\s+(\S.{0,120}))?\s*$"),
    ],
    # Australian Commonwealth Procurement Rules: paragraph numbers "5.4" alone or
    # before their text.
    "decimal_clause": [
        re.compile(r"^\s{0,6}(\d{1,2}\.\d{1,2})(?:\s+(\S.{0,110}))?\s*$"),
    ],
    # Portuguese (Timor-Leste, Jornal da República): "Artigo 5.º" (older issues print
    # the ordinal as a letter: "Artigo 10.o") with the
    # heading on the same or the next line. Capital "Artigo" only — wrapped body
    # cross-references ("... do artigo 5.º") are lowercase.
    "portuguese": [
        re.compile(r"^\s{0,6}Artigo\s+(\d{1,3})\s*\.?\s*[º°ªo]?\.?\s*(?:[-–—:]\s*)?([A-ZÀ-Ý(].{0,400})?$"),
    ],
}
# Superscript digits mark inserted articles in Russian/Mongolian consolidated
# texts (18¹ = 18.1). Normalised in section labels only; text is untouched.
_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹",
                                    "0123456789")


def _decimal_label(number: str) -> str:
    """"18¹" -> "18.1" so inserted articles sort and cite like consultant/garant."""
    match = re.fullmatch(r"(\d+)([¹²³⁰-⁹]+)", number)
    if not match:
        return number
    return f"{match.group(1)}.{match.group(2).translate(_SUPERSCRIPT_DIGITS)}"


# Grammars whose statutes insert articles as superscripts (4¹, 18¹). When a
# server-generated PDF flattens the superscript into the text layer ("4¹" -> "41",
# verified in legalinfo.mn exports), the label is recovered from its neighbours.
_INSERTED_ARTICLE_PATTERNS = {id(p) for name in ("russian", "mongolian")
                              for p in SECTION_GRAMMARS[name]}
# Keyword heading grammars ("Статья N.", "N дүгээр зүйл.", "ມາດຕາ N", "Artigo N.º"):
# when declared and matched, they are the act's structure. The generic "N." grammar
# can find MORE starts only by counting the parts inside articles (223-FZ: 20
# articles vs 32 monotonic part numbers), so yield must not overrule them — unless
# the keyword hits are stray mentions (< 30% of the best yield: a TL overview
# document citing "Artigo" twice among 52 numbered paragraphs).
_KEYWORD_HEADING_PATTERNS = {id(p) for name in ("russian", "mongolian", "lao", "portuguese",
                                                "indonesian")
                             for p in SECTION_GRAMMARS[name]}


# Russian articles number their parts "1. ", "2. " at the start of a line; each
# part becomes its own unit "Art. N(k)" (the gold's "Art. 12.7" = part 7 of Art. 12).
_PART_LINES = {id(p): re.compile(r"^\s{0,6}(\d{1,3})([¹²³⁰-⁹]{0,2})\.\s+\S")
               for p in SECTION_GRAMMARS["russian"]}
# Items "1) ..." inside a part; split only when the part itself is too long to align.
_LIST_ITEM_LINE = re.compile(r"^\s{0,6}(\d{1,3})()\)\s+\S")
LONG_PART_CHARS = 8000


def _numbered_starts(lines: list[str], line_pattern: re.Pattern) -> list[tuple[int, str]]:
    """[(line offset, "k")] of consecutive numbers 1, 2, 3 ... opening a line
    (line 0 — the unit's own heading — is skipped). An inserted part "1¹." between
    1 and 2 is kept as "1.1" without breaking the sequence (126-FZ Art. 64(1.1))."""
    starts: list[tuple[int, str]] = []
    expected = 1
    for offset, line in enumerate(lines[1:], start=1):
        found = line_pattern.match(line)
        if not found:
            continue
        base, inserted = int(found.group(1)), found.group(2)
        if inserted and base == expected - 1:
            starts.append((offset, _decimal_label(f"{base}{inserted}")))
        elif not inserted and base == expected:
            starts.append((offset, found.group(1)))
            expected += 1
    return starts


def _numbered_part_starts(pattern, section_lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Parts 1, 2, 3 ... of one article; empty for grammars without parts."""
    part_line = _PART_LINES.get(id(pattern))
    if part_line is None:
        return []
    return _numbered_starts([line for _, line in section_lines], part_line)


def _merged_superscript_labels(numbers: list[str]) -> dict[int, str]:
    """{position: "N.d"} for flattened inserted articles: a label "Nd" (or run
    "Nd", "Ne", ...) that follows N and is followed by N+1. Every other sequence is
    left untouched — a genuine jump (e.g. repealed sections) never meets both
    neighbours."""
    def plain(value: str) -> bool:  # str.isdigit() is also True for "¹" and "໑"
        return re.fullmatch(r"[0-9]+", value) is not None

    repairs: dict[int, str] = {}
    for i in range(1, len(numbers) - 1):
        base = numbers[i - 1]
        if not plain(base) or i in repairs:
            continue
        run = i
        while (run < len(numbers) and plain(numbers[run])
               and len(numbers[run]) == len(base) + 1 and numbers[run].startswith(base)
               and numbers[run][-1] != "0"):
            run += 1
        if run > i and run < len(numbers) and plain(numbers[run]) \
                and int(numbers[run]) == int(base) + 1:
            for j in range(i, run):
                repairs[j] = f"{base}.{numbers[j][-1]}"
    return repairs
CITATION_TEMPLATES: dict[str, str] = {"treaty": "Art. {label}"}

_SUBSECTION = re.compile(r"\((\d{1,2})\)\s")


def _sec_sort_key(num: str) -> tuple[int, int, int, str]:
    """Sortable body/schedule/code path, including nested clause 4.10.3."""
    annex = re.fullmatch(r"(\d+)([A-Z]+)\.(\d+)([A-Z]*)", num.upper())
    if annex:
        letters = 0
        for char in annex.group(2):
            letters = letters * 26 + ord(char) - 64
        return (int(annex.group(1)), 1000 + letters,
                int(annex.group(3)), annex.group(4))
    # Thai inserted provisions: "27/3" sorts after "27" and before "28".
    inserted = re.fullmatch(r"(\d+)/(\d+)", num)
    if inserted:
        return (int(inserted.group(1)), int(inserted.group(2)), -1, "")
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?([A-Z]*)", num.upper())
    if not match:
        return (0, -1, -1, "")
    return (int(match.group(1)), int(match.group(2) or -1),
            int(match.group(3) or -1), match.group(4))


_OCR_LOWER_SUFFIX = re.compile(r"^(\s{0,6})(\d{1,3})([a-z])(\.\s+.*)$")


def _repair_ocr_section_labels(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Repair lowercase OCR suffixes using neighbouring statutory sequence.

    This handles font confusions such as A, ``s``, C where the middle glyph is
    a misread B, without knowing an Act or citation in advance.
    """
    hits = []
    for index, (_page, line) in enumerate(lines):
        match = _OCR_LOWER_SUFFIX.match(line)
        if match:
            hits.append((index, match.group(2), match.group(3), match))
    replacements: dict[int, str] = {}
    for position, (index, base, suffix, match) in enumerate(hits):
        repaired = suffix.upper()
        previous = hits[position - 1] if position else None
        following = hits[position + 1] if position + 1 < len(hits) else None
        if previous and following and previous[1] == base == following[1]:
            before, after = previous[2].upper(), following[2].upper()
            if ord(after) - ord(before) == 2:
                repaired = chr(ord(before) + 1)
        replacements[index] = f"{match.group(1)}{base}{repaired}{match.group(4)}"
    return [(page, replacements.get(index, line))
            for index, (page, line) in enumerate(lines)]


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
    if any(str(page.metadata.get("extraction", "")).startswith("ocr")
           or page.metadata.get("ocr_engine") for page in pages):
        lines = _repair_ocr_section_labels(lines)

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
    def _next_text(index: int) -> str:
        for _, following in lines[index + 1:index + 4]:
            if following.strip():
                return following.strip()
        return ""

    best: list[dict] = []
    best_pattern = None
    tried: list[tuple[re.Pattern, list[dict]]] = []
    for pattern in (extra_section_patterns or []) + _SECTION_PATTERNS:
        sections: list[dict] = []
        last_key = (0, -1, -1, "")
        relabel: dict[int, str] = {}
        if id(pattern) in _INSERTED_ARTICLE_PATTERNS:
            heads = [(index, re.sub(r"\s+", "", found.group(1)))
                     for index, (_, text) in enumerate(lines) if (found := pattern.match(text))]
            relabel = {heads[pos][0]: label for pos, label in
                       _merged_superscript_labels([number for _, number in heads]).items()}
        for index, (page_no, line) in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            # R5 guards: prose continuations ("Section 187B removes...") and
            # running headers/footers (page number + act name) are not headings.
            if not _plausible_heading(match.group(2) or "", act_name):
                continue
            # A bare heading line ("Section 29") followed by a lowercase
            # continuation ("of this Act ...") is a wrapped cross-reference.
            if not (match.group(2) or "").strip() and _REFERENCE_CONTINUATION.match(_next_text(index)):
                continue
            number = relabel.get(index) or _decimal_label(re.sub(r"\s+", "", match.group(1)))
            key = _sec_sort_key(number)
            if sections:
                same_base_sibling = key[:-1] == last_key[:-1] and key[-1] != last_key[-1]
                if not same_base_sibling and (key <= last_key or key[0] > last_key[0] + 40):
                    continue  # non-monotonic or absurd jump = list item / page artifact
                # letter-suffix siblings (25 -> 25AA -> 25A) may print out of order
                # in multi-column compilations; accept any order within one base number
                if same_base_sibling and any(s["number"] == number for s in sections[-6:]):
                    continue  # exact duplicate
            elif key[0] == 0:
                continue
            sections.append({"number": number, "page": page_no, "line_index": index})
            last_key = max(last_key, key)
        tried.append((pattern, sections))
        if len(sections) > len(best):
            best, best_pattern = sections, pattern
    keyword = max(((pat, secs) for pat, secs in tried if id(pat) in _KEYWORD_HEADING_PATTERNS),
                  key=lambda item: len(item[1]), default=None)
    if keyword and len(keyword[1]) >= max(2, 0.3 * len(best)):
        best, best_pattern = keyword[1], keyword[0]
    sections = best
    if best_pattern is CLAUSE_PATTERN and citation_template == "s. {label}":
        citation_template = "cl. {label}"

    units: list[RuleUnit] = []
    for pos, sec in enumerate(sections):
        end = sections[pos + 1]["line_index"] if pos + 1 < len(sections) else len(lines)
        body = "\n".join(line for _, line in lines[sec["line_index"]:end])
        body = re.sub(r"\s+", " ", body).strip()
        body = re.sub(rf"^{re.escape(sec['number'])}\.\s*", "", body)
        number = sec["number"].upper()

        # split on top-level (1) (2) ... markers, in increasing order
        markers = []
        expected = 1
        for m in _SUBSECTION.finditer(body):
            if int(m.group(1)) == expected:
                markers.append((m.start(), m.group(1)))
                expected += 1
        pieces: list[tuple[str, str]] = []
        part_starts = _numbered_part_starts(best_pattern, lines[sec["line_index"]:end])
        if len(part_starts) >= 2 and len(markers) < 2:
            # Civil-law parts ("1. ...", "2. ...") open their own line: split on the
            # line structure, before whitespace is collapsed. Long consolidated
            # articles otherwise exceed the aligner's page window.
            sec_lines = [line for _, line in lines[sec["line_index"]:end]]

            def _joined(chunk: list[str]) -> str:
                return re.sub(r"\s+", " ", "\n".join(chunk)).strip()

            head = _joined(sec_lines[:part_starts[0][0]])
            if head:
                pieces.append((number, head))
            for j, (start, label) in enumerate(part_starts):
                stop = part_starts[j + 1][0] if j + 1 < len(part_starts) else len(sec_lines)
                part = sec_lines[start:stop]
                items = _numbered_starts(part, _LIST_ITEM_LINE)
                if len(_joined(part)) <= LONG_PART_CHARS or len(items) < 2:
                    pieces.append((f"{number}({label})", _joined(part)))
                    continue
                # A very long part is a list of powers/duties "1) ... 40) ...":
                # one unit per item keeps it alignable and pinpoints "13(1)(4)".
                pieces.append((f"{number}({label})", _joined(part[:items[0][0]])))
                for k, (item_start, item) in enumerate(items):
                    item_stop = items[k + 1][0] if k + 1 < len(items) else len(part)
                    pieces.append((f"{number}({label})({item})",
                                   _joined(part[item_start:item_stop])))
        elif len(markers) >= 2:
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
