"""Measured cost accounting (README contract: measured, never estimated).

Providers report real token usage here after every API call; the orchestrator
writes the accumulated report to the envelope + logs/cost_report.json.
Prices are per 1M tokens (USD, as of Jul 2026) — edit PRICES when they change.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PRICES = {  # standard per 1M tokens: (input, cached input, output), Jul 2026
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
}

_USAGE: dict[str, dict] = defaultdict(lambda: {
    "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "calls": 0,
})


def record(model: str, input_tokens: int, output_tokens: int = 0,
           cached_input_tokens: int = 0, *, batch: bool = False) -> None:
    if batch:
        model = f"{model} [batch]"
    entry = _USAGE[model]
    entry["input_tokens"] += int(input_tokens or 0)
    entry["cached_input_tokens"] += int(cached_input_tokens or 0)
    entry["output_tokens"] += int(output_tokens or 0)
    entry["calls"] += 1


def reset() -> None:
    _USAGE.clear()


def report() -> dict:
    models = {}
    total = 0.0
    for model, u in _USAGE.items():
        base_model = model.removesuffix(" [batch]")
        pin, pcached, pout = PRICES.get(base_model, (0.0, 0.0, 0.0))
        if model.endswith(" [batch]"):
            pin, pcached, pout = pin / 2, pcached / 2, pout / 2
        cached = min(u["cached_input_tokens"], u["input_tokens"])
        uncached = u["input_tokens"] - cached
        cost = (uncached / 1e6 * pin + cached / 1e6 * pcached
                + u["output_tokens"] / 1e6 * pout)
        models[model] = {**u, "usd": round(cost, 4), "priced": base_model in PRICES}
        total += cost
    return {"models": models, "total_usd": round(total, 4),
            "note": "measured from real API usage objects; prices per 1M tokens (PRICES)"}


def append_log(run_id: str, extra: dict | None = None,
               path: str | Path = "logs/cost_report.json") -> dict:
    entry = {"run_id": run_id, "at": datetime.now(timezone.utc).isoformat(),
             **report(), **(extra or {})}
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    log = json.loads(p.read_text()) if p.is_file() else []
    log.append(entry)
    p.write_text(json.dumps(log, indent=1))
    return entry
