'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileCheck2,
  Filter,
  LoaderCircle,
  Play,
  Search,
  ShieldAlert,
  X,
  XCircle,
} from 'lucide-react'
import { AnimatePresence, LazyMotion, MotionConfig, domAnimation, m } from 'motion/react'

import { useAuth } from '@/contexts/AuthContext'
import { useEngineActions, useLaunchEngineAction, useSubmission } from '@/hooks/workspace'
import { cn } from '@/lib/utils'
import type { SubmissionParams, SubmissionRow } from '@/types/workspace'

const ECONOMIES = ['', 'Singapore', 'Malaysia', 'Australia']
const REVIEWS = ['', 'pending', 'approved', 'rejected'] as const

function text(value: unknown, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function gateSummary(item: SubmissionRow) {
  const gates = item.verification.gates
  if (!gates.length) {
    return 'No affirmative citation gates are attached to this row; review its coverage or block evidence in the drawer.'
  }
  const nonPassing = gates.filter((gate) => String(gate.status).toUpperCase() !== 'PASS')
  if (!nonPassing.length) {
    return `All gates pass: ${gates.map((gate) => text(gate.gate_id, 'unnamed')).join(', ')}`
  }
  return `Non-passing gates: ${nonPassing.map((gate) => {
    const reason = text(gate.reason, '')
    return `${text(gate.gate_id, 'unnamed')} (${text(gate.status, 'UNKNOWN')})${reason ? ` — ${reason}` : ''}`
  }).join('; ')}`
}

function readParams(search: URLSearchParams): SubmissionParams {
  const page = Math.max(1, Number(search.get('page') ?? 1))
  const review = search.get('review') as SubmissionParams['review']
  return {
    page,
    page_size: 25,
    q: search.get('q') ?? undefined,
    economy: search.get('economy') ?? undefined,
    pillar: search.get('pillar') ?? undefined,
    tag: search.get('tag') ?? undefined,
    status: search.get('status') ?? undefined,
    review: review || undefined,
  }
}

function SubmissionDrawer({ item, close }: { item: SubmissionRow; close: () => void }) {
  return <><m.button className="submission-scrim" aria-label="Close row details" onClick={close} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} /><m.aside className="submission-drawer" initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', stiffness: 330, damping: 34 }}><header><div><span>PROVENANCE RECORD</span><h2>{text(item.row['Law Name'])}</h2><p>{text(item.row['Article / Section'])} · {text(item.row['Indicator ID'])}</p></div><button onClick={close} aria-label="Close"><X size={18} /></button></header><div className="submission-drawer-body"><section className="submission-quote"><span>Exact exported snippet</span><p>{text(item.row['Verbatim Snippet'])}</p></section><section><h3>Mapping rationale</h3><p>{text(item.row['Mapping Rationale'])}</p></section><dl><div><dt>Match</dt><dd>{item.verification.match_label}</dd></div><div><dt>Source domain</dt><dd>{text(item.verification.source_domain)}</dd></div><div><dt>Page / anchor</dt><dd>{text(item.verification.page_or_anchor)}</dd></div><div><dt>Access date</dt><dd>{text(item.verification.access_date)}</dd></div><div><dt>Status</dt><dd>{text(item.verification.status)}</dd></div><div><dt>Review</dt><dd>{item.review_state.decision ?? 'pending'}</dd></div></dl><section><h3>SHA-256</h3><code className="submission-full-hash">{item.verification.source_sha256}</code></section><section><h3>Deterministic gates</h3><div className="submission-gates">{item.verification.gates.length ? item.verification.gates.map((gate, index) => <span className={String(gate.status) === 'PASS' ? 'pass' : 'fail'} key={index}>{text(gate.gate_id)} · {text(gate.status)}</span>) : <span className="na">No affirmative citation gates</span>}</div></section><div className="submission-drawer-actions"><Link href={`/match/${item.finding_key}`}><FileCheck2 size={15} /> Open Source Match</Link>{item.row['Source URL'] ? <a href={text(item.row['Source URL'])} target="_blank" rel="noreferrer">Official source <ExternalLink size={14} /></a> : null}</div></div></m.aside></>
}

export default function SubmissionExplorer() {
  const search = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const params = useMemo(() => readParams(search), [search])
  const query = useSubmission(params)
  const actions = useEngineActions()
  const launch = useLaunchEngineAction()
  const { user } = useAuth()
  const [draftSearch, setDraftSearch] = useState(params.q ?? '')
  const selectedKey = search.get('row')
  const selected = query.data?.results.find((row) => row.finding_key === selectedKey) ?? null
  const latestReplay = actions.data?.results.find((action) => action.kind === 'replay')

  useEffect(() => {
    if (latestReplay?.status === 'succeeded') void query.refetch()
  }, [latestReplay?.id, latestReplay?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const update = (changes: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams(search.toString())
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === '') next.delete(key)
      else next.set(key, String(value))
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false })
  }
  const replay = () => {
    if (!window.confirm('Queue deterministic submission replay from current named approvals? This does not approve any pending row.')) return
    launch.mutate({ kind: 'replay' })
  }

  return <LazyMotion features={domAnimation}><MotionConfig reducedMotion="user"><div className="submission-explorer"><header className="submission-header"><div><span><FileCheck2 size={14} /> Aggregated evidence · all economies and pillars</span><h1>Consolidated RDTII dataset</h1><p>Final artifacts are produced only by deterministic engine replay—not by this table.</p>{query.data?.release ? <em className="submission-release-state">Release {query.data.release.state}</em> : null}</div>{user?.is_superuser ? <button onClick={replay} disabled={launch.isPending || ['queued', 'running'].includes(latestReplay?.status ?? '')}><Play size={15} /> Run approval replay</button> : null}</header>
    {query.data?.final_artifacts.available ? <section className="submission-final-ready"><CheckCircle2 size={19} /><div><strong>Replayed artifacts available · {query.data.final_artifacts.rows} approved rows</strong><span>CSV {query.data.final_artifacts.csv_sha256?.slice(0, 12)}… · JSON {query.data.final_artifacts.json_sha256?.slice(0, 12)}…</span></div></section> : <section className="submission-final-pending"><AlertTriangle size={19} /><div><strong>No replayed final artifact is available</strong><span>The table below contains candidates; pending or rejected rows are not silently exported.</span></div></section>}
    {latestReplay ? <section className={cn('submission-replay-state', `state-${latestReplay.status}`)}>{latestReplay.status === 'failed' ? <XCircle size={18} /> : latestReplay.status === 'succeeded' ? <CheckCircle2 size={18} /> : <LoaderCircle size={18} />}<div><strong>Replay {latestReplay.status}</strong><span>{latestReplay.error || latestReplay.stdout || 'Waiting for the dedicated engine worker.'}</span></div></section> : null}
    <section className="submission-filters"><label className="submission-search"><Search size={15} /><input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') update({ q: draftSearch, page: 1 }) }} placeholder="Law, citation, indicator or quote…" /><button onClick={() => update({ q: draftSearch, page: 1 })}>Search</button></label><label><Filter size={14} /><select value={params.economy ?? ''} onChange={(event) => update({ economy: event.target.value, page: 1 })}>{ECONOMIES.map((value) => <option value={value} key={value}>{value || 'All economies'}</option>)}</select></label><label><select value={params.pillar ?? ''} onChange={(event) => update({ pillar: event.target.value, page: 1 })}><option value="">All pillars</option><option value="6">Pillar 6</option><option value="7">Pillar 7</option></select></label><label><select value={params.tag ?? ''} onChange={(event) => update({ tag: event.target.value, page: 1 })}><option value="">NEW + KNOWN</option><option value="NEW">NEW</option><option value="KNOWN">KNOWN</option></select></label><label><select value={params.review ?? ''} onChange={(event) => update({ review: event.target.value, page: 1 })}>{REVIEWS.map((value) => <option value={value} key={value}>{value || 'All review states'}</option>)}</select></label></section>
    {query.isPending ? <div className="submission-page-state"><LoaderCircle size={25} /> Loading candidate rows…</div> : query.isError || !query.data ? <div className="submission-page-state error"><ShieldAlert size={25} /> Submission API is unavailable.</div> : <><div className="submission-table-meta"><span>{query.data.count} candidate rows</span><span>13 required template fields + mechanical verification</span></div><div className="submission-table-wrap"><table><thead><tr><th className="sticky-col">Review</th>{query.data.template_columns.map((column) => <th key={column}>{column}</th>)}<th>Domain · tier</th><th>Match</th><th>Page / anchor</th><th>SHA-256</th><th>Access</th><th>Status</th><th>Gates</th></tr></thead><tbody>{query.data.results.map((item) => <tr key={item.finding_key} className={cn(item.verification.blocked && 'blocked')} onClick={() => update({ row: item.finding_key })}><td className="sticky-col"><span className={cn('submission-review-chip', item.review_state.decision ?? 'pending')}>{item.review_state.decision ?? 'pending'}</span></td>{query.data.template_columns.map((column) => <td key={column} title={text(item.template[column], '')}>{column === 'Discovery Tag' ? <b className={text(item.template[column]).toLowerCase()}>{text(item.template[column])}</b> : text(item.template[column])}</td>)}<td>{text(item.verification.source_domain)}<small>{text(item.verification.citation_tier)}</small></td><td><span className={cn('submission-match', item.verification.match_mode)}>{item.verification.match_label}</span></td><td>{text(item.verification.page_or_anchor)}</td><td><code>{item.verification.source_sha256.slice(0, 10)}…</code></td><td>{text(item.verification.access_date)}</td><td>{text(item.verification.status)}</td><td><span title={gateSummary(item)} aria-label={gateSummary(item)} className={item.verification.gates_pass ? 'gate-pass' : 'gate-warn'}>{item.verification.gates_pass ? '●●●' : '●○○'}</span></td></tr>)}</tbody></table></div><nav className="submission-pagination"><button disabled={!query.data.previous} onClick={() => update({ page: Math.max(1, Number(params.page) - 1) })}><ChevronLeft size={15} /> Previous</button><span>Page {params.page ?? 1} of {Math.max(1, Math.ceil(query.data.count / 25))}</span><button disabled={!query.data.next} onClick={() => update({ page: Number(params.page) + 1 })}>Next <ChevronRight size={15} /></button></nav></>}
    <AnimatePresence>{selected ? <SubmissionDrawer item={selected} close={() => update({ row: undefined })} /> : null}</AnimatePresence>
  </div></MotionConfig></LazyMotion>
}
