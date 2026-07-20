"""Precision-first, auditable curation of redundant NEW legal findings.

This stage never changes KNOWN rows and never turns a rejected candidate into an
absence conclusion. It keeps a functionally diverse shortlist per
(economy, indicator, instrument), while recording every excluded row and reason
in the run manifest.
"""
from __future__ import annotations

import re
from collections import defaultdict

from packages.core.schemas import MappedFinding


_LIMITS = {
    "P7-I1": 1,  # one strong provision can establish framework existence/scope
    "P7-I2": 2,  # framework/system + one operative cyber obligation
    "P7-I3": 3,  # distinct retention duties can be independently valuable
    "P7-I4": 2,
    "P7-I5": 2,  # distinct access mechanisms only
}


def _legal_function(finding: MappedFinding) -> str:
    text = f"{finding.verbatim_snippet} {finding.mapping_rationale}".lower()
    patterns = (
        ("framework", r"purpose|object|framework|national cyber security system|govern"),
        ("incident", r"incident|notify|notification|report"),
        ("risk_audit", r"risk assessment|audit|vulnerability|exercise"),
        ("controls", r"code of practice|standard|measure|mechanism|program|plan"),
        ("retention", r"retain|keep|preserve|year|month|day"),
        ("data_access", r"computer(?:i[sz]ed)? data|access to data|produce document|intercept"),
        ("search_seizure", r"search|seiz|enter premises|warrant"),
        ("investigation", r"investigat|authorised officer|authorized officer"),
    )
    for name, pattern in patterns:
        if re.search(pattern, text):
            return name
    return "other"


def _directness(finding: MappedFinding) -> int:
    text = f"{finding.verbatim_snippet} {finding.mapping_rationale}".lower()
    patterns = {
        "P7-I1": r"purpose|govern|personal data protection|horizontal",
        "P7-I2": r"cyber security system|cybersecurity framework|risk management|incident",
        "P7-I3": r"at least|not less than|for (?:a period of )?\w+ years?|\d+ years?",
        "P7-I4": r"data protection officer|impact assessment|responsible for compliance",
        "P7-I5": r"without (?:first )?(?:obtaining )?(?:a )?warrant|computer(?:i[sz]ed)? data|intercept",
    }
    return 1 if re.search(patterns.get(finding.indicator_id, r"$^"), text) else 0


def _rank(finding: MappedFinding) -> tuple:
    proof = finding.citation_proof
    resolved = int(bool(proof and proof.alignment_status in {"exact", "anchor"}))
    warning_count = len(finding.verifier_risks)
    pinpoint = int("(" in finding.article_section)
    # Higher values win. Stable citation ordering makes replay deterministic.
    return (resolved, _directness(finding), -warning_count,
            float(finding.confidence), pinpoint, finding.article_section)


def curate_new_findings(findings: list[MappedFinding]) -> tuple[list[MappedFinding], list[dict]]:
    groups: dict[tuple[str, str, str], list[MappedFinding]] = defaultdict(list)
    passthrough: list[MappedFinding] = []
    for finding in findings:
        if finding.discovery_tag != "NEW" or "NO_EVIDENCE_FOUND" in finding.verbatim_snippet:
            passthrough.append(finding)
            continue
        key = (finding.economy, finding.indicator_id, finding.law_name)
        groups[key].append(finding)

    kept: list[MappedFinding] = list(passthrough)
    excluded: list[dict] = []
    for key, group in sorted(groups.items()):
        limit = _LIMITS.get(key[1], 2)
        ranked = sorted(group, key=_rank, reverse=True)
        selected: list[MappedFinding] = []
        used_functions: set[str] = set()
        # Functional diversity first; a second pass fills any remaining slots.
        for finding in ranked:
            function = _legal_function(finding)
            if function in used_functions:
                continue
            selected.append(finding)
            used_functions.add(function)
            if len(selected) == limit:
                break
        if len(selected) < limit:
            for finding in ranked:
                if finding not in selected:
                    selected.append(finding)
                    if len(selected) == limit:
                        break
        kept.extend(selected)
        selected_ids = {id(f) for f in selected}
        for finding in group:
            if id(finding) in selected_ids:
                continue
            excluded.append({
                "economy": finding.economy,
                "indicator_id": finding.indicator_id,
                "law_name": finding.law_name,
                "article_section": finding.article_section,
                "reason": (f"redundant NEW evidence after precision curation; retained at most {limit} "
                           "functionally distinct provisions for this law/indicator"),
                "legal_function": _legal_function(finding),
                "confidence": finding.confidence,
                "verifier_risks": list(finding.verifier_risks),
            })
    return kept, excluded
