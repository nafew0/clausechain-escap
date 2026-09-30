import os
import subprocess
from pathlib import Path

import pytest

from packages.core import review_layout
from scripts import prepare_review_inputs as prepare


def _write(path: Path, when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    os.utime(path, (when, when))


@pytest.fixture
def engine_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(review_layout.MODE_ENV, raising=False)
    for run in review_layout.HYBRID_RUNS:
        _write(tmp_path / "outputs" / run / "output.json", 1_000)
    _write(tmp_path / "submission" / "consolidated.json", 2_000)
    calls = []

    def fake_run(argv, *args, **kwargs):
        calls.append((argv[1], os.environ.get(review_layout.MODE_ENV)))
        failing = argv[1].endswith("champion_validate.py")
        return subprocess.CompletedProcess(argv, 1 if failing else 0)

    monkeypatch.setattr(prepare.subprocess, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["prepare_review_inputs.py"])
    yield tmp_path, calls
    os.environ.pop(review_layout.MODE_ENV, None)


def scripts(calls):
    return [script for script, _ in calls]


def test_unchanged_runs_only_export_the_bundle(engine_tree):
    _, calls = engine_tree
    assert prepare.changed_runs(review_layout.current()) == []
    assert prepare.main() == 0
    assert scripts(calls) == ["scripts/export_ui_bundle.py"]


def test_a_round2_rerun_is_rebuilt_before_export(engine_tree):
    root, calls = engine_tree
    _write(root / "outputs" / "final_r2_th_p6" / "output.json", 3_000)
    assert prepare.changed_runs(review_layout.current()) == ["final_r2_th_p6"]
    # champion_validate exits 1 (a FAIL report); the refresh still completes.
    assert prepare.main() == 0
    assert scripts(calls) == [
        "scripts/refute_new.py",
        "scripts/consolidate_submission.py",
        "scripts/zone3_score.py",
        "scripts/build_review_bundle.py",
        "scripts/champion_validate.py",
        "scripts/export_ui_bundle.py",
    ]  # recall adjudication stays round-1 only
    assert {mode for _, mode in calls} == {"hybrid"}


def test_a_failed_rebuild_step_stops_the_refresh(engine_tree, monkeypatch):
    root, calls = engine_tree
    _write(root / "outputs" / "final_si_p6" / "output.json", 3_000)
    monkeypatch.setattr(prepare.subprocess, "run", lambda argv, *a, **k: (
        calls.append((argv[1], None)) or subprocess.CompletedProcess(argv, 2 if "consolidate" in argv[1] else 0)))
    with pytest.raises(SystemExit):
        prepare.main()
    assert scripts(calls)[-1] == "scripts/consolidate_submission.py"
    assert "scripts/export_ui_bundle.py" not in scripts(calls)


def test_local_mode_builds_its_own_workspace_with_the_open_weights_model(engine_tree, monkeypatch):
    root, calls = engine_tree
    _write(root / "outputs" / "local_si_p6" / "output.json", 3_000)
    _write(root / "outputs" / "local_th_p7" / "output.json", 3_000)
    monkeypatch.setattr("sys.argv", ["prepare_review_inputs.py", "--mode", "local"])
    assert prepare.main() == 0
    # First Local refresh: no Local consolidated set yet, so every Local run is rebuilt;
    # recall runs on the round-1 run only; no hybrid UI bundle is exported.
    assert scripts(calls) == [
        "scripts/refute_new.py",
        "scripts/consolidate_submission.py",
        "scripts/adjudicate_recall.py",
        "scripts/zone3_score.py",
        "scripts/build_review_bundle.py",
        "scripts/champion_validate.py",
    ]
    assert {mode for _, mode in calls} == {"local"}
    layout = review_layout.current()
    assert layout.runs == ("local_si_p6", "local_th_p7")
    assert layout.provider_profile == "local_openweights"
    assert layout.consolidated == Path("submission/local/consolidated.json")


def test_local_keys_never_collide_with_hybrid_keys(monkeypatch):
    from packages.core.finalization import finding_key
    from packages.core.schemas import MappedFinding

    finding = MappedFinding.model_validate({
        "Economy": "Singapore", "Law Name": "PDPA 2012", "Indicator ID": "P6-I4",
        "Article / Section": "s. 26", "Discovery Tag": "KNOWN", "Verbatim Snippet": "x",
        "Mapping Rationale": "r", "Source URL": "https://example.test", "Confidence": 1,
        "Location Reference": "s. 26",
    })
    monkeypatch.delenv(review_layout.MODE_ENV, raising=False)
    hybrid = finding_key(finding)
    monkeypatch.setenv(review_layout.MODE_ENV, "local")
    assert finding_key(finding) != hybrid


def test_a_cancelled_refresh_resumes_without_repeating_model_calls(engine_tree, monkeypatch):
    root, calls = engine_tree
    _write(root / "outputs" / "local_si_p6" / "output.json", 3_000)
    _write(root / "outputs" / "local_ma_p6" / "output.json", 3_000)
    # The refuter and zone-3 already finished Singapore before the cancel.
    _write(root / "data" / "review" / "refutation_local_si_p6.json", 4_000)
    _write(root / "data" / "zone3" / "local" / "singapore_p6_scores.json", 4_000)
    monkeypatch.setattr(prepare.subprocess, "run", lambda argv, *a, **k: (
        calls.append((" ".join(argv[1:]), None)) or subprocess.CompletedProcess(argv, 0)))
    monkeypatch.setattr("sys.argv", ["prepare_review_inputs.py", "--mode", "local"])
    assert prepare.main() == 0
    commands = [command for command, _ in calls]
    assert "scripts/refute_new.py outputs/local_ma_p6" in commands
    assert "scripts/zone3_score.py outputs/local_ma_p6" in commands
    assert not any("local_si_p6" in command for command in commands
                   if command.startswith(("scripts/refute_new.py", "scripts/zone3_score.py")))
