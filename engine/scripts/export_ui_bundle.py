"""Export ui_export.zip — everything the hosted web app imports (Sprint Plan §1).

Contents (all REAL engine artifacts, no reshaping):
  review_payload.json   all review queues + refuter verdicts (canonical shapes)
  consolidated.json     full-provenance evidence rows
  decisions.template.json  the exact decisions contract submission_replay consumes
  proof/                pre-rendered source-page assets + review index (as-is)
  runs/<run>/output.json   six envelopes
  runs/cost_report.json    measured spend
  champion_validation.json gate report (stale/fail banners)
  manifest.json         SHA-256 of every file + generation time

Usage: .venv/bin/python scripts/export_ui_bundle.py [--out ui_export.zip]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RUNS = ["final_si_p6", "final_si_p7", "final_ma_p6", "final_ma_p7",
        "final_au_p6", "final_au_p7"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="ui_export.zip")
    args = parser.parse_args()

    from scripts.export_finding_key_map import main as _  # noqa: F401 (ensure importable)
    from scripts.export_legal_review_payload import build_payload

    payload = build_payload()
    import subprocess as _sp
    _sp.run([sys.executable, "scripts/export_finding_key_map.py", "--out",
             "/tmp/finding_key_map.json"], check=True)

    entries: dict[str, bytes] = {
        "review_payload.json": json.dumps(payload, indent=1, ensure_ascii=False).encode(),
        "consolidated.json": Path("submission/consolidated.json").read_bytes(),
        "decisions.template.json": Path("submission/review/decisions.template.json").read_bytes(),
        "champion_validation.json": Path("reports/champion_validation.json").read_bytes(),
        "runs/cost_report.json": Path("logs/cost_report.json").read_bytes(),
        "finding_key_map.json": Path("/tmp/finding_key_map.json").read_bytes(),
    }
    for run in RUNS:
        entries[f"runs/{run}/output.json"] = Path(f"outputs/{run}/output.json").read_bytes()
    for path in sorted(Path("submission/review").rglob("*")):
        if path.is_file() and path.name != ".DS_Store":
            entries[f"proof/{path.relative_to('submission/review')}"] = path.read_bytes()

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": payload.get("counts", {}),
        "refuter_status": payload.get("refuter_status", ""),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())},
    }
    entries["manifest.json"] = json.dumps(manifest, indent=1).encode()

    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            z.writestr(name, data)
    size_mb = Path(args.out).stat().st_size / 1e6
    print(f"wrote {args.out} — {len(entries)} files, {size_mb:.1f} MB, "
          f"bundle {manifest['files']['review_payload.json'][:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
