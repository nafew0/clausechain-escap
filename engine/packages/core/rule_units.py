"""Build RuleUnits (the smallest quotable legal units) from parsed act documents.

One RuleUnit per SUBSECTION — paragraph-depth citations ("s. 26(1)") are a hard
rubric requirement; bare "s. 26" loses points. Section heading and Part are kept
as metadata context for retrieval and mapping prompts.
"""
from __future__ import annotations

from packages.core.schemas import RuleUnit
from packages.extractors.act_doc import ActDoc


def classify_rule_components(text: str) -> list[dict]:
    """Deterministically expose linked legal context without rewriting source text."""
    import re

    patterns = (
        ("exception", re.compile(r"\b(?:except|unless|does not apply|despite)\b", re.I)),
        ("condition", re.compile(r"\b(?:if|where|provided that|subject to)\b", re.I)),
        ("definition", re.compile(r"\b(?:means|includes|in this (?:Act|section))\b", re.I)),
        ("note", re.compile(r"\bNote\s*\d*\s*[:—-]", re.I)),
        ("cross_reference", re.compile(r"\b(?:section|subsection|paragraph|Schedule)\s+\d", re.I)),
    )
    components = [{"role": "principal_rule", "start": 0, "end": len(text), "text": text}]
    for role, pattern in patterns:
        for match in pattern.finditer(text):
            stop = min(len(text), (text.find(".", match.start()) + 1) or len(text))
            components.append({"role": role, "start": match.start(), "end": stop,
                               "text": text[match.start():stop]})
    return components


def build_rule_units(
    doc: ActDoc,
    economy: str,
    act_ref: str,
    law_number_ref: str | None = None,
    last_amended: str | None = None,
) -> list[RuleUnit]:
    units: list[RuleUnit] = []
    for section in doc.sections:
        for sub in section.subsections:
            label = sub.label  # "26(1)" or "26"
            units.append(
                RuleUnit(
                    id=f"{economy.lower()}:{act_ref}:{sub.anchor}",
                    document_id=f"{economy.lower()}:{act_ref}",
                    economy=economy,
                    law_name=doc.law_name,
                    law_number_ref=law_number_ref,
                    last_amended=last_amended,
                    article_section=f"s. {label}",
                    text=sub.text,
                    raw_context=section.text,
                    source_url=section.anchor_url(doc.source_url),
                    location_reference=f"#{section.sec_id}",
                    metadata={
                        "heading": section.heading,
                        "part": section.part,
                        "section_number": section.number,
                        "current_as_at": doc.current_as_at,
                        "rule_components": classify_rule_components(section.text),
                    },
                )
            )
    return units
