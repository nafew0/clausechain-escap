"""ESCAP master (gold) audit for one economy: nothing missed, errors caught.

Generalises scripts/my_error_audit.py to every economy with a jurisdiction pack.
For each master row (default: Pillars 6-7) it records whether the corpus can
reproduce it and whether the row itself looks wrong:

  C1-instrument-not-in-corpus   a cited law resolves to no corpus instrument
  C2-article-not-found          a cited article resolves to no provision of that law
  F-not-in-force                the cited law is superseded/repealed/not yet effective
  D-bill-as-measure             a Bill/draft cited as a measure
  G-identity-mismatch           year or registration number differs from the official text
  J-amending-law-citation       an amending law cited instead of the consolidated act (info)
  B-non-official-source         References cite a non-official domain
  A-dead-link                   References URL not reachable (skip with --no-fetch)
  H-score-divergence            master score differs from the research conclusion (panel)
  I-claim-check                 (--verify-claims) the cited official text does not support
                                the master's statement, per the hybrid legal model
  K-gold-not-reproduced         (--run DIR) a run did not reproduce a master anchor
  OK-covered                    one line per row whose instruments and articles all resolve

Output: data/audit/gold_audit_<cc>.csv (+ _claims.json cache). Findings are
machine-detected leads; Legal confirms before any master row is changed.

Usage: .venv/bin/python scripts/gold_audit.py --economy "Lao PDR" [--no-fetch]
          [--verify-claims [--refresh-claims]] [--run outputs/final_r2_la_p6 ...] [--pillars 6,7]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

import httpx  # noqa: E402
import yaml  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from packages.discovery.diff import KnownIndex, laws_match, section_base  # noqa: E402

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ClauseChain-research/0.1")}
# Whole parts, so an operative item deep in a long part (149-FZ Art. 10.4(1) item 10
# sits at ~4,600 chars) is never truncated away from the judge.
UNIT_CHARS = 6000
FIELDS = ["economy", "pillar", "indicator", "score", "act", "check", "verdict", "evidence",
          "suggested_correction"]
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
NUMBER = re.compile(r"\bno\.?\s*([0-9]+)", re.I)


def load_pack(economy: str) -> tuple[str, dict]:
    for path in sorted(Path("configs/jurisdictions").glob("*.yaml")):
        pack = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if pack.get("name") == economy:
            return path.stem, pack
    raise SystemExit(f"No jurisdiction pack named {economy!r}")


def load_corpus(economy: str) -> list[dict]:
    import sqlite3
    import os

    db = sqlite3.connect(os.getenv("GRAPH_DB_PATH") or "data/graph_v2.db")
    rows = db.execute("SELECT props FROM nodes WHERE label='Provision' "
                      "AND json_extract(props,'$.economy')=?", (economy,)).fetchall()
    return [json.loads(props) for (props,) in rows]


def _tokens(value: str) -> set[str]:
    return {w for w in re.sub(r"[^\w]", " ", value.lower()).split()
            if len(w) > 2 and w not in {"the", "act", "notification", "b", "e"}}


def seed_status(pack: dict, seeds: list[dict]) -> dict[str, str]:
    """Pack status per seeded instrument (the builder's own assertion rule)."""
    assertions = pack.get("status_assertions") or {}
    statuses: dict[str, str] = {}
    for act in {row["act"] for row in seeds}:
        best, overlap = None, 0.0
        act_tokens, act_years = _tokens(act), set(YEAR.findall(act))
        for key, value in assertions.items():
            key_tokens, key_years = _tokens(key), set(YEAR.findall(key))
            if not key_tokens or (act_years and key_years and not act_years & key_years):
                continue
            share = len(key_tokens & act_tokens) / len(key_tokens)
            if share > overlap and share >= 0.6:
                best, overlap = value, share
        statuses[act] = (best or {}).get("status", "unknown")
    return statuses


def official_domains(pack: dict, economy: str) -> set[str]:
    domains = {s["domain"].lower() for s in pack.get("official_sources", [])}
    mined = Path(pack.get("whitelist_source") or "data/official_domains.json")
    if mined.is_file():
        block = json.loads(mined.read_text()).get("economies", {}).get(economy, {})
        domains |= {d.lower() for d in block.get("official_whitelist", {})}
    return {d.removeprefix("www.") for d in domains}


def is_official(url: str, domains: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in domains)


class ClaimVerdict(BaseModel):
    supports_claim: str          # yes | partly | no
    citation_matches: str        # yes | no | unclear — is this the provision the row cites?
    score_consistent: str        # yes | no | unclear
    issue: str                   # none | wrong_article | claim_not_in_text | score_inconsistent | other
    explanation: str


def _label_key(unit: dict) -> list:
    return [int(n) if n.isdigit() else n
            for n in re.findall(r"\d+|[^\d\s().,]+", unit.get("article_section", ""))]


def claim_units(per_ref: list[list[dict]], per_ref_chars: int = 9000,
                total_chars: int = 24000) -> list[dict]:
    """The official text a cited ref denotes, in legal order: the precise part when
    the master cites one, otherwise the article's parts from the first (operative)
    part on. Heading-only units are dropped when parts exist. Budgeted per ref."""
    chosen: list[dict] = []
    used = 0
    for matched in per_ref:
        ordered = sorted({u["id"]: u for u in matched}.values(), key=_label_key)
        with_parts = [u for u in ordered if "(" in u.get("article_section", "")]
        ordered = with_parts or ordered
        budget = per_ref_chars
        for unit in ordered:
            size = min(len(unit.get("text") or ""), UNIT_CHARS)
            if budget - size < 0 or used + size > total_chars:
                break
            chosen.append(unit)
            budget -= size
            used += size
    return chosen


def claim_prompt(row: dict, indicator: dict, units: list[dict]) -> str:
    provisions = "\n\n".join(
        f"[{u.get('law_name')} — {u.get('article_section')}]\n{(u.get('text') or '')[:UNIT_CHARS]}"
        for u in units)
    return f"""You audit the UN ESCAP RDTII master dataset (the "gold") against the official legal text.

Indicator {row['indicator_code']} — {indicator.get('name', '')}
Question: {indicator.get('question', '')}
Scoring: {json.dumps(indicator.get('scoring', {}), ensure_ascii=False)}
Exclusions: {json.dumps(indicator.get('exclusions', []), ensure_ascii=False)[:800]}

Gold row: score {row.get('score')}; cites {row.get('articles')} of: {row.get('act', '')[:300]}
Gold statement: {(row.get('impact') or '')[:1500]}

Official text of the cited provision(s) as archived by ClauseChain (may be in the original language):
{provisions}

Decide strictly from the official text:
- supports_claim: does the text support what the gold statement says about this indicator? yes | partly | no
- citation_matches: is this plausibly the provision the gold cites (right article/part)? yes | no | unclear
- score_consistent: is the gold score consistent with the scoring rule given this text? yes | no | unclear
- issue: none | wrong_article | claim_not_in_text | score_inconsistent | other
- explanation: at most 60 words, cite the operative words.
Return JSON with exactly these keys."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--economy", required=True)
    parser.add_argument("--pillars", default="6,7")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--verify-claims", action="store_true")
    parser.add_argument("--refresh-claims", action="store_true",
                        help="ignore cached claim verdicts and re-ask the model")
    parser.add_argument("--run", action="append", default=[],
                        help="run output dir(s) whose reproduction of the gold to check")
    args = parser.parse_args()

    economy = args.economy
    cc, pack = load_pack(economy)
    pillars = {p.strip() for p in args.pillars.split(",")}
    index_path = pack.get("known_index") or "data/known_index.json"
    master = [r for r in json.loads(Path(index_path).read_text())["economies"].get(economy, [])
              if str(r.get("pillar")) in pillars]
    known = KnownIndex(index_path)
    corpus = load_corpus(economy)
    known.register_corpus(economy, corpus)
    laws = sorted({p.get("law_name", "") for p in corpus})
    seeds = json.loads(Path(pack.get("seeds") or "data/seeds.json").read_text())["economies"].get(economy, [])
    statuses = seed_status(pack, seeds)
    domains = official_domains(pack, economy)
    research = pack.get("research_scores") or {}
    rubric = {}
    for pillar in pillars:
        path = Path(f"configs/rdtii/pillar_{pillar}.yaml")
        if path.is_file():
            rubric.update(yaml.safe_load(path.read_text()).get("indicators", {}))

    findings: list[dict] = []

    def add(row: dict, check: str, verdict: str, evidence: str, correction: str = "") -> None:
        findings.append({"economy": economy, "pillar": row.get("pillar"),
                         "indicator": row.get("indicator_code"), "score": row.get("score"),
                         "act": " | ".join(row.get("acts_norm", []))[:160],
                         "check": check, "verdict": verdict, "evidence": evidence[:400],
                         "suggested_correction": correction[:300]})

    if not master:
        print(f"{economy}: no master rows for pillars {sorted(pillars)} in {index_path} — "
              "every finding is NEW; nothing to audit.")

    claim_cache_path = Path(f"data/audit/gold_audit_{cc}_claims.json")
    claim_cache = (json.loads(claim_cache_path.read_text())
                   if claim_cache_path.is_file() and not args.refresh_claims else {})
    llm = None
    checked_urls: dict[str, str] = {}
    client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=45, verify=False)
    for row in master:
        acts = [a for a in row.get("acts_norm", []) if a]
        row_ok = True
        resolved: dict[str, str] = {}
        for act in acts:
            if re.search(r"\b(bill|draft)\b", act):
                add(row, "D-bill-as-measure", "ERROR", f"'{act}' is a bill/draft",
                    "Cite the enacted instrument or remove the row")
                row_ok = False
            alias = known._resolve_alias(economy, act)
            hits = [law for law in laws if laws_match(alias, law)]
            if "amendment" in act or "amending" in act:
                if hits:
                    add(row, "J-amending-law-citation", "INFO",
                        f"'{act[:90]}' is an amending law; its text is read in {hits[0][:80]}",
                        "Cite the consolidated principal act and article the amendment inserted")
            if not hits:
                seeded = [s for s in statuses if laws_match(alias, s)]
                status = next((statuses[s] for s in seeded if statuses[s] != "in_force"), None)
                if status:
                    add(row, "F-not-in-force", "ERROR",
                        f"'{act[:90]}' is {status} per the pack status evidence",
                        "Replace with the current instrument (see the pack status_assertions)")
                else:
                    add(row, "C1-instrument-not-in-corpus", "ERROR",
                        f"'{act[:90]}' matches no corpus instrument ({len(laws)} loaded)",
                        "Seed the official text, alias the name in the pack, or confirm the instrument "
                        "does not exist")
                row_ok = False
                continue
            resolved[act] = hits[0]
            if len(hits) > 1:
                add(row, "C1-ambiguous-match", "WARN", f"'{act[:70]}' matches {len(hits)} "
                    f"instruments: {'; '.join(h[:50] for h in hits[:3])}",
                    "Disambiguate with a pack gold_alias")
            if "amendment" not in act and "amending" not in act:
                ours = hits[0]
                gy, oy = set(YEAR.findall(act)), set(YEAR.findall(ours))
                gn, on = set(NUMBER.findall(act)), set(NUMBER.findall(ours))
                if gy and oy and not gy & oy:
                    add(row, "G-identity-mismatch", "WARN",
                        f"year {sorted(gy)} in master vs {sorted(oy)} in the official title '{ours[:70]}'",
                        "Correct the year in the Act column")
                if gn and on and not gn & on:
                    add(row, "G-identity-mismatch", "WARN",
                        f"number {sorted(gn)} in master vs {sorted(on)} in the official title '{ours[:70]}'",
                        "Correct the instrument number in the Act column")
        # Articles: every cited ref must resolve to a provision of a resolved law.
        cited_units: list[dict] = []
        per_ref: list[list[dict]] = []
        for ref in row.get("articles", []):
            base = section_base(ref)
            if not base or not resolved:
                continue
            matched = []
            for act, law in resolved.items():
                gold_ref = known.translate_ref(economy, [act], ref)
                matched += [p for p in corpus if p.get("law_name") == law
                            and known.gold_ref_matches(economy, law, gold_ref,
                                                       p.get("article_section", ""))]
            if matched:
                cited_units += matched
                per_ref.append(matched)
            else:
                add(row, "C2-article-not-found", "WARN",
                    f"{ref} resolves to no provision of {', '.join(v[:50] for v in resolved.values())}",
                    "Verify the article number against the current official text")
                row_ok = False
        # References.
        for ref_text in row.get("references", []):
            for url in re.findall(r"https?://[^\s;,]+", ref_text):
                url = url.rstrip(").")
                if not is_official(url, domains):
                    inner = re.search(r"web\.archive\.org/web/\d+[a-z_]*/(https?://.+)", url)
                    archived = bool(inner and is_official(inner.group(1), domains))
                    official = [s["url"] for s in seeds
                                if any(laws_match(s["act"], law) for law in resolved.values())
                                and is_official(s["url"], domains)]
                    add(row, "B-non-official-source", "WARN" if archived else "ERROR",
                        f"References cite {urlparse(url).hostname}"
                        f"{' (archive of an official page)' if archived else ' (not an official portal)'}",
                        f"Cite {official[0]}" if official else
                        "Cite the official portal URL (see the pack official_sources)")
                if not args.no_fetch and url not in checked_urls:
                    time.sleep(0.5)
                    try:
                        checked_urls[url] = str(client.get(url).status_code)
                    except httpx.HTTPError as error:
                        checked_urls[url] = f"unreachable ({type(error).__name__})"
                status = checked_urls.get(url)
                if status and status != "200":
                    add(row, "A-dead-link", "ERROR", f"{url[:110]} -> {status}",
                        "Replace with a live official link")
        # Claim check against the official text.
        if args.verify_claims and cited_units:
            units = claim_units(per_ref)
            key = hashlib.sha256(json.dumps([row.get("act"), row.get("indicator_code"),
                                             row.get("score"), row.get("articles"),
                                             [u.get("id") for u in units]],
                                            ensure_ascii=False).encode()).hexdigest()[:16]
            if key not in claim_cache:
                if llm is None:
                    from packages.providers.model_router import resolve_llm
                    llm = resolve_llm("hybrid_accuracy", tier="high_reasoning")
                verdict = llm.complete(claim_prompt(row, rubric.get(row["indicator_code"], {}),
                                                    units), ClaimVerdict)
                claim_cache[key] = verdict.model_dump()
                claim_cache_path.parent.mkdir(parents=True, exist_ok=True)
                claim_cache_path.write_text(json.dumps(claim_cache, indent=1, ensure_ascii=False))
            verdict = claim_cache[key]
            if verdict["issue"] != "none" or verdict["supports_claim"] == "no":
                add(row, "I-claim-check", "ERROR" if verdict["supports_claim"] == "no" else "WARN",
                    f"supports={verdict['supports_claim']} citation={verdict['citation_matches']} "
                    f"score_consistent={verdict['score_consistent']}: {verdict['explanation']}",
                    "Legal to re-read the cited provision and correct the row")
        if row_ok:
            refs = ", ".join(row.get("articles", [])) or "no article cited"
            add(row, "OK-covered", "OK",
                f"{'; '.join(v[:60] for v in resolved.values())} [{refs}]")

    # Indicator scores: master (max over rows) vs research conclusion.
    master_scores: dict[str, float] = {}
    for row in master:
        try:
            score = float(str(row.get("score", "")).strip())
        except ValueError:
            continue
        code = row.get("indicator_code", "")
        master_scores[code] = max(master_scores.get(code, 0.0), score)
    for code, research_score in sorted(research.items()):
        if code in master_scores and float(research_score) != master_scores[code]:
            add({"pillar": code[1], "indicator_code": code, "score": master_scores[code],
                 "acts_norm": []}, "H-score-divergence", "INFO",
                f"master {master_scores[code]} vs research {research_score}",
                "Zone-3 panel decides; the research conclusion is in the pack notes")

    # Run reproduction: every cited master anchor should come back KNOWN.
    for run_dir in args.run:
        output = json.loads((Path(run_dir) / "output.json").read_text())
        pillar = str(output.get("pillar"))
        found = [(f.get("Law Name") or f.get("law_name", ""),
                  f.get("Article / Section") or f.get("article_section", ""),
                  f.get("Indicator ID") or f.get("indicator_id", ""),
                  f.get("Discovery Tag") or f.get("discovery_tag", ""))
                 for f in output.get("findings", [])]
        for row in master:
            if str(row.get("pillar")) != pillar or not row.get("articles"):
                continue
            for ref in row["articles"]:
                hit = any(indicator == row["indicator_code"] and tag == "KNOWN"
                          and any(laws_match(known._resolve_alias(economy, a), law)
                                  and known.gold_ref_matches(
                                      economy, law, known.translate_ref(economy, [a], ref), section)
                                  for a in row.get("acts_norm", []))
                          for law, section, indicator, tag in found)
                if not hit:
                    add(row, "K-gold-not-reproduced", "WARN",
                        f"{run_dir}: no KNOWN {row['indicator_code']} finding for {ref}",
                        "Check the run's RECALL HOLE warnings and the recall queue")

    out = Path(f"data/audit/gold_audit_{cc}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(findings)
    counts = Counter((f["verdict"], f["check"]) for f in findings)
    covered = sum(1 for f in findings if f["check"] == "OK-covered")
    print(f"{economy}: {len(master)} master rows (P{','.join(sorted(pillars))}), "
          f"{covered} fully covered -> {out}")
    for (verdict, check), count in sorted(counts.items()):
        print(f"  {verdict:5s} {check:28s} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
