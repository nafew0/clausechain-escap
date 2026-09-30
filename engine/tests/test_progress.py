import json

from packages.core import progress


def test_events_stream_to_stderr_and_event_log_with_labels(tmp_path, monkeypatch, capsys):
    log = tmp_path / "events.jsonl"
    monkeypatch.setenv("CLAUSECHAIN_EVENT_LOG", str(log))
    token = progress.set_label("P6-I4 · screen")
    progress.emit("screen", "batch 1/3: 2 of 12 kept", detail="PDPA s. 28\nPDPA s. 29")
    progress.reset_label(token)
    progress.emit("done", "finished")
    err = capsys.readouterr().err
    assert "SCREEN" in err and "P6-I4 · screen · batch 1/3" in err
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert [e["stage"] for e in events] == ["screen", "done"]
    assert events[0]["label"] == "P6-I4 · screen" and "s. 29" in events[0]["detail"]
    assert events[1]["label"] == "" and events[1]["seq"] > events[0]["seq"]


def test_parallel_model_calls_keep_the_callers_label(tmp_path, monkeypatch):
    from pydantic import BaseModel

    from packages.providers.llm_providers import OpenAIChatProvider

    class Out(BaseModel):
        ok: bool

    log = tmp_path / "events.jsonl"
    monkeypatch.setenv("CLAUSECHAIN_EVENT_LOG", str(log))
    provider = OpenAIChatProvider("m", base_url="http://local.test/v1", concurrency=3)
    monkeypatch.setattr(provider, "complete",
                        lambda prompt, schema, prompt_cache_key=None: (
                            progress.emit("llm", f"call {prompt}"), Out(ok=True))[1])
    token = progress.set_label("P7-I1 · map")
    results = provider.complete_many(["a", "b", "c"], Out)
    progress.reset_label(token)
    assert len(results) == 3
    labels = sorted(json.loads(line)["label"] for line in log.read_text().splitlines())
    assert labels == ["P7-I1 · map 1/3", "P7-I1 · map 2/3", "P7-I1 · map 3/3"]
