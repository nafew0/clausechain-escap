"""Aggregate expected-anchor diagnostics from six immutable run envelopes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

RUNS = ("final_si_p6", "final_si_p7", "final_ma_p6", "final_ma_p7",
        "final_au_p6", "final_au_p7")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--out", default="reports/anchor_traces.json")
    args = parser.parse_args()
    traces = []
    for run in RUNS:
        path = Path(args.outputs) / run / "output.json"
        envelope = json.loads(path.read_text())
        by_indicator = (envelope.get("metadata", {}).get("pipeline_stats", {})
                        .get("by_indicator", {}))
        for indicator, stats in by_indicator.items():
            for trace in stats.get("expected_anchor_trace", []):
                traces.append({"run": run, "indicator": indicator, **trace})
    counts: dict[str, int] = {}
    for trace in traces:
        counts[trace["outcome"]] = counts.get(trace["outcome"], 0) + 1
    payload = {
        "contract": "clausechain-anchor-trace-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "traces": traces,
    }
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"anchor traces: {len(traces)} -> {out} {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
