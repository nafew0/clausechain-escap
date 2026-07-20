'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import axios from 'axios'
import {
  AnimatePresence,
  LazyMotion,
  MotionConfig,
  domAnimation,
  m,
} from 'motion/react'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  ExternalLink,
  FileCheck2,
  Filter,
  Gavel,
  History,
  Info,
  Library,
  Menu,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
  XCircle,
} from 'lucide-react'

import { useAuth } from '@/contexts/AuthContext'
import {
  useDecide,
  useDecisionHistory,
  useReviewContext,
  useReviewQueue,
  useSummary,
} from '@/hooks/workspace'
import { cn } from '@/lib/utils'
import type {
  FindingQueue,
  FindingVerdict,
  JsonObject,
  RecallVerdict,
  ReviewItem,
  ReviewStage,
  WorkspaceQueue,
  Zone3Score,
} from '@/types/workspace'
import { rowRecord } from '@/types/workspace'

const QUEUES: { key: WorkspaceQueue; label: string; short: string; description: string }[] = [
  { key: 'new', label: 'NEW evidence', short: 'NEW', description: 'Newly discovered legal evidence' },
  { key: 'absence', label: 'Absence', short: 'ABS', description: 'No-evidence conclusions' },
  { key: 'recall', label: 'Recall', short: 'REC', description: 'Master-known misses' },
  { key: 'zone3', label: 'Zone-3', short: 'Z3', description: 'Indicator scoring review' },
  { key: 'known', label: 'KNOWN', short: 'K', description: 'Recovered master evidence' },
]

const RECALL_VERDICTS: { value: RecallVerdict; label: string }[] = [
  { value: 'REAL_MISS', label: 'Real miss' },
  { value: 'GOLD_WRONG', label: 'Gold wrong' },
  { value: 'GOLD_AMBIGUOUS', label: 'Gold ambiguous' },
  { value: 'CORRECT_ABSTENTION', label: 'Correct abstention' },
  { value: 'NEEDS_CORRECTION', label: 'Needs correction' },
]

function text(value: unknown, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function reviewLoadError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (!error.response) return 'The review API is unavailable. Start the backend and try again.'
  }
  return error instanceof Error ? error.message : 'The review workspace could not be loaded.'
}

function parseJson(value: unknown) {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function badgeTone(value: unknown) {
  const normalized = text(value, '').toUpperCase()
  if (normalized.includes('KEEP') || normalized === 'APPROVED') return 'success'
  if (normalized.includes('SPLIT') || normalized.includes('PENDING')) return 'warning'
  if (normalized.includes('REJECT') || normalized.includes('BLOCK')) return 'danger'
  return 'neutral'
}

function reviewId(record: JsonObject, item: ReviewItem) {
  return text(
    record['Finding ID'] ?? record['Absence ID'] ?? record['Miss ID'] ?? record['Score ID'],
    item.stable_key.slice(0, 8)
  )
}

function itemTitle(record: JsonObject) {
  return text(
    record['Law/instrument'] ??
      record['Configured governing instrument'] ??
      record['Master act/instrument'] ??
      record['Indicator question'],
    'Review item'
  )
}

function isTyping(target: EventTarget | null) {
  const element = target as HTMLElement | null
  return Boolean(element?.closest('input, textarea, select, [contenteditable="true"]'))
}

function StageStrip({ item }: { item: ReviewItem }) {
  const stages = item.review_state?.stages ?? {}
  return (
    <div className="review-stage-strip" aria-label="Review stages">
      {(['citation', 'mapping', 'status'] as ReviewStage[]).map((stage) => {
        const current = stages[stage]
        return (
          <div className={cn('review-stage', current && 'is-complete')} key={stage}>
            {current ? <CheckCircle2 size={15} /> : <CircleDashed size={15} />}
            <span>
              <strong>{stage}</strong>
              <small>{current ? `${current.reviewer_name} · ${new Date(current.reviewed_at).toLocaleDateString()}` : 'Awaiting reviewer'}</small>
            </span>
          </div>
        )
      })}
    </div>
  )
}

function EvidenceSection({ title, children, open = true }: { title: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details className="review-evidence-section" open={open}>
      <summary>
        <span>{title}</span>
        <ChevronDown size={16} />
      </summary>
      <div className="review-evidence-body">{children}</div>
    </details>
  )
}

function QueueSpecificEvidence({ queue, record }: { queue: WorkspaceQueue; record: JsonObject }) {
  if (queue === 'absence') {
    const manifest = parseJson(record['Search coverage manifest'])
    return (
      <>
        <div className="review-caution">
          <ShieldAlert size={18} />
          <div><strong>No evidence found is not proof of nonexistence.</strong><span>Approve only after the governing instruments, searches, caps and unresolved failures have been checked.</span></div>
        </div>
        <EvidenceSection title="Search coverage manifest">
          <pre className="review-json">{text(manifest)}</pre>
        </EvidenceSection>
      </>
    )
  }
  if (queue === 'recall') {
    return (
      <>
        <div className="review-fact-grid">
          <div><span>Technical class</span><strong>{text(record['Technical class'])}</strong></div>
          <div><span>Proposed verdict</span><strong>{text(record['Proposed verdict'])}</strong></div>
          <div><span>Emitted under</span><strong>{text(record['Emitted under'])}</strong></div>
        </div>
        <EvidenceSection title="System rationale">
          <p>{text(record['Plain-language system rationale'])}</p>
        </EvidenceSection>
      </>
    )
  }
  if (queue === 'zone3') {
    return (
      <>
        <div className="review-score-hero">
          <span>Deterministic score</span>
          <strong>{text(record['Deterministic score'])}</strong>
          <p>{text(record['Deterministic reason'])}</p>
        </div>
        <div className="review-fact-grid four">
          <div><span>Judge scores</span><strong>{text(record['Judge scores'])}</strong></div>
          <div><span>Agreement α</span><strong>{text(record['Agreement alpha'])}</strong></div>
          <div><span>Band</span><strong>{text(record['Score band'])}</strong></div>
          <div><span>Spread</span><strong>{text(record['Spread'])}</strong></div>
        </div>
        <EvidenceSection title="Judge reasoning" open={false}>
          <p>{text(record['Judge reasoning'])}</p>
        </EvidenceSection>
      </>
    )
  }
  return (
    <>
      {queue === 'new' && text(record['Refuter verdict']).toUpperCase() === 'SPLIT' ? <div className="review-split-dissent"><AlertTriangle size={17} /><div><strong>Refuter dissent requires a human ruling</strong><span>{text(record['Refuter panel reasoning'])}</span></div></div> : null}
      <EvidenceSection title="Exact source quote">
        <blockquote className="cc-verbatim">{text(record['Exact source snippet'])}</blockquote>
      </EvidenceSection>
      <EvidenceSection title="Mapping analysis">
        <p>{text(record['System mapping rationale'])}</p>
      </EvidenceSection>
      <EvidenceSection title="Status & currentness">
        <p>{text(record['Status evidence'])}</p>
      </EvidenceSection>
      {text(record['Gate warnings'], '').toLowerCase() !== 'none' && text(record['Gate warnings'], '') ? (
        <div className="review-warning"><AlertTriangle size={17} /><span>{text(record['Gate warnings'])}</span></div>
      ) : null}
      {queue === 'new' ? (
        <EvidenceSection title="Refuter analysis" open={false}>
          <div className={cn('review-chip', `tone-${badgeTone(record['Refuter verdict'])}`)}>{text(record['Refuter verdict'])}</div>
          <p>{text(record['Refuter panel reasoning'])}</p>
        </EvidenceSection>
      ) : null}
    </>
  )
}

function ReferenceDrawer({ open, onClose, record, context, loading }: {
  open: boolean
  onClose: () => void
  record: JsonObject
  context: ReturnType<typeof useReviewContext>['data']
  loading: boolean
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLElement>(null)
  useEffect(() => {
    if (open) closeRef.current?.focus()
  }, [open])
  return (
    <AnimatePresence>
      {open ? (
        <>
          <m.button
            className="review-drawer-scrim"
            aria-label="Close reference panel"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <m.aside
            ref={drawerRef}
            className="review-reference-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reference-title"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 330, damping: 34 }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') onClose()
              if (event.key !== 'Tab') return
              const focusable = drawerRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
              if (!focusable?.length) return
              const first = focusable[0]
              const last = focusable[focusable.length - 1]
              if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
              if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
            }}
          >
            <header>
              <div><span className="review-eyebrow">Authoritative context</span><h2 id="reference-title">Act reference</h2></div>
              <button ref={closeRef} onClick={onClose} className="review-icon-button" aria-label="Close reference panel"><X size={19} /></button>
            </header>
            {loading || !context ? <div className="review-drawer-loading" /> : (
              <div className="review-drawer-content">
                <section>
                  <h3><FileCheck2 size={16} /> Source context</h3>
                  <p className="cc-verbatim compact">{text(record['Surrounding source context'] ?? record['Exact source snippet'] ?? record['Plain-language system rationale'])}</p>
                  {record['Official source URL'] ? <a href={text(record['Official source URL'])} target="_blank" rel="noreferrer">Open official source <ExternalLink size={13} /></a> : null}
                </section>
                <section>
                  <h3><Library size={16} /> Related provisions</h3>
                  {context.related_evidence.length ? context.related_evidence.slice(0, 12).map((row) => (
                    <article className="review-related" key={row.finding_key}>
                      <strong>{text(row.row['Law Name'])} · {text(row.row['Article / Section'])}</strong>
                      <p>{text(row.row['Verbatim Snippet']).slice(0, 240)}</p>
                      <span>{row.same_law ? 'Same law' : 'Same indicator'}</span>
                      <Link href={`/match/${row.finding_key}?economy=${encodeURIComponent(text(row.row['Economy'], ''))}&indicator=${encodeURIComponent(text(row.row['Indicator ID'], ''))}`}>Open Source Match <ExternalLink size={12} /></Link>
                    </article>
                  )) : <p className="review-muted">No related evidence rows in this snapshot.</p>}
                </section>
                <section>
                  <h3><BookOpenCheck size={16} /> ESCAP Master Known</h3>
                  {context.master_known.length ? context.master_known.map((entry, index) => (
                    <article className="review-master" key={index}>
                      <strong>{text(entry['Act/instrument'])}</strong>
                      <p>{text(entry['Article references'])}</p>
                      <span>Methodology score {text(entry['Methodology score'])}</span>
                      <p>{text(entry['Master impact/rationale'])}</p>
                    </article>
                  )) : <p className="review-muted">No matching Master Known entry.</p>}
                </section>
                <section>
                  <h3><Gavel size={16} /> Indicator methodology</h3>
                  {context.indicator_criteria ? (
                    <>
                      <strong>{text(context.indicator_criteria['Name'])}</strong>
                      <p>{text(context.indicator_criteria['Legal question'])}</p>
                      <dl className="review-methodology">
                        <div><dt>Scoring</dt><dd><pre>{text(parseJson(context.indicator_criteria['Scoring criteria']))}</pre></dd></div>
                        <div><dt>Exclusions</dt><dd><pre>{text(parseJson(context.indicator_criteria['Exclusions']))}</pre></dd></div>
                        <div><dt>Polarity</dt><dd>{text(context.indicator_criteria['Polarity'])}</dd></div>
                      </dl>
                    </>
                  ) : <p className="review-muted">Methodology context is unavailable.</p>}
                </section>
              </div>
            )}
          </m.aside>
        </>
      ) : null}
    </AnimatePresence>
  )
}

function DecisionPanel({ queue, item, record, context }: {
  queue: WorkspaceQueue
  item: ReviewItem
  record: JsonObject
  context: ReturnType<typeof useReviewContext>['data']
}) {
  const { user } = useAuth()
  const summary = useSummary()
  const decide = useDecide()
  const [stage, setStage] = useState<ReviewStage>('citation')
  const [note, setNote] = useState('')
  const [recallVerdict, setRecallVerdict] = useState<RecallVerdict>(() => {
    const proposed = text(record['Proposed verdict'], '').toUpperCase()
    return RECALL_VERDICTS.find((entry) => proposed.includes(entry.value))?.value ?? 'REAL_MISS'
  })
  const [score, setScore] = useState<Zone3Score>(() => Number(record['Deterministic score'] ?? 0) as Zone3Score)
  const [override, setOverride] = useState(false)
  const [officialSource, setOfficialSource] = useState(() => text(record['Reviewer official source URL'], ''))
  const [receipt, setReceipt] = useState<{ exported: boolean; hash: string } | null>(null)
  const roles = summary.data?.reviewer_roles ?? []
  const availableStages = (['citation', 'mapping', 'status'] as ReviewStage[]).filter((role) => roles.includes(`${role}_reviewer`) || roles.includes('admin'))
  const effectiveStage = availableStages.includes(stage) ? stage : availableStages[0] ?? stage
  const stale = summary.data?.snapshot.stale ?? true
  const technicallyEligible = context?.approval_eligibility.eligible ?? item.approval_eligibility?.eligible ?? false
  const disabled = decide.isPending || stale || item.blocked

  const submitFinding = useCallback(async (decision: FindingVerdict) => {
    if (!item.finding_key || !availableStages.includes(effectiveStage)) return
    if (decision === 'rejected' && !note.trim()) return
    const response = await decide.mutateAsync({
      domain: 'findings',
      payload: {
        finding_key: item.finding_key,
        queue: queue as FindingQueue,
        review_stage: effectiveStage,
        decision,
        citation_checked: effectiveStage === 'citation',
        mapping_checked: effectiveStage === 'mapping',
        status_checked: effectiveStage === 'status',
        note,
        expected_latest_decision_id: item.review_state?.stages[effectiveStage]?.id ?? null,
      },
    })
    if ('engine_exported' in response) setReceipt({ exported: response.engine_exported, hash: response.authoritative_file_hash })
  }, [availableStages, decide, effectiveStage, item, note, queue])

  const requestCorrection = useCallback(async () => {
    if (!item.finding_key || note.trim().length < 3) return
    const response = await decide.mutateAsync({
      domain: 'correction',
      payload: {
        finding_key: item.finding_key,
        queue: queue as FindingQueue,
        explanation: note,
        expected_latest_correction_id: item.latest_correction?.id ?? null,
      },
    })
    setReceipt({ exported: false, hash: response.authoritative_file_hash })
  }, [decide, item, note, queue])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey || disabled) return
      if (event.key === 'a' && queue !== 'recall' && queue !== 'zone3' && technicallyEligible) void submitFinding('approved')
      if (event.key === 'r') document.getElementById('review-note')?.focus()
      if (event.key === 'c') document.getElementById('review-note')?.focus()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [disabled, queue, submitFinding, technicallyEligible])

  if (queue === 'recall') {
    const expected = item.latest_decision?.id ?? null
    return (
      <div className="review-decision-panel">
        <div className="review-decision-heading"><div><span className="review-eyebrow">Legal adjudication</span><h3>Recall verdict</h3></div><span>{user?.full_name ?? user?.email ?? 'Authenticated reviewer'}</span></div>
        <div className="review-radio-grid">
          {RECALL_VERDICTS.map((entry) => <label key={entry.value}><input type="radio" checked={recallVerdict === entry.value} onChange={() => setRecallVerdict(entry.value)} /> <span>{entry.label}</span></label>)}
        </div>
        <textarea id="review-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Reasoning and official-source conclusion…" />
        <label className="review-field"><span>Official source URL</span><input type="url" value={officialSource} onChange={(event) => setOfficialSource(event.target.value)} placeholder="https://official-register.example/…" /></label>
        <button className="review-primary" disabled={disabled || (recallVerdict === 'NEEDS_CORRECTION' && !note.trim()) || !roles.some((role) => ['mapping_reviewer', 'admin'].includes(role))} onClick={() => void decide.mutateAsync({ domain: 'recall', payload: { recall_key: item.stable_key, verdict: recallVerdict, reasoning: note, official_source_url: officialSource, expected_latest_decision_id: expected } })}>
          {decide.isPending ? 'Saving review—waiting for authoritative receipt.' : 'Record recall verdict'}
        </button>
      </div>
    )
  }

  if (queue === 'zone3') {
    return (
      <div className="review-decision-panel">
        <div className="review-decision-heading"><div><span className="review-eyebrow">Indicator-level decision</span><h3>Approve or override score</h3></div><span>{user?.full_name ?? user?.email ?? 'Authenticated reviewer'}</span></div>
        <div className="review-score-choice">
          <button className={cn(!override && 'selected')} onClick={() => { setOverride(false); setScore(Number(record['Deterministic score'] ?? 0) as Zone3Score) }}>Approve deterministic</button>
          <button className={cn(override && 'selected')} onClick={() => setOverride(true)}>Override</button>
        </div>
        {override ? <div className="review-score-values">{([0, 0.5, 1] as Zone3Score[]).map((value) => <button key={value} onClick={() => setScore(value)} className={cn(score === value && 'selected')}>{value}</button>)}</div> : null}
        <textarea id="review-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder={override ? 'Required legal reasoning for override…' : 'Optional reviewer note…'} />
        <button className="review-primary" disabled={disabled || (override && !note.trim()) || !roles.some((role) => ['mapping_reviewer', 'admin'].includes(role))} onClick={() => void decide.mutateAsync({ domain: 'zone3', payload: { score_key: item.stable_key, verdict: override ? 'overridden' : 'approved', score, reasoning: note, expected_latest_decision_id: item.latest_decision?.id ?? null } })}>
          {decide.isPending ? 'Saving review—waiting for authoritative receipt.' : `${override ? 'Override' : 'Approve'} score ${score}`}
        </button>
      </div>
    )
  }

  return (
    <div className="review-decision-panel">
      <div className="review-decision-heading"><div><span className="review-eyebrow">Your authority</span><h3>Record review stage</h3></div><span>{user?.full_name ?? user?.email ?? 'Authenticated reviewer'}</span></div>
      <StageStrip item={item} />
      {availableStages.length ? <div className="review-stage-tabs" role="tablist">{availableStages.map((value) => <button role="tab" aria-selected={effectiveStage === value} className={cn(effectiveStage === value && 'selected')} onClick={() => setStage(value)} key={value}>{value}</button>)}</div> : <div className="review-warning"><ShieldAlert size={17} />You do not have a review role for this evidence.</div>}
      {!technicallyEligible ? <div className="review-block"><ShieldAlert size={17} /><span>{context?.approval_eligibility.reason ?? item.approval_eligibility?.reason ?? 'Technical evidence is incomplete.'}</span></div> : null}
      <textarea id="review-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Required for rejection or correction; optional for approval…" />
      <div className="review-decision-actions">
        <button className="review-primary" disabled={disabled || !technicallyEligible || !availableStages.includes(effectiveStage)} onClick={() => void submitFinding('approved')}><Check size={17} /> Approve {effectiveStage}</button>
        <button className="review-secondary danger" disabled={disabled || !note.trim() || !availableStages.includes(effectiveStage)} onClick={() => void submitFinding('rejected')}><XCircle size={17} /> Reject</button>
        <button className="review-secondary" disabled={disabled || note.trim().length < 3 || !availableStages.length} onClick={() => void requestCorrection()}><ShieldAlert size={17} /> Request correction</button>
      </div>
      <AnimatePresence mode="wait">
        {decide.isPending ? <m.div className="review-saving" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>Saving review—waiting for authoritative receipt.</m.div> : receipt ? <m.div className={cn('review-receipt', receipt.exported ? 'exported' : 'partial')} initial={{ opacity: 0, scale: .98 }} animate={{ opacity: 1, scale: 1 }}><CheckCircle2 size={17} /><span>{receipt.exported ? `Final approval exported to engine · ${receipt.hash.slice(0, 8)}` : 'Stage recorded, awaiting the required second reviewer; no final decision was exported to the engine.'}</span></m.div> : null}
      </AnimatePresence>
    </div>
  )
}

export default function ReviewWorkbench() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const requestedQueue = searchParams.get('queue') as WorkspaceQueue | null
  const queue = QUEUES.some((entry) => entry.key === requestedQueue) ? requestedQueue! : 'new'
  const requestedItem = searchParams.get('item')
  const [filter, setFilter] = useState(searchParams.get('filter') ?? '')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [mobileRailOpen, setMobileRailOpen] = useState(!requestedItem)
  const [selectedKnown, setSelectedKnown] = useState<Set<string>>(new Set())
  const summary = useSummary()
  const queueQuery = useReviewQueue(queue, { page_size: 200 })
  const loadError = summary.error ?? queueQuery.error
  const records = useMemo(() => (queueQuery.data?.results ?? []).map((item) => ({ item, record: rowRecord(queueQuery.data?.headers ?? [], item.row) })).sort((left, right) => {
    const leftDecided = queue === 'recall' || queue === 'zone3' ? Boolean(left.item.latest_decision) : Boolean(left.item.review_state?.decision)
    const rightDecided = queue === 'recall' || queue === 'zone3' ? Boolean(right.item.latest_decision) : Boolean(right.item.review_state?.decision)
    if (leftDecided !== rightDecided) return leftDecided ? 1 : -1
    if (queue === 'new') {
      const rank: Record<string, number> = { SPLIT: 0, KEEP: 1, REJECT: 2 }
      const difference = (rank[text(left.record['Refuter verdict']).toUpperCase()] ?? 3) - (rank[text(right.record['Refuter verdict']).toUpperCase()] ?? 3)
      if (difference) return difference
    }
    return left.item.position - right.item.position
  }), [queue, queueQuery.data])
  const filtered = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase()
    if (!needle) return records
    return records.filter(({ record }) => Object.values(record).some((value) => text(value, '').toLocaleLowerCase().includes(needle)))
  }, [filter, records])
  const selectedIndex = Math.max(0, filtered.findIndex(({ item }) => item.stable_key === requestedItem))
  const selected = filtered[selectedIndex] ?? filtered[0] ?? null
  const context = useReviewContext(queue, selected?.item.stable_key)
  const historyDomain = queue === 'recall' ? 'recall' : queue === 'zone3' ? 'zone3' : 'findings'
  const history = useDecisionHistory(historyDomain, selected?.item.stable_key)
  const decide = useDecide()

  const setUrl = useCallback((nextQueue: WorkspaceQueue, stableKey?: string, nextFilter = '') => {
    const params = new URLSearchParams()
    params.set('queue', nextQueue)
    if (stableKey) params.set('item', stableKey)
    if (nextFilter.trim()) params.set('filter', nextFilter.trim())
    router.replace(`${pathname}?${params.toString()}`, { scroll: false })
  }, [pathname, router])

  useEffect(() => {
    if (!requestedItem && filtered[0]) setUrl(queue, filtered[0].item.stable_key, filter)
  }, [filter, filtered, queue, requestedItem, setUrl])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey || !selected) return
      if (event.key !== 'j' && event.key !== 'k') return
      event.preventDefault()
      const offset = event.key === 'j' ? 1 : -1
      const next = filtered[Math.min(filtered.length - 1, Math.max(0, selectedIndex + offset))]
      if (next) { setUrl(queue, next.item.stable_key); setMobileRailOpen(false) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [filtered, queue, selected, selectedIndex, setUrl])

  const bulkEligible = filtered.filter(({ item, record }) => {
    const warnings = text(record['Gate warnings'], '').trim().toLowerCase()
    return item.finding_key && !item.blocked && item.approval_eligibility?.eligible !== false && (!warnings || warnings === 'none' || warnings === '—')
  })

  const submitBulk = async () => {
    const keys = [...selectedKnown]
    if (!keys.length) return
    const stage: ReviewStage = summary.data?.reviewer_roles.includes('citation_reviewer') ? 'citation' : 'mapping'
    await decide.mutateAsync({
      domain: 'findings-bulk',
      payload: {
        finding_keys: keys,
        review_stage: stage,
        citation_checked: stage === 'citation',
        mapping_checked: stage === 'mapping',
        expected_latest_decision_ids: Object.fromEntries(keys.map((key) => {
          const item = records.find((entry) => entry.item.finding_key === key)?.item
          return [key, item?.review_state?.stages[stage]?.id ?? null]
        })),
      },
    })
    setSelectedKnown(new Set())
  }

  return (
    <LazyMotion features={domAnimation}>
      <MotionConfig reducedMotion="user">
        <div className="review-workbench">
          <header className="review-page-header">
            <div>
              <span className="review-eyebrow"><ShieldCheck size={14} /> Authoritative legal review</span>
              <h1>Review & approve</h1>
              <p>Every decision is staged, attributed and written through the engine&apos;s authoritative audit path.</p>
            </div>
            <div className="review-shortcuts" aria-label="Keyboard shortcuts"><kbd>J</kbd><kbd>K</kbd><span>navigate</span><kbd>A</kbd><span>approve</span></div>
          </header>

          <nav className="review-queue-tabs" aria-label="Review queues">
            {QUEUES.map((entry) => {
              const progress = summary.data?.progress[entry.key]
              return <button key={entry.key} className={cn(queue === entry.key && 'active')} onClick={() => { setUrl(entry.key); setMobileRailOpen(true); setSelectedKnown(new Set()) }}>
                {queue === entry.key ? <m.span layoutId="queue-indicator" className="review-tab-indicator" /> : null}
                <span>{entry.label}</span><small suppressHydrationWarning>{progress?.decided ?? 0}/{progress?.total ?? 0}</small>
              </button>
            })}
          </nav>

          {loadError ? <section className="review-load-error" role="alert">
            <AlertTriangle size={22} />
            <div><strong>Review data is not ready</strong><p>{reviewLoadError(loadError)}</p></div>
            <button onClick={() => void Promise.all([summary.refetch(), queueQuery.refetch()])}>Try again</button>
          </section> : <div className={cn('review-layout', mobileRailOpen && 'mobile-list-open')}>
            <aside className="review-rail" aria-label={`${queue} review queue`}>
              <div className="review-rail-tools">
                <label><Search size={15} /><input value={filter} onChange={(event) => { const value = event.target.value; setFilter(value); setUrl(queue, selected?.item.stable_key, value) }} placeholder="Filter this queue…" /><Filter size={14} /></label>
                <span>{filtered.length} rows</span>
              </div>
              {queue === 'known' ? <div className="review-bulk-bar"><label><input type="checkbox" checked={bulkEligible.length > 0 && selectedKnown.size === bulkEligible.length} onChange={(event) => setSelectedKnown(event.target.checked ? new Set(bulkEligible.map(({ item }) => item.finding_key!)) : new Set())} /> Select eligible filtered rows</label><button disabled={!selectedKnown.size || decide.isPending} onClick={() => void submitBulk()}>Approve {selectedKnown.size || ''}</button></div> : null}
              <div className="review-rail-list">
                <AnimatePresence initial={false} mode="popLayout">
                  {filtered.map(({ item, record }, index) => {
                    const active = selected?.item.stable_key === item.stable_key
                    const decided = queue === 'recall' || queue === 'zone3' ? Boolean(item.latest_decision) : Boolean(item.review_state?.decision)
                    return <m.article layout key={item.stable_key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ delay: Math.min(index, 8) * .035 }} className={cn('review-rail-card', active && 'active', item.blocked && 'blocked')}>
                      {queue === 'known' ? <input aria-label={`Select ${reviewId(record, item)}`} type="checkbox" disabled={!bulkEligible.some((entry) => entry.item.stable_key === item.stable_key)} checked={Boolean(item.finding_key && selectedKnown.has(item.finding_key))} onChange={(event) => { const next = new Set(selectedKnown); if (item.finding_key) { if (event.target.checked) next.add(item.finding_key); else next.delete(item.finding_key) } setSelectedKnown(next) }} /> : null}
                      <button onClick={() => { setUrl(queue, item.stable_key); setMobileRailOpen(false) }}>
                        <span className="review-rail-meta"><strong>{reviewId(record, item)}</strong><em>{text(record['Economy'])} · {text(record['Indicator'])}</em>{decided ? <CheckCircle2 size={14} /> : item.blocked ? <ShieldAlert size={14} /> : <CircleDashed size={14} />}</span>
                        <h3>{itemTitle(record)}</h3>
                        <p>{text(record['Article/section'] ?? record['Master citation'] ?? record['Deterministic reason'] ?? record['Review guidance']).slice(0, 130)}</p>
                        {record['Refuter verdict'] ? <span className={cn('review-chip', `tone-${badgeTone(record['Refuter verdict'])}`)}>{text(record['Refuter verdict'])}</span> : null}
                      </button>
                    </m.article>
                  })}
                </AnimatePresence>
              </div>
            </aside>

            <main className="review-canvas">
              {selected ? <m.div key={selected.item.stable_key} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: .22 }}>
                <div className="review-canvas-toolbar"><button className="review-mobile-back" onClick={() => setMobileRailOpen(true)}><ArrowLeft size={17} /> Queue</button><div className="review-toolbar-meta"><span>{reviewId(selected.record, selected.item)}</span><span>{selectedIndex + 1} of {filtered.length}</span></div><div className="review-toolbar-actions">{selected.item.finding_key ? <Link className="review-reference-button" href={`/match/${selected.item.finding_key}?queue=${queue}`}><FileCheck2 size={16} /> Source Match</Link> : null}<button className="review-reference-button" onClick={() => setDrawerOpen(true)}><BookOpenCheck size={16} /> Act reference <ChevronRight size={15} /></button></div></div>
                <article className={cn('review-focus-card', selected.item.blocked && 'blocked')}>
                  <header>
                    <div><span className="review-eyebrow">{text(selected.record['Economy'])} · {text(selected.record['Indicator'])}</span><h2>{itemTitle(selected.record)}</h2><p>{text(selected.record['Article/section'] ?? selected.record['Master citation'] ?? selected.record['Indicator question'])}</p></div>
                    <div className={cn('review-status-mark', selected.item.review_state?.decision === 'approved' && 'approved', selected.item.blocked && 'blocked')}>{selected.item.blocked ? <ShieldAlert size={18} /> : selected.item.review_state?.decision === 'approved' ? <CheckCircle2 size={18} /> : <CircleDashed size={18} />}<span>{selected.item.blocked ? 'Blocked' : selected.item.review_state?.decision ?? 'Pending'}</span></div>
                  </header>
                  {selected.item.blocked ? <div className="review-block"><ShieldAlert size={18} /><span>{selected.item.block_reason}</span></div> : null}
                  {context.data?.score_semantics ? <div className="review-score-semantics"><Info size={17} /><div><strong>Evidence row—not a standalone score</strong><span>{context.data.score_semantics.explanation} Effective indicator score: <b>{context.data.zone3?.effective_score ?? 'pending'}</b> ({context.data.zone3?.source ?? 'not available'}).</span></div></div> : null}
                  <QueueSpecificEvidence queue={queue} record={selected.record} />
                </article>
                <DecisionPanel key={selected.item.stable_key} queue={queue} item={selected.item} record={selected.record} context={context.data} />
                {history.data && history.data.results.length ? <section className="review-history"><h3><History size={16} /> Append-only history</h3>{history.data.results.slice().reverse().map((entry) => <article key={entry.id}><strong>{'stage' in entry ? entry.stage : entry.verdict}</strong><span>{entry.reviewer_name} · {new Date(entry.reviewed_at).toLocaleString()}</span></article>)}</section> : null}
              </m.div> : queueQuery.isPending ? <div className="review-canvas-loading" /> : <div className="review-empty"><Menu size={24} /><h2>No rows match this filter</h2><button onClick={() => setFilter('')}>Clear filter</button></div>}
            </main>
          </div>}
          {selected ? <ReferenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} record={selected.record} context={context.data} loading={context.isPending} /> : null}
        </div>
      </MotionConfig>
    </LazyMotion>
  )
}
