"""Bring engine runs into the review inputs of one model backend.

A run only writes outputs/<run>/output.json. The review snapshot is imported
from files derived from those outputs (refuter verdicts, the consolidated
candidate set, recall adjudication, zone-3 score suggestions, the review bundle
and its unsigned decision template, the champion report), so a run reaches the
app only after they are rebuilt. This is the chain of deploy/night_chain.sh, run
for the runs whose output.json is newer than the mode's consolidated set:

  refute_new (changed runs) -> consolidate (all runs) -> adjudicate_recall
  (round-1 runs, only when one of them changed) -> zone3_score (changed runs)
  -> build_review_bundle -> champion_validate [-> export_ui_bundle, hybrid]

--mode hybrid (default) keeps the signed snapshot's historical paths and models.
--mode local runs the same chain with the open-weights model and writes only the
separate Local files (packages/core/review_layout.py), so the two workspaces never
share a file or a key. Signed decisions are never touched here: apply_decisions.py
carries every decision whose finding and review subject survive the new template.

Usage: .venv/bin/python scripts/prepare_review_inputs.py [--mode hybrid|local]
           [--out ui_export.zip] [--run <run name> ...]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core import progress, review_layout  # noqa: E402


def changed_runs(layout: review_layout.Layout) -> list[str]:
    """Runs whose output is newer than the mode's consolidated candidate set."""
    outputs = [run for run in layout.runs if Path(f"outputs/{run}/output.json").is_file()]
    if not layout.consolidated.is_file():
        return outputs
    built = layout.consolidated.stat().st_mtime
    return [run for run in outputs if Path(f"outputs/{run}/output.json").stat().st_mtime > built]


def needs(result: Path, run: str) -> bool:
    """A per-run result is reusable when it is newer than the run's output (a
    cancelled refresh resumes without repeating finished model calls)."""
    output = Path(f"outputs/{run}/output.json")
    return not result.is_file() or result.stat().st_mtime < output.stat().st_mtime


def zone3_result(layout: review_layout.Layout, run: str) -> Path:
    economy = review_layout.ECONOMY_BY_CODE[review_layout.run_code(run)].lower()
    return layout.zone3_dir / f"{economy}_{run.rsplit('_', 1)[-1]}_scores.json"


def step(name: str, argv: list[str], *, advisory: bool = False) -> None:
    started = time.time()
    progress.emit("prepare", f"{name}…")
    result = subprocess.run([sys.executable, *argv])
    if result.returncode and advisory:
        # A FAIL report is itself the output: the app shows it as the
        # evidence-integrity banner, so it must not block the refresh.
        progress.emit("prepare", f"{name} reported failures (exit {result.returncode}); "
                                 "they are shown in the app", level="warn")
    elif result.returncode:
        progress.emit("prepare", f"{name} failed (exit {result.returncode}); "
                                 "the snapshot was not refreshed", level="error")
        raise SystemExit(result.returncode)
    progress.emit("prepare", f"{name} done in {time.time() - started:.0f}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("hybrid", "local"), default="hybrid")
    parser.add_argument("--out", default="ui_export.zip")
    parser.add_argument("--run", action="append",
                        help="force a run through the chain even if its output is not newer")
    args = parser.parse_args()

    # Every step below (and anything it spawns) reads the same layout.
    os.environ[review_layout.MODE_ENV] = args.mode
    layout = review_layout.current()
    unknown = sorted(set(args.run or []) - set(layout.runs))
    if unknown:
        parser.error(f"not a {args.mode} run with an output: {', '.join(unknown)}")
    if not layout.runs:
        progress.emit("prepare", f"no {args.mode} run has an output yet", level="error")
        return 1

    changed = sorted(set(changed_runs(layout)) | set(args.run or []), key=list(layout.runs).index)
    dirs = [f"outputs/{run}" for run in layout.runs]
    model = "open-weights model" if args.mode == "local" else "hybrid models"
    if changed:
        progress.emit("prepare", f"{args.mode}: rebuilding review inputs for {', '.join(changed)} "
                                 f"with the {model}")
        to_refute = [f"outputs/{run}" for run in changed if needs(layout.refutation(run), run)]
        if to_refute:
            step("refuter panel on new rows", ["scripts/refute_new.py", *to_refute])
        else:
            progress.emit("prepare", "refuter verdicts are current for every changed run")
        step("consolidating the candidate set", ["scripts/consolidate_submission.py", *dirs])
        round1 = layout.round1_runs
        if round1 and any(run in round1 for run in changed):
            step("recall adjudication", ["scripts/adjudicate_recall.py",
                                         *[f"outputs/{run}" for run in round1]])
        to_score = [f"outputs/{run}" for run in changed if needs(zone3_result(layout, run), run)]
        if to_score:
            step("zone-3 score suggestions", ["scripts/zone3_score.py", *to_score])
        else:
            progress.emit("prepare", "zone-3 suggestions are current for every changed run")
        step("review bundle and decision template", ["scripts/build_review_bundle.py"])
        step("champion validation", ["scripts/champion_validate.py"], advisory=True)
    else:
        progress.emit("prepare", f"{args.mode}: no run changed since the last consolidation")
    if args.mode == "hybrid":
        step("exporting the UI bundle", ["scripts/export_ui_bundle.py", "--out", args.out])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
