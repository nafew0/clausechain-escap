# ClauseChain Engine

This is the clean Python engine for the ClauseChain Round 1 submission.

It is intentionally isolated from the old Django/Next SaaS starter. The judged artifact starts here: a CLI engine that produces the required CSV and JSON outputs from legal evidence.

Current status: **champion-core candidate pipeline implemented; legal freeze not yet passed**.
The engine performs official acquisition, provenance-preserving extraction, retrieval,
mapping, deterministic gates, static review, and approval-only replay. Run
`scripts/champion_validate.py` for the machine-readable gate audit. A final submission
must not be claimed while that audit reports `FAIL`.

## What This Engine Must Do

The final engine will:

1. Collect official legal sources for SG, MY, and AU.
2. Extract clean legal text from HTML/PDF/OCR sources.
3. Split law into section-aware `RuleUnit` objects.
4. Store legal structure and evidence paths in local Neo4j.
5. Retrieve candidate provisions with BM25 + dense embeddings + graph expansion.
6. Map candidates to RDTII Pillar 6 / Pillar 7 indicators.
7. Verify exact source spans, currentness, authority, and NEW/KNOWN status.
8. Export a template-exact `output.csv` and transparent `output.json`.

Stub output is test-only and watermarked `STUB-NON-SUBMITTABLE`; `run.py` rejects stub
mode outside tests.

## Quick Start

Install `uv` if you do not already have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Create the locked environment and run the engine:

```bash
cd engine
uv sync --frozen --group dev
uv run pytest
uv run python run.py --country SG --pillar 6 --out outputs/demo
# --economy is an alias (matches the organizer README): 
uv run python run.py --economy Singapore --pillar 6 --out outputs/demo
```

## Operating modes and finalization

- `live`: official acquisition plus configured providers from `.env`.
- `offline-eval`: prebuilt archives/graph plus the documented local Ollama and BGE-M3
  weights; no official-site or cloud-provider access is required after those weights
  are installed.
- `submission-replay`: `scripts/submission_replay.py`, which reads immutable candidates
  and named approvals. `run.py` can never create a final file.

```bash
# Candidate sweep (never finalizes rows)
zsh scripts/final_sweep.sh

# Recall diagnosis and static source/highlight review
uv run python scripts/adjudicate_recall.py outputs/final_*
uv run python scripts/build_review_bundle.py

# Expected to FAIL until human/legal gates are closed
uv run python scripts/champion_validate.py

# Only after named decisions.json exists
uv run python scripts/submission_replay.py
uv run python scripts/validate_submission.py
```

The 30-page extraction fixture remains `extraction_gold_v1.draft.json` until a named
human reviewer supplies the transcriptions/labels and signs every page. The benchmark
refuses to treat draft/native-extracted text as human gold.

P0 data + spike commands (run once, in this order):

```bash
# 1. Build the KNOWN/NEW baseline from the ESCAP files (master = primary, 10-Jun mail)
uv run python scripts/build_known_index.py
# 2. Grade any output.csv against the baseline (the scoreboard)
uv run python scripts/eval_vs_master.py --output outputs/demo/output.csv --economy Singapore --pillar 6
# 3. AI-1 spike: fetch the SG PDPA page (httpx first; --playwright if blocked)
uv run python scripts/spike_sg_fetch.py
# 4. AI-1 spike: prove scanned-PDF detection on the sample kit
uv run python scripts/spike_ocr_check.py
# 5. AI-2 spike: real model routing (needs OPENAI_API_KEY in .env; GEMINI_API_KEY optional)
uv run python scripts/spike_providers.py
```

Expected outputs:

```text
outputs/demo/output.csv
outputs/demo/output.json
```

If `uv` cannot write to its default cache on your machine, use:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/private/tmp/uv-cache uv run python run.py --country SG --pillar 6 --out outputs/demo
```

## Output Contract

The CSV header is non-negotiable. It must stay exactly:

```text
Economy, Law Name, Law Number / Ref, Last Amended, Indicator ID, Article / Section, Discovery Tag, Location Reference, Verbatim Snippet, Mapping Rationale, Source URL, Confidence, Notes
```

The code-level source of truth is `packages/export/csv_writer.py`.

Every exported row must eventually pass verifier gates for:

- exact verbatim source span
- article/section with paragraph
- official/live source URL
- currentness / not superseded
- correct RDTII indicator
- NEW/KNOWN tag
- confidence and rationale

P0 uses dummy data, so the current verifier gates are placeholders.

## Folder Map

```text
engine/
  run.py                      CLI entrypoint (--country / --economy)
  pyproject.toml              Python project + dependencies (groups: dev, crawl, ocr)
  configs/
    models.yaml               model routing profiles (+ graph backend)
    graph.yaml                GraphStore backend contract (sqlite default / neo4j optional)
    rdtii/
      pillar_6.yaml           indicator rules + official 0/0.5/1 criteria + weights
      pillar_7.yaml           same, incl. the P7-I1/I2 polarity (absence = 1)
    jurisdictions/
      sg.yaml my.yaml au.yaml portals, citation grammar, anchor instruments, notes
  packages/
    core/                     schemas.py · interfaces.py · orchestrator.py
    connectors/
      sg_sso.py               SG fetcher (httpx first, Playwright fallback)
    ingest/
      xlsx.py                 stdlib-only xlsx reader
      known_index.py          master-DB Impact parser -> KNOWN baseline
    export/                   csv_writer.py (template-exact) · json_writer.py
    graph/
      store.py                get_graph_store() factory (GRAPH_BACKEND)
      sqlite_graph.py         DEFAULT judged-path store
      neo4j_client.py         optional demo swap
      schema.cypher           Neo4j constraints
    providers/
      model_router.py         profiles + resolve_llm()/resolve_embedding()
      llm_providers.py        OpenAI + Gemini (REST) + FallbackLLM
      embedding_provider.py   OpenAI embeddings + stub
      ocr_provider.py         P0 placeholder (real OCR lands in P2)
  scripts/
    build_known_index.py      ESCAP files -> data/known_index.json + data/seeds.json
    eval_vs_master.py         the scoreboard (KNOWN recall + format checks)
    spike_sg_fetch.py         AI-1 spike: live SG fetch
    spike_ocr_check.py        AI-1 spike: scanned-PDF detection
    spike_providers.py        AI-2 spike: real routing (needs API keys)
  data/
    known_index.json          KNOWN baseline (master = primary; built artifact)
    seeds.json                crawler seeds (Legal Inventory, all pillars)
    gold/gold_rows.csv        the answer key (Legal verifies every row)
  tests/                      16 tests incl. template-contract guard (fixtures/)
```

## Model Routing

Do not hardcode model names inside prompts, retrieval code, or verifier code. Route through `configs/models.yaml`.

Current routing:

| Task | Model |
|---|---|
| Final dense retrieval | `text-embedding-3-large` |
| Cheap dev/testing | `text-embedding-3-small` |
| Query expansion / keyword generation | `gpt-5.4-nano` or Gemini |
| Candidate screening | `gpt-5.4-nano` in compact groups |
| Legal mapping / rationale | `gpt-5.4-nano` first |
| Hard-case adjudication | `gpt-5.4-mini` only after a recorded deterministic escalation |
| Embedding fallback experiment | `gemini-embedding-001` |

Rule: embeddings use embedding models, not chat/reasoning models.

Mapping prompts use stable per-indicator `prompt_cache_key` values. OpenAI prompt
caching is automatic when the shared exact prefix is long enough; measured cached
tokens and model-route counts are written to the run cost report. For a non-interactive
final sweep, enable the OpenAI Batch API (50% lower token prices; completion may take
up to 24 hours):

```bash
CLAUSECHAIN_OPENAI_BATCH=1 zsh scripts/final_sweep.sh
```

Do not enable Batch for the live demo. The normal path is synchronous. Batch results
are restored by `custom_id`, schema-validated, and then pass the identical gates.

## Environment

Copy the example env file when real providers are wired:

```bash
cp .env.example .env
```

Important variables:

```bash
OPENAI_API_KEY=
GEMINI_API_KEY=
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
```

The P0 dummy run does not require API keys or Neo4j.

## Legal evidence graph (SQLite default, Neo4j optional)

**Final decision (GraphRAG Strategy §12):** the graph is a *data model* behind the
swappable `GraphStore` interface — same nodes/edges either way:

- economies, instruments, versions, sections, provisions, source spans,
  indicators, candidate findings, verified findings

Backends:

| Backend | When | Setup |
|---|---|---|
| `sqlite` (**default**) | The judged path. Zero extra services — judges run pip-only. | none (`data/graph.db` auto-created) |
| `neo4j` (optional) | Live-demo graph view + Cypher answers in the interview. | set `GRAPH_BACKEND=neo4j` + the `NEO4J_*` vars |

The swap is one env var — the same trick as the LLM/OCR swap, and demoed the same way.
`packages/graph/schema.cypher` defines the Neo4j constraints; `packages/graph/sqlite_graph.py`
is the default store. The dummy run works with no graph service at all.

## Team Responsibilities

Lead:

- Keep `run.py` runnable.
- Own schemas, orchestrator, CSV/JSON output, and integration.
- Reject changes that break the dummy run or output contract.

AI-1:

- Build connectors and extraction.
- First target: SG official HTML source.
- Next target: MY scanned/OCR source.
- Return `SourceDocument` and `ExtractedPage` objects only.

AI-2:

- Build retrieval, embeddings, graph expansion, reranking, predicate extraction, RDTII mapping, and verifier gates.
- Return `RuleUnit`, `CandidateFinding`, `MappedFinding`, and `GateResult` objects.
- Keep all model calls behind provider interfaces.

Legal:

- Own indicator meaning, gold rows, known provisions, and final mapping correctness.
- Provide exact quotes, article/section, source URL, expected indicator, and NEW/KNOWN label.

## Development Rules

- No UI work until the CLI produces real SG/P6 output.
- No direct model calls outside provider modules.
- No CSV column changes without updating tests and leadership approval.
- No LLM-generated graph edge without source-span verification.
- No final export row without a source URL and verbatim snippet.
- Keep old `backend/`, `frontend/`, and `agentic-rag-knowledge-graph/` untouched unless explicitly assigned.

## Test Commands

Run all tests:

```bash
uv run pytest
```

Run the public skeleton command:

```bash
uv run python run.py --country SG --pillar 6 --out outputs/demo
```

Inspect output:

```bash
cat outputs/demo/output.csv
cat outputs/demo/output.json
```

## Next Engineering Milestones

P0 complete when: ✅ DONE (11 Jun)

- [x] tests pass (16)
- [x] dummy command writes CSV + JSON (header verified against the official template file)
- [x] schemas are stable enough for team work
- [x] each owner knows which objects they must return
- [x] rubric YAMLs encode the official scoring criteria (incl. P7 polarity)
- [x] KNOWN baseline built from the master DB (306 article refs parsed from Impact prose)
- [x] graph store swappable (sqlite default / neo4j optional)
- [x] eval scoreboard runs (`scripts/eval_vs_master.py`)
- [ ] HUMAN VERIFY: API-key spike (`scripts/spike_providers.py`) + SG fetch spike — need keys/network

P1 target:

```bash
uv run python run.py --country SG --pillar 6 --out outputs/sg-p6
```

That command should produce real Singapore Pillar 6 output from official source data, with no UI dependency.
