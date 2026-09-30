"""Final-round deliverable: OUTPUT_TEMPLATE_FINAL_ROUND in Excel, CSV and JSON.

Columns A-O are ESCAP's final-round template, in its exact names and order (the
secretariat validates against them). Evidence, verification and review columns
follow from column P onwards, which ESCAP allows ("free to add more columns";
orientation, Sep 2026). The Excel file is filled into ESCAP's own workbook so its
Indicator Reference, Coverage Matrix and morning sheets travel with the data.

The rows are the workspace's current results (scripts/export_final_round.py): every
provision a reviewer approved or has not yet decided, with its review state, and
the indicator matrix as it stands. Rejected findings are left out.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from copy import copy, deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

from packages.core.finalization import finding_key
from packages.core.schemas import MappedFinding

ENGINE_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ENGINE_ROOT / "configs" / "templates" / "OUTPUT_TEMPLATE_FINAL_ROUND.xlsx"
RUBRIC_DIR = ENGINE_ROOT / "configs" / "rdtii"
FILE_STEM = "OUTPUT_FINAL_ROUND"

PILLAR_COLUMN = "Pillar (auto — do not edit)"
TEMPLATE_COLUMNS: tuple[str, ...] = (
    "Economy",
    "Law Name",
    "Law Number / Ref",
    "Last Amended",
    "Indicator ID",
    "Article / Section",
    "Discovery Tag",
    "Location Reference",
    "Verbatim Snippet",
    "Mapping Rationale",
    "Source URL",
    "Confidence",
    "Notes",
    "Language of Source",
    PILLAR_COLUMN,
)
# Added after column O, with the help text shown in the template's description row.
EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Indicator Question", "The RDTII 2.1 legal question this provision answers."),
    ("Source Language (exact)", "The document's language when column N reads 'Other' (e.g. Portuguese, Malay), else the same as N."),
    ("Coverage", "Horizontal, or the sector the provision is confined to."),
    ("Legal Status", "Whether the provision was in force when it was checked."),
    ("Currentness Evidence", "Why the provision is treated as in force: the official status fact that was checked."),
    ("Currentness Source URL", "Official page the in-force status was checked against."),
    ("Currentness Checked At", "When the in-force status was last checked (UTC)."),
    ("Citation Alignment", "How the snippet was matched to the official text: exact = character-identical; anchor = located by its section anchor. Score 0-1."),
    ("Source Page", "Page of the official document holding the snippet."),
    ("Source Character Span", "Start-end character offsets of the snippet in the official document's extracted text."),
    ("Source Document SHA-256", "Hash of the exact official file the snippet was verified against; recompute it to check the source is unchanged."),
    ("Archived Copy Accessed", "Date the official source was downloaded and archived."),
    ("Verification Gates", "Automated evidence checks run before review (quote found in the source, official domain, "
                           "location, currentness statement, rule and exception together, must/may wording, "
                           "indicator fit, cross-references, complete sentence): how many passed, and which were "
                           "left to the reviewer's judgement."),
    ("Model", "Models that proposed the mapping: first-pass model, escalation model for hard cases, and the "
              "embedding model used for retrieval."),
    ("Engine Mode", "Hybrid = cloud models; Local = self-hosted open-weights model. Same engine, corpus and gates."),
    ("Review Decision", "approved = a named reviewer approved the citation, mapping and status; pending = engine finding "
                        "not yet fully reviewed. Rejected findings are not exported."),
    ("Citation Reviewer", "Who confirmed the quote is the cited provision of the official text."),
    ("Mapping Reviewer", "Who confirmed the provision answers this indicator's legal question."),
    ("Status Reviewer", "Who confirmed the provision is in force."),
    ("Reviewer Note", "The reviewer's own reasoning or correction."),
    ("Indicator Score", "The RDTII score (0 / 0.5 / 1) for this economy and indicator: the reviewer's decision, "
                        "or the engine's proposal while it awaits review (see Score Status)."),
    ("Score Status", "reviewer-approved, reviewer-overridden (reviewer changed the engine's score), or engine proposal."),
    ("Score Reasoning", "Why the indicator received that score."),
    ("Score Reviewer", "Who decided the indicator score."),
)
ALL_COLUMNS: tuple[str, ...] = TEMPLATE_COLUMNS + tuple(name for name, _ in EXTRA_COLUMNS)

# Template rule: official UN names. The template's own Coverage Matrix shortens Lao.
UN_ECONOMY_NAMES = {"Lao PDR": "Lao People's Democratic Republic", "Laos": "Lao People's Democratic Republic",
                    "Vietnam": "Viet Nam", "Russia": "Russian Federation", "South Korea": "Republic of Korea"}
TEMPLATE_LANGUAGES = ("English", "Thai", "Vietnamese", "Bahasa Indonesia", "Chinese", "Hindi",
                      "Kazakh", "Russian", "Lao", "Mongolian", "Other")
LOCAL_LATIN_LANGUAGE = {"Indonesia": "Bahasa Indonesia", "Viet Nam": "Vietnamese",
                        "Timor-Leste": "Portuguese", "Malaysia": "Malay", "Kazakhstan": "Kazakh"}
ENGINE_MODES = {"hybrid": "Hybrid (cloud models)", "local": "Local (open-weights model)"}
RATIONALE_LIMIT = 300

# ── template-clean display values ───────────────────────────────────────────
# The engine's own values stay as they are: a law name is part of the finding key,
# so renaming at the source would void every signed approval. The export shows the
# template's form instead: full official name plus year, no internal annotations.
OFFICIAL_LAW_NAMES = {
    "AANZFTA Second Protocol Chapter 10 (E-Commerce)":
        "Second Protocol to Amend the Agreement Establishing the ASEAN-Australia-New Zealand Free Trade Area "
        "2023, Chapter 10 (Electronic Commerce)",
    "CPTPP Chapter 14 (Malaysia MITI text)":
        "Comprehensive and Progressive Agreement for Trans-Pacific Partnership 2018, Chapter 14 (Electronic Commerce)",
    "RCEP Chapter 12 (official text)":
        "Regional Comprehensive Economic Partnership Agreement 2020, Chapter 12 (Electronic Commerce)",
    "IA-CEPA Chapter 13 (E-Commerce)":
        "Indonesia-Australia Comprehensive Economic Partnership Agreement 2019, Chapter 13 (Electronic Commerce)",
    "Digital Economy Partnership Agreement": "Digital Economy Partnership Agreement 2020",
    "Singapore-Australia Digital Economy Agreement": "Singapore-Australia Digital Economy Agreement 2020",
    "Convention for the Protection of Individuals with regard to Automatic Processing of Personal Data (ETS No. 108)":
        "Convention for the Protection of Individuals with regard to Automatic Processing of Personal Data 1981 "
        "(ETS No. 108)",
    "Personal Data Protection Act B.E. 2562 official EN translation": "Personal Data Protection Act B.E. 2562 (2019)",
    "Computer Crime Act B.E. 2550 as amended B.E. 2560 (ETDA consolidated)":
        "Computer Crime Act B.E. 2550 (2007), as amended by the Computer Crime Act (No. 2) B.E. 2560 (2017)",
    "PDPC Notification on Security Measures of Controllers B.E. 2565":
        "Notification of the Personal Data Protection Committee on Security Measures of the Data Controller "
        "B.E. 2565 (2022)",
    "Law No. 27 of 2022 on Personal Data Protection (official BPK full PDF)":
        "Law No. 27 of 2022 on Personal Data Protection",
    "PBI 23/6/PBI/2021 Payment Service Providers":
        "Bank Indonesia Regulation No. 23/6/PBI/2021 on Payment Service Providers",
    "PBI 23/7/PBI/2021 Payment System Infrastructure":
        "Bank Indonesia Regulation No. 23/7/PBI/2021 on Payment System Infrastructure Operators",
    "POJK 4/POJK.05/2021 NBFI IT Risk":
        "Financial Services Authority Regulation No. 4/POJK.05/2021 on the Implementation of Risk Management in the "
        "Use of Information Technology by Non-Bank Financial Services Institutions",
    "BSSN Regulation 2/2024 Cyber Crisis Management":
        "National Cyber and Crypto Agency (BSSN) Regulation No. 2 of 2024 on Cyber Crisis Management",
    "SEBI CSCRF 2024":
        "Securities and Exchange Board of India Cybersecurity and Cyber Resilience Framework for SEBI Regulated "
        "Entities 2024",
    "ANC Guidelines on the Registration of SIM Cards for Prepaid Mobile Services":
        "National Communications Authority (ANC) Guidelines on the Registration of SIM Cards for Prepaid Mobile "
        "Services",
}
# Where the law's own name records its latest amendment and no amendment date was captured.
LAST_AMENDED_FROM_NAME = {
    "Computer Crime Act B.E. 2550 as amended B.E. 2560 (ETDA consolidated)": "2017",
    "Public Procurement (Preference to Make in India) Order 2017 (DPIIT, revised 19 July 2024)": "2024",
}
SEED_NAME_CAP = 200   # seed files stored law names cut at 200 characters
BASELINE_FILES = ("data/known_index_round2.json", "data/known_index.json")
GATE_LABELS = {"G1": "quote found in source", "G2": "location matches citation", "G3": "official source",
               "G4": "currentness statement on the portal", "G5": "rule and exception together",
               "G6": "must/may wording", "G7": "indicator fit", "G8": "cross-references",
               "G9": "complete sentence"}
LEGAL_STATUS = {"in_force": "In force", "repealed": "Repealed", "not_in_force": "Not in force"}

# English function words only: legal vocabulary like "data" also appears in Indonesian or
# Malay text and would mislabel it.
_ENGLISH_WORDS = frozenset(
    "the of and to in is shall be by or for that this with as on any such which may "
    "under from not are an it where".split())
_SCRIPTS = (("Thai", "฀", "๿"), ("Lao", "຀", "໿"), ("Cyrillic", "Ѐ", "ӿ"),
            ("Chinese", "一", "鿿"), ("Hindi", "ऀ", "ॿ"))


def economy_name(name: str) -> str:
    return UN_ECONOMY_NAMES.get((name or "").strip(), (name or "").strip())


def indicator_code(indicator_id: str) -> str:
    """'P6-I4' -> '6.4'; 'P12-I10' -> '12.10'; an RDTII code ('6.4') passes through."""
    value = str(indicator_id or "").strip()
    match = re.fullmatch(r"P(\d+)[-_ ]?I(\d+)", value, re.I)
    return f"{int(match.group(1))}.{int(match.group(2))}" if match else value


def pillar_of(code: str) -> int | None:
    match = re.match(r"(\d+)", code or "")
    return int(match.group(1)) if match else None


def source_language(snippet: str, economy: str) -> tuple[str, str]:
    """(template value for column N, exact language) from the snippet's script."""
    text = snippet or ""
    letters = [ch for ch in text if ch.isalpha()] or [" "]
    for script, lo, hi in _SCRIPTS:
        if sum(1 for ch in letters if lo <= ch <= hi) >= 0.3 * len(letters):
            if script == "Cyrillic":
                exact = {"Mongolia": "Mongolian", "Kazakhstan": "Kazakh"}.get(economy, "Russian")
            else:
                exact = script
            return (exact if exact in TEMPLATE_LANGUAGES else "Other"), exact
    tokens = re.findall(r"[A-Za-z]+", text.casefold())
    hits = sum(1 for t in tokens if t in _ENGLISH_WORDS)
    if tokens and hits >= 2 and hits >= 0.12 * len(tokens):
        return "English", "English"
    exact = LOCAL_LATIN_LANGUAGE.get(economy, "English")
    return (exact if exact in TEMPLATE_LANGUAGES else "Other"), exact


@lru_cache(maxsize=1)
def _baseline_names() -> tuple[str, ...]:
    """Every long string in ESCAP's baseline index, whitespace-normalised."""
    found: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, str):
            if len(value) > SEED_NAME_CAP:
                found.add(" ".join(value.split()))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for name in BASELINE_FILES:
        path = ENGINE_ROOT / name
        if path.is_file():
            walk(json.loads(path.read_text(encoding="utf-8")))
    return tuple(sorted(found))


def law_name(name: str) -> str:
    """Column B: the full official name. Restores names the seed files cut at 200
    characters from ESCAP's baseline, and replaces abbreviated or annotated ones."""
    value = " ".join(str(name or "").split())
    if len(value) >= SEED_NAME_CAP:
        fuller = [full for full in _baseline_names() if full.startswith(value) and len(full) > len(value)]
        if fuller:
            value = min(fuller, key=len)
    return OFFICIAL_LAW_NAMES.get(value, value)


def last_amended(value, name: str) -> str:
    """Column D: the year of the latest amendment (template rule), blank when unknown."""
    match = re.search(r"\b(\d{4})\b", str(value or ""))
    if match:
        year = int(match.group(1))
        return str(year - 543 if year > 2400 else year)   # Thai Buddhist Era
    return LAST_AMENDED_FROM_NAME.get(" ".join(str(name or "").split()), "")


_NOTE = re.compile(r"^Discovery:\s*(?P<discovery>.*?)\.\s*Modality:\s*(?P<modality>.*?);\s*exceptions:\s*(?P<exceptions>.*)$",
                   re.S)


def plain_notes(text: str) -> str:
    """Column M in plain words: why the row is NEW or KNOWN, the operative wording and
    any exception, without the engine's internal identifiers."""
    raw = " ".join(str(text or "").split())
    match = _NOTE.match(raw)
    if not match:
        return raw
    discovery, modality, exceptions = (match.group(k).strip() for k in ("discovery", "modality", "exceptions"))
    parts = []
    if discovery.startswith("instrument not in the master dataset"):
        parts.append("New instrument: not in the 2025 RDTII database for this economy.")
    elif discovery.startswith("instrument is known but"):
        parts.append("New provision: the 2025 RDTII database has this law but not this provision.")
    elif discovery.startswith("master dataset already records"):
        parts.append("Provision already in the 2025 RDTII database.")
    elif discovery:
        parts.append(discovery[0].upper() + discovery[1:] + ".")
    if modality and modality.casefold() not in ("n/a", "none"):
        parts.append(f"Operative wording: {modality}.")
    if exceptions and exceptions.casefold().rstrip(".") != "none":
        parts.append(f"Exception: {exceptions.rstrip('.;')}.")
    return " ".join(parts)


_INTERNAL_TAG = re.compile(r"\s*\[[^\]]*\b(?:workbook|batch entry|supersedes)\b[^\]]*\]", re.I)


def reviewer_text(text: str) -> str:
    """A reviewer's note or score reasoning without internal session tags."""
    return _INTERNAL_TAG.sub("", str(text or "")).strip()


def model_route(route: str) -> str:
    """'openai/gpt-5.4-nano/escalate:openai/gpt-5.4-mini+text-embedding-3-small' in words."""
    value = str(route or "").strip()
    if not value:
        return ""
    route_part, _, embeddings = value.partition("+")
    first, _, escalation = route_part.partition("/escalate:")
    strip = lambda name: name.strip().removeprefix("openai/")  # noqa: E731
    first, escalation, embeddings = strip(first), strip(escalation), strip(embeddings)
    words = [first]
    if escalation and escalation != first:
        words.append(f"escalation: {escalation}")
    if embeddings:
        words.append(f"embeddings: {embeddings}")
    return "; ".join(words)


def short_rationale(text: str) -> str:
    """Column J: at most 300 characters, cut at a word boundary."""
    value = " ".join(str(text or "").split())
    if len(value) <= RATIONALE_LIMIT:
        return value
    cut = value[: RATIONALE_LIMIT - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def rubric_questions() -> dict[str, str]:
    questions: dict[str, str] = {}
    for path in sorted(RUBRIC_DIR.glob("pillar_*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        for code, cfg in (data.get("indicators") or {}).items():
            if isinstance(cfg, dict) and cfg.get("question"):
                questions[indicator_code(code)] = str(cfg["question"]).strip()
    return questions


SCORE_STATUS = {"approved": "reviewer-approved", "overridden": "reviewer-overridden",
                "pending": "engine proposal (awaiting review)"}


def index_scores(cells: Iterable[dict]) -> dict[tuple[str, str], dict]:
    """The indicator matrix as it stands, keyed by (UN economy name, template indicator code).

    Each cell carries the engine proposal ("deterministic"), the reviewer's state and
    effective score, and the judge panel / reference score fields of the matrix API."""
    return {(economy_name(cell.get("economy", "")), indicator_code(cell.get("indicator", ""))): cell
            for cell in cells if cell.get("economy") and cell.get("indicator")}


def _cell_score(cell: dict):
    decided = cell.get("state") in ("approved", "overridden")
    return _score(cell.get("effective") if decided else cell.get("deterministic"))


def _cell_reasoning(cell: dict) -> str:
    if cell.get("state") in ("approved", "overridden"):
        return reviewer_text(cell.get("reasoning"))
    return cell.get("deterministic_reason") or ""


def _gate_summary(gates: list[dict]) -> str:
    """'9 of 9 checks passed', or which checks were left to the reviewer."""
    if not gates:
        return ""
    passed = sum(1 for g in gates if g.get("status") == "PASS")
    flagged = [GATE_LABELS.get(str(g.get("gate_id")), str(g.get("gate_id"))) for g in gates
               if g.get("status") != "PASS"]
    summary = f"{passed} of {len(gates)} checks passed"
    return summary + (f"; reviewer judged: {', '.join(flagged)}" if flagged else "")


def _score(value) -> float | str:
    try:
        return "" if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return ""


def build_rows(entries: Iterable[tuple[MappedFinding, dict | None]], *, mode: str = "hybrid",
               scores: dict[tuple[str, str], dict] | None = None) -> list[dict]:
    """One ordered row per provision, keyed by ALL_COLUMNS.

    entries pair each finding with its current review state (decision, stage
    reviewers, date, note); None falls back to a review already on the finding."""
    questions, scores = rubric_questions(), scores or {}
    keyed = []
    for finding, current_review in entries:
        data = finding.model_dump(by_alias=True, mode="json")
        economy = economy_name(data.get("Economy"))
        code = indicator_code(data.get("Indicator ID"))
        proof = data.get("citation_proof") or {}
        status_record = data.get("status_evidence_record") or {}
        review = current_review if current_review is not None else (data.get("review") or {})
        language, exact_language = source_language(data.get("Verbatim Snippet"), economy)
        rationale = " ".join(str(data.get("Mapping Rationale") or "").split())
        score = scores.get((economy, code), {})
        start, end = proof.get("source_start_char"), proof.get("source_end_char")
        alignment = proof.get("alignment_status") or ""
        if alignment and proof.get("alignment_score") is not None:
            alignment = f"{alignment} ({float(proof['alignment_score']):.2f})"
        keyed.append((finding_key(finding), {
            "Economy": economy,
            "Law Name": law_name(data.get("Law Name")),
            "Law Number / Ref": data.get("Law Number / Ref") or "",
            "Last Amended": last_amended(data.get("Last Amended"), data.get("Law Name")),
            "Indicator ID": code,
            "Article / Section": data.get("Article / Section") or "",
            "Discovery Tag": data.get("Discovery Tag") or "",
            "Location Reference": data.get("Location Reference") or "",
            "Verbatim Snippet": data.get("Verbatim Snippet") or "",
            "Mapping Rationale": short_rationale(rationale),
            "Source URL": data.get("Source URL") or "",
            "Confidence": "" if data.get("Confidence") is None else round(float(data["Confidence"]), 2),
            "Notes": plain_notes(data.get("Notes")),
            "Language of Source": language,
            PILLAR_COLUMN: pillar_of(code),
            "Indicator Question": questions.get(code, ""),
            "Source Language (exact)": exact_language,
            "Coverage": data.get("Coverage") or "",
            "Legal Status": LEGAL_STATUS.get(data.get("Status") or "", str(data.get("Status") or "").replace("_", " ")),
            "Currentness Evidence": data.get("status_evidence") or status_record.get("fact_text") or "",
            "Currentness Source URL": status_record.get("fact_url") or "",
            "Currentness Checked At": status_record.get("checked_at") or "",
            "Citation Alignment": alignment,
            "Source Page": proof.get("page_number") or "",
            "Source Character Span": f"{start}–{end}" if start is not None and end is not None else "",
            "Source Document SHA-256": proof.get("source_sha256") or "",
            "Archived Copy Accessed": data.get("access_date") or "",
            "Verification Gates": _gate_summary(proof.get("gate_results") or []),
            "Model": model_route(data.get("model_version")),
            "Engine Mode": ENGINE_MODES.get(mode, mode),
            "Review Decision": review.get("decision") or "pending",
            "Citation Reviewer": review.get("citation_reviewer_name") or review.get("reviewer_name") or "",
            "Mapping Reviewer": review.get("mapping_reviewer_name") or review.get("reviewer_name") or "",
            "Status Reviewer": review.get("status_reviewer_name") or review.get("reviewer_name") or "",
            "Reviewer Note": reviewer_text(review.get("correction_note")),
            "Indicator Score": _cell_score(score) if score else "",
            "Score Status": SCORE_STATUS.get(score.get("state"), "") if score else "",
            "Score Reasoning": _cell_reasoning(score) if score else "",
            "Score Reviewer": score.get("reviewer_name") or "",
        }))
    keyed.sort(key=lambda kr: (kr[1]["Economy"], kr[1][PILLAR_COLUMN] or 0,
                               tuple(int(p) for p in re.findall(r"\d+", kr[1]["Indicator ID"])),
                               kr[1]["Law Name"], kr[1]["Article / Section"], kr[0]))
    return [row for _, row in keyed]


SCORE_COLUMNS = ("Economy", "Indicator ID", "Pillar", "Indicator Question", "Score", "Score Status",
                 "Engine Score", "Engine Reason", "Judge Panel Scores", "Judge Agreement (alpha)",
                 "RDTII Reference Score", "Reasoning", "Reviewer", "Evidence Rows Exported")


def score_rows(scores: dict[tuple[str, str], dict], rows: list[dict]) -> list[dict]:
    """The Indicator Scores sheet: one row per matrix cell, keyed by SCORE_COLUMNS."""
    questions = rubric_questions()
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        counts[(row["Economy"], row["Indicator ID"])] = counts.get((row["Economy"], row["Indicator ID"]), 0) + 1
    out = []
    for (economy, code), cell in sorted(scores.items(), key=lambda kv: (
            kv[0][0], pillar_of(kv[0][1]) or 0, tuple(int(p) for p in re.findall(r"\d+", kv[0][1])))):
        decided = cell.get("state") in ("approved", "overridden")
        out.append({"Economy": economy, "Indicator ID": code, "Pillar": pillar_of(code),
                    "Indicator Question": questions.get(code) or cell.get("question") or "",
                    "Score": _cell_score(cell), "Score Status": SCORE_STATUS.get(cell.get("state"), ""),
                    "Engine Score": _score(cell.get("deterministic")),
                    "Engine Reason": cell.get("deterministic_reason") or "",
                    "Judge Panel Scores": cell.get("judge_scores") or "",
                    "Judge Agreement (alpha)": _score(cell.get("agreement_alpha")),
                    "RDTII Reference Score": _score(cell.get("master_gold")),
                    "Reasoning": reviewer_text(cell.get("reasoning")) if decided else "",
                    "Reviewer": (cell.get("reviewer_name") or "") if decided else "",
                    "Evidence Rows Exported": counts.get((economy, code), 0)})
    return out


# ── writers ──────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict], path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ALL_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_json(rows: list[dict], path: Path, *, manifest: dict, scores: list[dict]) -> Path:
    payload = {
        "template": "OUTPUT_TEMPLATE_FINAL_ROUND",
        "manifest": manifest,
        "columns": list(ALL_COLUMNS),
        "template_columns": list(TEMPLATE_COLUMNS),
        "column_descriptions": dict(EXTRA_COLUMNS),
        "rows": rows,
        "indicator_scores": scores,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


FIRST_DATA_ROW = 7          # ESCAP's layout once example rows 7-8 are deleted
# The template's reference, checklist, instruction and blank on-the-day sheets are
# not part of the data; only the Coverage Matrix (it counts Output Data) is kept.
KEPT_TEMPLATE_SHEETS = ("Output Data", "Coverage Matrix")
_PILLAR_FORMULA = ('=IF($E{r}="","",IFERROR(INT($E{r}),'
                   'IFERROR(VALUE(LEFT($E{r},FIND(".",$E{r})-1)),"?")))')


def write_xlsx(rows: list[dict], path: Path, *, manifest: dict, scores: list[dict],
               template: Path = TEMPLATE_PATH) -> Path:
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.cell_range import MultiCellRange

    wb = load_workbook(template)
    ws = wb["Output Data"]
    headers = [ws.cell(4, c).value for c in range(1, len(TEMPLATE_COLUMNS) + 1)]
    if tuple(headers) != TEMPLATE_COLUMNS:
        raise ValueError(f"template columns changed: {headers!r}")
    validations = list(ws.data_validations.dataValidation)
    new_rule = next((rule for _, rules in ws.conditional_formatting._cf_rules.items() for rule in rules), None)
    data_style = {c: copy(ws.cell(9, c)._style) for c in range(1, len(TEMPLATE_COLUMNS) + 1)}
    header_styles = {r: copy(ws.cell(r, len(TEMPLATE_COLUMNS))._style) for r in (3, 4, 5)}

    ws.delete_rows(7, 2)  # "Remove rows 7 and 8 before submitting."
    last = FIRST_DATA_ROW + max(len(rows), 1) - 1
    old_last = ws.max_row
    for r in range(FIRST_DATA_ROW, max(old_last, last) + 1):
        for c in range(1, len(ALL_COLUMNS) + 1):
            cell = ws.cell(r, c)
            cell.value = None
    ws.cell(6, 1).value = (f"▸ DATA ROWS — {len(rows)} provisions ({manifest.get('approved_rows', 0)} approved by "
                           f"named reviewers, {manifest.get('pending_rows', 0)} awaiting review), exported by "
                           f"ClauseChain on {manifest.get('generated_at', '')[:10]} from the "
                           f"{manifest.get('engine_mode', '')} results")

    # Extra column headers (row 3 label, row 4 name, row 5 description), styled like O.
    extra_fill = PatternFill("solid", fgColor="FF1D4ED8")
    for offset, (name, description) in enumerate(EXTRA_COLUMNS):
        col = len(TEMPLATE_COLUMNS) + 1 + offset
        for r, value in ((3, "CLAUSECHAIN"), (4, name), (5, description)):
            cell = ws.cell(r, col, value)
            cell._style = copy(header_styles[r])
            if r in (3, 4):
                cell.fill = extra_fill
        ws.column_dimensions[get_column_letter(col)].width = 44 if "Snippet" in name or "Reason" in name \
            or "Evidence" in name or "Question" in name or "Note" in name or "full" in name else 22

    pending_fill = PatternFill("solid", fgColor="FFFFF4D6")
    decision_col = ALL_COLUMNS.index("Review Decision") + 1
    for i, row in enumerate(rows):
        r = FIRST_DATA_ROW + i
        for c, column in enumerate(ALL_COLUMNS, start=1):
            cell = ws.cell(r, c)
            cell._style = copy(data_style.get(c, data_style[len(TEMPLATE_COLUMNS) - 1]))
            if column == PILLAR_COLUMN:
                cell.value = _PILLAR_FORMULA.format(r=r)
            elif column == "Indicator ID":
                cell.value, cell.number_format = str(row[column]), "@"
            else:
                value = row[column]
                cell.value = None if value == "" else value
        if row["Review Decision"] != "approved":
            ws.cell(r, decision_col).fill = pending_fill
    ws.freeze_panes = f"A{FIRST_DATA_ROW}"

    # Validations and the NEW highlight, re-anchored to the real data range.
    ws.data_validations.dataValidation = []
    for dv in validations:
        col_letter = str(dv.sqref).split(":")[0].rstrip("0123456789")
        clone = deepcopy(dv)
        clone.sqref = MultiCellRange(f"{col_letter}{FIRST_DATA_ROW}:{col_letter}{last}")
        if clone.formula1:  # the 300-character rule points at its first data cell
            clone.formula1 = re.sub(r"\b([A-O])9\b", rf"\g<1>{FIRST_DATA_ROW}", clone.formula1)
        ws.data_validations.append(clone)
    from openpyxl.formatting.formatting import ConditionalFormattingList
    ws.conditional_formatting = ConditionalFormattingList()
    if new_rule is not None:
        ws.conditional_formatting.add(f"G{FIRST_DATA_ROW}:G{last}", new_rule)

    _rebuild_coverage(wb, sorted({row["Economy"] for row in rows}), last)
    for name in [name for name in wb.sheetnames if name not in KEPT_TEMPLATE_SHEETS]:
        del wb[name]
    _scores_sheet(wb, scores, Font, PatternFill)
    wb.active = 0
    wb.save(path)
    return path


def _rebuild_coverage(wb, economies: list[str], last: int) -> None:
    """Point the Coverage Matrix at every data row; name every exported economy."""
    cm = wb["Coverage Matrix"]
    first_row, template_last = 4, 37
    names = [cm.cell(r, 1).value for r in range(first_row, template_last + 1)]
    styles = {kind: [copy(cm.cell(row, c)._style) for c in range(1, 15)]
              for kind, row in (("economy", first_row), ("total", 38), ("count", 40), ("note", 41))}
    count_label, note_text = cm.cell(40, 1).value, cm.cell(41, 1).value
    names = sorted({economy_name(n) for n in names if n} | set(economies), key=str.casefold)
    for r in range(first_row, first_row + len(names) + 8):
        for c in range(1, 15):
            cm.cell(r, c).value = None
    data = f"'Output Data'!$O${FIRST_DATA_ROW}:$O${last}", f"'Output Data'!$A${FIRST_DATA_ROW}:$A${last}"
    for i, name in enumerate(names):
        r = first_row + i
        cm.cell(r, 1, name)
        for pillar in range(1, 13):
            cm.cell(r, pillar + 1, f"=COUNTIFS({data[0]},{pillar},{data[1]},$A{r})")
        cm.cell(r, 14, f"=SUM(B{r}:M{r})")
        for c in range(1, 15):
            cm.cell(r, c)._style = copy(styles["economy"][c - 1])
    end = first_row + len(names) - 1
    total = end + 1
    cm.cell(total, 1, "Column total")
    for c in range(2, 15):
        letter = chr(64 + c)
        cm.cell(total, c, f"=SUM({letter}{first_row}:{letter}{end})")
    for c in range(1, 15):
        cm.cell(total, c)._style = copy(styles["total"][c - 1])
        cm.cell(total + 2, c)._style = copy(styles["count"][c - 1])
        cm.cell(total + 3, c)._style = copy(styles["note"][c - 1])
    cm.cell(total + 2, 1, count_label)
    cm.cell(total + 2, 4, f"=SUMPRODUCT(--(N{first_row}:N{end}>0))")
    cm.cell(total + 3, 1, note_text)


def _header(ws, row: int, values: list[str], Font, PatternFill) -> None:
    for c, value in enumerate(values, start=1):
        cell = ws.cell(row, c, value)
        cell.font = Font(bold=True, color="FFFFFFFF")
        cell.fill = PatternFill("solid", fgColor="FF166534")


def _scores_sheet(wb, scores: list[dict], Font, PatternFill) -> None:
    ws = wb.create_sheet("Indicator Scores")
    ws.cell(1, 1, "RDTII 2.1 indicator scores").font = Font(bold=True, size=14)
    ws.cell(2, 1, "Score = the named reviewer's decision (reviewer-overridden: the reviewer changed the engine's "
                  "proposal and gave the reason), or the engine's proposal while it awaits review. The engine score, "
                  "an independent three-judge panel and ESCAP's published RDTII score are shown beside it.")
    _header(ws, 4, list(SCORE_COLUMNS), Font, PatternFill)
    for i, row in enumerate(scores, start=5):
        for c, column in enumerate(SCORE_COLUMNS, start=1):
            value = row.get(column)
            ws.cell(i, c, None if value == "" else value)
        ws.cell(i, 2).number_format = "@"
    for letter, width in zip("ABCDEFGHIJKLMN", (22, 11, 8, 50, 9, 22, 9, 40, 30, 11, 11, 70, 22, 11)):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A5"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


FORMATS = ("xlsx", "csv", "json")
EXPORT_RULE = ("Every provision a named reviewer approved at the citation, mapping and status stages, plus every "
               "provision still awaiting review (marked pending). Rejected findings and no-evidence placeholders "
               "are left out.")


def export_final_round(entries: list[tuple[MappedFinding, dict | None]], out_dir: Path, *, mode: str = "hybrid",
                       score_cells: Iterable[dict] = (), source: dict | None = None,
                       excluded: dict | None = None, formats: Iterable[str] = FORMATS) -> dict:
    """Write OUTPUT_FINAL_ROUND.<format> for each requested format into out_dir; return the manifest."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    score_map = index_scores(score_cells)
    rows = build_rows(entries, mode=mode, scores=score_map)
    scores = score_rows(score_map, rows)
    source, excluded = source or {}, excluded or {}
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "ClauseChain",
        "template": "OUTPUT_TEMPLATE_FINAL_ROUND (ESCAP, final round)",
        "engine_mode": ENGINE_MODES.get(mode, mode),
        "source_snapshot": source.get("id"),
        "source_snapshot_created_at": source.get("created_at"),
        "source_sha256": source.get("source_hash"),
        "rows": len(rows),
        "approved_rows": sum(1 for r in rows if r["Review Decision"] == "approved"),
        "pending_rows": sum(1 for r in rows if r["Review Decision"] != "approved"),
        "excluded_rejected": int(excluded.get("rejected", 0)),
        "excluded_no_evidence_placeholders": int(excluded.get("absence", 0)),
        "economies": sorted({r["Economy"] for r in rows}),
        "pillars": sorted({r[PILLAR_COLUMN] for r in rows if r[PILLAR_COLUMN]}),
        "indicators": len({(r["Economy"], r["Indicator ID"]) for r in rows}),
        "new_rows": sum(1 for r in rows if r["Discovery Tag"] == "NEW"),
        "indicator_scores": len(scores),
        "indicator_scores_decided": sum(1 for s in scores if s["Score Status"].startswith("reviewer")),
        "rule": EXPORT_RULE,
    }
    writers = {"csv": lambda path: write_csv(rows, path),
               "json": lambda path: write_json(rows, path, manifest=dict(manifest), scores=scores),
               "xlsx": lambda path: write_xlsx(rows, path, manifest=manifest, scores=scores)}
    for fmt in formats:
        manifest[f"{fmt}_sha256"] = sha256_file(writers[fmt](out / f"{FILE_STEM}.{fmt}"))
    return manifest
