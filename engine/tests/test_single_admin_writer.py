"""Single-admin approval: REAL writer integration (no mocks).

The backend now lets one admin hold all three review stages; the engine writer
must accept identical citation/mapping reviewer names ONLY when
reviewer_role == "admin" — and the finalization validator must mirror the same
recorded-waiver rule so an admin-approved row survives replay.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
SCRIPT = ENGINE / "scripts" / "apply_decisions.py"
KEY = "a" * 64
SUBJECT = "b" * 64


def _decision(role: str) -> dict:
    return {"decisions": [{
        "finding_key": KEY,
        "review_subject_hash": SUBJECT,
        "review": {
            "decision": "approved",
            "reviewer_name": "Abu Naser Md. Nafew",
            "reviewer_role": role,
            "reviewed_at": "2026-08-02T12:00:00+00:00",
            "citation_checked": True, "mapping_checked": True, "status_checked": True,
            "citation_reviewer_name": "Abu Naser Md. Nafew",
            "mapping_reviewer_name": "Abu Naser Md. Nafew",
            "status_reviewer_name": "Abu Naser Md. Nafew",
            "correction_note": "single-admin synchronization test",
        },
    }]}


def _run_real_writer(tmp_path: Path, role: str) -> subprocess.CompletedProcess:
    root = tmp_path / f"root_{role.replace(' ', '_')}"
    (root / "submission/review").mkdir(parents=True)
    (root / "data/review").mkdir(parents=True)
    (root / "submission/review/decisions.template.json").write_text(json.dumps(
        [{"finding_key": KEY, "review_subject_hash": SUBJECT, "review": None}]))
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--domain", "findings", "--root", str(root)],
        input=json.dumps(_decision(role)), capture_output=True, text=True,
        cwd=ENGINE, timeout=120,
    ), root


def test_real_writer_accepts_identical_reviewers_for_admin(tmp_path):
    result, root = _run_real_writer(tmp_path, "admin")
    assert result.returncode == 0, result.stderr
    written = json.loads((root / "data/review/decisions.json").read_text())
    entry = next(item for item in written if item["finding_key"] == KEY)
    assert entry["review"]["decision"] == "approved"
    assert entry["review"]["reviewer_role"] == "admin"
    # the collapsed separation stays visible in the receipt
    assert (entry["review"]["citation_reviewer_name"]
            == entry["review"]["mapping_reviewer_name"])


def test_real_writer_rejects_identical_reviewers_for_non_admin(tmp_path):
    result, root = _run_real_writer(tmp_path, "Team Lead, Team zAI BD")
    assert result.returncode != 0
    assert "different people" in (result.stderr + result.stdout)
    assert not (root / "data/review/decisions.json").exists() or KEY not in \
        (root / "data/review/decisions.json").read_text()


def test_finalization_mirrors_the_admin_waiver():
    sys.path.insert(0, str(ENGINE))
    from packages.core.finalization import validate_final_finding, FinalizationError
    from packages.core.schemas import MappedFinding, ReviewDecision

    def finding(role: str) -> MappedFinding:
        f = MappedFinding(Economy="Thailand", **{
            "Law Name": "Example Act", "Indicator ID": "P7-I1",
            "Article / Section": "s. 1", "Discovery Tag": "NEW",
            "Location Reference": "#s1", "Verbatim Snippet": "The duty applies.",
            "Mapping Rationale": "Establishes the duty.",
            "Source URL": "https://official.example/act", "Confidence": 0.9,
            "Status": "in_force",
        })
        f.reviewer_decision = "approved"
        f.review = ReviewDecision(
            decision="approved", reviewer_name="A", reviewer_role=role,
            reviewed_at="2026-08-02T12:00:00+00:00",
            citation_checked=True, mapping_checked=True, status_checked=True,
            citation_reviewer_name="A", mapping_reviewer_name="A",
            status_reviewer_name="A")
        return f

    def errors_for(role: str) -> str:
        try:
            validate_final_finding(finding(role), artifacts={}, spans=None)
        except FinalizationError as error:
            return str(error)
        return ""

    assert "not independent" in errors_for("Team Lead")
    assert "not independent" not in errors_for("admin")
