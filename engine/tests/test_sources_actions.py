import json

import httpx

from scripts import archive_sources


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def test_clear_downloads_archives_everything_and_deletes_nothing(tmp_path, monkeypatch):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("CLAUSECHAIN_EVENT_LOG", str(events))
    raw = tmp_path / "data/raw/la"
    raw.mkdir(parents=True)
    (raw / "seeds_manifest.json").write_text("{}")
    (raw / "seed_abc.pdf").write_bytes(b"%PDF-1.7")
    cache = tmp_path / "data/cache"
    cache.mkdir(parents=True)
    (cache / "embeddings_la__bge-m3.json").write_text("{}")
    (cache / "embeddings_th__bge-m3.json").write_text("{}")  # another economy: untouched

    record = archive_sources.archive("Lao PDR", root=tmp_path)

    assert not raw.exists()
    archived = tmp_path / record["moved"][0]["to"]
    assert (archived / "seed_abc.pdf").read_bytes() == b"%PDF-1.7"
    assert (archived / "seeds_manifest.json").is_file()
    assert (tmp_path / record["moved"][1]["to"]).is_file()
    assert (cache / "embeddings_th__bge-m3.json").is_file()
    assert json.loads((archived.parent / "ARCHIVED.json").read_text())["economy"] == "Lao PDR"
    assert any("nothing deleted" in e["message"] for e in _events(events))


def test_each_download_is_recorded_for_the_run_record(tmp_path, monkeypatch):
    from packages.connectors import seeds_fetch

    monkeypatch.chdir(tmp_path)
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("CLAUSECHAIN_EVENT_LOG", str(events))
    monkeypatch.setattr(seeds_fetch, "POLITE_DELAY_S", 0.0)
    url = "https://bol.gov.la/law.pdf"
    (tmp_path / "data").mkdir()
    (tmp_path / "data/seeds_r2.json").write_text(json.dumps({"economies": {"Lao PDR": [
        {"act": "Law on Electronic Data Protection", "url": url, "indicator_code": "P7-I1"},
        {"act": "Gone decree", "url": "https://bol.gov.la/gone.pdf", "indicator_code": "P7-I2"}]}}))

    def fake_get(self, requested, **kwargs):
        request = httpx.Request("GET", requested)
        if requested.endswith("gone.pdf"):
            return httpx.Response(404, request=request, content=b"")
        return httpx.Response(200, request=request, content=b"%PDF-" + b"x" * 2048,
                              headers={"content-type": "application/pdf"})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(seeds_fetch, "_browser_fetch", lambda url: None)
    seeds_fetch.fetch_seeds("Lao PDR", ("P7",), seeds_path="data/seeds_r2.json")

    details = [json.loads(e["detail"]) for e in _events(events) if e["stage"] == "fetch" and e["detail"]]
    [download] = [d for d in details if d["kind"] == "download"]
    assert (download["url"], download["file_type"], download["bytes"]) == (url, "PDF", 2053)
    assert download["fetched_at"]
    assert [d["kind"] for d in details if d["url"].endswith("gone.pdf")] == ["dead"]

    # A second pass fetches nothing: the archived document is reused, not re-downloaded.
    events.unlink()
    seeds_fetch.fetch_seeds("Lao PDR", ("P7-I1",), seeds_path="data/seeds_r2.json")
    kinds = [json.loads(e["detail"])["kind"] for e in _events(events) if e["stage"] == "fetch" and e["detail"]]
    assert kinds == ["cached"]
