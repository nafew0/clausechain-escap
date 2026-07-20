from __future__ import annotations

import csv
import json
import subprocess
import sys


def test_dummy_run_creates_csv_and_json(tmp_path) -> None:
    out_dir = tmp_path / "demo"
    result = subprocess.run(
        [
            sys.executable,
            "run.py",
            "--country",
            "SG",
            "--pillar",
            "6",
            "--out",
            str(out_dir),
        ],
        check=True,
        cwd=".",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    csv_path = out_dir / "output.csv"
    json_path = out_dir / "output.json"
    assert csv_path.exists()
    assert json_path.exists()

    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    row = rows[0]
    assert row["Discovery Tag"] in {"NEW", "KNOWN"}
    assert row["Verbatim Snippet"]
    assert row["Source URL"]
    assert row["Article / Section"]
    assert row["Mapping Rationale"]

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["provider_profile"] == "hybrid_accuracy"
    assert payload["metadata"]["graph_required"] is False

