from __future__ import annotations

from datetime import datetime, timezone

from packages.core.schemas import (PageArtifact, RuleUnit, SourceArtifact,
                                   StatusEvidence, TextSpan)
from packages.graph.neo4j_client import Neo4jGraphStore
from packages.graph.sqlite_graph import SqliteGraphStore
from packages.graph.sqlite_graph import GRAPH_SCHEMA_VERSION
from packages.graph.store import get_graph_store


def _rule_unit() -> RuleUnit:
    return RuleUnit(
        id="sg-pdpa-2012-s26-1",
        document_id="doc-1",
        economy="Singapore",
        law_name="Personal Data Protection Act 2012",
        article_section="s. 26(1)",
        text="An organisation shall not transfer any personal data ...",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
        location_reference="Part 6, s. 26(1)",
    )


def test_sqlite_store_upserts_rule_unit(tmp_path) -> None:
    store = SqliteGraphStore(db_path=tmp_path / "graph.db")
    uri = store.upsert_rule_unit(_rule_unit())
    assert uri == "sqlite://rule-unit/sg-pdpa-2012-s26-1"
    assert store.count_nodes() == 3  # Instrument + Section + Provision
    store.upsert_rule_unit(_rule_unit())  # idempotent
    assert store.count_nodes() == 3
    assert store.schema_version() == GRAPH_SCHEMA_VERSION
    store.close()


def test_factory_defaults_to_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GRAPH_BACKEND", raising=False)
    store = get_graph_store(db_path=tmp_path / "g.db")
    assert isinstance(store, SqliteGraphStore)


def test_factory_env_swap_to_neo4j(monkeypatch) -> None:
    monkeypatch.setenv("GRAPH_BACKEND", "neo4j")
    assert isinstance(get_graph_store(), Neo4jGraphStore)


def test_sqlite_rejects_incompatible_schema_version(tmp_path) -> None:
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("create table graph_metadata(key text primary key,value text not null)")
    conn.execute("insert into graph_metadata values('schema_version','1')")
    conn.commit(); conn.close()
    store = SqliteGraphStore(path)
    import pytest
    with pytest.raises(RuntimeError, match="incompatible"):
        store.schema_version()


def test_generation_prune_removes_only_stale_provisions(tmp_path) -> None:
    store = SqliteGraphStore(tmp_path / "g.db")
    old = _rule_unit().model_copy(deep=True); old.id = "old"; old.metadata["build_generation"] = "old"
    new = _rule_unit().model_copy(deep=True); new.id = "new"; new.metadata["build_generation"] = "new"
    store.upsert_rule_unit(old); store.upsert_rule_unit(new)
    assert store.prune_economy_generation("Singapore", "new") == 1
    ids = {r[0] for r in store._connect().execute("select id from nodes where label='Provision'")}
    assert ids == {"provision:new"}


class _FakeResult:
    def __init__(self, version=GRAPH_SCHEMA_VERSION): self.version = version
    def single(self): return {"version": self.version}
    def __iter__(self): return iter(())


class _FakeSession:
    def __init__(self, calls): self.calls = calls
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def run(self, query, **params):
        self.calls.append((query, params)); return _FakeResult()


class _FakeDriver:
    def __init__(self): self.calls = []
    def session(self): return _FakeSession(self.calls)
    def close(self): pass


def test_neo4j_mirrors_artifact_page_span_and_schema_ids() -> None:
    store = Neo4jGraphStore(); driver = _FakeDriver(); store._driver = driver
    status = StatusEvidence(status="in_force", fact_url="https://official.example",
        fact_text="Official in force", resolution_rule="official field")
    artifact = SourceArtifact(id="sha256:" + "a" * 64,
        original_url="https://official.example/a", retrieved_url="https://official.example/a.pdf",
        source_type="act", mime_type="application/pdf", byte_length=100, sha256="a" * 64,
        accessed_at=datetime.now(timezone.utc), official_domain="official.example", official=True,
        local_path="data/a.pdf", status_evidence=status)
    page = PageArtifact(id=f"{artifact.id}:p1", source_artifact_id=artifact.id, page_number=1,
        width=600, height=800, route="NATIVE_SIMPLE", route_reasons=["native"], raw_text="Law",
        searchable_text="law", page_image_sha256="b" * 64, span_ids=[f"{artifact.id}:p1:s0"])
    span = TextSpan(id=f"{artifact.id}:p1:s0", source_artifact_id=artifact.id, page_number=1,
        text="Law", start_char=0, end_char=3, bbox=(1, 2, 3, 4), reading_order=0,
        extraction_method="pymupdf_rawdict", engine_version="1")
    store.upsert_source_artifact(artifact); store.upsert_page_artifacts([page])
    store.upsert_text_spans([span])
    assert store.schema_version() == GRAPH_SCHEMA_VERSION
    cypher = "\n".join(query for query, _ in driver.calls)
    assert "SourceArtifact" in cypher and "PageArtifact" in cypher and "TextSpan" in cypher
    assert "HAS_PAGE" in cypher and "HAS_SPAN" in cypher
