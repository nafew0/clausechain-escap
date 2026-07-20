"""ClauseChain pipeline orchestrator — the real P1 pipeline (SG × Pillar 6 first).

Stages: jurisdiction pack -> corpus (acquire+parse+graph-load, cached) ->
per-indicator broad-recall retrieval -> LLM screen (bulk) -> LLM mapping (high)
-> deterministic gates G1/G3/G4 -> NEW/KNOWN diff -> MappedFinding rows.
Indicators with no surviving evidence emit an explicit "no provision found" row
citing the governing law (never blank — 15-Jun rule).
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from packages.core.citations import citation_path
from packages.core.schemas import (CitationProof, GateResult, MappedFinding, RunEnvelope,
                                   SearchCoverageManifest)

ECONOMY_NAMES = {"SG": "Singapore", "MY": "Malaysia", "AU": "Australia"}
CODE_BY_NAME = {name.upper(): code for code, name in ECONOMY_NAMES.items()}
ENGINE_ROOT = Path(__file__).resolve().parents[2]

def _pack_corpus_acts(pack: dict) -> list[tuple[str, str | None]]:
    acts = [(a["ref"], a.get("number")) for a in pack.get("corpus_acts", [])]
    return acts or [("PDPA2012", "No. 26 of 2012")]


def _load_yaml(rel_path: str) -> dict:
    return yaml.safe_load((ENGINE_ROOT / rel_path).read_text(encoding="utf-8"))


def _partition_current_anchors(candidates: list, gold_anchor_ids: set[str]) -> tuple[list, list]:
    anchors = [candidate for candidate in candidates
               if candidate.provision_id in gold_anchor_ids]
    rest = [candidate for candidate in candidates
            if candidate.provision_id not in gold_anchor_ids]
    return anchors, rest


def _whitelist(pack: dict) -> set[str]:
    domains = {s["domain"].lower() for s in pack.get("official_sources", [])}
    mined = pack.get("whitelist_source")
    if mined and (ENGINE_ROOT / mined).is_file():
        import json

        data = json.loads((ENGINE_ROOT / mined).read_text())
        for economy_block in data.get("economies", {}).values():
            domains.update(d.lower() for d in economy_block.get("official_whitelist", {}))
    return domains


def _ensure_corpus(store, pack: dict, economy: str) -> list[dict]:
    """Return the economy's provision corpus, auto-building it for SG (whose
    connector is fully automatic). MY/AU corpora are built by their build
    scripts (seeds-driven PDF/HTML paths); an empty corpus raises with the
    command to run."""
    from packages.retrieval.hybrid import load_corpus

    corpus = load_corpus(store, economy)
    if corpus:
        return corpus
    import os
    if os.getenv("CLAUSECHAIN_OFFLINE") == "1":
        raise RuntimeError(f"offline-eval requires a prebuilt v2 corpus for {economy}")
    # MY/AU: auto-chain the corpus build (fresh-clone contract — one command, no
    # manual steps). The build scripts fetch seeds themselves when missing.
    import subprocess
    import sys as _sys

    script_code = {"Singapore": "sg", "Malaysia": "my", "Australia": "au"}[economy]
    script = ENGINE_ROOT / f"scripts/build_{script_code}_corpus.py"
    if script.is_file():
        print(f"[corpus] {economy} corpus empty — building via {script.name} (first run only)")
        result = subprocess.run([_sys.executable, str(script)], cwd=ENGINE_ROOT)
        if result.returncode == 0:
            corpus = load_corpus(store, economy)
            if corpus:
                return corpus
    raise RuntimeError(
        f"No corpus loaded for {economy}. Build it manually: "
        f".venv/bin/python scripts/build_{economy[:2].lower()}_corpus.py"
    )


def _absence_row(economy: str, indicator_id: str, governing_law: str,
                 source_url: str, model_version: str,
                 coverage: SearchCoverageManifest, governing_props: dict | None = None) -> MappedFinding:
    governing_props = governing_props or {}
    status_fact = governing_props.get("status_evidence") or {}
    return MappedFinding(
        economy=economy,
        law_name=governing_law,
        indicator_id=indicator_id,
        article_section="n/a",
        discovery_tag="KNOWN",
        location_reference="n/a",
        verbatim_snippet="NO_EVIDENCE_FOUND_PENDING_REVIEW",
        mapping_rationale=(
            f"No qualifying provision found for {indicator_id} after a full-corpus sweep. "
            "The configured governing law is cited as the reference basis (score-0 pattern, A3)."
        ),
        source_url=source_url,
        confidence=0.6,
        notes="Absence row (NO_EVIDENCE_FOUND_PENDING_REVIEW): human approval required "
              "before this becomes a score-0 final row (P3.5 A3).",
        coverage="Horizontal",
        status=governing_props.get("legal_status", "unknown"),
        status_evidence=(status_fact.get("fact_text") if isinstance(status_fact, dict)
                         else "absence conclusion pending human review"),
        status_evidence_record=status_fact if isinstance(status_fact, dict) and status_fact else None,
        model_version=model_version,
        reviewer_decision="pending",
        search_coverage_manifest=coverage,
        source_artifact_id=governing_props.get("source_artifact_id"),
    )


def _governing_props(corpus: list[dict], law_name: str) -> dict:
    from packages.discovery.diff import laws_match

    hit = next((row["props"] for row in corpus
                if laws_match(law_name, row["props"].get("law_name", ""))), None)
    return hit or {}


def _coverage_manifest(economy: str, indicator_id: str, cfg: dict, pack: dict,
                       warnings: list[str], corpus: list[dict], candidates: list | None = None
                       ) -> SearchCoverageManifest:
    from packages.core.acquisition import (format_acquisition_failure,
                                           unresolved_seed_acquisitions)
    from packages.discovery.diff import laws_match
    from packages.retrieval.hybrid import build_query_pack

    instruments: dict[str, dict] = {}
    for row in corpus:
        props = row.get("props", {})
        law = props.get("law_name", "")
        if law and law not in instruments:
            instruments[law] = {
                "instrument": law,
                "searched": True,
                "source_artifact_id": props.get("source_artifact_id"),
                "legal_status": props.get("legal_status"),
                "evidence_eligible": props.get("evidence_eligible", False),
            }
    queries = build_query_pack(indicator_id, cfg)
    query_counts = {q: 0 for q in queries}
    for candidate in candidates or []:
        for query in set(candidate.matched_queries):
            if query in query_counts:
                query_counts[query] += 1
    unresolved = [w for w in warnings if "RECALL HOLE" in w and indicator_id in w]
    for record in instruments.values():
        if not record["source_artifact_id"]:
            unresolved.append(f"{record['instrument']}: missing SourceArtifact")
    # A dead or never-attempted configured source is a search-coverage failure,
    # never proof of legal absence.  An alternate successfully loaded official
    # copy of the same instrument satisfies the failed URL (e.g. an SSO print-view
    # acquisition replacing a blocked ordinary landing-page fetch).
    acquisition_failures = unresolved_seed_acquisitions(
        economy, indicator_id, ENGINE_ROOT)
    loaded_laws = [record["instrument"] for record in instruments.values()
                   if record.get("source_artifact_id")
                   and record.get("legal_status") == "in_force"
                   and record.get("evidence_eligible") is True]
    for failure in acquisition_failures:
        if any(laws_match(failure.get("act", ""), law) for law in loaded_laws):
            continue
        unresolved.append(format_acquisition_failure(failure))
    return SearchCoverageManifest(
        economy=economy,
        indicator_id=indicator_id,
        portals=[s.get("name", s.get("domain", "")) for s in pack.get("official_sources", [])],
        instruments=list(instruments),
        queries=queries,
        exclusions=[w for w in warnings if "INELIGIBLE" in w],
        caps=[w for w in warnings if "screened top" in w],
        unresolved_failures=sorted(set(unresolved)),
        instrument_results=list(instruments.values()),
        query_result_counts=query_counts,
    )


def _stub_envelope(code: str, economy: str, pillar: int, provider_profile: str) -> RunEnvelope:
    """Deterministic offline envelope: schema/contract tests + keyless sandboxes (no network, no LLM)."""
    finding = MappedFinding(
        economy=economy,
        law_name="Personal Data Protection Act 2012",
        law_number_ref="No. 26 of 2012",
        last_amended="2020",
        indicator_id=f"P{pillar}-I4" if pillar == 6 else f"P{pillar}-I1",
        article_section="s. 26(1)",
        discovery_tag="KNOWN",
        location_reference="#pr26-",
        verbatim_snippet=(
            "An organisation must not transfer any personal data to a country or territory "
            "outside Singapore except in accordance with requirements prescribed under this Act"
        ),
        mapping_rationale="Stub row (CLAUSECHAIN_PIPELINE=stub): proves the export contract offline.",
        source_url="https://sso.agc.gov.sg/Act/PDPA2012#pr26-",
        confidence=0.99,
        notes="STUB-NON-SUBMITTABLE: offline contract fixture; no live crawling or LLM calls.",
        coverage="Horizontal",
        status="in_force",
        model_version="stub",
    )
    return RunEnvelope(
        run_id=f"stub-{code.lower()}-p{pillar}",
        country=code,
        pillar=pillar,
        provider_profile=provider_profile,
        findings=[finding],
        gates=[GateResult(gate_id="G0", status="PASS", reason="stub mode")],
        warnings=["CLAUSECHAIN_PIPELINE=stub: deterministic offline output."],
        metadata={"graph_required": False, "live_llm_calls": False, "live_ocr_calls": False},
    )


def run(country: str, pillar: int, provider_profile: str = "hybrid_accuracy") -> RunEnvelope:
    import os as _os

    raw0 = country.strip().upper()
    code0 = CODE_BY_NAME.get(raw0, raw0)
    if _os.getenv("CLAUSECHAIN_PIPELINE", "").lower() == "stub":
        if not (_os.getenv("PYTEST_CURRENT_TEST") or
                _os.getenv("CLAUSECHAIN_ALLOW_STUB_FOR_TESTS") == "1"):
            raise RuntimeError("stub pipeline is test-only and cannot produce user-facing output")
        return _stub_envelope(code0, ECONOMY_NAMES.get(code0, country.strip()), pillar, provider_profile)

    from packages.discovery.diff import KnownIndex
    from packages.core.corpus_fingerprint import corpus_fingerprint
    from packages.graph.store import get_graph_store
    from packages.providers.model_router import resolve_embedding, resolve_llm
    from packages.rdtii.mapper import SCREEN_CAP_PER_INDICATOR, map_candidates, screen_candidates
    from packages.retrieval.hybrid import EmbeddingCache, retrieve_for_indicator
    from packages.verifier.gates import run_gates

    started = time.time()
    raw = country.strip().upper()
    code = CODE_BY_NAME.get(raw, raw)
    economy = ECONOMY_NAMES.get(code, country.strip())
    if code not in ECONOMY_NAMES:
        raise ValueError(f"Unknown Round-1 economy: {country!r} (SG/MY/AU)")

    pack = _load_yaml(f"configs/jurisdictions/{code.lower()}.yaml")
    rubric = _load_yaml(f"configs/rdtii/pillar_{pillar}.yaml")
    whitelist = _whitelist(pack)
    store = get_graph_store()
    corpus = _ensure_corpus(store, pack, economy)

    llm_bulk = resolve_llm(provider_profile, tier="bulk")
    llm_high = resolve_llm(provider_profile, tier="high_reasoning")
    llm_escalation = resolve_llm(provider_profile, tier="legal_escalation")
    embedder = resolve_embedding(provider_profile)
    cache = EmbeddingCache(embedder, f"data/cache/embeddings_{code.lower()}.json")
    known = KnownIndex()
    model_version = (f"{getattr(llm_high.primary, 'model', 'llm')}"
                     f"/escalate:{getattr(llm_escalation.primary, 'model', 'llm')}"
                     f"+{getattr(embedder, 'model', 'emb')}")

    findings: list[MappedFinding] = []
    gates_out: list[GateResult] = []
    warnings: list[str] = []
    stats = {"candidates": 0, "screened_in": 0, "mapped": 0, "gate_rejected": 0,
             "nano_mappings": 0, "mini_escalations": 0, "escalation_reasons": {},
             "by_indicator": {}}

    for indicator_id, cfg in rubric.get("indicators", {}).items():
        if cfg.get("regulatory") is False:
            continue  # 6.5: non-regulatory — engine does not extract
        retrieval_caps: list[dict] = []
        candidates = retrieve_for_indicator(store, cache, corpus, indicator_id, cfg, economy,
                                            caps_out=retrieval_caps)
        for cap in retrieval_caps:
            warnings.append(f"{indicator_id}: retrieval union capped at {cap['limit']} of "
                            f"{cap['input_count']} candidates (cap logged, not silent)")
        # Source-type scoping now happens INSIDE retrieval, before ranking/caps
        # (rubric `allowed_source_types`; default excludes treaties) — see
        # packages/retrieval/hybrid.py.
        indicator_stats = {"candidate_count": len(candidates), "resolved_known_anchors": 0,
                           "candidate_recall": None, "screen_survival_recall": None,
                           "mapper_survival_recall": None, "gate_survival_recall": None,
                           "injected_anchor_count": 0, "caps": retrieval_caps}
        # KNOWN-RECALL INJECTION (reviewer, 9 Jul): every master-known (law+section)
        # for this economy must reach the mapper regardless of retrieval rank. Missing
        # from the corpus entirely -> loud warning (a recall hole to fix, never silent).
        have_ids = {c.provision_id for c in candidates}
        organic_ids = set(have_ids)  # what retrieval found before injection (L2)
        from packages.discovery.diff import (laws_match as _lm, section_base as _sb,
                                             section_matches as _section_matches)
        known_rows = [r for r in known._by_economy.get(economy, [])
                      if str(r.get("pillar")) == str(pillar)
                      and r.get("indicator_code") == indicator_id]
        gold_anchor_ids: set[str] = set()
        anchor_matches: dict[str, set[str]] = {}
        from packages.ingest.known_index import expected_anchors
        for krow in known_rows:
            for anchor in expected_anchors(krow):
                ref = anchor["ref"]
                kbase = _sb(ref)
                if not kbase:
                    continue
                scoped_laws = anchor.get("laws_norm") or krow.get("acts_norm", [])
                acts_resolved = [known._resolve_alias(economy, a)
                                 for a in scoped_laws if a]
                def _base_hits(ubase: str | None) -> bool:
                    return _section_matches(kbase, ubase)
                matches = [c for c in corpus
                           if any(_lm(a, c["props"].get("law_name", "")) for a in acts_resolved)
                           and _base_hits(_sb(c["props"].get("article_section", "")))]
                if not matches:
                    hole = (f"RECALL HOLE {indicator_id}: master-known {krow.get('act','')[:40]} "
                            f"{ref} not in the {economy} corpus")
                    if hole not in warnings:
                        warnings.append(hole)
                    continue
                anchor_key = f"{'|'.join(acts_resolved)}|{ref}|{indicator_id}"
                anchor_matches.setdefault(anchor_key, set()).update(
                    m["provision_id"] for m in matches)
                for m in matches:
                    gold_anchor_ids.add(m["provision_id"])
                    if m["provision_id"] not in have_ids:
                        from packages.retrieval.hybrid import Candidate as _Cand
                        candidates.append(_Cand(m["provision_id"], m["text"], m["props"],
                                                matched_queries=["known-injection"]))
                        have_ids.add(m["provision_id"])
        # L2 (P3.5): measurable retrieval stats — how many master-known anchors
        # retrieval found on its own vs. how many only the injection saved.
        organic_anchor_count = sum(bool(ids & organic_ids) for ids in anchor_matches.values())
        injected_anchor_count = len(anchor_matches) - organic_anchor_count
        stats["anchors_retrieved_organically"] = (stats.get("anchors_retrieved_organically", 0)
                                                  + organic_anchor_count)
        stats["anchors_injection_saved"] = (stats.get("anchors_injection_saved", 0)
                                            + injected_anchor_count)
        indicator_stats["resolved_known_anchors"] = len(anchor_matches)
        indicator_stats["candidate_recall"] = (organic_anchor_count / len(anchor_matches)
                                                 if anchor_matches else None)
        indicator_stats["injected_anchor_count"] = injected_anchor_count
        stats["candidates"] += len(candidates)
        if len(candidates) > SCREEN_CAP_PER_INDICATOR:
            warnings.append(
                f"{indicator_id}: screened top {SCREEN_CAP_PER_INDICATOR} of "
                f"{len(candidates)} retrieval candidates (cap logged, not silent)"
            )
            indicator_stats["caps"].append({"stage": "screen", "limit": SCREEN_CAP_PER_INDICATOR,
                                             "input_count": len(candidates)})
        # KNOWN-anchor bypass: candidates matching a (law + section) that the master
        # dataset itself records are human-confirmed terrain — they go straight to the
        # mapper and must never be screen-dropped (reproducing KNOWN proves recall).
        # Bypass screening only for anchors recorded under THIS indicator.
        # Using every section known anywhere in the master dataset caused a broad
        # parent ref to bypass hundreds of unrelated descendants under every indicator.
        anchors, rest = _partition_current_anchors(candidates, gold_anchor_ids)
        survivors = anchors + screen_candidates(llm_bulk, indicator_id, cfg, rest)
        survivor_ids = {c.provision_id for c in survivors}
        indicator_stats["screen_survival_recall"] = (
            sum(bool(ids & survivor_ids) for ids in anchor_matches.values()) / len(anchor_matches)
            if anchor_matches else None)
        stats["screened_in"] += len(survivors)
        stats["known_anchors"] = stats.get("known_anchors", 0) + len(anchors)

        indicator_rows = 0
        mapped_anchor_ids: set[str] = set()
        passed_anchor_ids: set[str] = set()
        mapping_decisions = map_candidates(
            llm_high, indicator_id, cfg, survivors, gold_anchor_ids,
            llm_escalation=llm_escalation,
        )
        for candidate, decision in zip(survivors, mapping_decisions, strict=True):
            if decision._model_route == "mini-escalation":
                stats["mini_escalations"] += 1
                for reason in decision._escalation_reasons:
                    stats["escalation_reasons"][reason] = (
                        stats["escalation_reasons"].get(reason, 0) + 1)
            else:
                stats["nano_mappings"] += 1
            if not decision.applies:
                continue
            if candidate.provision_id in gold_anchor_ids:
                mapped_anchor_ids.add(candidate.provision_id)
            props = candidate.props
            # RuleUnit.text may be a shortened retrieval view.  The legal proof
            # contract is the canonical structural context, including immediate
            # child list items and exceptions.
            source_context = props.get("raw_context") or candidate.text
            from packages.verifier.gates import finalize_snippet_result

            finalized = finalize_snippet_result(
                decision.verbatim_snippet, source_context)
            decision.verbatim_snippet = finalized.text
            gate_results, ok = run_gates(
                snippet=decision.verbatim_snippet,
                source_text=source_context,
                source_url=props.get("source_url", ""),
                whitelist_domains=whitelist,
                current_as_at=props.get("current_as_at")
                or (props.get("props") or {}).get("current_as_at"),
                legal_status=props.get("legal_status", "unknown"),
            )
            from packages.verifier.gates import (citation_tier, g2_location, g5_whole_rule,
                                                 g6_meaning_support, g7_indicator_fit,
                                                 g8_counter_and_dangling,
                                                 g9_structural_closure)

            fit = g7_indicator_fit(indicator_id, decision.verbatim_snippet,
                                   source_context, props.get("law_name", ""))
            from packages.discovery.diff import section_base as _sb2

            same_act_sections = set()
            for c in corpus:
                if c["props"].get("law_name") == props.get("law_name"):
                    b = _sb2(c["props"].get("article_section", ""))
                    if b:
                        same_act_sections.add(b.upper())
            gate_results.extend([
                fit,
                g2_location(props.get("article_section", ""), props.get("location_reference", "")),
                g5_whole_rule(indicator_id, decision.verbatim_snippet, source_context),
                g6_meaning_support(decision.rationale, decision.verbatim_snippet, source_context),
                g8_counter_and_dangling(decision.verbatim_snippet, source_context,
                                        props.get("law_name", ""), same_act_sections),
                g9_structural_closure(finalized),
            ])
            ok = ok and all(g.status != "FAIL" for g in gate_results)
            for g in gate_results:
                g.evidence_reference = f"{indicator_id} {props.get('article_section', '')}"
            gates_out.extend(gate_results)
            if not ok:
                stats["gate_rejected"] += 1
                warnings.append(
                    f"REJECTED by gates: {indicator_id} {props.get('article_section')} "
                    f"({[g.gate_id for g in gate_results if g.status == 'FAIL']})"
                )
                continue
            if economy == "Australia" and props.get("pdf_alignment") != "exact":
                stats["gate_rejected"] += 1
                warnings.append(
                    f"REJECTED unaligned AU evidence: {indicator_id} {props.get('article_section')}"
                )
                continue
            if props.get("ocr_citation_disagreement"):
                stats["gate_rejected"] += 1
                warnings.append(
                    f"REJECTED OCR citation-token disagreement: {indicator_id} {props.get('article_section')}"
                )
                continue
            tag, why = known.tag(economy, props.get("law_name", ""),
                                 props.get("article_section", ""))
            status = props.get("legal_status") or "unknown"
            status_fact = props.get("status_evidence") or {}
            loc = props.get("location_reference", "")
            import re as _re3
            page_match = _re3.search(r"page\s+(\d+)", loc, _re3.I)
            source_hash = props.get("content_sha256") or ""
            proof = None
            if source_hash and props.get("source_artifact_id"):
                span_ids = props.get("linked_span_ids") or []
                span_boxes = (props.get("metadata", {}).get("pdf_span_boxes", []) or
                              props.get("metadata", {}).get("citation_span_boxes", []))
                page_exact = bool(page_match and span_ids and span_boxes)
                alignment_exact = props.get("pdf_alignment") == "exact" or page_exact
                proof = CitationProof(
                    source_artifact_id=props["source_artifact_id"], source_sha256=source_hash,
                    page_number=int(page_match.group(1)) if page_match else None,
                    anchor=loc if loc.startswith("#") else None,
                    article_path=citation_path(props.get("article_section", "")),
                    span_ids=span_ids,
                    bboxes=span_boxes,
                    exact_snippet=decision.verbatim_snippet,
                    normalized_snippet=" ".join(decision.verbatim_snippet.split()).lower(),
                    source_start_char=finalized.source_start,
                    source_end_char=finalized.source_end,
                    alignment_status=("exact" if alignment_exact else
                                      "anchor" if loc.startswith("#") else "unaligned"),
                    alignment_score=float(props.get("alignment_score") or
                                          (1.0 if alignment_exact or loc.startswith("#") else 0.0)),
                    gate_results=[g.model_dump(mode="json") for g in gate_results],
                )
            findings.append(
                MappedFinding(
                    economy=economy,
                    law_name=props.get("law_name", ""),
                    law_number_ref=props.get("law_number_ref"),
                    last_amended=props.get("last_amended"),
                    indicator_id=indicator_id,
                    article_section=props.get("article_section", ""),
                    discovery_tag=tag,
                    location_reference=props.get("location_reference", "n/a") or "n/a",
                    verbatim_snippet=decision.verbatim_snippet,
                    mapping_rationale=decision.rationale[:300],
                    source_url=props.get("source_url", ""),
                    confidence=decision.confidence,
                    notes=f"Discovery: {why}. Modality: {decision.modality or 'n/a'}; "
                          f"exceptions: {'; '.join(decision.exceptions) or 'none'}",
                    coverage=(decision.coverage + (f" ({decision.sector})" if decision.sector else "")),
                    status=status,
                    status_evidence=(status_fact.get("fact_text") if isinstance(status_fact, dict)
                                     else str(status_fact or "no currentness assertion captured")),
                    status_evidence_record=(status_fact if isinstance(status_fact, dict) and status_fact else None),
                    model_version=model_version,
                    archived_copy=props.get("archived_copy") or None,
                    access_date=props.get("access_date") or None,
                    mean_ocr_confidence=(round(props["confidence"], 4)
                                         if props.get("confidence") not in (None, 1.0)
                                         and str(props.get("extraction", "")).startswith("ocr") else None),
                    ocr_quality_cer=None,  # true CER only vs human gold (R6)
                    citation_tier=citation_tier(props.get("article_section", "")),
                    verifier_risks=[g.reason for g in gate_results if g.status == "WARN"],
                    source_artifact_id=props.get("source_artifact_id"),
                    citation_proof=proof,
                    raw_context=source_context,
                )
            )
            if candidate.provision_id in gold_anchor_ids:
                passed_anchor_ids.add(candidate.provision_id)
            indicator_rows += 1
            stats["mapped"] += 1

        indicator_stats["mapper_survival_recall"] = (
            sum(bool(ids & mapped_anchor_ids) for ids in anchor_matches.values()) / len(anchor_matches)
            if anchor_matches else None)
        indicator_stats["gate_survival_recall"] = (
            sum(bool(ids & passed_anchor_ids) for ids in anchor_matches.values()) / len(anchor_matches)
            if anchor_matches else None)
        stats["by_indicator"][indicator_id] = indicator_stats

        if indicator_rows == 0 and not any(f.indicator_id == indicator_id for f in findings):
            gov = (pack.get("governing_instruments") or {}).get(
                indicator_id, (pack.get("governing_instruments") or {}).get("default", {}))
            if not gov.get("law") or not gov.get("url"):
                raise RuntimeError(f"No governing instrument configured for {economy} {indicator_id}")
            findings.append(_absence_row(
                economy, indicator_id, gov["law"], gov["url"], model_version,
                _coverage_manifest(economy, indicator_id, cfg, pack, warnings, corpus, candidates),
                _governing_props(corpus, gov["law"]),
            ))

    # Post-pass: deterministic 6.1-vs-6.4 disambiguation (drops false ban rows),
    # then guarantee every regulatory indicator still has at least one row.
    if pillar == 6:
        from packages.verifier.gates import g7_ban_vs_conditional

        findings, g7_gates = g7_ban_vs_conditional(findings)
        gates_out.extend(g7_gates)
    for indicator_id, cfg in rubric.get("indicators", {}).items():
        if cfg.get("regulatory") is False:
            continue
        if not any(f.indicator_id == indicator_id for f in findings):
            gov = (pack.get("governing_instruments") or {}).get(
                indicator_id, (pack.get("governing_instruments") or {}).get("default", {}))
            if not gov.get("law") or not gov.get("url"):
                raise RuntimeError(f"No governing instrument configured for {economy} {indicator_id}")
            findings.append(_absence_row(
                economy, indicator_id, gov["law"], gov["url"], model_version,
                _coverage_manifest(economy, indicator_id, cfg, pack, warnings, corpus, []),
                _governing_props(corpus, gov["law"]),
            ))
    # Precision-first NEW curation: retain a small functionally diverse set per
    # law/indicator and preserve every excluded candidate in run metadata.
    from packages.core.curation import curate_new_findings

    findings, excluded_new = curate_new_findings(findings)
    stats["curation"] = {
        "excluded_count": len(excluded_new),
        "excluded": excluded_new,
    }
    findings.sort(key=lambda f: f.indicator_id)

    from packages.providers import cost

    run_id = f"run-{code.lower()}-p{pillar}-{int(started)}"
    from packages.core.finalization import finding_key
    if hasattr(store, "upsert_finding"):
        for finding in findings:
            store.upsert_finding(finding_key(finding), run_id, finding)
    cost_entry = cost.append_log(run_id, {"economy": economy, "pillar": pillar,
                                          "elapsed_seconds": round(time.time() - started, 1)})
    return RunEnvelope(
        run_id=run_id,
        country=code,
        pillar=pillar,
        provider_profile=provider_profile,
        findings=findings,
        gates=gates_out,
        warnings=warnings,
    metadata={
            "corpus_provisions": len(corpus),
            "corpus_fingerprint": corpus_fingerprint(corpus),
            "known_index_sha256": __import__("hashlib").sha256(
                Path("data/known_index.json").read_bytes()).hexdigest(),
            "pipeline_stats": stats,
            "elapsed_seconds": round(time.time() - started, 1),
            "live_llm_calls": True,
            "graph_backend": type(store).__name__,
            "cost_report": cost_entry,
        },
    )
