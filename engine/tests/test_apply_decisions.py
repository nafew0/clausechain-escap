"""W2: atomic decision writers — merge, validation, concurrency, bundle, replay input."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]


def _seed_root(tmp_path: Path) -> Path:
    (tmp_path / "submission/review").mkdir(parents=True)
    (tmp_path / "data/review").mkdir(parents=True)
    template = [{"finding_key": f"{i:02d}" * 32,
                 "review": {"decision": "rejected", "reviewer_name": "", "reviewer_role": "",
                            "reviewed_at": "", "citation_checked": False, "mapping_checked": False,
                            "status_checked": False, "citation_reviewer_name": "",
                            "mapping_reviewer_name": "", "status_reviewer_name": "",
                            "correction_note": "UNSIGNED TEMPLATE"}} for i in range(3)]
    (tmp_path / "submission/review/decisions.template.json").write_text(json.dumps(template))
    return tmp_path


def _run(root: Path, domain: str, batch: dict, extra: list[str] = []):
    proc = subprocess.run(
        [sys.executable, str(ENGINE / "scripts/apply_decisions.py"),
         "--domain", domain, "--root", str(root), *extra],
        input=json.dumps(batch), capture_output=True, text=True, cwd=ENGINE)
    return proc.returncode, json.loads(proc.stdout or "{}")


def _approval(key: str) -> dict:
    return {"finding_key": key, "review": {
        "decision": "approved", "reviewer_name": "Nafew", "reviewer_role": "Team Lead",
        "reviewed_at": "2026-07-18T12:00:00Z", "citation_checked": True,
        "mapping_checked": True, "status_checked": True,
        "citation_reviewer_name": "Nafew", "mapping_reviewer_name": "Adv. Rahman",
        "status_reviewer_name": "Nafew", "correction_note": ""}}


def test_findings_merge_is_template_complete_and_atomic(tmp_path):
    root = _seed_root(tmp_path)
    key = "00" * 32
    code, out = _run(root, "findings", {"decisions": [_approval(key)]})
    assert code == 0 and out["ok"], out
    merged = json.loads((root / "data/review/decisions.json").read_text())
    assert len(merged) == 3  # template-complete
    assert merged[0]["review"]["decision"] == "approved"
    assert merged[1]["review"]["correction_note"] == "UNSIGNED TEMPLATE"


def test_same_reviewer_for_citation_and_mapping_is_refused(tmp_path):
    root = _seed_root(tmp_path)
    bad = _approval("01" * 32)
    bad["review"]["mapping_reviewer_name"] = "Nafew"
    code, out = _run(root, "findings", {"decisions": [bad]})
    assert code == 2 and "different people" in out["error"]


def test_needs_correction_never_reaches_the_file(tmp_path):
    root = _seed_root(tmp_path)
    bad = _approval("01" * 32)
    bad["review"]["decision"] = "needs-correction"
    code, out = _run(root, "findings", {"decisions": [bad]})
    assert code == 2 and "app-only" in out["error"]


def test_optimistic_concurrency_conflict(tmp_path):
    root = _seed_root(tmp_path)
    _run(root, "findings", {"decisions": [_approval("00" * 32)]})
    code, out = _run(root, "findings", {"decisions": [_approval("01" * 32)]},
                     extra=["--expected-sha", "deadbeef"])
    assert code == 3 and out["conflict"]


def test_recall_zone3_and_bundle(tmp_path):
    root = _seed_root(tmp_path)
    code, _ = _run(root, "recall", {"decisions": [
        {"recall_key": "ab" * 32, "verdict": "GOLD_WRONG", "reviewer_name": "Nafew",
         "reviewer_role": "Team Lead", "reviewed_at": "2026-07-18T12:00:00Z"}]})
    assert code == 0
    code, out = _run(root, "zone3", {"decisions": [
        {"economy": "Malaysia", "indicator": "P7-I1", "action": "override", "score": 0.5,
         "reviewer_name": "Nafew", "reviewed_at": "2026-07-18T12:00:00Z"}]},
        extra=["--bundle-after"])
    assert code == 0 and "bundles" in out["bundle"]
    bundle = Path(out["bundle"])
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert "zone3_decisions.json" in manifest["files"]
