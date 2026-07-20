"""Build the SG corpus: acquire acts from SSO, parse, and load RuleUnits into the graph.

Usage (from engine/):
    .venv/bin/python scripts/build_sg_corpus.py                  # default acts
    GRAPH_BACKEND=sqlite .venv/bin/python scripts/build_sg_corpus.py

Loads into the GraphStore selected by GRAPH_BACKEND (.env) and ALWAYS also into
SQLite (Path A parity), so both backends stay in sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.envfile import load_env_file  # noqa: E402

load_env_file()

import os  # noqa: E402
import hashlib  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from packages.connectors.sg_sso import acquire_act  # noqa: E402
from packages.core.rule_units import build_rule_units  # noqa: E402
from packages.core.evidence import source_artifact_from_file  # noqa: E402
from packages.core.legal_controls import resolve_status  # noqa: E402
from packages.core.schemas import TextSpan  # noqa: E402
from packages.extractors.html_act import parse_sso_act  # noqa: E402
from packages.graph.store import get_graph_store  # noqa: E402

import yaml  # noqa: E402


def corpus_acts() -> list[tuple[str, str | None]]:
    pack = yaml.safe_load((Path(__file__).resolve().parents[1] /
                           "configs/jurisdictions/sg.yaml").read_text())
    return [(a["ref"], a.get("number")) for a in pack.get("corpus_acts", [])]


def load_act(act_ref: str, law_number_ref: str | None, stores, generation: str,
             kind: str = "Act", source_type: str = "act") -> int:
    cached = Path(f"data/raw/sg/{act_ref}.manifest.json")
    manifest = (__import__("json").loads(cached.read_text()) if cached.is_file()
                else acquire_act(act_ref, kind=kind))
    html = Path(manifest["html_path"]).read_text(encoding="utf-8")
    doc = parse_sso_act(html, manifest["url"])
    units = build_rule_units(doc, economy="Singapore", act_ref=act_ref,
                             law_number_ref=law_number_ref)
    status = resolve_status(
        fact_url=manifest["url"],
        fact_text=f"Singapore Statutes Online current version as at {doc.current_as_at}",
        current_as_at=doc.current_as_at,
    )
    raw_access = str(manifest["access_date"])
    accessed = datetime.fromisoformat(raw_access.replace("Z", "+00:00"))
    if accessed.tzinfo is None:
        accessed = accessed.replace(tzinfo=timezone.utc)
    artifact = source_artifact_from_file(
        manifest["html_path"], original_url=manifest["url"], source_type=source_type,
        status_evidence=status, accessed_at=accessed, register_id=act_ref,
        version_id=doc.current_as_at, official_domains={"sso.agc.gov.sg"},
        expected_mime="text/html",
    )
    spans = []
    offset = 0
    for unit in units:
        unit.metadata["archived_copy"] = manifest["html_path"]
        unit.metadata["access_date"] = manifest["access_date"]
        unit.metadata["content_sha256"] = manifest["sha256"]
        unit.metadata["legal_status"] = status.status
        unit.metadata["evidence_eligible"] = True
        unit.metadata["source_type"] = source_type
        unit.metadata["build_generation"] = generation
        unit.metadata["status_evidence"] = status.model_dump(mode="json")
        unit.source_artifact_id = artifact.id
        span_id = "span:" + hashlib.sha256(
            f"{artifact.id}:{unit.id}:{unit.text}".encode()).hexdigest()
        spans.append(TextSpan(id=span_id, source_artifact_id=artifact.id, page_number=1,
            text=unit.text, start_char=offset, end_char=offset + len(unit.text),
            bbox=(0.0, 0.0, 0.0, 0.0), reading_order=len(spans),
            extraction_method="sso_html_dom", engine_version="clausechain-html-v1"))
        offset += len(unit.text) + 1
        unit.linked_span_ids = [span_id]
        # build_rule_units retains the complete parent section as raw_context.
    for store in stores:
        if hasattr(store, "upsert_source_artifact"):
            store.upsert_source_artifact(artifact)
        if hasattr(store, "upsert_text_spans"):
            store.upsert_text_spans(spans)
        if hasattr(store, "upsert_rule_units"):   # batched (Neo4j UNWIND)
            store.upsert_rule_units(units)
        else:
            for unit in units:
                store.upsert_rule_unit(unit)
    print(f"{act_ref}: {doc.law_name!r} | current as at {doc.current_as_at} | "
          f"{len(doc.sections)} sections -> {len(units)} rule units")
    return len(units)


def _sso_ref(url: str) -> tuple[str, str] | None:
    """sso.agc.gov.sg URL -> (collection, ref): /Act/PDPA2012 or /SL/PDPA2012-S63-2021."""
    import re

    m = re.search(r"sso\.agc\.gov\.sg/(Act|SL)/([A-Za-z0-9.\-]+)", url)
    return (m.group(1), m.group(2)) if m else None


def load_seed_documents(stores, generation: str, loaded_refs: set[str]) -> int:
    """Seeds-manifest phase (Sol review, 19 Jul): P6/P7 seed rows beyond the core
    corpus_acts — SSO subsidiary legislation via the same print-view parser, and
    treaty PDFs via the generic PDF extractor with the treaty grammar. Everything
    is profile-driven from seeds.json data; nothing here names a target."""
    import json
    import yaml as _yaml

    from packages.connectors.seeds_fetch import fetch_seeds
    from packages.connectors.sg_sso import acquire_act
    from packages.core.legal_controls import content_eligibility, evidence_eligibility
    from packages.extractors.pdf import extract_pdf, materialize_page_evidence
    from packages.extractors.pdf_act import parse_act_text
    from packages.ingest.seed_profiles import seed_fingerprint_config, seed_parse_profile

    fetch_seeds("Singapore", ("P6", "P7"))
    manifest = json.loads(Path("data/raw/sg/seeds_manifest.json").read_text())
    pack = _yaml.safe_load((Path(__file__).resolve().parents[1] /
                            "configs/jurisdictions/sg.yaml").read_text())
    assertions = pack.get("status_assertions") or {}
    total = 0
    for url, entry in manifest.items():
        if not str(entry.get("indicator_code", "")).startswith(("P6", "P7")):
            continue
        act_name = (entry.get("act") or "").strip()
        profile = seed_parse_profile(entry)
        sso = _sso_ref(url)
        if sso:
            collection, ref = sso
            if ref in loaded_refs:
                continue  # already loaded from corpus_acts
            loaded_refs.add(ref)
            try:
                total += load_act(ref, None, stores, generation, kind=collection,
                                  source_type=profile["source_type"])
            except Exception as error:  # noqa: BLE001 — one blocked fetch must not kill the build
                print(f"  FAILED SSO {collection}/{ref}: {error}")
            continue
        # Non-SSO official document (treaty PDF on a whitelisted state domain)
        if entry.get("status") != "ok" or not str(entry.get("file", "")).endswith(".pdf"):
            continue
        file = entry["file"]
        assertion = assertions.get(act_name) or {}
        status = resolve_status(
            fact_url=assertion.get("fact_url", url),
            fact_text=assertion.get("fact_text",
                                    "Official source archived; currentness not yet asserted"),
            current_as_at=assertion.get("current_as_at"),
            effective_date=assertion.get("effective_date"),
            explicit_status=assertion.get("status"),
        )
        eligible, reason = evidence_eligibility(act_name, profile["source_type"], status.status)
        if not eligible:
            print(f"  INELIGIBLE {act_name[:52]}: {reason}")
            continue
        from urllib.parse import urlparse

        # G3 integrity (Sol review #3): domains come from the pack's pre-approved
        # official_sources list, never from the URL being processed.
        pack_domains = {s["domain"] for s in pack.get("official_sources", [])}
        host = urlparse(url).hostname or ""
        if not any(host == d or host.endswith("." + d.removeprefix("www."))
                   or ("www." + host.removeprefix("www.")) == d for d in pack_domains):
            print(f"  INELIGIBLE {act_name[:52]}: SOURCE_DOMAIN_NOT_PREAPPROVED ({host})")
            continue
        artifact = source_artifact_from_file(
            file, original_url=url, retrieved_url=url,
            source_type=profile["source_type"], status_evidence=status,
            accessed_at=datetime.now(timezone.utc),
            official_domains=pack_domains,
            expected_mime="application/pdf",
        )
        if not artifact.official:
            print(f"  INELIGIBLE {act_name[:52]}: NON_OFFICIAL_ARCHIVE")
            continue
        from packages.core.fingerprint import processing_fingerprint

        fingerprint = processing_fingerprint(
            artifact.sha256, profile["source_type"],
            config=seed_fingerprint_config(entry))
        restamp_counts = [st.restamp_artifact_generation("Singapore", fingerprint, generation)
                          if hasattr(st, "restamp_artifact_generation") else 0
                          for st in stores]
        if restamp_counts and all(c > 0 for c in restamp_counts):
            total += restamp_counts[0]
            print(f"  {act_name[:58]:58s} -> unchanged, {restamp_counts[0]} units restamped")
            continue
        try:
            pages = extract_pdf(file)
            content_ok, content_reason = content_eligibility([p.text for p in pages])
            if not content_ok:
                print(f"  INELIGIBLE {act_name[:52]}: {content_reason}")
                continue
            page_artifacts, text_spans = materialize_page_evidence(pages, artifact.id)
            units = parse_act_text(pages, economy="Singapore", act_name=act_name,
                                   act_ref=Path(file).stem.replace("seed_", ""),
                                   source_url=url,
                                   extra_section_patterns=profile["extra_section_patterns"],
                                   citation_template=profile["citation_template"])
        except Exception as error:  # noqa: BLE001
            print(f"  FAILED {act_name[:50]}: {error}")
            continue
        from packages.ingest.seed_profiles import missing_expectations

        missing = missing_expectations(entry, units)
        if missing:
            print(f"  FAILED EXPECTED_EVIDENCE {act_name[:45]}: missing {missing}")
            continue
        from packages.extractors.pdf_align import align_and_bind_pdf_evidence

        aligned, unit_count = align_and_bind_pdf_evidence(units, [file], [text_spans])
        if aligned != unit_count:
            print(f"  ALIGNMENT REVIEW {act_name[:45]}: {aligned}/{unit_count} exact")
        for unit in units:
            unit.metadata["archived_copy"] = file
            unit.metadata["access_date"] = entry.get("access_date")
            unit.metadata["content_sha256"] = artifact.sha256
            unit.metadata["legal_status"] = status.status
            unit.metadata["evidence_eligible"] = eligible
            unit.metadata["source_type"] = profile["source_type"]
            unit.metadata["processing_fingerprint"] = fingerprint
            unit.metadata["build_generation"] = generation
            unit.metadata["status_evidence"] = status.model_dump(mode="json")
            unit.source_artifact_id = artifact.id
            unit.raw_context = unit.raw_context or unit.text
        for st in stores:
            if hasattr(st, "upsert_source_artifact"):
                st.upsert_source_artifact(artifact)
            if hasattr(st, "upsert_page_artifacts"):
                st.upsert_page_artifacts(page_artifacts)
                st.upsert_text_spans(text_spans)
            if hasattr(st, "upsert_rule_units"):
                st.upsert_rule_units(units)
            else:
                for unit in units:
                    st.upsert_rule_unit(unit)
        total += len(units)
        print(f"  {act_name[:52]:52s} [{profile['source_type']:>7s}] -> {len(units):5d} units")
    return total


def main() -> int:
    backend = (os.getenv("GRAPH_BACKEND") or "sqlite").lower()
    primary = get_graph_store()
    stores = [primary]
    if backend != "sqlite":  # keep the Path A SQLite store in sync too
        from packages.graph.sqlite_graph import SqliteGraphStore

        stores.append(SqliteGraphStore())
    print(f"graph backend: {backend} (+ sqlite parity)" if len(stores) > 1
          else "graph backend: sqlite")
    for store in stores:
        if hasattr(store, "purge_ineligible_provisions"):
            store.purge_ineligible_provisions("Singapore")

    total = 0
    generation = datetime.now(timezone.utc).isoformat()
    loaded_refs: set[str] = set()
    for act_ref, number in corpus_acts():
        total += load_act(act_ref, number, stores, generation)
        loaded_refs.add(act_ref)

    # Seeds phase: subsidiary legislation + treaty PDFs from the research seeds.
    total += load_seed_documents(stores, generation, loaded_refs)

    for store in stores:
        if hasattr(store, "prune_economy_generation"):
            store.prune_economy_generation("Singapore", generation)

    for store in stores:
        hits = store.search_provisions("transfer personal data outside Singapore",
                                       economy="Singapore", limit=5)
        top = hits[0] if hits else None
        print(f"{type(store).__name__}: search smoke -> {len(hits)} hits; "
              f"top: {top['props'].get('article_section') if top and top.get('props') else (top['provision_id'] if top else None)}")
    print(f"TOTAL rule units: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
