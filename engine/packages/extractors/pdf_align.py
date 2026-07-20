"""Align RuleUnits to authorised-PDF pages (alignment-lite, format-level).

For any economy where a structured source (EPUB/XHTML/HTML) provides the
section tree but the authorised PDF is the quotation/page authority: locate
each unit's opening text in the PDF page text -> `page N` (volume-aware)
location + a `pdf_alignment` metadata flag (`exact-prefix` | `unaligned-review`).
"""
from __future__ import annotations

import re
import unicodedata

from packages.core.schemas import ExtractedPage, RuleUnit, TextSpan

MAX_ALIGNMENT_PAGES = 6


def _alignment_targets(unit: RuleUnit) -> list[tuple[str, str]]:
    """Return canonical-to-narrow alignment targets without duplicating text.

    ``raw_context`` is the structural source of truth because it carries sibling
    paragraphs, list children, exceptions and continuations.  The semantic unit
    remains a fallback locator for documents whose PDF furniture prevents a
    whole-section exact match; callers must not promote that fallback into a
    complete structural context.
    """
    candidates = [("canonical-context", unit.raw_context or ""),
                  ("semantic-unit", unit.text or "")]
    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    for mode, text in candidates:
        normalized = _norm(text)
        if len(normalized) < 25 or normalized in seen:
            continue
        seen.add(normalized)
        targets.append((mode, text))
    return targets


def _norm(text: str) -> str:
    return _normalize_with_offsets(text)[0]


def _normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    previous_space = True
    translations = {"‑": "-", "–": "-", "—": "-", "−": "-",
                    "‘": "'", "’": "'", "“": '"', "”": '"'}
    for original_index, original in enumerate(text):
        expanded = unicodedata.normalize("NFKC", original)
        for char in expanded:
            if char == "\u00ad":
                continue
            if unicodedata.category(char) == "Pd":
                char = "-"
            char = translations.get(char, char)
            if char.isspace():
                if previous_space:
                    continue
                chars.append(" "); offsets.append(original_index); previous_space = True
            else:
                chars.append(char.lower()); offsets.append(original_index); previous_space = False
    # Span-heavy XHTML often introduces harmless spaces around punctuation that
    # PDF text extraction does not. Remove them symmetrically while preserving
    # an offset for every retained canonical character.
    filtered_chars: list[str] = []
    filtered_offsets: list[int] = []
    for i, char in enumerate(chars):
        if char == " ":
            previous = chars[i - 1] if i else ""
            following = chars[i + 1] if i + 1 < len(chars) else ""
            # PDF engines disagree on spacing around Unicode hyphens (for
            # example ``law ‑ enforcement`` versus ``law-enforcement``). Treat
            # the hyphen like structural punctuation so both representations
            # share one exact-search form while retained offsets still recover
            # the original PDF characters.
            if following in ",.;:!?)]}-" or previous in "([{-":
                continue
        filtered_chars.append(char); filtered_offsets.append(offsets[i])
    while filtered_chars and filtered_chars[0] == " ":
        filtered_chars.pop(0); filtered_offsets.pop(0)
    while filtered_chars and filtered_chars[-1] == " ":
        filtered_chars.pop(); filtered_offsets.pop()
    return "".join(filtered_chars), filtered_offsets


def align_to_pdf(units: list[RuleUnit], pdf_paths: list[str]) -> tuple[int, int]:
    """Returns (aligned, total)."""
    import fitz

    pages: list[dict] = []
    for vol_index, path in enumerate(pdf_paths, start=1):
        with fitz.open(path) as doc:
            prefix = f"vol {vol_index}, " if len(pdf_paths) > 1 else ""
            for page_no, page in enumerate(doc, start=1):
                raw_text = page.get_text()
                raw = page.get_text("rawdict")
                spans = []
                page_height = float(page.rect.height)
                for block in raw.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            st = "".join(ch.get("c", "") for ch in span.get("chars", []))
                            if st:
                                spans.append({"text": st, "bbox": list(span["bbox"])})
                # Federal Register compilation furniture occupies stable bands:
                # running Part/Division/Section headers above 13% and the printed
                # page/compilation footer below 72%. Excluding by geometry—not
                # by numeric regex—prevents page 102 from becoming a section and
                # permits exact span assembly across page breaks.
                body_spans = [s for s in spans
                              if s["bbox"][1] >= page_height * 0.13
                              and s["bbox"][3] <= page_height * 0.72]
                if not body_spans:
                    body_spans = spans  # small/synthetic pages without compilation furniture
                body_raw = "\n".join(s["text"] for s in body_spans)
                body_normalized, body_offsets = _normalize_with_offsets(body_raw)
                full_normalized, full_offsets = _normalize_with_offsets(raw_text)
                pages.append({"location": f"{prefix}page {page_no}", "raw": raw_text,
                              "body_raw": body_raw, "normalized": full_normalized,
                              "full_offsets": full_offsets,
                              "body_normalized": body_normalized,
                              "body_offsets": body_offsets,
                              "spans": spans, "body_spans": body_spans,
                              "volume": vol_index, "page": page_no})

    # Units arrive in document order, so alignment is monotonic: search forward
    # from the previous hit first (template offence language repeats across an
    # act — a global search would bind to the first duplicate, not the right one).
    aligned = 0
    cursor = 0
    window_cache: dict[tuple[int, int, str], tuple[str, str, list[int]]] = {}
    for unit in units:
        targets = _alignment_targets(unit)
        if not targets:
            continue
        target_mode, structural_source = targets[0]
        target = _norm(structural_source)
        unit_target = _norm(unit.text)
        probe = target[:120]
        if len(probe) < 25:
            continue
        section_number = str(unit.metadata.get("section_number") or "").strip()
        section_anchor = _norm(f"Section {section_number}") if section_number else ""
        anchor_indices = [i for i, page in enumerate(pages)
                          if section_anchor and section_anchor in page["normalized"]]
        page_hint = re.search(r"page\s+(\d+)", unit.location_reference, re.I)
        volume_hint = re.search(r"vol\s+(\d+)", unit.location_reference, re.I)
        hint_indices = [i for i, page in enumerate(pages)
                        if page_hint and page["page"] == int(page_hint.group(1))
                        and (not volume_hint
                             or page["volume"] == int(volume_hint.group(1)))]
        hit_index = None
        hit_window: tuple[str, list[int], list[dict], int] | None = None
        preferred = list(dict.fromkeys(hint_indices + anchor_indices))
        search_order = preferred or (list(range(cursor, len(pages))) + list(range(0, cursor)))
        for candidate_mode, candidate_source in targets:
            candidate_target = _norm(candidate_source)
            for i in search_order:
                same_volume = []
                for page in pages[i:i + MAX_ALIGNMENT_PAGES]:
                    if page["volume"] != pages[i]["volume"]:
                        break
                    same_volume.append(page)
                for count in range(1, len(same_volume) + 1):
                    # Federal compilations prefer geometry-filtered body text;
                    # treaties/state PDFs fall back to the full page. This is a
                    # layout strategy, not an instrument-specific exception.
                    for mode in ("body", "full"):
                        cache_key = (i, count, mode)
                        if cache_key not in window_cache:
                            field = "body_raw" if mode == "body" else "raw"
                            raw_text = "\n".join(p[field] for p in same_volume[:count])
                            if count == 1:
                                normalized = (same_volume[0]["body_normalized"]
                                              if mode == "body"
                                              else same_volume[0]["normalized"])
                                offsets = (same_volume[0]["body_offsets"]
                                           if mode == "body"
                                           else same_volume[0]["full_offsets"])
                            else:
                                normalized, offsets = _normalize_with_offsets(raw_text)
                            window_cache[cache_key] = (raw_text, normalized, offsets)
                        raw_text, normalized, offsets = window_cache[cache_key]
                        pos = normalized.find(candidate_target)
                        if pos >= 0:
                            hit_index = i
                            hit_window = (raw_text, offsets, same_volume[:count], pos)
                            target = candidate_target
                            target_mode = candidate_mode
                            unit.metadata["alignment_text_layer"] = mode
                            break
                    if hit_index is not None:
                        break
                if hit_index is not None:
                    break
            if hit_index is not None:
                break
        if hit_index is not None and hit_window is not None:
            raw_text, offsets, matched_pages, pos = hit_window
            start, end = offsets[pos], offsets[pos + len(target) - 1] + 1
            exact_context = raw_text[start:end]
            unit.raw_context = exact_context
            # Preserve the unit boundary, but recover its characters from the
            # same PDF window rather than retaining XHTML/normalized parser text.
            unit_pos = normalized.find(unit_target, pos, pos + len(target))
            if unit_pos >= 0:
                unit_start = offsets[unit_pos]
                unit_end = offsets[unit_pos + len(unit_target) - 1] + 1
                unit.text = raw_text[unit_start:unit_end]
            else:
                unit.text = exact_context
            first_page, last_page = matched_pages[0], matched_pages[-1]
            unit.location_reference = first_page["location"]
            unit.metadata["pdf_alignment"] = "exact"
            unit.metadata["alignment_context"] = target_mode
            unit.metadata["alignment_score"] = 1.0
            unit.metadata["alignment_start_page"] = first_page["page"]
            unit.metadata["alignment_end_page"] = last_page["page"]
            unit.metadata["alignment_volume"] = first_page["volume"]
            unit.metadata["pdf_span_boxes"] = [
                s["bbox"] for page in matched_pages for s in page["spans"]
                if len(_norm(s["text"])) >= 2 and _norm(s["text"]) in target
            ]
            cursor = hit_index
            aligned += 1
        else:
            # Page furniture can interrupt an otherwise exact subsection across
            # pages. The XHTML semantic blocks correspond to PDF paragraphs, so
            # align every block independently and reconstruct only from exact
            # original PDF slices. This is still source-exact span assembly—no
            # generated or fuzzy text enters the RuleUnit.
            semantic = [b for b in unit.metadata.get("semantic_blocks", [])
                        if len(_norm(b.get("text", ""))) >= 4]
            block_hits: list[tuple[int, str]] = []
            starts = anchor_indices or [cursor]
            for anchor_index in starts:
                candidate_hits: list[tuple[int, str]] = []
                anchor_volume = pages[anchor_index]["volume"]
                allowed = [i for i in range(anchor_index, min(len(pages), anchor_index + MAX_ALIGNMENT_PAGES))
                           if pages[i]["volume"] == anchor_volume]
                last_index = anchor_index
                for block in semantic:
                    block_target = _norm(block["text"])
                    found = None
                    for page_index in allowed:
                        if page_index < last_index:
                            continue
                        for mode in ("body", "full"):
                            normalized = (pages[page_index]["body_normalized"]
                                          if mode == "body" else pages[page_index]["normalized"])
                            offsets = (pages[page_index]["body_offsets"]
                                       if mode == "body" else pages[page_index]["full_offsets"])
                            position = normalized.find(block_target)
                            if position >= 0:
                                raw_key = "body_raw" if mode == "body" else "raw"
                                start = offsets[position]
                                end = offsets[position + len(block_target) - 1] + 1
                                found = (page_index, pages[page_index][raw_key][start:end])
                                break
                        if found is not None:
                            break
                    if found is None:
                        candidate_hits = []
                        break
                    candidate_hits.append(found)
                    last_index = found[0]
                if semantic and len(candidate_hits) == len(semantic):
                    block_hits = candidate_hits
                    break
            if semantic and len(block_hits) == len(semantic):
                first_index, last_index = block_hits[0][0], block_hits[-1][0]
                first_page, last_page = pages[first_index], pages[last_index]
                unit.text = "\n".join(text for _, text in block_hits)
                unit.raw_context = unit.text
                unit.location_reference = first_page["location"]
                unit.metadata["pdf_alignment"] = "exact"
                unit.metadata["alignment_mode"] = "exact-semantic-spans"
                unit.metadata["alignment_score"] = 1.0
                unit.metadata["alignment_start_page"] = first_page["page"]
                unit.metadata["alignment_end_page"] = last_page["page"]
                unit.metadata["alignment_volume"] = first_page["volume"]
                targets = [_norm(text) for _, text in block_hits]
                unit.metadata["pdf_span_boxes"] = [
                    span["bbox"] for page in pages[first_index:last_index + 1]
                    if page["volume"] == first_page["volume"] for span in page["spans"]
                    if len(_norm(span["text"])) >= 2
                    and any(_norm(span["text"]) in target for target in targets)
                ]
                cursor = first_index
                aligned += 1
            else:
                unit.metadata["pdf_alignment"] = "unaligned-review"
                unit.metadata["alignment_score"] = (len(block_hits) / len(semantic)
                                                    if semantic else 0.0)
    return aligned, len(units)


def align_and_bind_pdf_evidence(
    units: list[RuleUnit],
    pdf_paths: list[str],
    spans_by_volume: list[list[TextSpan]],
    extracted_pages_by_volume: list[list[ExtractedPage]] | None = None,
) -> tuple[int, int]:
    """Shared PDF route for every economy: align text, then bind proof spans.

    ``spans_by_volume`` follows ``pdf_paths`` order.  This single route keeps SG,
    MY and AU from drifting into different alignment/proof contracts.
    """
    if len(pdf_paths) != len(spans_by_volume):
        raise ValueError("each PDF volume requires its own immutable TextSpan collection")
    if extracted_pages_by_volume is not None:
        if len(pdf_paths) != len(extracted_pages_by_volume):
            raise ValueError("each PDF volume requires its canonical extracted pages")
        aligned, total = align_to_extracted_pages(units, extracted_pages_by_volume)
    else:
        aligned, total = align_to_pdf(units, pdf_paths)
    for unit in units:
        volume = int(unit.metadata.get("alignment_volume") or 1)
        if not 1 <= volume <= len(spans_by_volume):
            unit.metadata["pdf_alignment"] = "unaligned-review"
            unit.metadata["alignment_score"] = 0.0
            unit.linked_span_ids = []
            continue
        spans = spans_by_volume[volume - 1]
        start_page = int(unit.metadata.get("alignment_start_page") or 0)
        end_page = int(unit.metadata.get("alignment_end_page") or start_page)
        selected = [span for span in spans
                    if start_page and start_page <= span.page_number <= end_page]
        unit.linked_span_ids = [span.id for span in selected]
        unit.metadata["pdf_span_boxes"] = [list(span.bbox) for span in selected]
    return aligned, total


def align_to_extracted_pages(
    units: list[RuleUnit], pages_by_volume: list[list[ExtractedPage]]
) -> tuple[int, int]:
    """Align semantic units to canonical native/OCR PageArtifacts.

    Scanned PDFs have no native text layer; their authoritative quotation text
    is the stored OCR output with token boxes. Native and mixed documents can
    use the same route, preventing format-specific evidence logic.
    """
    pages: list[dict] = []
    for volume, extracted_pages in enumerate(pages_by_volume, start=1):
        for page in extracted_pages:
            normalized, offsets = _normalize_with_offsets(page.text)
            pages.append({
                "volume": volume,
                "page": page.page_number,
                "raw": page.text,
                "normalized": normalized,
                "offsets": offsets,
                "tokens": page.tokens,
            })
    aligned = 0
    cursor = 0
    window_cache: dict[tuple[int, int], tuple[str, str, list[int]]] = {}
    target_hit_cache: dict[str, tuple[int, list[dict], str] | None] = {}
    probe_cache: dict[str, list[int]] = {}
    for unit in units:
        targets = _alignment_targets(unit)
        if not targets:
            unit.metadata["pdf_alignment"] = "unaligned-review"
            unit.metadata["alignment_score"] = 0.0
            continue
        page_hint = re.search(r"page\s+(\d+)", unit.location_reference, re.I)
        volume_hint = re.search(r"vol\s+(\d+)", unit.location_reference, re.I)
        hinted = [i for i, page in enumerate(pages)
                  if page_hint and page["page"] == int(page_hint.group(1))
                  and (not volume_hint or page["volume"] == int(volume_hint.group(1)))]
        hit = None
        target_mode = "semantic-unit"
        for candidate_mode, candidate_source in targets:
            target = _norm(candidate_source)
            cached = target_hit_cache.get(target, ...)
            if cached is not ...:
                if cached is not None:
                    hit = cached
                    target_mode = candidate_mode
                if hit:
                    break
                continue
            section = str(unit.metadata.get("section_number") or "").strip()
            heading = str(unit.metadata.get("toc_hint") or
                          unit.metadata.get("heading") or "").strip()
            anchor = _norm(f"{section} {heading}") if section and heading else ""
            anchor_indices = ([i for i, page in enumerate(pages)
                               if anchor and anchor in page["normalized"]]
                              if anchor else [])
            probe = target[:100]
            if probe not in probe_cache:
                probe_cache[probe] = [i for i, page in enumerate(pages)
                                      if probe in page["normalized"]]
            local = list(range(max(0, cursor - 1), min(len(pages), cursor + 24)))
            order = list(dict.fromkeys(hinted + anchor_indices + probe_cache[probe] + local))
            if not order:
                order = list(range(len(pages)))
            for start_index in order:
                same_volume = []
                for page in pages[start_index:start_index + MAX_ALIGNMENT_PAGES]:
                    if page["volume"] != pages[start_index]["volume"]:
                        break
                    same_volume.append(page)
                for count in range(1, len(same_volume) + 1):
                    cache_key = (start_index, count)
                    if cache_key not in window_cache:
                        raw = "\n".join(page["raw"] for page in same_volume[:count])
                        normalized, offsets = _normalize_with_offsets(raw)
                        window_cache[cache_key] = (raw, normalized, offsets)
                    raw, normalized, offsets = window_cache[cache_key]
                    position = normalized.find(target)
                    if position >= 0:
                        start = offsets[position]
                        end = offsets[position + len(target) - 1] + 1
                        hit = (start_index, same_volume[:count], raw[start:end])
                        target_mode = candidate_mode
                        break
                if hit:
                    break
            target_hit_cache[target] = hit
            if hit:
                break
        if not hit:
            unit.metadata["pdf_alignment"] = "unaligned-review"
            unit.metadata["alignment_score"] = 0.0
            continue
        start_index, matched_pages, exact = hit
        first_page, last_page = matched_pages[0], matched_pages[-1]
        unit.raw_context = exact
        exact_normalized, exact_offsets = _normalize_with_offsets(exact)
        unit_target = _norm(unit.text)
        unit_position = exact_normalized.find(unit_target)
        if unit_position >= 0:
            unit_start = exact_offsets[unit_position]
            unit_end = exact_offsets[unit_position + len(unit_target) - 1] + 1
            unit.text = exact[unit_start:unit_end]
        else:
            unit.text = exact
        prefix = f"vol {first_page['volume']}, " if len(pages_by_volume) > 1 else ""
        unit.location_reference = f"{prefix}page {first_page['page']}"
        unit.metadata.update({
            "pdf_alignment": "exact",
            "alignment_context": target_mode,
            "alignment_mode": "canonical-page-text",
            "alignment_text_layer": "ocr" if any(
                token.confidence is not None
                for page in matched_pages for token in page["tokens"]
            ) else "native",
            "alignment_score": 1.0,
            "alignment_start_page": first_page["page"],
            "alignment_end_page": last_page["page"],
            "alignment_volume": first_page["volume"],
            "pdf_span_boxes": [list(token.bbox) for page in matched_pages
                               for token in page["tokens"] if token.bbox],
        })
        cursor = start_index
        aligned += 1
    return aligned, len(units)
