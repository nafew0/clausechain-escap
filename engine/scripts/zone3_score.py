"""Zone-3 scoring as a NOISE AUDIT (P3-E; 12-Jun method + DoDont §9.1).

Two layers, kept separate (never collapse evidence into scores early):
  1. DETERMINISTIC score from the gated evidence rows (official 0/0.5/1 criteria:
     polarity, court-order test, coverage tiers) — code, not LLM.
  2. NOISE AUDIT: N persona LLM judges score independently -> distribution,
     spread band, Krippendorff's alpha across all indicators -> uncertainty.
Output = SUGGESTIONS ONLY (reviewer_decision: pending); the user approves each.

Usage: .venv/bin/python scripts/zone3_score.py outputs/p1_sg_p6_v4 outputs/p1_sg_p7_v2 [...]
Writes data/zone3/<economy>_p<pillar>_scores.json per run dir.
"""
from __future__ import annotations

import csv
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

import yaml  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

PERSONAS = [
    "a strict textualist trade lawyer who only accepts what the quoted text plainly states",
    "an ESCAP data-collection consultant applying the RDTII 2.1 guide criteria literally",
    "a skeptical peer reviewer looking for reasons the score should be LOWER",
]


class JudgeScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)   # 0 / 0.5 / 1
    reason: str = ""


def evidence_rows(run_dir: Path) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for r in csv.DictReader((run_dir / "output.csv").open(encoding="utf-8")):
        rows.setdefault(r["Indicator ID"], []).append(r)
    return rows


def master_gold_scores(economy: str) -> dict[str, float]:
    """ESCAP's own recorded score per indicator (the answer key for our 3 economies).
    Generic: read from known_index, never hardcoded. Used as a TRIPWIRE — any
    det-vs-gold divergence auto-flags for human adjudication (19 Jul rule after
    13 silent mismatches passed the persona panel unanimously)."""
    import json as _json
    from pathlib import Path as _P

    gold: dict[str, float] = {}
    idx = _json.loads(_P("data/known_index.json").read_text())["economies"]
    for e in idx.get(economy, []):
        code = str(e.get("indicator_code") or "")
        if e.get("source") == "master" and code and code not in gold:
            try:
                gold[code] = float(str(e.get("score", "")).strip())
            except (TypeError, ValueError):
                continue
    return gold


def deterministic_score(indicator_id: str, rows: list[dict]) -> tuple[float, str]:
    """Official 0/0.5/1 criteria over the evidence rows (DoDont §9.1)."""
    real = [r for r in rows if r["Article / Section"] not in ("n/a", "")]
    horizontal = any(r.get("Coverage", "").startswith("Horizontal") for r in real)
    if indicator_id in ("P6-I1", "P6-I2", "P6-I4"):
        if not real:
            return 0.0, "no qualifying measure found (absence row) -> 0"
        return (1.0, "covers personal data / horizontal -> 1") if horizontal else \
               (0.5, "sectoral/specific-data measure(s) only -> 0.5")
    if indicator_id == "P6-I3":
        return (1.0, "infrastructure requirement exists") if real else (0.0, "none found")
    if indicator_id == "P6-I5":
        # Inverse polarity: qualifying binding-agreement evidence means the
        # claim that the economy joined no such agreement is false.
        return ((0.0, "binding cross-border data-transfer agreement evidenced") if real else
                (1.0, "no qualifying binding data-transfer agreement found"))
    if indicator_id == "P7-I1":
        if not real:
            return 1.0, "no DP framework evidence found -> lacks framework -> 1"
        return (0.0, "comprehensive horizontal framework evidenced -> 0") if horizontal else \
               (0.5, "sectoral-only DP evidence -> 0.5")
    if indicator_id == "P7-I2":
        if not real:
            return 1.0, "no cybersecurity framework evidence -> 1"
        return (0.0, "dedicated horizontal framework evidenced -> 0") if horizontal else \
               (0.5, "sectoral-only / non-dedicated -> 0.5")
    if indicator_id == "P7-I3":
        return (1.0, "minimum retention period(s) evidenced") if real else (0.0, "none")
    if indicator_id == "P7-I4":
        if not real:
            return 0.0, "no DPO/DPIA requirement found"
        return (1.0, "all-sectors DPO/DPIA evidenced") if horizontal else (0.5, "sector-specific only")
    if indicator_id == "P7-I5":
        court_gated_only = real and all("COURT-GATED" in (r.get("Notes", "") + str(r)) for r in real)
        if not real:
            return 0.0, "no government-access measure found"
        return (0.0, "all access powers appear court-gated (7.5 court-order test) -> 0") if court_gated_only \
            else (1.0, "warrantless government access evidenced -> 1")
    return 0.0, "unknown indicator"


def persona_scores(llm, indicator_id: str, cfg: dict, rows: list[dict]) -> list[dict]:
    evidence = "\n".join(
        f"- {r['Law Name']} {r['Article / Section']} ({r.get('Coverage','')}): {r['Verbatim Snippet'][:200]}"
        for r in rows[:6]) or "- (no qualifying provisions found)"
    scoring = "\n".join(f"  score {k}: {v}" for k, v in (cfg.get("scoring") or {}).items())
    out = []
    for persona in PERSONAS:
        prompt = f"""You are {persona}.

Score RDTII indicator {indicator_id} ({cfg.get('name','')}) for this economy on the official scale:
{scoring}

EVIDENCE (gate-verified rows):
{evidence}

Return score (exactly 0, 0.5 or 1) and a one-sentence reason. Judge independently."""
        try:
            result = llm.complete(prompt, JudgeScore)
            out.append({"persona": persona.split()[1], "score": result.score, "reason": result.reason[:160]})
        except Exception as error:  # noqa: BLE001
            out.append({"persona": persona.split()[1], "score": None, "error": str(error)[:80]})
    return out


def krippendorff_alpha(matrix: list[list[float]]) -> float | None:
    """Nominal-metric alpha; units = indicators, raters = personas."""
    pairs_agree, pairs_total = 0, 0
    values = [v for row in matrix for v in row if v is not None]
    if len(set(values)) <= 1:
        return 1.0
    for row in matrix:
        vals = [v for v in row if v is not None]
        for a, b in combinations(vals, 2):
            pairs_total += 1
            pairs_agree += 1 if a == b else 0
    if not pairs_total:
        return None
    observed_disagreement = 1 - pairs_agree / pairs_total
    from collections import Counter

    counts = Counter(values)
    n = len(values)
    expected_agree = sum(c * (c - 1) for c in counts.values()) / (n * (n - 1)) if n > 1 else 1
    expected_disagreement = 1 - expected_agree
    if expected_disagreement == 0:
        return 1.0
    return round(1 - observed_disagreement / expected_disagreement, 3)


def main() -> int:
    from packages.providers.model_router import resolve_llm

    llm = resolve_llm("hybrid_accuracy", tier="high_reasoning")
    out_dir = Path("data/zone3")
    out_dir.mkdir(parents=True, exist_ok=True)

    for arg in sys.argv[1:]:
        run_dir = Path(arg)
        env = json.loads((run_dir / "output.json").read_text())
        pillar = env["pillar"]
        economy = env["findings"][0]["Economy"] if env["findings"] else env["country"]
        cfg_all = yaml.safe_load(Path(f"configs/rdtii/pillar_{pillar}.yaml").read_text())["indicators"]
        rows_by_ind = evidence_rows(run_dir)

        report, matrix = {}, []
        gold_map = master_gold_scores(economy)
        for indicator_id, cfg in cfg_all.items():
            if cfg.get("regulatory") is False:
                continue
            rows = rows_by_ind.get(indicator_id, [])
            det, det_reason = deterministic_score(indicator_id, rows)
            gold = gold_map.get(indicator_id)
            diverges = gold is not None and abs(det - gold) > 0.01
            judges = persona_scores(llm, indicator_id, cfg, rows)
            scores = [j["score"] for j in judges if j.get("score") is not None]
            matrix.append(scores)
            band = (min(scores + [det]), max(scores + [det])) if scores else (det, det)
            report[indicator_id] = {
                "deterministic": det, "deterministic_reason": det_reason,
                "master_gold": gold,
                "gold_divergence": bool(diverges),
                "gold_divergence_note": (
                    f"det {det} vs master gold {gold} — human adjudication required; "
                    "check evidence currentness vs master baseline before approving"
                ) if diverges else None,
                "judges": judges,
                "band": list(band),
                "spread": round(band[1] - band[0], 2),
                "flag_for_review": bool(band[1] != band[0]) or bool(diverges),
                "reviewer_decision": "pending",
            }
        alpha = krippendorff_alpha(matrix)
        payload = {"economy": economy, "pillar": pillar, "run": env.get("run_id"),
                   "krippendorff_alpha": alpha, "indicators": report,
                   "note": "AI suggestions only — every score requires human approval "
                           "(reviewer_decision) before it ships."}
        path = out_dir / f"{economy.lower()}_p{pillar}_scores.json"
        path.write_text(json.dumps(payload, indent=1))
        flagged = sum(1 for v in report.values() if v["flag_for_review"])
        print(f"{economy} P{pillar}: alpha={alpha} | {flagged}/{len(report)} flagged -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
