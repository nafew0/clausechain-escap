"""Generic Round-2 corpus builder: archived seeds -> RuleUnits -> graph.

The MY builder's integrity rules, parameterized by jurisdiction pack:
duplicate-register guard, status assertions, evidence/content eligibility,
fail-closed expected-evidence, structure-coverage floor, span alignment,
generation pruning. OCR comes from the pack's `ocr:` block (hybrid routing).

Usage: .venv/bin/python scripts/build_seeds_corpus.py --economy Thailand [--only-act X] [--force]
"""
from __future__ import annotations

import argparse
import re
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

import yaml  # noqa: E402

from packages.core.evidence import source_artifact_from_file  # noqa: E402
from packages.core.fingerprint import processing_fingerprint  # noqa: E402
from packages.core.legal_controls import (content_eligibility, evidence_eligibility,  # noqa: E402
                                          resolve_status)
from packages.discovery.diff import normalize_law  # noqa: E402
from packages.extractors.pdf import extract_pdf, materialize_page_evidence  # noqa: E402
from packages.extractors.pdf_act import parse_act_text  # noqa: E402
from packages.extractors.pdf_align import align_and_bind_pdf_evidence  # noqa: E402
from packages.graph.sqlite_graph import SqliteGraphStore  # noqa: E402
from packages.graph.store import get_graph_store  # noqa: E402
from packages.ingest.seed_profiles import (missing_expectations, seed_fingerprint_config,  # noqa: E402
                                           seed_parse_profile)
from packages.providers.ocr_provider import build_ocr  # noqa: E402

CC = {"Thailand": "th", "India": "in", "Indonesia": "id",
      "Russian Federation": "ru", "Mongolia": "mn", "Lao PDR": "la", "Timor-Leste": "tl",
      # Round-1 economies: only through --pillars (their P6/P7 corpora come from the
      # dedicated SSO / AGC / Federal Register builders, which this must not prune).
      "Singapore": "sg", "Malaysia": "my", "Australia": "au"}
ROUND1_BUILDERS = {"Singapore", "Malaysia", "Australia"}
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
LAO_DIGITS = str.maketrans("໐໑໒໓໔໕໖໗໘໙", "0123456789")
# Mojibake guard: a native text layer must carry the pack's primary script.
SCRIPT_RANGES = {"th": ("฀", "๿"), "hi": ("ऀ", "ॿ"),
                 "lo": ("຀", "໿"), "ru": ("Ѐ", "ӿ"),
                 "mn": ("Ѐ", "ӿ")}


_ENGLISH_FUNCTION_WORDS = frozenset(
    "the of and to in a is shall be by or for that this with as on any such which may "
    "under from not are an it where data personal".split())


def readable_english(text: str) -> bool:
    """True for genuine English prose: at least 12% of tokens are common English
    function words. Subset-font mojibake ("Nล@$>@/...") and letter soup never
    reach that; a real statute translation sits around 35-45%."""
    tokens = re.findall(r"[A-Za-z]+", text.casefold())
    if len(tokens) < 50:
        return False
    return sum(1 for token in tokens if token in _ENGLISH_FUNCTION_WORDS) >= 0.12 * len(tokens)


# Everyday Lao function words. Legacy-font text layers (LSC Decision 11: "ມາດຕາ"
# stored as "ຓາຈຉາ") are Lao-block codepoints but the wrong letters: they score
# ~2 of these per 1,000 Lao chars, genuine Lao ~40 (measured 29 Sep 2026).
_LAO_FUNCTION_WORDS = ("ການ", "ແລະ", "ຂອງ", "ທີ່", "ໃນ", "ມາດຕາ")


def readable_lao(text: str) -> bool:
    lao_chars = sum(1 for ch in text if "\u0e80" <= ch <= "\u0eff")
    if lao_chars < 500:
        return True  # too little Lao to judge; the script-share guard handles it
    hits = sum(text.count(word) for word in _LAO_FUNCTION_WORDS)
    return hits * 1000 / lao_chars >= 10


def _normalize_labels(units) -> None:
    """Thai/Lao-numeral section labels -> Arabic in ids/citations (text untouched)."""
    for unit in units:
        for attr in ("id", "article_section"):
            value = getattr(unit, attr, None)
            if value and any("๐" <= ch <= "๙" or "໐" <= ch <= "໙" for ch in str(value)):
                setattr(unit, attr, str(value).translate(THAI_DIGITS).translate(LAO_DIGITS))


def _page_scope(entry: dict) -> tuple[int, int] | None:
    """A seed's `page_range: [first, last]` (1-based, inclusive): the instrument's
    pages inside a multi-instrument gazette issue (Jornal da República bundles
    several laws per PDF). The archived artifact stays the whole official file."""
    scope = entry.get("page_range")
    if not scope:
        return None
    first, last = int(scope[0]), int(scope[1])
    if first < 1 or last < first:
        raise ValueError(f"invalid page_range {scope!r}")
    return first, last


def say(message: str) -> None:
    """Print for the terminal and stream the same line to the live run console."""
    from packages.core import progress

    print(message)
    text = message.strip()
    level = "warn" if text.startswith(("INELIGIBLE", "FAILED", "DUPLICATE", "ALIGNMENT")) else "info"
    progress.emit("build", text, level=level)


def main() -> int:
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--economy", required=True, choices=sorted(CC))
    parser.add_argument("--only-act", default=None)
    parser.add_argument("--force", action="store_true",
                        help="re-extract every instrument of this economy even when its "
                             "fingerprint matches (after a parser/grammar fix; the "
                             "fingerprint does not change until EXTRACTION_VERSION is bumped)")
    parser.add_argument("--pillars", default=None,
                        help="additive build of one pillar's seeds, e.g. P2: fetch them from "
                             "data/seeds_r2.json, extract only those instruments and never "
                             "prune the economy's other units")
    args = parser.parse_args()
    economy, cc = args.economy, CC[args.economy]
    pillars = tuple(p.strip().upper() for p in (args.pillars or "").split(",") if p.strip())
    if economy in ROUND1_BUILDERS and not pillars:
        parser.error(f"{economy}'s P6/P7 corpus has its own builder; use --pillars P2")
    pack = yaml.safe_load(Path(f"configs/jurisdictions/{cc}.yaml").read_text())
    manifest_path = Path(f"data/raw/{cc}/seeds_manifest.json")
    if not pillars:
        # Fresh-clone contract (MY-builder rule): fetch the pack's seeds first. A full
        # build also fetches any P6/P7 seed its manifest lacks: after "Clear downloads"
        # and a one-pillar build the manifest holds only that pillar, and the prune at
        # the end would otherwise drop every instrument missing from it. Archived
        # successes are never refetched. (A pillar build fetches only that pillar below.)
        seeds_path = pack.get("seeds") or "data/seeds_r2.json"
        seed_rows = json.loads(Path(seeds_path).read_text())["economies"].get(economy, [])
        known = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
        if any(str(r.get("indicator_code", "")).startswith(("P6", "P7"))
               and (r.get("url") or "").strip().startswith("http")
               and (r.get("url") or "").strip() not in known for r in seed_rows):
            from packages.connectors.seeds_fetch import fetch_seeds
            fetch_seeds(economy, ("P6", "P7"), seeds_path=seeds_path)
    pillar_urls: set[str] | None = None
    if pillars:
        from packages.connectors.seeds_fetch import fetch_seeds
        fetch_seeds(economy, pillars, seeds_path="data/seeds_r2.json")
        rows = json.loads(Path("data/seeds_r2.json").read_text())["economies"].get(economy, [])
        pillar_urls = {r["url"].strip() for r in rows
                       if str(r.get("indicator_code", "")).startswith(pillars) and r.get("url")}
    manifest = json.loads(manifest_path.read_text())
    grammars = pack.get("section_grammars") or []
    assertions = pack.get("status_assertions") or {}
    official_domains = {s["domain"] for s in pack.get("official_sources", [])}
    ocr = build_ocr(pack.get("ocr") or {})
    ocr_tag = f"ocr:{(pack.get('ocr') or {}).get('provider', 'local')}:" \
              f"{(pack.get('ocr') or {}).get('route', '-')}"
    citation_template = pack.get("citation_template") or (
        "Art. {label}" if cc == "id" else "s. {label}")

    stores = [get_graph_store()]
    if (os.getenv("GRAPH_BACKEND") or "sqlite").lower() != "sqlite":
        stores.append(SqliteGraphStore())
    generation = datetime.now(timezone.utc).isoformat()
    total = loaded = skipped_html = 0
    build_complete = True
    processed: set[str] = set()

    for url, entry in manifest.items():
        if entry.get("status") != "ok":
            continue
        act_name = (entry.get("act") or "").strip()
        if not act_name:
            continue
        if args.only_act and args.only_act.casefold() not in act_name.casefold():
            continue
        if pillar_urls is not None and url not in pillar_urls:
            continue
        file = entry.get("file", "")
        if not file.endswith(".pdf"):
            # HTML landing/detail pages (BPK Details, JDIH, OJK regulasi): resolve
            # the embedded same-domain PDF link and fetch it once (MY-builder rule).
            import re as _re2
            import time as _time2
            from urllib.parse import urljoin, urlparse

            import httpx as _httpx

            resolved = None
            try:
                html = Path(file).read_text(encoding="utf-8", errors="ignore")
                for link in _re2.findall(r'href="([^"]+(?:\.pdf|/Download/[^"]*)[^"]*)"',
                                         html, _re2.I):
                    pdf_url = urljoin(url, link.replace("&amp;", "&"))
                    if (urlparse(pdf_url).hostname or "") == (urlparse(url).hostname or ""):
                        resolved = pdf_url
                        break
            except OSError:
                pass
            pdf_file = Path(file).with_suffix(".resolved.pdf")
            if not pdf_file.is_file() and resolved:
                _time2.sleep(2.0)
                try:
                    from urllib.parse import quote as _q
                    safe_ref = _q(url, safe=":/?&=%#")
                    resp = _httpx.get(_q(resolved, safe=":/?&=%#"), follow_redirects=True,
                                      timeout=120,
                                      headers={"User-Agent": "Mozilla/5.0 ClauseChain-research/0.1",
                                               "Referer": safe_ref})
                    if resp.status_code == 200 and resp.content[:5] == b"%PDF-":
                        pdf_file.write_bytes(resp.content)
                except _httpx.HTTPError:
                    pass
            if pdf_file.is_file():
                file = str(pdf_file)
            else:
                skipped_html += 1
                continue
        register_key = normalize_law(act_name)
        if register_key in processed:
            say(f"  DUPLICATE seed skipped for {act_name[:52]}")
            continue
        def _tokens(s: str) -> set[str]:
            import re as _re
            return {w for w in _re.sub(r"[^\w]", " ", s.lower()).split()
                    if len(w) > 2 and w not in {"the", "act", "notification", "b", "e"}}

        act_tokens = _tokens(act_name)
        assertion = None
        best_overlap = 0.0
        import re as _re_y
        act_years = set(_re_y.findall(r"\b(?:19|20|25)\d{2}\b", act_name))
        for key, value in assertions.items():
            kt = _tokens(key)
            if not kt:
                continue
            key_years = set(_re_y.findall(r"\b(?:19|20|25)\d{2}\b", key))
            # Year guard: when both sides state a statute year, they must agree —
            # never stamp one instrument with another vintage's in-force fact.
            if act_years and key_years and not (act_years & key_years):
                continue
            overlap = len(kt & act_tokens) / len(kt)
            if overlap > best_overlap and overlap >= 0.6:
                assertion, best_overlap = value, overlap
        status = resolve_status(
            fact_url=(assertion or {}).get("fact_url", url),
            fact_text=(assertion or {}).get(
                "fact_text", "Official source archived; legal currentness not yet asserted"),
            current_as_at=(assertion or {}).get("current_as_at"),
            effective_date=(assertion or {}).get("effective_date"),
            explicit_status=(assertion or {}).get("status"),
        )
        profile = seed_parse_profile(entry, grammars)
        eligible, reason = evidence_eligibility(act_name, profile["source_type"], status.status)
        if not eligible:
            for st in stores:
                if hasattr(st, "add_discovery_lead"):
                    st.add_discovery_lead(f"{cc}:{Path(file).stem}", reason or "INELIGIBLE",
                                          {"name": act_name, "url": url, "file": file})
            say(f"  INELIGIBLE {act_name[:52]}: {reason}")
            continue
        raw_access = str(entry.get("access_date") or "")
        try:
            accessed = datetime.fromisoformat(raw_access.replace("Z", "+00:00"))
        except ValueError:
            accessed = datetime.now(timezone.utc)
        try:
            artifact = source_artifact_from_file(
                file, original_url=url, retrieved_url=entry.get("final_url") or url,
                source_type=profile["source_type"], status_evidence=status,
                accessed_at=accessed, official_domains=official_domains,
                expected_mime="application/pdf",
            )
        except Exception as error:  # noqa: BLE001 — e.g. wayback PDFs w/ trailing bytes
            repaired = None
            if "EOF" in str(error):
                raw = Path(file).read_bytes()
                cut = raw.rfind(b"%%EOF")
                if cut > 0:
                    candidate = Path(file).with_suffix(".clean.pdf")
                    candidate.write_bytes(raw[: cut + 5] + b"\n")
                    try:
                        repaired = source_artifact_from_file(
                            str(candidate), original_url=url,
                            retrieved_url=entry.get("final_url") or url,
                            source_type=profile["source_type"], status_evidence=status,
                            accessed_at=accessed, official_domains=official_domains,
                            expected_mime="application/pdf")
                        file = str(candidate)
                        say(f"  repaired trailing bytes: {act_name[:48]}")
                    except Exception:  # noqa: BLE001
                        repaired = None
            if repaired is None:
                for st in stores:
                    if hasattr(st, "add_discovery_lead"):
                        st.add_discovery_lead(f"{cc}:{Path(file).stem}", "SOURCE_BYTES_INVALID",
                                              {"name": act_name, "url": url, "file": file,
                                               "error": str(error)[:160]})
                say(f"  INELIGIBLE {act_name[:52]}: SOURCE_BYTES_INVALID ({str(error)[:60]})")
                build_complete = False
                continue
            artifact = repaired
        if not artifact.official:
            for st in stores:
                if hasattr(st, "add_discovery_lead"):
                    st.add_discovery_lead(f"{cc}:{Path(file).stem}", "NON_OFFICIAL_ARCHIVE",
                                          {"name": act_name, "url": url, "file": file})
            say(f"  INELIGIBLE {act_name[:52]}: NON_OFFICIAL_ARCHIVE")
            continue
        fingerprint = processing_fingerprint(artifact.sha256, profile["source_type"],
                                             grammars, (ocr_tag,),
                                             config=seed_fingerprint_config(entry))
        if not args.only_act and not args.force:
            restamps = [st.restamp_artifact_generation(economy, fingerprint, generation)
                        if hasattr(st, "restamp_artifact_generation") else 0
                        for st in stores]
            if restamps and all(c > 0 for c in restamps):
                loaded += 1
                total += restamps[0]
                processed.add(register_key)
                say(f"  {act_name[:58]:58s} -> unchanged, {restamps[0]} units restamped")
                continue
        try:
            pages = extract_pdf(file, ocr_engine=ocr)
            # Mojibake guard (Thai gazette subset fonts): a "native" text layer
            # without the pack's primary script is garbage — force full OCR.
            primary_lang = ((pack.get("languages") or {}).get("primary") or "en")
            script_range = SCRIPT_RANGES.get(primary_lang)
            if script_range:
                lo, hi = script_range
                joined = "".join(p.text for p in pages)
                # Official English translations (PDPA EN, PDPC notifications) are
                # legitimately script-free: only a text layer that is readable in
                # neither the pack script nor English is font garbage.
                lacks_script = (joined.strip()
                                and sum(1 for ch in joined if lo <= ch <= hi) < len(joined) * 0.05
                                and not readable_english(joined))
                # Lao legacy fonts keep the script but not the letters.
                legacy_font = (primary_lang == "lo" and joined.strip()
                               and not readable_lao(joined) and not readable_english(joined))
                if lacks_script or legacy_font:
                    say(f"  mojibake text layer -> forced OCR: {act_name[:44]}")
                    pages = ocr.extract(file)
                    for p in pages:
                        p.metadata["ocr_forced_reason"] = (
                            "native text layer lacks primary script" if lacks_script
                            else "native text layer is a legacy-font encoding")
            scope = _page_scope(entry)
            if scope:
                pages = [p for p in pages if scope[0] <= p.page_number <= scope[1]]
                if not pages:
                    raise ValueError(f"page_range {list(scope)} outside the document")
            content_ok, content_reason = content_eligibility([p.text for p in pages])
            if not content_ok:
                for st in stores:
                    if hasattr(st, "add_discovery_lead"):
                        st.add_discovery_lead(f"{cc}:{Path(file).stem}",
                                              content_reason or "INELIGIBLE_CONTENT",
                                              {"name": act_name, "url": url, "file": file})
                say(f"  INELIGIBLE {act_name[:52]}: {content_reason}")
                continue
            page_artifacts, text_spans = materialize_page_evidence(pages, artifact.id)
            units = parse_act_text(pages, economy=economy, act_name=act_name,
                                   act_ref=Path(file).stem.replace("seed_", ""),
                                   source_url=artifact.retrieved_url,
                                   extra_section_patterns=profile["extra_section_patterns"],
                                   citation_template=(entry.get("citation_template")
                                                      or citation_template))
            _normalize_labels(units)
        except Exception as error:  # noqa: BLE001 — one bad PDF must not kill the build
            say(f"  FAILED {act_name[:50]}: {str(error)[:90]}")
            build_complete = False
            continue
        missing = missing_expectations(entry, units)
        if missing:
            say(f"  FAILED EXPECTED_EVIDENCE {act_name[:45]}: missing {missing}")
            build_complete = False
            continue
        # Short subordinate notifications (<=3 pages) are legitimately 1-2 clauses.
        minimum_units = max(1 if len(pages) <= 3 else 3, len(pages) // 5)
        if len(units) < minimum_units:
            for st in stores:
                if hasattr(st, "add_discovery_lead"):
                    st.add_discovery_lead(f"{cc}:{Path(file).stem}", "STRUCTURE_COVERAGE_LOW",
                                          {"name": act_name, "url": url, "file": file,
                                           "pages": len(pages), "units": len(units),
                                           "minimum_units": minimum_units})
                purge = getattr(st, "purge_instrument_provisions", None)
                if purge:
                    purge(economy, act_name, "STRUCTURE_COVERAGE_LOW")
            say(f"  INELIGIBLE {act_name[:52]}: STRUCTURE_COVERAGE_LOW "
                  f"({len(units)} units/{len(pages)} pages)")
            build_complete = False
            continue
        aligned, unit_count = align_and_bind_pdf_evidence(units, [file], [text_spans], [pages])
        if aligned != unit_count:
            say(f"  ALIGNMENT REVIEW {act_name[:45]}: {aligned}/{unit_count} exact")
        for unit in units:
            unit.metadata.update(
                archived_copy=file, access_date=entry.get("access_date"),
                inventory_url=url, content_sha256=artifact.sha256,
                legal_status=status.status,
                evidence_eligible=(eligible and unit.metadata.get("pdf_alignment") == "exact"),
                source_type=profile["source_type"],
                processing_fingerprint=fingerprint, build_generation=generation,
                status_evidence=status.model_dump(mode="json"))
            unit.source_artifact_id = artifact.id
            unit.raw_context = unit.raw_context or unit.text
        for st in stores:
            if hasattr(st, "upsert_source_artifact"):
                st.upsert_source_artifact(artifact)
            if hasattr(st, "upsert_page_artifacts"):
                st.upsert_page_artifacts(page_artifacts)
                st.upsert_text_spans(text_spans)
            if hasattr(st, "upsert_rule_units"):
                st.upsert_rule_units(units)
            else:
                for unit in units:
                    st.upsert_rule_unit(unit)
            mark = getattr(st, "mark_artifact_build_complete", None)
            if mark:
                mark(economy, fingerprint, generation, len(units))
        if units:
            loaded += 1
            total += len(units)
            processed.add(register_key)
            escalated = sum(1 for p in pages if p.metadata.get("ocr_escalation_reason"))
            vision_pages = sum(1 for p in pages if p.metadata.get("ocr_engine") == "google_vision")
            note = f" [vision:{vision_pages}p]" if vision_pages else ""
            say(f"  {act_name[:58]:58s} -> {len(units):4d} units{note}"
                  f"{f' esc:{escalated}' if escalated else ''}")

    if not args.only_act and not pillars:
        for st in stores:
            if hasattr(st, "prune_economy_generation"):
                st.prune_economy_generation(economy, generation)
    if not build_complete:
        say(f"{cc.upper()} build incomplete: unresolved acquisitions recorded; "
              "stale generation pruned")
    hits = stores[0].search_provisions("personal data", economy=economy, limit=3)
    top = hits[0]["props"].get("article_section") if hits else None
    say(f"\n{economy} corpus: {loaded} instruments, {total} rule units "
          f"(html-only seeds: {skipped_html}) | search smoke top: {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
