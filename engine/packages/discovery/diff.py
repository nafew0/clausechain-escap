"""NEW/KNOWN discovery diff vs the ESCAP master dataset (the 20-point lever).

Rules (10-Jun mail + 15-Jun Q&A, official):
- Baseline = the master DB (data/known_index.json, built from its Impact column).
- Granularity = (instrument + article). A new provision inside an already-recorded
  law is NEW; ESCAP's own refs are section-level ("s. 26"), so we compare at
  BASE-SECTION level: our "s. 26(1)" matches their "s. 26" -> KNOWN;
  our "s. 48E(3)" with no recorded s. 48E -> NEW.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_SECTION_BASE = re.compile(r"(\d+(?:\.\d+){0,2}[A-Z]*)", re.I)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize_law(name: str) -> str:
    name = _NON_ALNUM.sub(" ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def section_base(article_section: str) -> str | None:
    """'s. 26(1)' -> '26'; 'Art. 12(2)' -> '12'; 's. 48E(3)' -> '48E';
    's. 474.17A(1)' -> '474.17A'; 'Sch 1, cl. 8(1)' -> 'sch1cl8'.

    Year-like refs ("reg. 2021") are Impact-prose parse artifacts, not sections."""
    ref = article_section or ""
    # Schedule refs get their own base space — clause numbering restarts per
    # Schedule, so "Sch 1, cl. 5" must never equal body "s. 5". A bare "Sch. 2"
    # (whole-schedule gold ref) -> "sch2"; anchor matching treats it as a prefix.
    sch = re.search(r"\bSch(?:edule)?\.?\s+(\d+[A-Z]*)", ref, re.I)
    if sch:
        cl = re.search(r"\bcl\.?\s+(\d+[A-Z]*)", ref, re.I)
        return f"sch{sch.group(1)}" + (f"cl{cl.group(1)}" if cl else "")
    match = _SECTION_BASE.search(ref)
    if not match:
        return None
    base = match.group(1).upper()
    if base.isdigit() and int(base) >= 1000:  # a year, not a section number
        return None
    return base


def section_matches(gold_base: str | None, candidate_base: str | None) -> bool:
    """Exact statute match, plus parent→child matching for official code clauses."""
    if not gold_base or not candidate_base:
        return False
    if gold_base.startswith("sch"):
        return candidate_base == gold_base or (
            "cl" not in gold_base and candidate_base.startswith(f"{gold_base}cl"))
    return candidate_base == gold_base or candidate_base.startswith(f"{gold_base}.")


_STOP_TOKENS = {"act", "acts", "the", "of", "and", "a", "an", "no", "pu"}


def law_tokens(name: str) -> set[str]:
    """Significant tokens of a law name — robust to '(Act 709)' insertions,
    reorderings, and filler words. 'Personal Data Protection Act (Act 709) 2010'
    and 'personal data protection act 2010' both -> {personal,data,protection,2010,709…}."""
    return {t for t in normalize_law(name).split() if t not in _STOP_TOKENS}


# Registration numbers that ARE a law's identity: Russian "152-FZ", Lao "25/NA",
# "225/GOL", "3643/MTC". Two names carrying different such numbers are different
# instruments even when their titles overlap ("152-FZ On Personal Data" vs
# "572-FZ On ... Biometric Personal Data").
_REGISTRATION_NUMBER = re.compile(
    r"\b(\d+(?:-\d+)?)\s*(?:-\s*)?(fz|фз)\b|\b(\d+)\s*/?\s*(na|gol|govt|mtc|mpt|ທຫລ)\b", re.I)


def registration_numbers(name: str) -> set[str]:
    numbers: set[str] = set()
    for fz_no, fz, reg_no, reg in _REGISTRATION_NUMBER.findall(name or ""):
        numbers.add(f"{fz_no}-fz" if fz else f"{reg_no}/{reg.lower()}")
    return numbers


def laws_match(gold_act_norm: str, law_name: str) -> bool:
    gold, ours = law_tokens(gold_act_norm), law_tokens(law_name)
    if not gold or not ours:
        return False
    gold_numbers, our_numbers = registration_numbers(gold_act_norm), registration_numbers(law_name)
    if gold_numbers and our_numbers and not gold_numbers & our_numbers:
        return False
    if gold <= ours or ours <= gold:
        return True
    # Master cells often bind a principal Act and its enacted amendment in one
    # display value.  Compilation years and amendment numbers must not make the
    # same Act family look like two unrelated instruments.  Eligibility still
    # rejects Bills separately; this matcher only resolves legal identity.
    def family(tokens: set[str]) -> set[str]:
        return {token for token in tokens
                if token not in {"amendment", "amending"}
                and not re.fullmatch(r"(?:\d+|[a-z]\d+)", token)}

    gold_family, our_family = family(gold), family(ours)
    return (len(gold_family) >= 3 and len(our_family) >= 3
            and (gold_family <= our_family or our_family <= gold_family))


_FIRST_PART = re.compile(r"\(([^)]+)\)")


class KnownIndex:
    def __init__(self, path: str | Path = "data/known_index.json") -> None:
        data = json.loads(Path(path).read_text())
        self._by_economy: dict[str, list[dict]] = data.get("economies", {})
        self._aliases: dict[str, dict[str, str]] = {}
        # Economies whose master writes an article's parts as decimals (RU "Art. 12.7"
        # = part 7 of Art. 12; MN "Art. 14.1" = para 1 of Art. 14). Declared per pack
        # (gold_ref_style: decimal_parts); every other economy keeps exact matching.
        self._decimal_parts: set[str] = set()
        # Master rows citing an amending law's item ("208-FZ Art. 1.10") mapped to the
        # consolidated article it inserted (pack gold_ref_crosswalk).
        self._crosswalk: dict[str, dict[str, dict[str, str]]] = {}
        self._articles: dict[str, dict[str, set[str]]] = {}
        try:
            import yaml as _yaml
            base = Path(path).resolve().parents[1] / "configs" / "jurisdictions"
            for f in sorted(base.glob("*.yaml")):
                pack = _yaml.safe_load(f.read_text()) or {}
                econ = pack.get("name")
                if not econ:
                    continue
                if pack.get("gold_aliases"):
                    self._aliases[econ] = {normalize_law(k): v
                                           for k, v in pack["gold_aliases"].items()}
                if pack.get("gold_ref_style") == "decimal_parts":
                    self._decimal_parts.add(econ)
                if pack.get("gold_ref_crosswalk"):
                    self._crosswalk[econ] = {normalize_law(k): dict(v)
                                             for k, v in pack["gold_ref_crosswalk"].items()}
        except Exception:
            pass

    def _resolve_alias(self, economy: str, act_norm: str) -> str:
        return self._aliases.get(economy, {}).get(normalize_law(act_norm), act_norm)

    def translate_ref(self, economy: str, acts: list[str], ref: str) -> str:
        """A master ref under an amending law -> the consolidated article (crosswalk)."""
        table = self._crosswalk.get(economy)
        if table:
            for act in acts:
                mapped = table.get(normalize_law(act or ""), {}).get(ref)
                if mapped:
                    return mapped
        return ref

    def register_corpus(self, economy: str, provisions: list[dict]) -> None:
        """Article labels per law, so a decimal master ref can be read as either an
        inserted article (RU 22.1 = Art. 22¹) or an article's part (RU 12.7)."""
        labels: dict[str, set[str]] = {}
        for props in provisions:
            base = section_base(props.get("article_section", "") or "")
            if base:
                labels.setdefault(props.get("law_name", ""), set()).add(base)
        self._articles[economy] = labels

    def gold_ref_matches(self, economy: str, law_name: str, gold_ref: str,
                         article_section: str) -> bool:
        """Does the master's ref denote this provision? Exact/parent->child for every
        economy; decimal-parts economies first try the ref as an article label, then
        as article + part (the longest existing article prefix)."""
        gold, candidate = section_base(gold_ref), section_base(article_section)
        if economy not in self._decimal_parts:
            return section_matches(gold, candidate)
        if not gold or not candidate:
            return False
        labels = self._articles.get(economy, {}).get(law_name)
        if not labels:
            return section_matches(gold, candidate)
        if gold in labels:
            return candidate == gold
        if section_matches(gold, candidate):
            return True  # a chapter/clause parent ("3" -> clause "3.2")
        parts = gold.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            article = ".".join(parts[:cut])
            if article in labels:
                if candidate != article:
                    return False
                found = _FIRST_PART.search(article_section)
                return found is None or found.group(1) == parts[cut]
        return False

    def _known_refs(self, economy: str, law_name: str) -> list[str] | None:
        """Refs ESCAP recorded for this law (crosswalked), or None if the law is unknown."""
        refs: list[str] = []
        law_known = False
        for row in self._by_economy.get(economy, []):
            for act in row.get("acts_norm", []):
                resolved = self._resolve_alias(economy, act) if act else act
                if resolved and laws_match(resolved, law_name):
                    law_known = True
                    refs.extend(self.translate_ref(economy, [act], ref)
                                for ref in row.get("articles", []))
        return refs if law_known else None

    def known_sections(self, economy: str, law_name: str) -> set[str] | None:
        """Base sections ESCAP recorded for this law, or None if the law itself is unknown."""
        refs = self._known_refs(economy, law_name)
        if refs is None:
            return None
        return {base for ref in refs if (base := section_base(ref))}

    def tag(self, economy: str, law_name: str, article_section: str) -> tuple[str, str]:
        """Returns (tag, why). Provision-level: known law + unrecorded section = NEW."""
        refs = self._known_refs(economy, law_name)
        base = section_base(article_section)
        if refs is None:
            return "NEW", f"instrument not in the master dataset for {economy}"
        sections = {known for ref in refs if (known := section_base(ref))}
        if base and any(self.gold_ref_matches(economy, law_name, ref, article_section)
                        for ref in refs):
            return "KNOWN", f"master dataset already records s. {base} of this law"
        return "NEW", (
            f"instrument is known but s. {base} is not among its recorded provisions "
            f"({sorted(sections) or 'none recorded'})"
        )
