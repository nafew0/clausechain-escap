"""Build the KNOWN/NEW baseline from the ESCAP-provided files.

Per the ESCAP 10-June mail:
- PRIMARY baseline  = master dataset (`ESCAP-RDTII-2.1_ Round 1 Database.xlsx`).
  Article references live inside its free-text "Impact" column — we parse them out.
- SECONDARY         = portals CSV (P6/P7 law↔indicator names) and the 384-row
  Legal Inventory CSV (all pillars; crawler seeds only, never the KNOWN baseline).

Output: data/known_index.json + data/seeds.json (built by scripts/build_known_index.py).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from packages.ingest.xlsx import read_rows, sheet_names

# --- article / section reference extraction -------------------------------

_REF_NUMBER = r"\d+(?:\.\d+){0,2}[A-Z]{0,2}(?:\s*\(\s*\w{1,3}\s*\))*"
_REF_PATTERNS = [
    # Malay statutory citation forms (rerun-fix #3): "Seksyen 12A", "Perkara 5", "Peraturan 4"
    (re.compile(rf"\b[Ss]eksyen\s+({_REF_NUMBER})"), "s."),
    (re.compile(rf"\b[Pp]erkara\s+({_REF_NUMBER})"), "Art."),
    (re.compile(rf"\b[Pp]eraturan\s+({_REF_NUMBER})"), "reg."),
    (re.compile(rf"\bArticles?\s+({_REF_NUMBER})", re.I), "Art."),
    (re.compile(rf"\bArt\.?\s*({_REF_NUMBER})", re.I), "Art."),
    (re.compile(rf"\bSections?\s+({_REF_NUMBER})", re.I), "s."),
    (re.compile(rf"\bSec\.?\s*({_REF_NUMBER})", re.I), "s."),
    (re.compile(rf"\b[Ss]\.\s*({_REF_NUMBER})"), "s."),
    (re.compile(rf"\bRegulations?\s+({_REF_NUMBER})", re.I), "reg."),
    (re.compile(rf"\bRules?\s+({_REF_NUMBER})(?!\s*of)", re.I), "r."),
    (re.compile(rf"\bClauses?\s+({_REF_NUMBER})", re.I), "cl."),
    (re.compile(r"\bSchedules?\s+(\d+[A-Z]{0,2})", re.I), "Sch."),
]


def extract_refs(text: str) -> list[str]:
    """Pull normalized provision references (e.g. 's. 245(2)', 'Art. 18') from prose."""
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pattern, prefix in _REF_PATTERNS:
        for match in pattern.finditer(text):
            raw = re.sub(r"\s+", "", match.group(1))
            ref = f"{prefix} {raw}"
            key = ref.lower()
            if key not in seen:
                seen.add(key)
                found.append(ref)
    return found


_DEFINITION_CONTEXT = re.compile(
    r"\b(defin(?:e[sd]?|ition)|means|refers? to)\b", re.I)
_SUPPORTING_CONTEXT = re.compile(
    r"\b(see also|read with|as defined in|provided for under)\b",
    re.I,
)
_SIGNIFICANT_LAW_TOKENS = {
    "act", "acts", "the", "of", "and", "a", "an", "bill", "code", "regulations",
    "amendment", "legislation", "organisation", "organization",
}


def _reference_context(text: str, start: int, end: int, radius: int = 360) -> str:
    """Return a bounded prose window around a master reference.

    Master cells are narrative rather than a citation table. A window is more
    reliable than sentence splitting because spreadsheet prose frequently omits
    periods or uses bullet fragments.
    """
    floor, ceiling = max(0, start - radius), min(len(text), end + radius)
    boundaries_before = [text.rfind(token, floor, start) for token in (". ", "\n", "• ")]
    left = max(boundaries_before)
    boundaries_after = [pos for token in (". ", "\n", " •")
                        if (pos := text.find(token, end, ceiling)) >= 0]
    right = min(boundaries_after) + 1 if boundaries_after else ceiling
    context = text[left + 1:right].strip()
    if re.match(r"^(?:It|This)\b", context):
        prior = max(text.rfind(token, floor, max(floor, left)) for token in (". ", "\n", "• "))
        context = text[prior + 1:right].strip()
    return re.sub(r"\s+", " ", context).strip()


def _law_hints(context: str, act_cell: str) -> list[str]:
    """Bind a prose citation to the instrument(s) actually named near it.

    If no instrument can be resolved confidently the caller retains the complete
    act list. This avoids inventing a pairing while preventing the old Cartesian
    product when the narrative clearly names the relevant Act.
    """
    context_tokens = set(normalize_law_name(context).split())
    candidates: list[tuple[tuple[int, float, int, int], str]] = []
    for act in split_act_names(act_cell):
        norm = normalize_law_name(act)
        tokens = {t for t in norm.split()
                  if t not in _SIGNIFICANT_LAW_TOKENS and not t.isdigit()}
        overlap = tokens & context_tokens
        if tokens and len(overlap) >= min(2, len(tokens)) and len(overlap) / len(tokens) >= 0.5:
            # Prefer the most specific named instrument.  A phrase such as
            # "Telecommunications (Interception and Access) Act" also contains
            # the words "Telecommunications Act"; returning both recreates the
            # old citation x instrument Cartesian product.
            score = (len(overlap), len(overlap) / len(tokens), len(tokens), len(norm.split()))
            candidates.append((score, norm))
    if not candidates:
        return []
    best = max(score for score, _ in candidates)
    hints = [norm for score, norm in candidates if score == best]
    # An Amendment Act's provisions live in the CONSOLIDATED principal act —
    # the amendment never exists as a corpus law on its own. If every resolved
    # hint is an amendment instrument, retain the principal act(s) from the
    # same cell too, or the anchor can never match anything (the s. 26 trap:
    # "PDPA 2012; PDPA (Amendment) Act 2020" bound s. 26 to the amendment only).
    if all(re.search(r"\bamend", hint) for hint in hints):
        principals = [normalize_law_name(act) for act in split_act_names(act_cell)
                      if not re.search(r"\bamend", normalize_law_name(act))]
        hints.extend(p for p in principals if p and p not in hints)
    return hints


def _indicator_context_fit(indicator: str | None, context: str) -> bool:
    """Conservative lexical test for whether a cited section is operative evidence.

    This is used only to define recall anchors from free-text master prose. It does
    not decide final legal mapping. When uncertain, the reference remains operative.
    """
    text = context.lower()
    transfer = re.search(r"transfer|transmit|send", text)
    cross_border = re.search(r"outside|abroad|foreign|cross[- ]border|out of", text)
    if indicator == "P6-I1":
        return bool(transfer and cross_border and re.search(r"must not|shall not|prohibit|ban", text))
    if indicator == "P6-I2":
        return bool(re.search(r"stor|keep|maintain|records?", text)
                    and re.search(r"local|within|in malaysia|in singapore|in australia|territor", text))
    if indicator == "P6-I3":
        return bool(re.search(r"server|data cent|infrastructure|facility", text)
                    and re.search(r"local|within|territor", text))
    if indicator == "P6-I4":
        return bool(transfer and cross_border and re.search(
            r"unless|\bif\b|consent|adequate|contract|condition|approval|safeguard", text))
    if indicator == "P7-I3":
        return bool(re.search(r"retain|keep|preserve|maintain", text)
                    and re.search(r"year|month|day|week|period of|not less than|at least", text))
    if indicator == "P7-I5":
        return bool(re.search(r"access|search|intercept|produce|seiz|investigat", text)
                    and re.search(r"government|police|officer|authority|commissioner|prosecutor|minister|"
                                  r"organisation|organization|agency|security intelligence|law enforcement", text))
    return True


def master_anchor_expected(indicator: str | None, score: str) -> bool:
    """Whether a master row should create positive provision-recall anchors.

    P7-I1/I2 are reverse-polarity framework indicators: score 0 normally means a
    framework exists, so its cited provisions remain positive evidence. For the
    presence/restriction indicators, score 0 is negative evidence and must not be
    forced into a positive output row.
    """
    try:
        value = float(str(score).strip())
    except (TypeError, ValueError):
        return True
    if indicator in {"P7-I1", "P7-I2"}:
        return value < 1
    return value > 0


def classify_ref_mentions(text: str, act_cell: str, indicator: str | None,
                          score: str) -> list[dict[str, Any]]:
    """Extract refs with audit-ready role, reason, context and law binding."""
    if not text:
        return []
    mentions: dict[str, dict[str, Any]] = {}
    positive_row = master_anchor_expected(indicator, score)
    for pattern, prefix in _REF_PATTERNS:
        for match in pattern.finditer(text):
            raw = re.sub(r"\s+", "", match.group(1))
            ref = f"{prefix} {raw}"
            context = _reference_context(text, match.start(), match.end())
            local_prefix = text[max(0, match.start() - 90):match.start()]
            if prefix == "reg." and raw.isdigit() and 1900 <= int(raw) <= 2100:
                role, reason = "instrument_title", "year in a Regulations title is not a provision"
            elif not positive_row:
                role, reason = "negative_evidence", "master score/polarity does not expect a positive row"
            elif _DEFINITION_CONTEXT.search(context):
                role, reason = "definition", "reference appears in definition/meaning context"
            elif _SUPPORTING_CONTEXT.search(context):
                role, reason = "supporting", "reference is descriptive or cross-referential, not the operative rule"
            elif re.search(r"(?:set out in|relevant to .{0,35} under|as mentioned in|defined in)\s*$",
                           local_prefix, re.I):
                role, reason = "supporting", "reference is a dependency of the operative provision"
            elif not _indicator_context_fit(indicator, context):
                role, reason = "supporting", f"nearby prose does not satisfy the {indicator} anchor predicate"
            else:
                role, reason = "operative", "positive master prose and indicator predicate support an operative anchor"
            item = {"ref": ref, "role": role, "reason": reason, "context": context,
                    "laws_norm": _law_hints(context, act_cell)}
            previous = mentions.get(ref.lower())
            # If the same ref occurs more than once, retain the strongest role.
            strength = {"instrument_title": 0, "negative_evidence": 1, "definition": 2,
                        "supporting": 3, "operative": 4}
            if previous is None or strength[role] > strength[previous["role"]]:
                mentions[ref.lower()] = item
    return list(mentions.values())


def expected_anchors(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only positive operative anchors, with legacy-index fallback."""
    if "ref_mentions" in entry:
        return [m for m in entry.get("ref_mentions", []) if m.get("role") == "operative"]
    if not master_anchor_expected(entry.get("indicator_code"), entry.get("score", "")):
        return []
    return [{"ref": ref, "role": "operative", "reason": "legacy index",
             "laws_norm": []} for ref in entry.get("articles", [])]


# --- normalization ----------------------------------------------------------

def normalize_law_name(name: str) -> str:
    """Normalize a title without erasing substantive parenthetical words.

    Acronyms and register identifiers are aliases (``(PDPA)``, ``(Act 854)``),
    while phrases such as ``(Interception and Access)`` distinguish one Act
    from another.  Treating every parenthesis as disposable collapses legally
    different instruments onto the same identifier.
    """
    def replace_parenthetical(match: re.Match[str]) -> str:
        value = match.group(1).strip()
        if re.fullmatch(r"[A-Z][A-Z0-9.&/-]{1,14}", value):
            return " "
        if re.fullmatch(r"(?:Act|No\.?)\s*\d+[A-Z-]*", value, re.I):
            return " "
        return f" {value} "

    text = re.sub(r"\(([^()]*)\)", replace_parenthetical, name or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_act_names(act_cell: str) -> list[str]:
    """The master DB packs several laws into one Act cell ('Law A; Law B')."""
    parts = re.split(r"[;\n]+", act_cell or "")
    return [part.strip() for part in parts if part.strip()]


def base_ref(ref: str) -> str:
    """'s. 26(1)' -> 's. 26' so paragraph-level cites match section-level gold."""
    return re.sub(r"\(.*$", "", ref or "").strip().lower()


_INDICATOR_NUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\b")

# Methodology policy names -> submission codes (P6/P7 only; methodology defs govern).
NAME_TO_CODE = {
    "ban and local processing requirements": "P6-I1",
    "local storage requirements": "P6-I2",
    "infrastructure requirements": "P6-I3",
    "conditional flow regimes": "P6-I4",
    "not in agreement with binding commitments on data transfer": "P6-I5",
    "lack of comprehensive legal framework for data protection": "P7-I1",
    "lack of dedicated legal framework for cybersecurity": "P7-I2",
    "minimum period of data retention requirements": "P7-I3",
    "data protection impact assessment or data protection officer requirements": "P7-I4",
    "requirements to allow government access to personal data": "P7-I5",
}


def _norm_policy(text: str) -> str:
    text = (text or "").lower().replace("&", "and")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def indicator_code(raw_indicator: str, raw_pillar: str = "") -> str | None:
    """Map '6.4', 'Indicator 6.4 ...' or a methodology policy name to 'P6-I4'."""
    match = _INDICATOR_NUM.search(raw_indicator or "")
    if match:
        pillar, num = int(match.group(1)), int(match.group(2))
        if 1 <= pillar <= 12:
            return f"P{pillar}-I{num}"
    by_name = NAME_TO_CODE.get(_norm_policy(raw_indicator))
    if by_name:
        return by_name
    if raw_pillar:
        try:
            pillar = int(float(raw_pillar))
        except ValueError:
            return None
        if 1 <= pillar <= 12:
            return f"P{pillar}-I?"
    return None


# --- master workbook parsing -------------------------------------------------

_HEADER_KEYS = {
    "country": ("country", "economy"),
    "pillar": ("pillar",),
    "indicator": ("indicator",),
    "score": ("raw score", "score"),
    "act": ("act",),
    "coverage": ("coverage",),
    "impact": ("impact",),
    "timeframe": ("timeframe",),
    "note": ("note",),
}


def _map_header(row: list[str]) -> dict[str, Any] | None:
    """Detect a header row. 'country' is optional — Round-2 sheets carry the economy
    in the sheet NAME (no country column), so we anchor on Act + (Indicator | Pillar)."""
    lowered = [cell.strip().lower() for cell in row]
    has_act = any(c.startswith("act") for c in lowered)
    has_indicator = any(c.startswith("indicator") for c in lowered)
    has_pillar = any(c.startswith("pillar") for c in lowered)
    if not (has_act and (has_indicator or has_pillar)):
        return None
    mapping: dict[str, Any] = {"refs": []}
    for idx, cell in enumerate(lowered):
        if not cell:
            continue
        if cell.startswith("reference"):
            mapping["refs"].append(idx)
            continue
        for key, prefixes in _HEADER_KEYS.items():
            if key not in mapping and any(cell.startswith(p) for p in prefixes):
                mapping[key] = idx
    return mapping if "act" in mapping else None


def _rows_from_sheet(path: Path, sheet: str, forced_country: str | None = None) -> list[dict]:
    rows = read_rows(path, sheet)
    header: dict[str, Any] | None = None
    entries: list[dict] = []
    for row in rows:
        if header is None:
            header = _map_header(row)
            continue
        def cell(key: str) -> str:
            idx = header.get(key)
            return row[idx].strip() if idx is not None and idx < len(row) else ""

        country = forced_country or cell("country")
        act = cell("act")
        if not act or not country:
            continue
        impact = cell("impact")
        code = indicator_code(cell("indicator"), cell("pillar"))
        entry = {
            "economy": country,
            "pillar": cell("pillar"),
            "indicator_raw": cell("indicator"),
            "indicator_code": code,
            "score": cell("score"),
            "act": act,
            "act_norm": normalize_law_name(act),
            "acts_norm": [normalize_law_name(part) for part in split_act_names(act)],
            "coverage": cell("coverage"),
            "impact": impact,
            "articles": extract_refs(impact),
            "ref_mentions": classify_ref_mentions(impact, act, code, cell("score")),
            "timeframe": cell("timeframe"),
            "references": [row[i].strip() for i in header["refs"] if i < len(row) and row[i].strip()],
            "source": "master",
        }
        entries.append(entry)
    return entries


def parse_master(path: str | Path) -> list[dict]:
    path = Path(path)
    names = sheet_names(path)
    if "Consolidated" in names:
        return _rows_from_sheet(path, "Consolidated")
    entries: list[dict] = []
    for sheet in names:
        if sheet.strip().lower() in {"australia", "malaysia", "singapore"}:
            entries.extend(_rows_from_sheet(path, sheet, forced_country=sheet.strip()))
    return entries


def parse_round2(path: str | Path) -> list[dict]:
    """Round-2 finals DB: one sheet per economy (CN/IN/ID/LA/MN/RU/TH), no 'country'
    column — the economy comes from the sheet name. Skips the methodology sheet."""
    path = Path(path)
    entries: list[dict] = []
    for sheet in sheet_names(path):
        low = sheet.strip().lower()
        if "methodology" in low or low.startswith("rdtii"):
            continue
        entries.extend(_rows_from_sheet(path, sheet, forced_country=sheet.strip()))
    return entries


# --- csv parsing (portals + legal inventory) ---------------------------------

def parse_known_csv(path: str | Path, source: str) -> list[dict]:
    """Parse the portals CSV / Legal Inventory CSV (same shape)."""
    entries: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            act = (row.get("Act.and.or.practice") or "").strip()
            country = (row.get("country") or "").strip()
            if not act or not country:
                continue
            policy = (row.get("policy.description") or "").strip()
            entries.append({
                "economy": country,
                "pillar": "",
                "indicator_raw": policy,
                "indicator_code": NAME_TO_CODE.get(_norm_policy(policy)),
                "score": "",
                "act": act,
                "act_norm": normalize_law_name(act),
                "acts_norm": [normalize_law_name(part) for part in split_act_names(act)],
                "coverage": (row.get("Coverage") or "").strip(),
                "impact": "",
                "articles": [],
                "timeframe": (row.get("Timeframe") or "").strip(),
                "references": [r for r in [(row.get("References") or "").strip()] if r],
                "cluster": (row.get("cluster") or "").strip(),
                "source": source,
            })
    return entries


# --- assembly -----------------------------------------------------------------

def build_index(master_entries: list[dict], portal_entries: list[dict]) -> dict:
    """KNOWN index: master is primary; portals add law↔indicator names (no articles)."""
    economies: dict[str, list[dict]] = {}
    for entry in master_entries + portal_entries:
        economies.setdefault(entry["economy"], []).append(entry)
    return {
        "baseline_ruling": "master = primary KNOWN reference; portals/inventory = secondary (ESCAP mail, 10 Jun 2026)",
        "counts": {
            "master_rows": len(master_entries),
            "portal_rows": len(portal_entries),
            "master_rows_with_articles": sum(1 for e in master_entries if e["articles"]),
        },
        "economies": economies,
    }
