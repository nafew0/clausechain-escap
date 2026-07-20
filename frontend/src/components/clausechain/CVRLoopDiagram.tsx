'use client'

import { useState, useEffect, useCallback } from 'react'
import { CheckCircle2, AlertTriangle, XCircle, Play, Pause } from 'lucide-react'

/* ─── Data ───────────────────────────────────────────────────────────────── */

const GATES = [
  {
    code: 'G1', label: 'Span',
    question: 'Does the exact span exist in the extracted source text?',
    threshold: 'Exact byte/char match. OCR-fuzzy allowed in OCR regions with edit distance ≤ 3 and original page image attached.',
    pass: 'Span found verbatim in extracted text',
    review: '—',
    reject: 'No match or edit distance > 3',
    canReview: false, canReject: true,
  },
  {
    code: 'G2', label: 'Location',
    question: 'Does the section / page / bbox resolve to the cited span?',
    threshold: 'bbox IoU ≥ 0.85, or section path match in the legal node tree.',
    pass: 'Location resolves in the audit UI',
    review: 'IoU 0.50 – 0.85',
    reject: 'IoU < 0.50 or section unresolved',
    canReview: true, canReject: true,
  },
  {
    code: 'G3', label: 'Authority',
    question: 'Is the source authoritative for a binding-law claim?',
    threshold: 'Authority rank ≤ 5 (binding tier). Guidelines (rank 6–7) are context, not evidence.',
    pass: 'Official binding source',
    review: 'Guideline — shown as context only',
    reject: 'Unofficial or rank > 5 as binding claim',
    canReview: true, canReject: true,
  },
  {
    code: 'G4', label: 'Currentness',
    question: 'Is the source current operative law?',
    threshold: 'status = binding_current AND not within 14 days of an open amendment.',
    pass: 'Consolidated current text',
    review: 'Consolidated age > 365 days',
    reject: 'status ∈ {repealed, draft, superseded}',
    canReview: true, canReject: true,
  },
  {
    code: 'G5', label: 'Structure',
    question: 'Is the cited node the correct legal unit and role?',
    threshold: 'Role matches expected (principal_rule, exception, etc.).',
    pass: 'Rule unit includes principal rule + exception',
    review: 'Role uncertain or unit incomplete',
    reject: '—',
    canReview: true, canReject: false,
  },
  {
    code: 'G6', label: 'Tuple',
    question: 'Does the evidence support the extracted predicate tuple?',
    threshold: 'Multilingual NLI entailment ≥ 0.70 across all populated predicate fields.',
    pass: 'NLI ≥ 0.70 on all fields',
    review: 'NLI 0.50 – 0.70',
    reject: 'NLI < 0.50',
    canReview: true, canReject: true,
  },
  {
    code: 'G7', label: 'RDTII',
    question: 'Do the tuple predicates satisfy the RDTII rubric criterion?',
    threshold: 'All required predicates present AND no exclusion rule triggered.',
    pass: 'Rubric predicates satisfied',
    review: 'Required predicate ambiguous',
    reject: 'Required predicate missing or exclusion triggered',
    canReview: true, canReject: true,
  },
  {
    code: 'G8', label: 'Counter-ev.',
    question: 'Did counter-evidence search find a contradiction?',
    threshold: 'Corpus search for repeal notice, amendment, exception, or higher-rank contradicting source.',
    pass: 'No conflict found',
    review: 'Conflict found — route to human',
    reject: 'Direct contradiction with current binding source',
    canReview: true, canReject: true,
  },
]

/* animation: step 0 = at input, steps 1-8 = clause at gate i, step 9 = verified */
const TOTAL_STEPS = GATES.length + 2  // 0..9

/* ─── Component ─────────────────────────────────────────────────────────── */

export default function CVRLoopDiagram() {
  const [step,      setStep]      = useState(0)
  const [playing,   setPlaying]   = useState(true)
  const [activeGate,setActiveGate]= useState<number | null>(null)

  const advance = useCallback(() => setStep(s => (s + 1) % TOTAL_STEPS), [])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(advance, 900)
    return () => clearInterval(id)
  }, [playing, advance])

  function handleGateClick(i: number) {
    setPlaying(false)
    setActiveGate(prev => (prev === i ? null : i))
  }

  /* step-to-gate mapping: step 1 → gate 0, step 2 → gate 1, … */
  const atGate    = step >= 1 && step <= GATES.length ? step - 1 : null
  const pastGates = step > 1 ? step - 1 : 0           /* gates that are "passed" */
  const verified  = step === GATES.length + 1

  return (
    <section className="border-t border-[var(--cc-ink-100)]">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10">

        {/* Header */}
        <div className="mb-14">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--cc-teal-600)]">
            Verification
          </p>
          <h2 className="mt-3 font-[var(--cc-font-display)] text-4xl font-semibold tracking-normal text-[var(--cc-ink-950)] sm:text-5xl">
            The CVR Loop
          </h2>
          <p className="mt-4 max-w-2xl text-base leading-7 text-[var(--cc-ink-600)]">
            <strong className="text-[var(--cc-ink-900)]">Cite · Verify · Reject.</strong>{' '}
            Every mapped clause flows through eight gates before it can ship as evidence.
            Any failure rejects or routes to human review. Click a gate to see its threshold.
          </p>
        </div>

        {/* ── Swimlane diagram ── */}
        <div className="relative mb-10 overflow-x-auto">
          <div className="min-w-[820px]">

            {/* REVIEW lane label */}
            <div className="mb-1.5 flex items-center gap-3 h-9">
              <div className="w-20 shrink-0 text-right text-[10px] font-bold uppercase tracking-wider text-amber-500">
                Review
              </div>
              {/* per-gate review indicators */}
              <div className="flex-1 grid gap-2" style={{ gridTemplateColumns: `repeat(${GATES.length}, 1fr)` }}>
                {GATES.map((g, i) => (
                  <div key={g.code} className="flex justify-center">
                    {g.canReview && atGate === i && (
                      <span className="animate-[cc-cvr-pop_0.25s_ease-out_both] rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[9px] font-semibold text-amber-600 whitespace-nowrap">
                        ↑ review
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div className="w-28 shrink-0" />
            </div>

            {/* PASS lane (main horizontal flow) */}
            <div className="flex items-center gap-0">

              {/* Lane label */}
              <div className="w-20 shrink-0 text-right text-[10px] font-bold uppercase tracking-wider text-emerald-600 mr-3">
                Pass
              </div>

              {/* "Clause in" chip */}
              <div className={`shrink-0 rounded-lg border-2 px-3 py-2 text-[11px] font-semibold transition-all duration-300
                ${step === 0 ? 'border-blue-400 bg-blue-50 text-blue-700 scale-105 shadow-md shadow-blue-100' : 'border-[var(--cc-ink-200)] bg-[var(--cc-ink-50)] text-[var(--cc-ink-400)]'}`}>
                Clause in
              </div>

              {/* Gate sequence */}
              {GATES.map((gate, i) => (
                <div key={gate.code} className="flex items-center flex-1 min-w-0">
                  {/* connector arrow */}
                  <div className={`h-0.5 flex-1 mx-1 transition-colors duration-300 ${pastGates > i ? 'bg-emerald-300' : 'bg-[var(--cc-ink-200)]'}`} />

                  {/* Gate card */}
                  <button
                    onClick={() => handleGateClick(i)}
                    className={`shrink-0 rounded-xl border-2 text-center transition-all duration-200 px-2 py-2.5 min-w-[72px]
                      ${atGate === i
                        ? 'border-blue-500 bg-blue-50 shadow-lg shadow-blue-100/80 scale-110 z-10'
                        : activeGate === i
                          ? 'border-amber-400 bg-amber-50 scale-105'
                          : pastGates > i
                            ? 'border-emerald-300 bg-emerald-50'
                            : 'border-[var(--cc-ink-200)] bg-white hover:border-[var(--cc-ink-300)] hover:shadow-sm'
                      }`}
                  >
                    <div className={`text-[9px] font-[var(--cc-font-mono)] font-bold mb-0.5
                      ${atGate === i ? 'text-blue-500' : pastGates > i ? 'text-emerald-500' : 'text-[var(--cc-ink-400)]'}`}>
                      {gate.code}
                    </div>
                    <div className={`text-[11px] font-semibold leading-tight
                      ${atGate === i ? 'text-blue-700' : pastGates > i ? 'text-emerald-700' : 'text-[var(--cc-ink-700)]'}`}>
                      {gate.label}
                    </div>
                    <div className="mt-1 flex justify-center h-3">
                      {pastGates > i && <CheckCircle2 className="h-3 w-3 text-emerald-400" />}
                      {atGate === i  && <div className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-ping" />}
                    </div>
                  </button>
                </div>
              ))}

              {/* final connector */}
              <div className={`h-0.5 w-6 shrink-0 ml-1 transition-colors duration-300 ${verified ? 'bg-emerald-300' : 'bg-[var(--cc-ink-200)]'}`} />

              {/* Verified terminal */}
              <div className={`shrink-0 rounded-xl border-2 px-4 py-2.5 text-center transition-all duration-300
                ${verified ? 'border-emerald-400 bg-emerald-50 scale-105 shadow-lg shadow-emerald-100/80' : 'border-[var(--cc-ink-200)] bg-[var(--cc-ink-50)]'}`}>
                <CheckCircle2 className={`h-5 w-5 mx-auto mb-1 transition-colors ${verified ? 'text-emerald-500' : 'text-[var(--cc-ink-300)]'}`} />
                <div className={`text-[11px] font-bold ${verified ? 'text-emerald-700' : 'text-[var(--cc-ink-400)]'}`}>
                  Verified
                </div>
              </div>

            </div>

            {/* REJECT lane label + indicators */}
            <div className="mt-1.5 flex items-center gap-3 h-9">
              <div className="w-20 shrink-0 text-right text-[10px] font-bold uppercase tracking-wider text-red-500">
                Reject
              </div>
              <div className="flex-1 grid gap-2" style={{ gridTemplateColumns: `repeat(${GATES.length}, 1fr)` }}>
                {GATES.map((g, i) => (
                  <div key={g.code} className="flex justify-center">
                    {g.canReject && atGate === i && (
                      <span className="animate-[cc-cvr-pop_0.25s_ease-out_both] rounded-full border border-red-300 bg-red-50 px-2 py-0.5 text-[9px] font-semibold text-red-600 whitespace-nowrap">
                        ↓ reject
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div className="w-28 shrink-0" />
            </div>
          </div>
        </div>

        {/* Playback control */}
        <div className="mb-10 flex items-center justify-center gap-3">
          <button
            onClick={() => { setPlaying(p => !p); setActiveGate(null) }}
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

        {/* Gate detail panel */}
        {activeGate !== null && (
          <div className="rounded-2xl border border-[var(--cc-ink-200)] bg-[var(--cc-ink-50)] p-6 transition-all">
            <div className="flex items-start gap-5">
              {/* Gate badge */}
              <div className="shrink-0 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-center">
                <div className="font-[var(--cc-font-mono)] text-sm font-bold text-amber-600">
                  {GATES[activeGate].code}
                </div>
                <div className="mt-0.5 text-xs font-medium text-amber-500">
                  {GATES[activeGate].label}
                </div>
              </div>

              <div className="flex-1 min-w-0">
                <p className="font-semibold text-[var(--cc-ink-900)]">
                  {GATES[activeGate].question}
                </p>
                <p className="mt-1 text-sm text-[var(--cc-ink-600)]">
                  {GATES[activeGate].threshold}
                </p>

                {/* Outcome cards */}
                <div className="mt-4 grid grid-cols-3 gap-3">
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                      <span className="text-xs font-bold text-emerald-700">PASS</span>
                    </div>
                    <p className="text-xs leading-5 text-emerald-700">{GATES[activeGate].pass}</p>
                  </div>

                  <div className={`rounded-lg border p-3 ${GATES[activeGate].canReview
                    ? 'border-amber-200 bg-amber-50' : 'border-[var(--cc-ink-200)] bg-white opacity-30'}`}>
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                      <span className="text-xs font-bold text-amber-600">REVIEW</span>
                    </div>
                    <p className="text-xs leading-5 text-amber-700">{GATES[activeGate].review}</p>
                  </div>

                  <div className={`rounded-lg border p-3 ${GATES[activeGate].canReject
                    ? 'border-red-200 bg-red-50' : 'border-[var(--cc-ink-200)] bg-white opacity-30'}`}>
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                      <span className="text-xs font-bold text-red-600">REJECT</span>
                    </div>
                    <p className="text-xs leading-5 text-red-700">{GATES[activeGate].reject}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Bottom summary row */}
        <div className="mt-10 grid grid-cols-3 gap-4 border-t border-[var(--cc-ink-100)] pt-10">
          {[
            { icon: CheckCircle2, color: 'text-emerald-600 bg-emerald-50 border-emerald-200',  label: 'VERIFIED', body: 'All 8 gates pass → claim exported with full provenance bundle.' },
            { icon: AlertTriangle,color: 'text-amber-600 bg-amber-50 border-amber-200',         label: 'HUMAN REVIEW', body: 'Any gate returns uncertain → claim enters the reviewer queue.' },
            { icon: XCircle,      color: 'text-red-600 bg-red-50 border-red-200',              label: 'REJECTED',  body: 'Any gate fails hard → claim blocked from export entirely.' },
          ].map(({ icon: Icon, color, label, body }) => (
            <div key={label} className={`rounded-xl border p-4 ${color.split(' ').slice(1).join(' ')}`}>
              <div className="flex items-center gap-2 mb-2">
                <Icon className={`h-4 w-4 shrink-0 ${color.split(' ')[0]}`} />
                <span className={`text-xs font-bold tracking-wide ${color.split(' ')[0]}`}>{label}</span>
              </div>
              <p className="text-xs leading-5 text-[var(--cc-ink-600)]">{body}</p>
            </div>
          ))}
        </div>

      </div>
    </section>
  )
}
