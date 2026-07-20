'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Wifi, Database, ShieldCheck, FileText, Layers,
  Search, BrainCircuit, Workflow, BadgeCheck, PackageOpen,
  ChevronDown, Play, Pause,
} from 'lucide-react'

/* ─── Data ───────────────────────────────────────────────────────────────── */

const STAGES = [
  {
    num: '01', label: 'Discovery', icon: Wifi, color: 'blue', model: 'local',
    desc: 'Scrapy + Playwright + Crawl4AI · robots-aware crawl',
    detail: 'Seeds from per-jurisdiction packs (SG · TH · BD). Crawls official statute databases, gazettes, and regulator portals politely with robots.txt respect and rate limiting. Tags candidates as law, regulation, amendment, guideline, draft, or translation.',
    gateIds: [],
  },
  {
    num: '02', label: 'Source Acquisition', icon: Database, color: 'blue', model: 'local',
    desc: 'Raw bytes · SHA-256 · headers · rendered pages',
    detail: 'Preserves each source exactly as downloaded — raw SHA-256, retrieval timestamp, HTTP headers, MIME type, redirect chain. PDFs are rendered to page images so every citation can be visually verified.',
    gateIds: [],
  },
  {
    num: '03', label: 'Authority & Currentness Resolver', icon: ShieldCheck, color: 'blue', model: 'local',
    desc: 'binding / draft / repealed / consolidated / amendment / translation',
    detail: 'Classifies each source using the jurisdiction authority hierarchy. Builds a current-law graph. Detects repeal, amendment, and consolidation markers. Prevents a correct quote from a wrong or outdated source.',
    gateIds: [2, 3],
  },
  {
    num: '04', label: 'Extraction + OCR', icon: FileText, color: 'blue', model: 'cloud-optional',
    desc: 'Trafilatura · Docling · PaddleOCR-VL · VLM repair on hard regions',
    detail: 'HTML → Trafilatura. Native PDF → Docling + PyMuPDF. Scanned PDF → PaddleOCR-VL vs. Tesseract comparison, logged with edit distance and bbox. VLM repair (Qwen2-VL or cloud Claude) runs only on low-confidence regions.',
    gateIds: [0, 1],
  },
  {
    num: '05', label: 'Legal Structure + Rule Units', icon: Layers, color: 'blue', model: 'local',
    desc: 'Section tree · principal rule + exception + condition binding',
    detail: 'Parses act → part → chapter → section → subsection → proviso → schedule. The Rule Unit Builder binds principal rules with their exceptions, conditions, definitions, and cross-references — chunking never separates them.',
    gateIds: [4],
  },
  {
    num: '06', label: 'Hybrid Retrieval', icon: Search, color: 'blue', model: 'local',
    desc: 'OpenSearch BM25 + BGE-M3 / Qwen3-Embedding + cross-encoder rerank',
    detail: 'Sparse + dense retrieval at rule-unit level (never arbitrary token windows). Query expansion from RDTII rubric terms and jurisdiction-specific synonyms. Reranked with BGE-reranker-v2-m3 or Qwen3-Reranker.',
    gateIds: [],
  },
  {
    num: '07', label: 'Legal Predicate Extraction', icon: BrainCircuit, color: 'violet', model: 'cloud-optional',
    desc: 'actor · action · object · modality · condition · exception tuple',
    detail: 'Extracts structured legal meaning before RDTII mapping. Constrained JSON schema enforced by Pydantic + Outlines. Each field links to one or more span IDs. Qwen2.5-7B local; GPT-4.1 or Claude escalated on confidence threshold.',
    gateIds: [5],
  },
  {
    num: '08', label: 'RDTII Mapping  (P6 · P7 · P8 · P9)', icon: Workflow, color: 'violet', model: 'cloud-optional',
    desc: 'Rubric-as-code deterministic checks + constrained classifier',
    detail: 'RDTII pillars encoded as YAML rubrics with required predicates, exclusion rules, positive/negative examples. Deterministic predicate checks run BEFORE the LLM classification call. Multi-label where a clause covers several obligations.',
    gateIds: [6],
  },
  {
    num: '09', label: 'Verification Gates  G1 – G8', icon: BadgeCheck, color: 'amber', model: 'local',
    desc: 'span · location · authority · currentness · structure · tuple · RDTII · counter-ev.',
    detail: 'All eight gates must pass for final_status: verified. Any gate returning review routes the claim to the human queue; any reject blocks it from export. Thresholds are configurable per jurisdiction pack.',
    gateIds: [0, 1, 2, 3, 4, 5, 6, 7],
  },
  {
    num: '10', label: 'Human Audit + Export', icon: PackageOpen, color: 'teal', model: 'local',
    desc: 'Review UI · JSONL · CSV · Markdown · provenance bundle',
    detail: 'Reviewer sees original source, span, predicate tuple, RDTII mapping, gate results, and counter-evidence side by side. Decisions are logged. Exports re-verifiable from raw bytes — source URL, SHA-256, section, page, char offsets, bbox, OCR confidence.',
    gateIds: [],
  },
]

const GATES = [
  { code: 'G1', label: 'Span',        threshold: 'Exact byte/char match · OCR-fuzzy edit dist ≤ 3', reject: true,  review: false },
  { code: 'G2', label: 'Location',    threshold: 'bbox IoU ≥ 0.85 or section path match',           reject: true,  review: true  },
  { code: 'G3', label: 'Authority',   threshold: 'Binding tier — authority rank ≤ 5',               reject: true,  review: false },
  { code: 'G4', label: 'Currentness', threshold: 'status = binding_current, not repealed / draft',  reject: true,  review: true  },
  { code: 'G5', label: 'Structure',   threshold: 'Correct rule unit, exception present',            reject: false, review: true  },
  { code: 'G6', label: 'Tuple',       threshold: 'Multilingual NLI entailment ≥ 0.70',              reject: true,  review: true  },
  { code: 'G7', label: 'RDTII',       threshold: 'Required predicates present, no exclusion',       reject: true,  review: true  },
  { code: 'G8', label: 'Counter-ev.', threshold: 'No repeal / amendment / conflict found',          reject: false, review: true  },
]

const COLOR = {
  blue: {
    activeBg: 'bg-blue-50', activeBorder: 'border-blue-400', activeRing: 'ring-1 ring-blue-200',
    iconBorder: 'border-blue-300', dot: 'bg-blue-500', text: 'text-blue-600',
    badge: 'bg-blue-100 text-blue-600',
  },
  violet: {
    activeBg: 'bg-violet-50', activeBorder: 'border-violet-400', activeRing: 'ring-1 ring-violet-200',
    iconBorder: 'border-violet-300', dot: 'bg-violet-500', text: 'text-violet-600',
    badge: 'bg-violet-100 text-violet-600',
  },
  amber: {
    activeBg: 'bg-amber-50', activeBorder: 'border-amber-400', activeRing: 'ring-1 ring-amber-200',
    iconBorder: 'border-amber-300', dot: 'bg-amber-500', text: 'text-amber-600',
    badge: 'bg-amber-100 text-amber-600',
  },
  teal: {
    activeBg: 'bg-teal-50', activeBorder: 'border-teal-400', activeRing: 'ring-1 ring-teal-200',
    iconBorder: 'border-teal-300', dot: 'bg-teal-500', text: 'text-teal-600',
    badge: 'bg-teal-100 text-teal-600',
  },
} as const

/* step 0 = inputs lit, steps 1-10 = stage (step-1) lit, step 11 = outputs lit */
const TOTAL_STEPS = STAGES.length + 2

/* ─── Component ─────────────────────────────────────────────────────────── */

export default function ArchitectureDiagram() {
  const [step,        setStep]        = useState(0)
  const [playing,     setPlaying]     = useState(true)
  const [activeStage, setActiveStage] = useState<number | null>(null)
  const [activeGate,  setActiveGate]  = useState<number | null>(null)

  const advance = useCallback(() => setStep(s => (s + 1) % TOTAL_STEPS), [])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(advance, 900)
    return () => clearInterval(id)
  }, [playing, advance])

  /* Which stage index is currently animated (null when at inputs/outputs step) */
  const atStep     = step >= 1 && step <= STAGES.length ? step - 1 : null
  const inputsLit  = step === 0
  const outputsLit = step === STAGES.length + 1

  /* Highlighted gates: click state takes priority, then animation */
  const highlightedGates = new Set<number>(
    activeStage !== null ? STAGES[activeStage].gateIds :
    activeGate  !== null ? [activeGate] :
    atStep      !== null ? STAGES[atStep].gateIds :
    []
  )

  /* Stages highlighted because activeGate uses them */
  const highlightedStages = new Set<number>(
    activeGate !== null
      ? STAGES.map((s, i) => s.gateIds.includes(activeGate!) ? i : -1).filter(i => i !== -1)
      : []
  )

  function toggleStage(i: number) {
    setPlaying(false)
    setActiveGate(null)
    setActiveStage(prev => (prev === i ? null : i))
  }
  function toggleGate(i: number) {
    setPlaying(false)
    setActiveStage(null)
    setActiveGate(prev => (prev === i ? null : i))
  }

  return (
    <section className="border-t border-[var(--cc-ink-100)]">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10">

        {/* Header */}
        <div className="mb-14">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--cc-teal-600)]">
            How it is built
          </p>
          <h2 className="mt-3 font-[var(--cc-font-display)] text-4xl font-semibold tracking-normal text-[var(--cc-ink-950)] sm:text-5xl">
            System Architecture
          </h2>
          <p className="mt-4 max-w-2xl text-base leading-7 text-[var(--cc-ink-600)]">
            Ten typed pipeline stages. Click any stage to see what it does and which verification gates it feeds. Click a gate to see which stages produce its evidence.
          </p>
        </div>

        <div className="grid gap-10 lg:grid-cols-[1fr_340px] lg:items-start">

          {/* ── Left: pipeline stages ── */}
          <div>

            {/* Input row */}
            <div className="mb-6 ml-[52px] grid grid-cols-2 gap-3">
              {['Jurisdiction Packs (YAML)', 'Official Portals  SG · TH · BD'].map(lbl => (
                <div key={lbl} className={`rounded-lg border-2 px-3 py-2.5 text-xs font-medium transition-all duration-300
                  ${inputsLit
                    ? 'border-blue-300 bg-blue-50 text-blue-700 shadow-sm'
                    : 'border-[var(--cc-ink-200)] bg-[var(--cc-ink-50)] text-[var(--cc-ink-500)]'
                  }`}>
                  {lbl}
                </div>
              ))}
            </div>

            {/* Stage cards */}
            <div className="space-y-2">
              {STAGES.map((stage, i) => {
                const c            = COLOR[stage.color as keyof typeof COLOR]
                const isAnimating  = atStep === i && activeStage === null && activeGate === null
                const isActive     = activeStage === i
                const isHighlighted = highlightedStages.has(i)
                const dim          = activeStage !== null && !isActive && !isHighlighted

                return (
                  <button
                    key={stage.num}
                    onClick={() => toggleStage(i)}
                    className={`group w-full text-left flex items-start gap-3 rounded-xl border-2 px-4 py-3 transition-all duration-200
                      ${isActive
                        ? `${c.activeBg} ${c.activeBorder} ${c.activeRing}`
                        : isAnimating
                          ? `${c.activeBg} ${c.activeBorder} scale-[1.015] shadow-sm`
                          : isHighlighted
                            ? `${c.activeBg} ${c.activeBorder}`
                            : dim
                              ? 'border-[var(--cc-ink-100)] bg-transparent opacity-40'
                              : 'border-[var(--cc-ink-200)] bg-white hover:border-[var(--cc-ink-300)] hover:shadow-sm'
                      }`}
                  >
                    {/* Timeline node */}
                    <div className={`relative z-10 mt-0.5 flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg border-2 transition-colors
                      ${isActive || isAnimating || isHighlighted
                        ? `${c.activeBg} ${c.iconBorder}`
                        : 'border-[var(--cc-ink-200)] bg-[var(--cc-ink-50)]'}`}>
                      <stage.icon className={`h-3.5 w-3.5 ${isActive || isAnimating || isHighlighted ? c.text : 'text-[var(--cc-ink-400)]'}`} />
                      {/* Ping dot for the currently animating stage */}
                      {isAnimating && (
                        <div className={`absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full ${c.dot} animate-ping`} />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className={`font-[var(--cc-font-mono)] text-[10px] ${isActive || isAnimating ? c.text : 'text-[var(--cc-ink-400)]'}`}>
                          {stage.num}
                        </span>
                        <span className={`text-sm font-semibold ${isActive || isAnimating || isHighlighted ? 'text-[var(--cc-ink-950)]' : 'text-[var(--cc-ink-700)]'}`}>
                          {stage.label}
                        </span>
                        {stage.model === 'cloud-optional' && (
                          <span className="rounded-full bg-violet-100 border border-violet-200 px-1.5 py-0.5 text-[9px] font-medium text-violet-600 leading-none">
                            cloud-optional
                          </span>
                        )}
                        {stage.gateIds.map(gid => (
                          <span key={gid}
                            className={`rounded px-1.5 py-0.5 text-[9px] font-[var(--cc-font-mono)] font-bold transition-colors
                              ${highlightedGates.has(gid) ? 'bg-amber-500 text-white' : 'bg-amber-100 text-amber-600'}`}>
                            {GATES[gid].code}
                          </span>
                        ))}
                      </div>
                      <p className="mt-0.5 text-[11px] leading-5 text-[var(--cc-ink-500)]">{stage.desc}</p>

                      {/* Expanded detail on click */}
                      {isActive && (
                        <p className="mt-3 border-t border-[var(--cc-ink-100)] pt-3 text-sm leading-6 text-[var(--cc-ink-700)]">
                          {stage.detail}
                        </p>
                      )}
                    </div>

                    <ChevronDown className={`mt-1 h-3.5 w-3.5 shrink-0 text-[var(--cc-ink-400)] transition-transform duration-200 ${isActive ? 'rotate-180' : ''}`} />
                  </button>
                )
              })}
            </div>

            {/* Output row */}
            <div className="mt-6 ml-[52px] grid grid-cols-3 gap-3">
              {['JSONL', 'CSV matrix', 'Provenance bundle'].map(lbl => (
                <div key={lbl}
                  className={`rounded-lg border-2 px-3 py-2.5 text-center text-xs font-semibold transition-all duration-300
                    ${outputsLit
                      ? 'border-teal-400 bg-teal-50 text-teal-700 shadow-sm'
                      : 'border-teal-200 bg-teal-50/50 text-teal-500'
                    }`}>
                  {lbl}
                </div>
              ))}
            </div>
          </div>

          {/* ── Right: gates sidebar ── */}
          <div className="lg:sticky lg:top-8 lg:self-start">
            <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5">
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-amber-600">
                Eight Verification Gates
              </p>
              <p className="mb-5 text-[11px] leading-5 text-[var(--cc-ink-500)]">
                All must pass before a claim is exported. Click to see thresholds.
              </p>

              <div className="space-y-1.5">
                {GATES.map((gate, i) => {
                  const isLit    = highlightedGates.has(i)
                  const isActive = activeGate === i
                  return (
                    <button
                      key={gate.code}
                      onClick={() => toggleGate(i)}
                      className={`w-full text-left rounded-lg border px-3 py-2.5 transition-all duration-150
                        ${isLit || isActive
                          ? 'border-amber-400 bg-amber-100/80 shadow-sm'
                          : 'border-[var(--cc-ink-200)] bg-white hover:border-amber-200 hover:bg-amber-50/50'}`}
                    >
                      <div className="flex items-center gap-2">
                        <span className={`w-8 font-[var(--cc-font-mono)] text-[10px] font-bold ${isLit || isActive ? 'text-amber-600' : 'text-[var(--cc-ink-400)]'}`}>
                          {gate.code}
                        </span>
                        <span className={`flex-1 text-xs font-medium ${isLit || isActive ? 'text-[var(--cc-ink-900)]' : 'text-[var(--cc-ink-600)]'}`}>
                          {gate.label}
                        </span>
                        <span className={`text-[9px] rounded px-1.5 py-0.5 font-medium
                          ${gate.reject ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600'}`}>
                          {gate.reject ? 'reject' : 'review'}
                        </span>
                      </div>
                      {(isLit || isActive) && (
                        <p className="mt-1.5 pl-10 text-[10px] leading-4 text-[var(--cc-ink-500)]">
                          {gate.threshold}
                        </p>
                      )}
                    </button>
                  )
                })}
              </div>

              {/* Model routing legend */}
              <div className="mt-5 border-t border-[var(--cc-ink-100)] pt-4 space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--cc-ink-400)] mb-2">
                  Model routing
                </p>
                {[
                  { label: 'Local-first',    sub: 'vLLM · Qwen / Llama',   dot: 'bg-blue-500'   },
                  { label: 'Cloud-optional', sub: 'OpenAI · Anthropic',     dot: 'bg-violet-500' },
                ].map(r => (
                  <div key={r.label} className="flex items-center gap-2">
                    <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${r.dot}`} />
                    <span className="text-[11px] font-medium text-[var(--cc-ink-600)]">{r.label}</span>
                    <span className="text-[10px] text-[var(--cc-ink-400)]">{r.sub}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Playback control */}
        <div className="mt-10 flex items-center justify-center gap-3">
          <button
            onClick={() => { setPlaying(p => !p); setActiveStage(null); setActiveGate(null) }}
            className="flex items-center gap-2 rounded-full border border-[var(--cc-ink-200)] bg-white px-4 py-1.5 text-sm font-medium text-[var(--cc-ink-600)] hover:bg-[var(--cc-ink-50)] transition-colors shadow-sm"
          >
            {playing
              ? <><Pause className="h-3.5 w-3.5" /> Pause</>
              : <><Play  className="h-3.5 w-3.5" /> Play</>}
          </button>
          <div className="flex gap-1">
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <button key={i} onClick={() => { setPlaying(false); setStep(i) }}
                className={`h-1.5 rounded-full transition-all duration-200 ${i === step ? 'w-4 bg-[var(--cc-teal-600)]' : 'w-1.5 bg-[var(--cc-ink-200)]'}`}
              />
            ))}
          </div>
        </div>

      </div>
    </section>
  )
}
