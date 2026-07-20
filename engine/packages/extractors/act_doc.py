"""Output contract for markup-based act extractors (the reuse seam for new portals).

Any portal-specific HTML/XHTML parser emits an `ActDoc`; `core.rule_units.
build_rule_units` turns it into RuleUnits without knowing the portal. A new
economy's HTML portal only needs a parser producing this shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Subsection:
    label: str          # "26(1)" — paragraph-depth citation label
    text: str           # normalized verbatim text (includes the "(1)" marker)
    anchor: str         # portal anchor id, e.g. "pr26-ps1-"


@dataclass
class Section:
    sec_id: str         # portal section id, e.g. "pr26-" or "Sc1-..."
    number: str         # "26" (or the schedule id for schedules)
    heading: str
    part: str           # e.g. "Part 6 CARE OF PERSONAL DATA" ("" if none)
    text: str           # full normalized section text (heading excluded)
    subsections: list[Subsection] = field(default_factory=list)

    def anchor_url(self, act_url: str) -> str:
        return f"{act_url}#{self.sec_id}"


@dataclass
class ActDoc:
    law_name: str
    current_as_at: str | None
    source_url: str
    sections: list[Section] = field(default_factory=list)
