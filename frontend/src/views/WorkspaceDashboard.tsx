'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Database,
  FileCheck2,
  History,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, SnapshotBanner, TruthBadge } from '@/components/clausechain/TruthState'
import { ModePageHeader } from '@/components/workspace/ModePageHeader'
import { useSummary } from '@/hooks/workspace'
import { friendlyFailure } from '@/lib/readiness'
import type { WorkspaceQueue } from '@/types/workspace'
import { modeHref } from '@/lib/runMode'

const QUEUES: { key: WorkspaceQueue; label: string }[] = [
  { key: 'new', label: 'New evidence' },
  { key: 'absence', label: 'Absence checks' },
  { key: 'recall', label: 'Recall adjudication' },
  { key: 'zone3', label: 'Zone-3 scoring' },
  { key: 'known', label: 'Known evidence' },
]

export default function WorkspaceDashboard() {
  const query = useSummary()
  const data = query.data
  const update = data?.registry.change_set
  const updateCounts = update?.counts
  const integrityPass = data?.champion.status === 'PASS'
  const integrityItems = Array.isArray(data?.champion.failures) ? data.champion.failures : []
  const [openStatus, setOpenStatus] = useState<'update' | 'integrity' | null>(null)
  const toggleStatus = (panel: 'update' | 'integrity') => setOpenStatus((current) => current === panel ? null : panel)

  return <WorkspaceShell breadcrumbs={[{ label: 'Dashboard' }]}><div className="cc-page live-dashboard">
    <ModePageHeader
      eyebrow={<><TruthBadge state="live" />{data ? <><SnapshotBanner snapshot={data.snapshot} />{update ? <button type="button" className={`dashboard-status-chip update ${update.state}`} aria-expanded={openStatus === 'update'} onClick={() => toggleStatus('update')} title="Latest evidence update"><RefreshCw size={15} /><span>Evidence update</span><b>{update.state.toUpperCase()}</b></button> : null}<button type="button" className={`dashboard-status-chip integrity ${integrityPass ? 'pass' : 'fail'}`} aria-expanded={openStatus === 'integrity'} onClick={() => toggleStatus('integrity')} title="Automated evidence integrity">{integrityPass ? <CheckCircle2 size={15} /> : <ShieldAlert size={15} />}<span>Evidence integrity</span><b>{integrityPass ? 'PASS' : integrityItems.length || '!'}</b></button></> : null}</>}
      title="ESCAP legal evidence registry"
      description="Current legal evidence, controlled updates and attributable review history."
      actions={<Link className="truth-primary-link" href={modeHref("/review")}>Open legal review <ArrowRight size={15} /></Link>}
    />
    {query.isError || !data ? <PageUnavailable pending={query.isPending} title={query.isPending ? 'Loading the authoritative registry…' : 'Registry data is unavailable'} /> : <>
      <section className="registry-overview" data-data-card>
        <div className="registry-overview-title"><Database /><div><span>Current evidence registry</span><strong>{data.registry.current.toLocaleString()} active evidence records</strong><small>{data.registry.retired.toLocaleString()} retired · {data.registry.not_reproduced.toLocaleString()} marked not reproduced</small></div></div>
        <dl>
          <div><dt>Approved in this application</dt><dd>{data.registry.approved}</dd></div>
          <div><dt>Rejected in this application</dt><dd>{data.registry.rejected}</dd></div>
          <div><dt>No app decision record</dt><dd>{data.registry.decision_unrecorded}</dd></div>
          <div><dt>Technically blocked</dt><dd>{data.registry.blocked}</dd></div>
        </dl>
      </section>

      {update && openStatus === 'update' ? <section className={`registry-update ${update.state}`} data-data-card>
        <header><div><RefreshCw /><span><small>Latest evidence update</small><strong>{update.state === 'draft' ? 'Candidate update awaiting resolution' : 'Update incorporated into the registry'}</strong></span></div><b>{update.state.toUpperCase()}</b></header>
        <div className="registry-update-grid">
          <span><strong>{updateCounts?.unchanged ?? 0}</strong> unchanged</span>
          <span><strong>{updateCounts?.revised ?? 0}</strong> revised</span>
          <span><strong>{updateCounts?.new ?? 0}</strong> new</span>
          <span><strong>{updateCounts?.not_reproduced ?? 0}</strong> not reproduced</span>
        </div>
        <footer><History size={14} />{update.state === 'draft' ? `${update.attention?.decided ?? 0} of ${update.attention?.total ?? 0} changed records resolved. Unchanged decisions remain attached to their evidence.` : `Published ${update.published_at ? new Date(update.published_at).toLocaleString() : 'as the initial registry baseline'}.`}<Link href={modeHref("/evidence-updates")}>View comparison <ArrowRight size={13} /></Link></footer>
      </section> : null}

      {openStatus === 'integrity' ? <section className="dashboard-champion" data-data-card><div className={integrityPass ? 'pass' : 'fail'}>{integrityPass ? <CheckCircle2 /> : <ShieldAlert />}<div><span>Automated evidence integrity</span><strong>{integrityPass ? 'GATES PASS' : 'ATTENTION REQUIRED'}</strong></div></div><ul>{integrityItems.length ? integrityItems.map((failure, index) => <li key={index}>{friendlyFailure(failure)}</li>) : <li>All automated evidence checks are green.</li>}</ul></section> : null}

      <section><div className="truth-section-heading"><div><span>Active engine snapshot</span><h2>Review queues for this update</h2><p>These percentages describe only the currently imported evidence update—not the completeness of the ESCAP registry.</p></div><Link href={modeHref("/review")}>Review workbench <ArrowRight size={14} /></Link></div><div className="cc-kpi-grid-five">{QUEUES.map(({ key, label }) => { const progress = data.progress[key]; const pct = progress?.total ? Math.round(progress.decided / progress.total * 100) : 0; return <Link href={modeHref(`/review?queue=${key}`)} key={key} className="truth-stat-card" data-data-card><span>{label}</span><strong>{progress?.decided ?? 0}<small> / {progress?.total ?? 0}</small></strong><div><i style={{ width: `${pct}%` }} /></div><em>{pct}% recorded</em></Link> })}</div></section>

      <section><div className="truth-section-heading"><div><span>Engine activity</span><h2>Latest jurisdiction evaluations</h2></div><Link href={modeHref("/runs")}>Run console <ArrowRight size={14} /></Link></div><div className="dashboard-run-grid">{(data.runs ?? []).map(run => <article key={run.run_name} className="truth-data-card" data-data-card><header><div><span>{run.country} · Pillar {run.pillar}</span><strong>{run.run_name}</strong></div>{run.warning_count ? <ShieldAlert size={17} /> : <CheckCircle2 size={17} />}</header><dl><div><dt>Rows</dt><dd>{run.rows_produced}</dd></div><div><dt>NEW</dt><dd>{run.discovery_counts.NEW}</dd></div><div><dt>KNOWN</dt><dd>{run.discovery_counts.KNOWN}</dd></div><div><dt>Warnings</dt><dd>{run.warning_count}</dd></div></dl><footer><Activity size={13} />{run.elapsed_seconds == null ? 'elapsed n/a' : `${Number(run.elapsed_seconds).toFixed(1)}s`}<span>{run.total_usd == null ? 'cost n/a' : `$${Number(run.total_usd).toFixed(4)}`}</span></footer></article>)}</div></section>

      <section className="dashboard-links"><Link href={modeHref("/submission")}><FileCheck2 /> <span><strong>Evidence Dataset</strong><small>Current evidence rows and deterministic gates</small></span><ArrowRight /></Link><Link href={modeHref("/raw-data")}><CircleDashed /><span><strong>Raw Data</strong><small>Immutable artifact explorer</small></span><ArrowRight /></Link></section>
    </>}
  </div></WorkspaceShell>
}
