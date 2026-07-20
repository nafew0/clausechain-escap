# Pitch — Policy Narrative Draft (P3-F2, for Legal's edit)

*Feeds deck slides 2–4, 7, 10 (official template). Technical half comes from DECISIONS.md.*

## The one-sentence story
**We didn't automate "legal research" — we automated ESCAP's own SOP, step by step, with their own pre-entry checklist as our quality gates.**

## The problem (their words)
10+ researchers, 1–4 weeks per country, 2,600+ regulations, 6–12-month refresh — "very costly… if we manage to make it happen this way, then we'll be able to sustain our work." ClauseChain is the sustainability plan for the RDTII.

## What makes our rows trustworthy (slide 7's demanded answers)
- **100% citation-match guarantee:** every snippet is mechanically verified against the archived source (G1); pinpoint cites are `[verify-pinpoint]`-tiered and re-checked — the fabrication class the judges' own reference plugin warns about.
- **Their failure taxonomy, caught structurally:** the hallucinated s.70B quote (G1), the lost-"unless" false ban (G5 + the deterministic 6.1-vs-6.4 gate), the canceled MAS-notice trap (G4 currentness), the broken-URL rule (G3 + archive), confidentiality-≠-localization (G7 legal-fit). Each is a regression test we can demo failing safely.
- **Chunking = legal structure, not tokens:** statutes parse into paragraph-depth RuleUnits (s. 26(1)), because citations are graded at paragraph depth.
- **Retrieval = broad recall (hybrid sparse+dense+graph), never top-k** — the 12-Jun result: evidence dropped early can't be recovered.

## The 20-point story: NEW evidence, disciplined
Provision-level NEW inside known laws (their 5-Jun ruling), found by sweeping the veins they told us about (7.5 beyond privacy law; 7.3 sectoral retention) — e.g. **Australia's TIA s.187A metadata-retention regime** and SG CPC s.34(1). Every NEW row survives the full gate stack + adversarial refuters + **human sign-off** — because a false NEW costs more than a miss.

## The double-weight Malaysia story
Malaysia was scored on error-checking. Our audit re-verified **every** master row: **124 findings — 58 non-official sources (their own inventory cites a university mirror for the PDPA, 8×), 32 dead links, 14 bills-cited-as-measures** — each with a proposed correction and an official-source upgrade (lom.agc.gov.my).

## Responsible AI (UNESCO/OECD framing; judges-look-for: Impact·Feasibility·Scalability·Innovation·Adoption)
- **Human accountability is non-delegable:** AI suggests, Legal approves — every NEW row and every Zone-3 score carries `reviewer_decision`; scores ship as **uncertainty bands from a multi-judge noise audit** (Krippendorff's α), never bare numbers. We accelerate Step 1 of their 5-step lifecycle ~100×; Steps 2–3 (review, government verification) remain human by design.
- **Transparency:** every row traces source → provision → graph path → gates → decision (the win condition a judge can click).
- **Scalability:** a new economy = one jurisdiction YAML (proven: SG portal-HTML, MY ministry-PDF+OCR, AU API — three radically different source types, one pipeline). The finals' 7 economies validate against the Round-2 gold we already ingested.
- **Competitive landscape (slide 10):** generic legal-AI (chatbots, markdown-RAG) optimizes answers; regulators need **auditable evidence** — the gap TINA/DTI/TH2OECD practitioners named in the workshops, and the one we built for.

*(Legal: mark edits inline; numbers above are measured, not estimated — cost per run ≈ $0.23, logs/cost_report.json.)*
