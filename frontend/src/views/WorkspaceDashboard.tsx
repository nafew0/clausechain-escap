'use client'

import Link from 'next/link'
import { Activity, ArrowRight, CheckCircle2, CircleDashed, FileCheck2, GitBranch, ShieldAlert } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, SnapshotBanner, TruthBadge } from '@/components/clausechain/TruthState'
import { useSummary } from '@/hooks/workspace'
import type { WorkspaceQueue } from '@/types/workspace'

const QUEUES: { key: WorkspaceQueue; label: string }[] = [
  { key: 'new', label: 'NEW findings' }, { key: 'absence', label: 'Absence' },
  { key: 'recall', label: 'Recall' }, { key: 'zone3', label: 'Zone-3' }, { key: 'known', label: 'KNOWN' },
]

export default function WorkspaceDashboard() {
  const query = useSummary()
  const data = query.data
  return <WorkspaceShell breadcrumbs={[{ label: 'Dashboard' }]}><div className="cc-page live-dashboard">
    <div className="cc-page-header"><div><TruthBadge state="live" /><h1 className="cc-page-title text-[36px] mt-3">ClauseChain evidence command centre</h1><p className="text-cc-ink-500 mt-1.5">Authoritative review progress, champion gates and engine runs—without simulated KPIs.</p></div><div className="cc-actions"><Link className="truth-primary-link" href="/review">Open legal review <ArrowRight size={15} /></Link></div></div>
    {query.isError || !data ? <PageUnavailable title={query.isPending ? 'Loading the authoritative workspace…' : 'Dashboard data is unavailable'} /> : <>
      <SnapshotBanner snapshot={data.snapshot} />
      <section className="dashboard-champion" data-data-card><div className={data.champion.status === 'PASS' ? 'pass' : 'fail'}>{data.champion.status === 'PASS' ? <CheckCircle2 /> : <ShieldAlert />}<div><span>Champion gate status</span><strong>{String(data.champion.status ?? 'UNKNOWN')}</strong></div></div><ul>{Array.isArray(data.champion.failures) && data.champion.failures.length ? data.champion.failures.map((failure, index) => <li key={index}>{String(failure)}</li>) : <li>No unresolved champion failures are recorded.</li>}</ul></section>
      <section><div className="truth-section-heading"><div><span>Legal decisions</span><h2>Queue progress</h2></div><Link href="/review">Review workbench <ArrowRight size={14} /></Link></div><div className="cc-kpi-grid-five">{QUEUES.map(({ key, label }) => { const progress = data.progress[key]; const pct = progress?.total ? Math.round(progress.decided / progress.total * 100) : 0; return <Link href={`/review?queue=${key}`} key={key} className="truth-stat-card" data-data-card><span>{label}</span><strong>{progress?.decided ?? 0}<small> / {progress?.total ?? 0}</small></strong><div><i style={{ width: `${pct}%` }} /></div><em>{pct}% decided</em></Link> })}</div></section>
      <section><div className="truth-section-heading"><div><span>Stored envelopes</span><h2>Six engine runs</h2></div><Link href="/runs">Run console <ArrowRight size={14} /></Link></div><div className="dashboard-run-grid">{(data.runs ?? []).map(run => <article key={run.run_name} className="truth-data-card" data-data-card><header><div><span>{run.country} · Pillar {run.pillar}</span><strong>{run.run_name}</strong></div>{run.warning_count ? <ShieldAlert size={17} /> : <CheckCircle2 size={17} />}</header><dl><div><dt>Rows</dt><dd>{run.rows_produced}</dd></div><div><dt>NEW</dt><dd>{run.discovery_counts.NEW}</dd></div><div><dt>KNOWN</dt><dd>{run.discovery_counts.KNOWN}</dd></div><div><dt>Warnings</dt><dd>{run.warning_count}</dd></div></dl><footer><Activity size={13} />{run.elapsed_seconds == null ? 'elapsed n/a' : `${Number(run.elapsed_seconds).toFixed(1)}s`}<span>{run.total_usd == null ? 'cost n/a' : `$${Number(run.total_usd).toFixed(4)}`}</span></footer></article>)}</div></section>
      <section className="dashboard-links"><Link href="/submission"><FileCheck2 /> <span><strong>Submission</strong><small>Candidate rows and deterministic gates</small></span><ArrowRight /></Link><Link href="/raw-data"><CircleDashed /><span><strong>Raw Data</strong><small>Immutable artifact explorer</small></span><ArrowRight /></Link><Link href="/knowledge-graph"><GitBranch /><span><strong>Knowledge Graph</strong><small>Read-only Neo4j provenance snapshot</small></span><ArrowRight /></Link></section>
    </>}
  </div></WorkspaceShell>
}
