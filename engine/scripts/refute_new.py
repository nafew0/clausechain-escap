"""B4 — rubric-aware adversarial control over every surviving NEW row.

The panel receives the complete indicator question, scoring criteria, exclusions,
hunt-in guidance, surrounding context, status evidence and deterministic gates.
Its three votes are analytical lenses produced by the configured model; they are
not represented as three independent models and remain advisory.

Usage: .venv/bin/python scripts/refute_new.py outputs/final_si_p6 [more run dirs]
Writes data/review/refutation_<runname>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

from pydantic import BaseModel, Field  # noqa: E402

REFUTER_LENSES = ["opposing_counsel", "methodology_reviewer", "strict_textualist"]

FAILURE_MODES = """Known failure modes to check (ESCAP's own ❌-bank):
- keyword match without the legal FUNCTION (confidentiality != localization; business transfer != data transfer)
- lost exception (a conditional regime misread as a ban, or vice versa)
- wrong direction (retention LIMIT "no longer than necessary" is never minimum retention 7.3)
- generic domestic disclosure/processing misread as cross-border (P6)
- court-gated access misread as warrantless (7.5 court-order test)
- provision evidences a different indicator than claimed
- the snippet does not actually support the rationale"""


class RefutationVote(BaseModel):
    lens: str
    refuted: bool
    failure_mode: str = Field(default="none")
    reason: str = Field(default="")


class RefutationPanel(BaseModel):
    votes: list[RefutationVote] = Field(min_length=3, max_length=3)


def _indicator_configs() -> dict[str, dict]:
    configs: dict[str, dict] = {}
    for pillar in ("6", "7"):
        path = Path(f"configs/rdtii/pillar_{pillar}.yaml")
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        scope_exclusions = payload.get("scope_exclusions") or []
        for indicator_id, cfg in (payload.get("indicators") or {}).items():
            item = dict(cfg or {})
            item["pillar_scope_exclusions"] = scope_exclusions
            configs[indicator_id] = item
    return configs


def _rubric_text(indicator_id: str, cfg: dict) -> str:
    selected = {
        "indicator": indicator_id,
        "name": cfg.get("name"),
        "question": cfg.get("question", cfg.get("legal_question")),
        "legal_test": cfg.get("legal_test"),
        "polarity": cfg.get("polarity"),
        "scoring": cfg.get("scoring", cfg.get("criteria")),
        "exclusions": cfg.get("exclusions") or [],
        "pillar_scope_exclusions": cfg.get("pillar_scope_exclusions") or [],
        "hunt_in": cfg.get("hunt_in") or [],
        "positive_cues": cfg.get("positive_cues") or [],
        "negative_cues": cfg.get("negative_cues") or [],
        "example": cfg.get("example"),
    }
    return yaml.safe_dump(selected, sort_keys=False, allow_unicode=True).strip()


def _gate_summary(finding: dict) -> str:
    proof = finding.get("citation_proof") or {}
    gates = proof.get("gate_results") or []
    if not gates:
        return "No finding-level gate results recorded."
    return "\n".join(
        f"- {g.get('gate_id', '?')}: {g.get('status', '?')} — {g.get('reason', '')}"
        for g in gates
    )


def _panel_prompt(finding: dict, cfg: dict) -> str:
    indicator_id = finding.get("Indicator ID", "")
    proof = finding.get("citation_proof") or {}
    context = finding.get("raw_context") or finding.get("Notes") or ""
    status = finding.get("status_evidence") or ""
    if not isinstance(status, str):
        status = json.dumps(status, ensure_ascii=False)
    return f"""You are an adversarial legal-review panel applying ESCAP RDTII 2.1.

Produce exactly three analytical LENSES in this order:
1. opposing_counsel — seek a concrete legal-function or scope defect.
2. methodology_reviewer — apply the supplied indicator rubric, including hunt_in and scoring.
3. strict_textualist — ask what the exact quoted text and context actually establish.

REFUTATION STANDARD
Set refuted=true ONLY when a named failure mode clearly makes this mapping wrong for the
supplied rubric. Sectoral evidence is NOT a defect when the rubric's hunt_in/scoring expressly
calls for sectoral evidence. A fixed duty to keep records for X years is a minimum retention
period unless the text makes X a ceiling or merely permissive. For absence-scored framework
indicators, a provision evidencing the framework may be a valid evidence row even though the
indicator score records the absence/presence outcome. A WARN is not automatically a refutation.

{FAILURE_MODES}

COMPLETE INDICATOR RUBRIC
{_rubric_text(indicator_id, cfg)}

CLAIMED NEW MAPPING
- Law: {finding.get('Law Name', '')}
- Citation: {finding.get('Article / Section', '')}
- Coverage: {finding.get('Coverage', '')}
- Exact source snippet: {finding.get('Verbatim Snippet', '')[:1200]}
- Surrounding source context: {context[:3500]}
- Mapping rationale: {finding.get('Mapping Rationale', '')[:900]}
- Source URL: {finding.get('Source URL', '')}
- Citation alignment: {proof.get('alignment_status', '')} ({proof.get('alignment_score', '')})
- Status evidence: {status[:1000]}
- Deterministic gates:
{_gate_summary(finding)}

For every lens return: lens, refuted, one named failure_mode (or "none"), and a concise reason
that explicitly applies the supplied rubric. Do not reject merely because evidence is sectoral
or because another provision might be a better quote when the rubric accepts this provision."""


def _normalise_votes(panel: RefutationPanel) -> list[dict]:
    by_lens = {vote.lens: vote for vote in panel.votes}
    ordered: list[dict] = []
    for lens in REFUTER_LENSES:
        vote = by_lens.get(lens)
        if vote is None:
            ordered.append({"persona": lens, "refuted": None,
                            "failure_mode": "invalid_panel",
                            "error": "model omitted required analytical lens"})
            continue
        ordered.append({"persona": lens, "refuted": vote.refuted,
                        "failure_mode": vote.failure_mode[:80],
                        "reason": vote.reason[:500]})
    return ordered


def main() -> int:
    from packages.providers.model_router import resolve_llm

    llm = resolve_llm("hybrid_accuracy", tier="high_reasoning")
    configs = _indicator_configs()
    out_dir = Path("data/review")
    out_dir.mkdir(parents=True, exist_ok=True)

    for arg in sys.argv[1:]:
        run_dir = Path(arg)
        envelope = json.loads((run_dir / "output.json").read_text(encoding="utf-8"))
        rows = [row for row in envelope.get("findings", [])
                if row.get("Discovery Tag") == "NEW"]
        prompts: list[str] = []
        cache_keys: list[str] = []
        for row in rows:
            indicator_id = row.get("Indicator ID", "")
            if indicator_id not in configs:
                raise KeyError(f"No indicator rubric found for {indicator_id!r}")
            prompts.append(_panel_prompt(row, configs[indicator_id]))
            cache_keys.append(f"clausechain:refuter-panel:v2:{indicator_id}")
        panels = (llm.complete_many(prompts, RefutationPanel,
                                    prompt_cache_keys=cache_keys) if prompts else [])

        report = []
        for row, panel in zip(rows, panels, strict=True):
            votes = _normalise_votes(panel)
            refuted_count = sum(1 for vote in votes if vote.get("refuted"))
            verdict = ("RECOMMEND-REJECT" if refuted_count >= 2 else
                       "RECOMMEND-KEEP" if refuted_count == 0 else "SPLIT-REVIEW")
            report.append({
                "indicator": row["Indicator ID"],
                "law": row["Law Name"][:60],
                "article": row["Article / Section"],
                "verdict": verdict,
                "rubric_version": "full-indicator-v2",
                "panel_type": "three-lens-single-configured-model",
                "refuter_votes": votes,
            })
        path = out_dir / f"refutation_{run_dir.name}.json"
        path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        summary: dict[str, int] = {}
        for item in report:
            summary[item["verdict"]] = summary.get(item["verdict"], 0) + 1
        print(f"{run_dir.name}: {len(report)} NEW rows -> {summary} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
