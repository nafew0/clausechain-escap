import json

from packages.providers import cost


def test_stage_spend_goes_to_its_own_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cost.reset()
    assert cost.append_stage_log("refuter") is None          # no model calls, nothing written
    assert not (tmp_path / "logs").exists()

    cost.record("openai/gpt-6-luna", 1_000_000, 100_000)     # $0.10 in + $0.05 out
    entry = cost.append_stage_log("zone3-judges", {"provider_profile": "hybrid_accuracy"})
    cost.reset()

    assert entry["stage"] == "zone3-judges" and entry["total_usd"] == 0.15
    ledger = json.loads((tmp_path / "logs" / "review_cost_report.json").read_text())
    assert [row["stage"] for row in ledger] == ["zone3-judges"]
    assert ledger[0]["provider_profile"] == "hybrid_accuracy"
    # the per-run ledger the app matches to runs is untouched
    assert not (tmp_path / "logs" / "cost_report.json").exists()
