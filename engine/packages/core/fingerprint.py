"""Processing fingerprint for incremental builds (Sol review #1, 19 Jul).

A cached extraction may be reused ONLY when everything that could change its
output is unchanged — not just the source bytes. The fingerprint binds:
  - source content sha256
  - EXTRACTION_VERSION (bump on ANY parser/grammar/extraction-strategy change)
  - the seed's parse profile (source_type) and jurisdiction grammar names
  - free-form extras (e.g. OCR profile) supplied by the builder

Builders restamp a prior generation's provisions only on a full fingerprint
match; any mismatch falls through to a fresh extraction.
"""
from __future__ import annotations

import hashlib
import json

# Bump whenever extractor/parser behavior changes so cached RuleUnits from the
# previous behavior can never satisfy an incremental rebuild.
# 2026-07-19.1: clause-boundary snippets, SSO subsection line-breaks, treaty +
#               malay grammars, monotonic-filter state as of the 19 Jul rerun.
EXTRACTION_VERSION = "2026-07-19.1"


def processing_fingerprint(content_sha256: str, source_type: str = "act",
                           grammars: list[str] | tuple[str, ...] = (),
                           extras: list[str] | tuple[str, ...] = (),
                           config: dict | None = None) -> str:
    config_json = json.dumps(config or {}, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
    basis = "\x1f".join([
        content_sha256,
        EXTRACTION_VERSION,
        source_type,
        ",".join(sorted(str(g) for g in grammars or ())),
        ",".join(str(e) for e in extras or ()),
        config_json,
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
