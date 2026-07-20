"""EPUB/XHTML act extractor: semantic-markup compilations -> RuleUnits.

Format family: legislatures that ship an EPUB (or bare XHTML) of the authorised
compilation with semantic heading classes. Structured markup eliminates the
regex-PDF failure modes (false sections from notes, page-footer headings,
decimal Schedule sections, indentation dependence).

Authority split (user-approved scope): XHTML = STRUCTURE oracle; the authorised
PDF remains the quotation/page authority — see `pdf_align.align_to_pdf` for the
page-location alignment pass.
"""
from __future__ import annotations

import io
import re
import zipfile

from packages.core.schemas import RuleUnit
from packages.extractors.textutil import clean_text

# --- legislation.gov.au markup profile (FROZEN ids — stored corpora, zone-3 ---
# scores, and refutation files reference the "au:{ref}:s..." scheme below).
# EPUB route: /{titleId}/{date}/{date}/text/original/epub — same authorised
# compilation as the PDF. Heading classes ActHead1 (Chapter/Schedule) ..
# ActHead5 (section); section numbers in CharSectno spans; TOC* classes are
# navigation-only and never match these patterns.
_ANY_HEAD = re.compile(r'<p\b[^>]*class="ActHead([1-5])"[^>]*>(.*?)</p>', re.I | re.S)
_SCHEDULE = re.compile(r"^Schedule\s+(\S+)\s*[—–-]", re.I)
_SECTNO = re.compile(r'class="CharSectno"[^>]*>(?:<[^>]+>)*([\dA-Z.]+)', re.I)
_ELEMENT_ID = re.compile(r'\bid=["\']([^"\']+)["\']', re.I)
_TOC5 = re.compile(r'<p\b[^>]*class=["\']TOC5["\'][^>]*>(.*?)</p>', re.I | re.S)
_ID_PREFIX = "au"
# --- end legislation.gov.au profile -------------------------------------------

_PARAGRAPH = re.compile(r"<p\b(?P<attrs>[^>]*)>(?P<body>.*?)</p>", re.I | re.S)
_CLASS = re.compile(r"\bclass\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_SUBSECTION_LABEL = re.compile(r"^\((\d{1,3}[A-Z]?)\)\s*", re.I)
_ITEM_LABEL = re.compile(r"^\(([a-z]{1,3}|[ivxlcdm]+)\)\s*", re.I)


def _semantic_blocks(section_html: str) -> list[tuple[str, str]]:
    blocks = []
    for paragraph in _PARAGRAPH.finditer(section_html):
        cm = _CLASS.search(paragraph.group("attrs"))
        css_class = cm.group(1).split()[0].lower() if cm else "plain"
        if css_class.startswith("acthead") or css_class.startswith("toc"):
            continue
        text = clean_text(paragraph.group("body"))
        if text:
            blocks.append((css_class, text))
    return blocks


def parse_epub_act(epub_bytes: bytes, economy: str, act_name: str, act_ref: str,
                   source_url: str, law_number_ref: str | None = None) -> list[RuleUnit]:
    z = zipfile.ZipFile(io.BytesIO(epub_bytes))
    html = "".join(
        z.read(n).decode("utf-8", errors="ignore")
        for n in z.namelist() if n.endswith((".xhtml", ".html"))
    )
    toc_hints: dict[str, str] = {}
    for toc in _TOC5.finditer(html):
        text = clean_text(toc.group(1))
        match = re.match(r"^(\d+(?:\.\d+)?[A-Z]{0,3})\s+(.+)$", text, re.I)
        if match:
            toc_hints.setdefault(match.group(1), match.group(2).strip())
    units: list[RuleUnit] = []
    heads = list(_ANY_HEAD.finditer(html))
    # Schedule tracking: clause numbering restarts inside Schedules (TIA Sch 1,
    # Telecom Act Schs) and would collide with body sections. Citation style:
    # "Sch 1, cl. 5" — EXCEPT decimal-numbered Code-style sections (Criminal
    # Code Schedule), which are conventionally cited as plain sections.
    schedule: tuple[str, int] | None = None  # (schedule number, heading level)
    hierarchy: dict[int, str] = {}
    in_endnotes = False
    for idx, head in enumerate(heads):
        level = int(head.group(1))
        if level < 5:
            head_text = clean_text(head.group(2))
            for deeper in [key for key in hierarchy if key >= level]:
                hierarchy.pop(deeper, None)
            hierarchy[level] = head_text
            if re.match(r"^Endnotes\b", head_text, re.I):
                in_endnotes = True
            sm = _SCHEDULE.match(head_text)
            if sm:
                schedule = (sm.group(1), level)
            elif schedule and level <= schedule[1]:
                schedule = None
            continue
        if in_endnotes:
            continue
        end = heads[idx + 1].start() if idx + 1 < len(heads) else len(html)
        section_html = html[head.start(): end]
        m = _SECTNO.search(section_html)
        if not m:
            continue
        number = m.group(1).strip().rstrip(".")
        in_schedule = schedule is not None and "." not in number
        heading = clean_text(head.group(2))
        heading = re.sub(rf"^{re.escape(number)}\s*", "", heading).strip()[:120]
        blocks = _semantic_blocks(section_html)
        raw_context = " ".join(text for _, text in blocks)

        # The official EPUB marks operative hierarchy explicitly. Only a
        # paragraph whose CSS class is `subsection` may start a subsection;
        # body references such as "under subsection (2)" can never split it.
        pieces: list[tuple[str, str, list[tuple[str, str]]]] = []
        current_label: str | None = None
        current_blocks: list[tuple[str, str]] = []
        preamble: list[tuple[str, str]] = []
        for css_class, block_text in blocks:
            if css_class == "subsectionhead":
                # A bold topic heading introduces the following subsection; it
                # is navigation/context, never the tail of the preceding rule.
                continue
            label_match = (_SUBSECTION_LABEL.match(block_text)
                           if css_class == "subsection" else None)
            if label_match:
                if current_label is not None:
                    pieces.append((f"{number}({current_label})",
                                   " ".join(t for _, t in current_blocks), current_blocks))
                current_label = label_match.group(1)
                current_blocks = [(css_class, block_text)]
            elif current_label is not None:
                current_blocks.append((css_class, block_text))
            else:
                preamble.append((css_class, block_text))
        if current_label is not None:
            pieces.append((f"{number}({current_label})",
                           " ".join(t for _, t in current_blocks), current_blocks))
        if not pieces:
            pieces.append((number, raw_context, blocks))

        for label, piece, piece_blocks in pieces:
            if len(piece) < 30:
                continue
            flat = label.replace("(", "-").replace(")", "")
            meta = {"heading": heading, "section_number": number,
                    "extraction": "xhtml_oracle",
                    "xhtml_anchor": ((_ELEMENT_ID.search(head.group(0)) or [None, None])[1]),
                    "toc_hint": toc_hints.get(number),
                    "hierarchy_path": [hierarchy[key] for key in sorted(hierarchy)] + [heading],
                    "part": next((value for value in hierarchy.values()
                                  if re.match(r"^Part\b", value, re.I)), ""),
                    "division": next((value for value in hierarchy.values()
                                      if re.match(r"^Division\b", value, re.I)), ""),
                    "semantic_classes": [c for c, _ in piece_blocks],
                    "semantic_blocks": [{"class": c, "text": t} for c, t in piece_blocks],
                    "hierarchy_labels": [m.group(1) for _, text in piece_blocks
                                         if (m := _ITEM_LABEL.match(text))]}
            if in_schedule:
                unit_id = f"{_ID_PREFIX}:{act_ref}:sch{schedule[0]}-cl{flat}"
                citation = f"Sch {schedule[0]}, cl. {label}"
                meta["schedule"] = schedule[0]
            else:
                unit_id = f"{_ID_PREFIX}:{act_ref}:s{flat}"
                citation = f"s. {label}"
            units.append(RuleUnit(
                id=unit_id,
                document_id=f"{_ID_PREFIX}:{act_ref}",
                economy=economy,
                law_name=act_name,
                law_number_ref=law_number_ref,
                article_section=citation,
                text=piece[:20000],
                source_url=source_url,
                location_reference="unaligned",
                raw_context=raw_context[:20000],
                metadata=meta,
            ))
    return units
