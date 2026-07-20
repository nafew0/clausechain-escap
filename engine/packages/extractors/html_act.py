"""Anchored-HTML act extractor: portal HTML -> ActDoc (sections + subsections).

Format family: statute portals that publish whole-act HTML with per-section
containers and named subsection anchors. Each portal's markup is a profile of
selector regexes below; the parse flow (split containers -> header/number ->
anchor-split subsections -> Part mapping) is shared. New economies with such
portals add a profile block + a `parse_*_act` entry point emitting `ActDoc`.

Citations: section anchor = {act_url}#pr26-; subsection label = "26(1)".
"""
from __future__ import annotations

import re

from packages.extractors.act_doc import ActDoc, Section, Subsection
from packages.extractors.textutil import clean_text

# Back-compat alias: the SSO parser predates the generic ActDoc contract.
SsoActDoc = ActDoc

# --- sso.agc.gov.sg portal profile (Singapore Statutes Online print view) ----
# Empirically verified on the live portal, 7 Jul 2026. Input: the archived
# output of `connectors.sg_sso.acquire_act` — one HTML file with the full act
# (86 `div.prov1` section blocks for the PDPA, part headings, schedules):
#   <td class="partHdr...">PART HEADING</td>
#   <div class="prov1">
#     <td class="prov1Hdr" id="pr26-"><span>Transfer of personal data...</span></td>
#     <td class="prov1Txt"><strong>26.</strong>
#         <a name="pr26-ps1-"></a> ... subsection (1) text ...
#   Schedules use id="Sc1-..." and class="sHdr".
_SECTION_SPLIT = re.compile(r'<div class="prov1">')
_SEC_ID = re.compile(r'class="prov1Hdr"[^>]*id="((?:pr|Sc)[^"]*)"')
_HDR_TEXT = re.compile(r'class="prov1Hdr"[^>]*>(.*?)</td>', re.DOTALL)
_NUMBER = re.compile(r"<strong>\s*([0-9]+[A-Z]*)\.?\s*</strong>")
_PART_HDR = re.compile(r'class="partHdr[^"]*"[^>]*>(.*?)</td>', re.DOTALL)
_PART_NO = re.compile(r'class="partNo[^"]*"[^>]*>(.*?)</td>', re.DOTALL)
_SUB_ANCHOR = re.compile(r'<a name="((?:pr|Sc)[^"]*?ps(\d+[A-Z]*)-)"\s*>')
_TITLE = re.compile(r"<title>([^<]*)</title>")
_CURRENT = re.compile(r"Current version as at ([0-9]{1,2} [A-Za-z]{3} [0-9]{4})")
_TITLE_SUFFIX = " - Singapore Statutes Online"
# --- end sso.agc.gov.sg profile ----------------------------------------------


def _parse_section(chunk: str, part: str) -> Section | None:
    id_match = _SEC_ID.search(chunk)
    if not id_match:
        return None
    sec_id = id_match.group(1)
    hdr = _HDR_TEXT.search(chunk)
    heading = clean_text(hdr.group(1)) if hdr else ""
    num = _NUMBER.search(chunk)
    number = num.group(1) if num else sec_id.strip("-").removeprefix("pr")

    # Subsections: split the chunk at <a name="...psN-"> anchors.
    anchors = list(_SUB_ANCHOR.finditer(chunk))
    subsections: list[Subsection] = []
    if anchors:
        for index, match in enumerate(anchors):
            start = match.end()
            end = anchors[index + 1].start() if index + 1 < len(anchors) else len(chunk)
            text = clean_text(chunk[start:end])
            text = re.sub(r"^[—–-]\s*", "", text)  # leading em-dash before "(1)"
            if text:
                subsections.append(
                    Subsection(label=f"{number}({match.group(2)})", text=text,
                               anchor=match.group(1))
                )
    if not subsections:
        # Single-body section: everything after the <strong>N.</strong> marker.
        body_start = num.end() if num else (hdr.end() if hdr else 0)
        text = clean_text(chunk[body_start:])
        if text:
            subsections.append(Subsection(label=number, text=text, anchor=sec_id))

    full_text = "\n".join(s.text for s in subsections)  # keep subsection line-breaks (rerun-fix #2)
    return Section(sec_id=sec_id, number=number, heading=heading, part=part,
                   text=full_text, subsections=subsections)


def parse_sso_act(html: str, source_url: str) -> ActDoc:
    title = _TITLE.search(html)
    law_name = clean_text(title.group(1)).replace(_TITLE_SUFFIX, "").strip() if title else ""
    current = _CURRENT.search(html)

    # Build a position -> part-heading map so each section knows its Part.
    part_positions: list[tuple[int, str]] = []
    part_numbers = [(m.start(), clean_text(m.group(1))) for m in _PART_NO.finditer(html)]
    for m in _PART_HDR.finditer(html):
        label = clean_text(m.group(1))
        number = ""
        for pos, num in reversed(part_numbers):
            if pos < m.start():
                number = num
                break
        part_positions.append((m.start(), f"{number} {label}".strip()))

    doc = ActDoc(
        law_name=law_name,
        current_as_at=current.group(1) if current else None,
        source_url=source_url,
    )
    chunks = _SECTION_SPLIT.split(html)
    offset = 0
    for chunk in chunks[1:]:
        offset = html.find(chunk, offset)
        part = ""
        for pos, label in reversed(part_positions):
            if pos < offset:
                part = label
                break
        section = _parse_section(chunk, part)
        if section is not None:
            doc.sections.append(section)
    return doc
