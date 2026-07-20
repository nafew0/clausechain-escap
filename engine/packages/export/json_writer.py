from __future__ import annotations

import json
from pathlib import Path

from packages.core.schemas import RunEnvelope


def write_json(envelope: RunEnvelope, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = envelope.model_dump(mode="json", by_alias=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

