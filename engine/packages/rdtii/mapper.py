"""RDTII mapping: cheap LLM screen (bulk tier) -> constrained mapping (high tier).

Legal logic comes from the DoDont playbook + rubric YAML, never invented here.
Every mapping decision returns a verbatim snippet that MUST later pass G1
(span-exists) — the model is told the quote will be mechanically verified.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, PrivateAttr

SCREEN_BATCH_SIZE = 12
import os as _os

# Rerun-fix #6: recall lever — cap raised and env-overridable (still logged, never silent)
SCREEN_CAP_PER_INDICATOR = int(_os.getenv("SCREEN_CAP_PER_INDICATOR", "200"))

GOLDEN_RULES = """LEGAL RULES (ESCAP RDTII methodology — binding):
- Map on legal FUNCTION, not keywords. A transfer CONDITION is 6.4 (conditional flow), NOT a 6.1 ban.
- A local-storage rule (copy stays in-country) is 6.2; a local server/data-centre PRECONDITION is 6.3; encryption/network-security rules are Pillar 7.2, never 6.x.
- Banking/professional secrecy or confidentiality duties are NOT transfer bans.
- Only current, in-force, official domestic law counts. Drafts/bills/repealed text never count.
- One provision can satisfy several indicators; judge THIS indicator's legal test only.
- If the legal test is not met, say applies=false — never force a mapping."""


class ScreenDecision(BaseModel):
    candidate_index: int
    relevant: bool
    reason: str = ""


class ScreenBatch(BaseModel):
    decisions: list[ScreenDecision] = Field(default_factory=list)


class MapDecision(BaseModel):
    applies: bool
    verbatim_snippet: str = ""
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: str = "Horizontal"            # Horizontal ONLY if ALL sectors; else Sectoral
    sector: str | None = None
    actor: str | None = None
    modality: str | None = None             # must/may/should (+not)
    action: str | None = None
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    _model_route: str = PrivateAttr(default="nano")
    _escalation_reasons: list[str] = PrivateAttr(default_factory=list)


def _complete(llm, prompt: str, schema: type[BaseModel], cache_key: str):
    """Use cache routing when supported; retain simple fake/local providers."""
    try:
        return llm.complete(prompt, schema, prompt_cache_key=cache_key)
    except TypeError as error:
        if "prompt_cache_key" not in str(error):
            raise
        return llm.complete(prompt, schema)


def _snippet_locatable(snippet: str, source: str) -> bool:
    if not snippet:
        return False
    if snippet in source:
        return True
    norm = lambda value: re.sub(r"\s+", " ", value).strip().casefold()
    return norm(snippet) in norm(source)


def _candidate_context(candidate) -> str:
    """Canonical provision context, including child items and exceptions."""
    return candidate.props.get("raw_context") or candidate.text


def escalation_reasons(decision: MapDecision, indicator_id: str, candidate,
                       gold_anchor: bool = False,
                       expected_anchor: bool = False) -> list[str]:
    """Deterministic mini boundary: only material ambiguity or malformed evidence."""
    reasons: list[str] = []
    context = _candidate_context(candidate)
    text = context.casefold()
    if gold_anchor and not decision.applies:
        reasons.append("known-anchor-rejected")
    elif expected_anchor and not decision.applies:
        reasons.append("expected-anchor-rejected")
    if decision.applies and not _snippet_locatable(decision.verbatim_snippet, context):
        reasons.append("snippet-not-source-locatable")
    if decision.applies and decision.confidence < 0.72:
        reasons.append("low-confidence-positive")
    if gold_anchor and decision.applies and decision.confidence < 0.80:
        reasons.append("low-confidence-known-anchor")

    # These are the two distinctions where a cheap classifier error can reverse
    # the legal effect and therefore merits the expensive second look.
    conditional_terms = (" unless ", " except ", "subject to", "provided that")
    if indicator_id in {"6.1", "6.4", "P6-I1", "P6-I4"} and decision.applies:
        if any(term in f" {text} " for term in conditional_terms):
            reasons.append("ban-vs-condition-ambiguity")
    if indicator_id in {"7.5", "P7-I5"} and decision.applies:
        if any(term in text for term in ("warrant", "court order", "judicial", "without consent")):
            reasons.append("judicial-access-ambiguity")
    return reasons


def _indicator_brief(indicator_id: str, cfg: dict) -> str:
    exclusions = "\n".join(f"- {e}" for e in (cfg.get("exclusions") or []))
    scoring = "\n".join(f"  score {k}: {v}" for k, v in (cfg.get("scoring") or {}).items())
    parts = [
        f"INDICATOR {indicator_id} — {cfg.get('name', '')}",
        f"Legal test: {cfg.get('question', '')}",
    ]
    if cfg.get("polarity") == "framework_absent_scores_high":
        parts.append(
            "EVIDENCE RULE (absence-scored indicator): applies=true when the provision "
            "ESTABLISHES or evidences the framework (purpose/scope clause, core obligation, "
            "or the controlling framework provision). ESCAP records the framework's existence "
            "as the evidence row; the SCORE (not your mapping) captures absence. Do NOT reject "
            "a provision merely because it proves the framework EXISTS."
        )
    if cfg.get("legal_test"):
        parts.append(str(cfg["legal_test"]).strip())
    if exclusions:
        parts.append(f"Exclusions (hard rules):\n{exclusions}")
    if scoring:
        parts.append(f"Official scoring criteria:\n{scoring}")
    return "\n".join(parts)


def screen_candidates(llm_bulk, indicator_id: str, cfg: dict, candidates: list) -> list:
    """Cheap relevance screen over retrieval candidates. Returns the surviving subset."""
    survivors = []
    pool = candidates[:SCREEN_CAP_PER_INDICATOR]
    for start in range(0, len(pool), SCREEN_BATCH_SIZE):
        batch = pool[start:start + SCREEN_BATCH_SIZE]
        listing = "\n\n".join(
            f"[{i}] ({c.props.get('article_section', '?')} — {c.props.get('heading', '')}) {c.text[:900]}"
            for i, c in enumerate(batch)
        )
        prompt = f"""You screen statutory provisions for an RDTII digital-trade-regulation indicator.

{_indicator_brief(indicator_id, cfg)}

{GOLDEN_RULES}

For EACH numbered candidate below, decide if it PLAUSIBLY satisfies the indicator's legal test
(err on the side of relevant=true when unsure — a later stage decides precisely; but apply the
Exclusions strictly: a candidate matching an exclusion is NOT relevant).

CANDIDATES:
{listing}

Return one decision per candidate, using each candidate's index number."""
        result = _complete(llm_bulk, prompt, ScreenBatch,
                           f"clausechain:screen:v2:{indicator_id}")
        for decision in result.decisions:
            if decision.relevant and 0 <= decision.candidate_index < len(batch):
                survivors.append(batch[decision.candidate_index])
    return survivors


def _mapping_prompt(indicator_id: str, cfg: dict, candidate,
                    gold_anchor: bool = False,
                    expected_anchor: bool = False) -> str:
    props = candidate.props
    canonical_context = _candidate_context(candidate)
    return f"""You are a legal analyst applying the ESCAP RDTII 2.1 methodology.

{_indicator_brief(indicator_id, cfg)}

{GOLDEN_RULES}

{"GOLD ANCHOR: ESCAP's master dataset records THIS provision under THIS indicator (KNOWN baseline). Reproducing it proves recall — unless the text PLAINLY contradicts the legal test, set applies=true and extract the operative quote." if gold_anchor else ""}
{"VERIFIED RESEARCH EXPECTATION: an official-source research report expects this provision to be assessed under this indicator. Do not assume it qualifies; make the legal-test decision explicitly and preserve a diagnostic reason if it does not." if expected_anchor and not gold_anchor else ""}

PROVISION UNDER ANALYSIS
Law: {props.get('law_name', '')}
Citation: {props.get('article_section', '')} — heading: {props.get('heading', '')} ({props.get('part', '')})
Text (verbatim from the official source):
\"\"\"{canonical_context[:12000]}\"\"\"

TASK
1. Extract the predicate: WHO is regulated, WHAT modality (must/may/should, negated?),
   WHAT action, under WHAT conditions, with WHAT exceptions.
2. Decide: does this provision satisfy indicator {indicator_id}'s legal test? (applies)
3. If applies: pick verbatim_snippet = an EXACT contiguous quote from the text above
   (copied character-for-character — it will be MECHANICALLY verified against the source;
   any edit fails the row). Include the operative actor, modality, action and object. The
   engine will extend a list introduction through its child items and closing full stop.
4. rationale (<= 300 chars): "This [section] [prohibits/requires/permits/establishes] [what].
   Maps to {indicator_id} because [one sentence of legal logic]." Name the legal FUNCTION.
5. coverage: "Horizontal" ONLY if it applies to ALL sectors; otherwise "Sectoral" + sector.
6. confidence 0-1. If the exception ("unless/except") changes the legal effect, account for it:
   a rule with a compliance path is conditional (6.4-type), not a ban (6.1-type)."""


def map_candidate(llm_primary, indicator_id: str, cfg: dict, candidate,
                  gold_anchor: bool = False, llm_escalation=None,
                  expected_anchor: bool = False) -> MapDecision:
    """Nano-first mapping; mini is restricted to deterministic escalation cases."""
    prompt = _mapping_prompt(indicator_id, cfg, candidate, gold_anchor, expected_anchor)
    decision = _complete(llm_primary, prompt, MapDecision,
                         f"clausechain:map:v3:{indicator_id}")
    reasons = escalation_reasons(
        decision, indicator_id, candidate, gold_anchor, expected_anchor
    )
    decision._model_route = "nano"
    decision._escalation_reasons = reasons
    if reasons and llm_escalation is not None:
        escalation_prompt = f"""{prompt}

SECOND-PASS REVIEW
A cheaper model returned this provisional decision:
{decision.model_dump_json()}
Escalation reasons: {', '.join(reasons)}.
Independently correct the decision. Do not defer to the provisional answer."""
        decision = _complete(llm_escalation, escalation_prompt, MapDecision,
                             f"clausechain:legal-escalation:v1:{indicator_id}")
        decision._model_route = "mini-escalation"
        decision._escalation_reasons = reasons
    return decision


def map_candidates(llm_primary, indicator_id: str, cfg: dict, candidates: list,
                   gold_anchor_ids: set[str], llm_escalation=None,
                   expected_anchor_ids: set[str] | None = None) -> list[MapDecision]:
    """Map an indicator pool together so final sweeps can use the 50%-off Batch API."""
    if not candidates:
        return []
    expected_anchor_ids = expected_anchor_ids or set()
    prompts = [_mapping_prompt(
                   indicator_id, cfg, candidate,
                   candidate.provision_id in gold_anchor_ids,
                   candidate.provision_id in expected_anchor_ids,
               )
               for candidate in candidates]
    keys = [f"clausechain:map:v3:{indicator_id}"] * len(prompts)
    if hasattr(llm_primary, "complete_many"):
        decisions = llm_primary.complete_many(prompts, MapDecision, prompt_cache_keys=keys)
    else:
        decisions = [_complete(llm_primary, prompt, MapDecision, key)
                     for prompt, key in zip(prompts, keys, strict=True)]

    escalation_indexes: list[int] = []
    escalation_prompts: list[str] = []
    reasons_by_index: dict[int, list[str]] = {}
    for index, (candidate, decision, prompt) in enumerate(
            zip(candidates, decisions, prompts, strict=True)):
        reasons = escalation_reasons(
            decision, indicator_id, candidate,
            candidate.provision_id in gold_anchor_ids,
            candidate.provision_id in expected_anchor_ids,
        )
        decision._model_route = "nano"
        decision._escalation_reasons = reasons
        if reasons and llm_escalation is not None:
            escalation_indexes.append(index)
            reasons_by_index[index] = reasons
            escalation_prompts.append(
                f"{prompt}\n\nSECOND-PASS REVIEW\nA cheaper model returned this provisional "
                f"decision:\n{decision.model_dump_json()}\nEscalation reasons: "
                f"{', '.join(reasons)}.\nIndependently correct the decision. Do not defer "
                "to the provisional answer.")
    if escalation_prompts:
        escalation_keys = [f"clausechain:legal-escalation:v1:{indicator_id}"] * len(escalation_prompts)
        if hasattr(llm_escalation, "complete_many"):
            reviewed = llm_escalation.complete_many(
                escalation_prompts, MapDecision, prompt_cache_keys=escalation_keys)
        else:
            reviewed = [_complete(llm_escalation, prompt, MapDecision, key)
                        for prompt, key in zip(escalation_prompts, escalation_keys, strict=True)]
        for index, decision in zip(escalation_indexes, reviewed, strict=True):
            decision._model_route = "mini-escalation"
            decision._escalation_reasons = reasons_by_index[index]
            decisions[index] = decision
    return decisions
