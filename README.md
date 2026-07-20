# ClauseChain — AI Tool for Digital Trade Regulatory Analysis

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: **zAI BD** (Bangladesh) | Round: **1**
Last updated: 2026-07-20

---

## TL;DR

**ClauseChain turns official statute portals, gazette PDFs and treaty texts into verified RDTII 2.1 evidence — with a reproducible proof for every exported legal row.**

- **One command**: `python run.py --economy Singapore --pillar 6` → template-exact CSV + JSON.
- **Corpus**: 53,969 provisions across Singapore, Malaysia and Australia, parsed into statute-structure RuleUnits (never fixed-size chunks), each carrying its archived source bytes + SHA-256.
- **Every exported row** passes **9 deterministic gates** — including byte-exact snippet verification against the archived official copy — then an adversarial refuter, then **named, role-separated human review**. The final file is regenerated from approvals alone by a deterministic replay.
- **74 provision-level NEW findings** beyond the sample kit in the final sweep, including the first treaty-evidenced P6-I5 rows (CPTPP Art. 14.11, DEPA Art. 4.3, RCEP Art. 12.15) parsed from official state registers.
- **Measured cost**: the entire 6-run sweep (3 economies × 2 pillars) cost **US$1.16** on the default cloud profile; the bundled Path A profile runs **fully key-free** on local models.
- We also **audit the provided gold data**: the engine detected the planted Malaysia errors — including master citations to clauses that do not exist — and filed corrections with receipts.

Skip to [Quick Start](#quick-start) to run it in under 10 minutes.

---

## What This Tool Does

This tool automates the two tasks required by the UN Regional Digital Trade Integration Index (RDTII):

**Task 1 — Automated Evidence Discovery.**
Given an economy and pillar, ClauseChain acquires legislation from official government portals (including subsidiary legislation, scanned gazettes and treaty registers), archives every source with content hashes and access dates, and extracts clean structured text — with no manual steps. Anti-bot walls are handled with a polite-backoff + real-browser fallback; a dead or blocked link becomes a recorded `ACQUISITION_UNRESOLVED` fact, never a silent gap.

**Task 2 — Intelligent Mapping & Categorization.**
Extracted provisions are mapped to RDTII indicator IDs (P6-I1…P6-I5, P7-I1…P7-I5) through hybrid retrieval and LLM reasoning constrained by a rubric-as-code layer (indicator polarity, 0.5 tiers, the 7.5 court-order test, exclusions — all in YAML data). Each matched provision is recorded with an exact article-level citation, a byte-exact verbatim snippet, and a Discovery Tag (**NEW** = found independently / **KNOWN** = matches the sample kit).

**Mandatory scope:** Pillar 6 (Cross-border Data Flows) and Pillar 7 (Domestic Data Protection)
**Economies covered:** Singapore, Malaysia, Australia (Round 1). Adding an economy is a data change, not a code change — see [Scaling](#supported-economies--portals).

---

## Quick Start

⚠ **Required for Round 1.** A reviewer with basic Python knowledge can run this in under 10 minutes.

### 1. Clone the repository

```bash
git clone https://github.com/nafew0/clausechain-escap.git
cd clausechain-escap/engine
```

### 2. Set up the environment

```bash
# Python 3.12+ required
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Get the corpus (choose one)

**Option A — prebuilt corpus (recommended, ~2 minutes):**
Download `clausechain_corpus_sqlite.zip` from this repository's **GitHub Releases** page and unzip into `engine/data/`:

```bash
unzip clausechain_corpus_sqlite.zip -d data/
# provides data/graph_v2.db (SQLite: 53,969 provisions, FTS index, source-artifact hashes)
```

**Option B — rebuild from official sources (~1–2 hours, network required):**

```bash
python scripts/build_sg_corpus.py     # Singapore: SSO acts + subsidiary legislation + treaties
python scripts/build_my_corpus.py     # Malaysia: statute/gazette PDFs + MITI treaty texts (OCR as needed)
python scripts/build_au_corpus.py     # Australia: Federal Register EPUB+PDF compilations
```

Rebuilds are incremental: unchanged documents are fingerprint-matched and never re-extracted.

### 4. Configure model keys

```bash
cp .env.example .env
```

Two profiles ship in `configs/models.yaml`:

- **`hybrid_accuracy` (default, Path B):** set `OPENAI_API_KEY=sk-...` in `.env`. Uses `gpt-5.4-nano` for bulk work, `gpt-5.4-mini` only for escalated ambiguity, `text-embedding-3-small` embeddings.
- **`local_fallback` (Path A, key-free):** no keys at all. Uses a local Ollama model (`qwen2.5:7b`) + BGE-M3 embeddings + local OCR. Run any command with `--provider-profile local_fallback`.

### 5. Run

```bash
python run.py --economy Singapore --pillar 6
```

**Output:** `outputs/run-sg-p6-<id>/output.csv` and `output.json` (schema below), plus `review.md`, `candidate_rows.csv` and a gate/warning log for audit.

---

## Full Usage

```bash
python run.py --economy "Malaysia" --pillar 7 --out outputs/my_p7
# --economy          : Singapore | Malaysia | Australia (or SG/MY/AU)
# --pillar           : 6 | 7
# --provider-profile : hybrid_accuracy (default, Path B) | local_fallback (Path A, key-free)
# --mode             : live (default) | offline-eval | submission-replay
```

Run the full Round-1 sweep and consolidate to one submission file:

```bash
for eco in Singapore Malaysia Australia; do
  for p in 6 7; do python run.py --economy $eco --pillar $p --out outputs/final_$(echo $eco | cut -c1-2 | tr A-Z a-z)_p$p; done
done
python scripts/refute_new.py outputs/final_*            # adversarial refuter on every NEW row
python scripts/consolidate_submission.py outputs/final_*  # -> submission/consolidated.csv + .json
python scripts/validate_graph.py                          # graph/source-artifact integrity report
python scripts/champion_validate.py                       # submission-readiness contract
```

Regenerate the final artifacts purely from human approvals (deterministic, no LLM):

```bash
python scripts/submission_replay.py
```

---

## Architecture Overview

```
Input: Economy + Pillar
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ TASK 1 — Evidence Discovery                                  │
│  1. Seeds & connectors  seeds.json (ESCAP inventory + deep-  │
│     research deltas) → polite fetch, Playwright anti-bot     │
│     fallback, archive + SHA-256, manifest reconciliation,    │
│     fail-closed expected-provision checks                    │
│  2. Format-based extractors  anchored-HTML (SSO print view), │
│     statute-PDF with grammar profiles (Commonwealth / treaty │
│     "Art. 14.11" / Malay "Seksyen 12A"), EPUB structure      │
│     oracle aligned to authorised PDF, OCR for scanned        │
│     gazettes (CER measured per page)                         │
└──────────────────────────────────────────────────────────────┘
        │  RuleUnits (provision-depth, source-exact, located)
        ▼
┌──────────────────────────────────────────────────────────────┐
│ GRAPH  Instrument → Section → Provision + CROSS_REFERENCES;  │
│ SQLite+FTS5 default, Neo4j via GRAPH_BACKEND=neo4j;          │
│ legal status evidence + eligibility + processing fingerprint │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ TASK 2 — Mapping & Verification                              │
│  3. Hybrid retrieval  exact-phrase ∪ BM25 ∪ dense cosine     │
│     (broad recall, never top-k); master-known anchors        │
│     injected; per-indicator source-type allowlists applied   │
│     BEFORE ranking; every truncation recorded                │
│  4. LLM mapping  rubric-as-code indicator briefs (polarity,  │
│     tiers, exclusions); nano-first with deterministic        │
│     escalation to mini on ambiguity                          │
│  5. Gates G1–G9  byte-exact snippet · location · official    │
│     domain · currentness · whole-rule · rationale support ·  │
│     indicator fit · dangling refs · span closure (fail-closed)│
│  6. Refuter + human review  adversarial verdict per NEW row; │
│     named role-separated reviewers; append-only receipts;    │
│     absence rows carry search-coverage manifests and are     │
│     BLOCKED while any configured acquisition is unresolved   │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
Output: template-exact CSV / JSON (+ replayable decision bundles)
```

### Key modules

| Module | Path | Description |
| :---- | :---- | :---- |
| Seeds fetcher | `packages/connectors/seeds_fetch.py` | Inventory-driven acquisition, archive+hash, reconciliation, browser fallback |
| SG portal connector | `packages/connectors/sg_sso.py` | SSO whole-act print view (Acts + subsidiary legislation), anti-bot backoff |
| HTML extractor | `packages/extractors/html_act.py` | Anchored portal HTML → sections/subsections with anchors |
| PDF extractor | `packages/extractors/pdf_act.py` | Statute PDFs → RuleUnits; named grammar profiles (treaty/Malay) |
| EPUB oracle | `packages/extractors/epub_act.py` + `pdf_align.py` | AU structure oracle aligned span-exact to the authorised PDF |
| OCR router | `packages/extractors/pdf.py` | Native-text / OCR routing with page confidence |
| Graph store | `packages/graph/sqlite_graph.py` | Swappable GraphStore (SQLite default, Neo4j optional) |
| Retrieval | `packages/retrieval/hybrid.py` | Exact-phrase + FTS5 + dense union, caps recorded |
| Mapper | `packages/rdtii/mapper.py` | Screen + map with rubric-as-code briefs, escalation |
| Gates | `packages/verifier/gates.py` | G1–G9 deterministic verification, snippet finalization |
| Orchestrator | `packages/core/orchestrator.py` | End-to-end pipeline, coverage manifests, NEW/KNOWN diff |
| Review CLI | `scripts/apply_decisions.py` | The only sanctioned decision writer (lock → validate → atomic write → receipt) |
| Replay | `scripts/submission_replay.py` | Approvals → final CSV/JSON, deterministic |

---

## Swapping the LLM

*No vendor lock-in — required by the rubric.* All model routing lives in `configs/models.yaml` profiles; code never names a model.

**Default (Path B, cloud):**

```yaml
# configs/models.yaml → profiles.hybrid_accuracy
bulk:            openai:gpt-5.4-nano
high_reasoning:  openai:gpt-5.4-nano     # nano-first; escalation is deterministic
legal_escalation: openai:gpt-5.4-mini
embedding:       openai text-embedding-3-small
```

**Key-free (Path A, local):**

```bash
ollama pull qwen2.5:7b && ollama serve
python run.py --economy Singapore --pillar 6 --provider-profile local_fallback
```

**Add a provider:** implement the small client contract in `packages/providers/llm_providers.py` (plain REST, no SDKs), register it in `model_router.py`, reference it from a profile. Fallback chains (`primary`/`fallback`) are built in.

---

## Swapping the OCR Engine

| Engine | Config | Notes |
| :---- | :---- | :---- |
| Local engine (default) | `OCR_PROVIDER=local` | Key-free; used by Path A |
| PaddleOCR (self-hosted VM) | `OCR_PROVIDER=remote_paddle` + `OCR_ENDPOINT=` | Our accuracy path for scanned gazettes |

Change `.env` — no code changes. Per-page OCR confidence and citation-token disagreement flags are carried into review; OCR quality is measured as character error rate (target < 5%).

---

## Supported Economies & Portals

| Economy | Official sources | Language | Notes |
| :---- | :---- | :---- | :---- |
| Singapore | sso.agc.gov.sg (Acts + SL print view); isomer/enterprisesg treaty registers | English | CloudFront anti-bot handled (backoff + browser fallback) |
| Malaysia | lom.agc.gov.my · Federal Gazette · pdp.gov.my · NACSA · fta.miti.gov.my | English/Malay | Bilingual PDFs; Malay grammar profile ("Seksyen/Perkara"); OCR path |
| Australia | legislation.gov.au API (authorised PDF + EPUB); DFAT treaty portal | English | Multi-volume compilations; EPUB↔PDF span alignment |

**Adding an economy = data, not code:** a jurisdiction YAML (portals, whitelist, citation grammar, status assertions) + seed rows. Grammar profiles are named data ("Pasal", "Статья", "มาตรา" next); the government-verified Round-2 gold database is already ingested as the finals evaluation baseline.

---

## Output Format

Each run writes CSV + JSON. **CSV columns are byte-identical to `OUTPUT_TEMPLATE_31MAY.xlsx` (a unit test enforces this):**

| # | Column | Notes |
| :---- | :---- | :---- |
| 1–13 | Economy · Law Name · Law Number / Ref · Last Amended · Indicator ID · Article / Section · Discovery Tag · Location Reference · Verbatim Snippet · Mapping Rationale · Source URL · Confidence · Notes | Exact template order |
| 14+ | Coverage · Verbatim Snippet (English) · Status (+ status evidence) | Appended columns, allowed per the 15-Jun Q&A |

The JSON carries the same fields plus: `source_artifact_id`, `content_sha256`, `citation_proof` (span ids, page, alignment status, gate results), `status_evidence_record`, `search_coverage_manifest` (absence rows), `mean_ocr_confidence`, `model_version`, `raw_context`, and run metadata (`corpus_fingerprint`, `pipeline_stats`, `cost_report`, `elapsed_seconds`).

Final Round-1 artifact: `submission/consolidated.csv` + `submission/consolidated.json` (one consolidated file across all six runs, per the 15-Jun ruling).

---

## Verification: the Proof Chain

What makes a ClauseChain row trustworthy (and what judges can independently check):

1. **Archived source** — every document's exact bytes are stored with SHA-256 + access date; the citation names the official URL we archived.
2. **G1 byte-exactness** — the exported snippet is constructed *first* (source-exact slice → clause-boundary extension) and the gates verify that exact final text. A quote that is not in the source cannot be exported.
3. **Nine gates, fail-closed** — location, official-domain authority, currentness/status (repealed-as-current is impossible by construction), whole-rule, rationale support, indicator fit, dangling cross-references, span closure.
4. **Adversarial refuter** — a second model attacks every NEW row before humans see it.
5. **Named human review** — citation reviewer ≠ mapping reviewer, enforced at write time; append-only receipts; every batch exports a content-hashed bundle.
6. **Deterministic replay** — `submission_replay.py` regenerates the final CSV/JSON from approvals alone; run it twice, get identical bytes.
7. **Honest absence** — "no provision found" rows carry a search-coverage manifest; an unresolved configured acquisition (e.g. a geo-blocked treaty register) **blocks** the absence conclusion.
8. **Gold auditing** — master-known anchors are tracked per run; misses are adjudicated (`REAL_MISS` / `GOLD_WRONG` / `CORRECT_ABSTENTION`) with receipts. This pass caught the planted Malaysia errors in the provided gold data.

---

## Actual Cost Per Document

Measured from real runs (`logs/cost_report.json` is written by every run; judges can verify against code).

**Full Round-1 sweep (3 economies × 2 pillars, 53,969-provision corpus, final run of 20 Jul 2026):**

| Run | Wall-clock | Measured cost |
| :---- | :---- | :---- |
| Singapore P6 / P7 | 6.5 min / 13.4 min | $0.104 / $0.266 |
| Malaysia P6 / P7 | 6.3 min / 15.5 min | $0.113 / $0.343 |
| Australia P6 / P7 | 6.1 min / 14.5 min | $0.079 / $0.260 |
| **Total sweep** | **~63 min** | **US$1.16** |

- **Per document:** the sweep evaluates 100+ statutes/instruments → **≈ $0.01 per legal document** on the accuracy profile (gpt-5.4-nano bulk + mini escalation + text-embedding-3-small).
- **Example run breakdown (Singapore P6):** 106 nano calls (187k in / 39k out tokens, $0.086) + mini escalations ($0.018) + 29 embedding calls ($0.000) = **$0.104**.
- **Open-weight swap (Path A):** Ollama `qwen2.5:7b` + BGE-M3 + local OCR = **$0.00 API cost** (compute only).
- Embeddings are disk-cached and documents are fingerprint-restamped when unchanged, so incremental re-runs spend only on changed evidence.

---

## Known Limitations

Honesty section — these are recorded in the tool's own reports, not hidden:

- **Geo/TLS-blocked portals:** dfat.gov.au (Akamai) rejects non-browser TLS from our region; the Playwright fallback did not clear it either. The four AU treaty seeds are recorded as `ACQUISITION_UNRESOLVED`, which deliberately blocks the AU P6-I5 absence conclusion. NSW/Vic state registers (403 bot-walls) are deferred the same way.
- **Master-gold recall:** a minority of master-known anchors are still missed; each miss is adjudicated with receipts (two were traced to errors in the provided gold itself). Repairs are per-anchor work, tracked in the recall report.
- **Delegated-legislation following:** cross-references from acts to subordinate instruments are captured as graph edges and seeded subsidiary legislation is ingested, but the engine does not yet auto-crawl every referenced instrument.
- **Confidence calibration:** confidence values are relative, not calibrated probabilities; rows under 0.80 are flagged for human review (and all NEW rows get human review regardless).
- **Long-span snippets:** provisions with no clause boundary inside the export budget are flagged `REVIEW_REQUIRED_LONG_SPAN` rather than truncated; a handful of list-introduced provisions await the structural-closure improvement.

---

## Running the Test Suite

```bash
cd engine && python -m pytest tests/     # 148 tests
```

| Test area | Files |
| :---- | :---- |
| Extractors (HTML/PDF/EPUB grammars) | `test_html_sso.py`, `test_epub_act.py`, `test_pdf_act.py`, `test_rerun_fixes.py` |
| Retrieval + caps + source-type scoping | `test_rerun_wiring.py`, `test_graph_search.py` |
| Gates & snippet finalization | `test_gates_p3.py`, `test_regression_dodont.py` |
| Output schema (byte-equal to template) | `test_csv_writer.py`, `test_template_contract.py` |
| Decision contract & replay | `test_apply_decisions.py`, `test_champion_contract.py` |
| Cost metering & model routing | `test_cost_routing.py`, `test_model_router.py` |

---

## Reproducing the Sample Kit Results

```bash
python scripts/eval_vs_master.py         # recall vs the provided master database
python scripts/validate_graph.py         # source-artifact + provision integrity
python scripts/champion_validate.py      # full submission-readiness contract
```

These print which known provisions were matched, which NEW ones were discovered, and every integrity failure by name.

---

## Team

| Role | Name | Responsibility |
| :---- | :---- | :---- |
| Team Lead / Technical Lead | Abu Naser Md. Nafew | Architecture, engine, full-stack, deployment |
| Substantive Lead | MD. INSAFUL RAHMAN TUSAR | Legal review, mapping sign-off, output QA |
| AI Engineer | Punam Chowdhury | AI engineering |
| AI Engineer | MD SANIUL BASIR SAZ | AI engineering |
| UI/UX Designer | FARHANA BORSHA | Review console & workspace design |

---

## License

Released under the **Apache License 2.0** in accordance with the hackathon submission requirements. See [LICENSE](LICENSE).

Third-party licences: Python (PSF), httpx/pydantic/numpy/pytest (BSD/MIT), pymupdf (AGPL — unmodified library use), SQLite/FTS5 (public domain), Neo4j Community (GPLv3, optional), Django/DRF (BSD), Next.js/React (MIT), BGE-M3 (MIT), Ollama-served open-weight models per their model licences.

---

## Key Dates

| Date | Milestone |
| :---- | :---- |
| **20 July 2026** | **Round 1 submission (this repository)** |
| 31 July 2026 | Shortlist announced |
| 3 August 2026 | Live online pitching |
| 5 August 2026 | Finalists announced |
| October 2026 | Grand Finale — Bangkok |

---

## Acknowledgements

Built for the UN Global Hackathon on AI for Digital Trade Regulatory Analysis, organised by UNESCAP and KMITL. We thank the workshop faculty whose sessions shaped this design — statute-reading methodology (Henry Gao), legal-finding fields (EUI DTI), GraphRAG-for-legal (KMITL), and the noise-audit uncertainty framing (Maynooth).
