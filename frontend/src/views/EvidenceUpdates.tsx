'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowRight, CheckCircle2, GitCompareArrows, History, ShieldAlert } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, SnapshotBanner, TruthBadge } from '@/components/clausechain/TruthState'
import { ModePageHeader } from '@/components/workspace/ModePageHeader'
import { useAuth } from '@/contexts/AuthContext'
import { useEvidenceChangeDecision, useEvidenceChanges, usePublishEvidenceChanges } from '@/hooks/workspace'
import { modeHref } from '@/lib/runMode'

type Filter = 'attention' | 'new' | 'revised' | 'not_reproduced' | 'unchanged'

export default function EvidenceUpdates() {
  const { user } = useAuth()
  const query = useEvidenceChanges()
  const decide = useEvidenceChangeDecision()
  const publish = usePublishEvidenceChanges()
  const [filter, setFilter] = useState<Filter>('attention')
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const changes = useMemo(() => {
    const rows = query.data?.results ?? []
    return filter === 'attention' ? rows.filter(row => row.kind !== 'unchanged') : rows.filter(row => row.kind === filter)
  }, [filter, query.data])

  const disposition = async (id: string, verdict: 'retain' | 'retire' | 'investigate', expected: string | null) => {
    const comment = notes[id]?.trim() ?? ''
    if (comment.length < 3) return
    setError('')
    try {
      await decide.mutateAsync({ changeId: id, verdict, comment, expectedLatestDecisionId: expected })
    } catch {
      setError('The authoritative update changed. Refresh and reconsider this disposition.')
    }
  }

  const publishRegistry = async () => {
    if (!window.confirm('Publish this fully reviewed evidence update to the current ESCAP registry?')) return
    setError('')
    try { await publish.mutateAsync() } catch { setError('Publishing is blocked until every changed or missing record has a final disposition.') }
  }

  return <WorkspaceShell breadcrumbs={[{ label: 'Evidence Updates' }]}><div className="cc-page evidence-updates">
    <ModePageHeader
      eyebrow={<><TruthBadge state="live" />{query.data ? <SnapshotBanner snapshot={query.data.snapshot} /> : null}</>}
      title="Evidence updates"
      description="Compare each engine rerun with the current ESCAP registry. Nothing historical is overwritten."
      actions={user?.is_superuser && query.data?.change_set.state === 'draft' ? <button className="truth-primary-link" disabled={publish.isPending} onClick={() => void publishRegistry()}>{publish.isPending ? 'Publishing…' : 'Publish reviewed update'}</button> : null}
    />
    {query.isError || !query.data ? <PageUnavailable title={query.isPending ? 'Reconciling evidence history…' : 'Evidence reconciliation is unavailable'} /> : <>
      <section className={`registry-update ${query.data.change_set.state}`} data-data-card><header><div><GitCompareArrows /><span><small>Registry reconciliation</small><strong>{query.data.change_set.state === 'draft' ? 'Candidate update' : 'Published registry version'}</strong></span></div><b>{query.data.change_set.state.toUpperCase()}</b></header><div className="registry-update-grid">{Object.entries(query.data.change_set.counts).map(([kind, count]) => <span key={kind}><strong>{count}</strong>{kind.replace('_', ' ')}</span>)}</div><footer><History size={14} />{query.data.change_set.attention.decided} of {query.data.change_set.attention.total} changed records have a final disposition.</footer></section>
      {error ? <div className="review-block"><ShieldAlert size={17} /><span>{error}</span></div> : null}
      <nav className="evidence-update-tabs">{(['attention', 'new', 'revised', 'not_reproduced', 'unchanged'] as Filter[]).map(value => <button className={filter === value ? 'active' : ''} onClick={() => setFilter(value)} key={value}>{value.replace('_', ' ')}</button>)}</nav>
      <section className="evidence-update-list">{changes.map(change => <article className={`evidence-update-card ${change.kind}`} key={change.id} data-data-card>
        <header><div><span>{change.identity.economy} · {change.identity.indicator_id}</span><h2>{change.identity.law_name}</h2><p>{change.identity.citation}</p></div><b>{change.kind.replace('_', ' ')}</b></header>
        {change.invalidated_stages.length ? <p className="evidence-update-impact"><AlertTriangle size={15} /> Re-review required: {change.invalidated_stages.join(', ')}</p> : <p className="evidence-update-impact retained"><CheckCircle2 size={15} /> Evidence-equivalent review stages remain valid.</p>}
        {change.current_finding_key && change.review_queue ? <Link href={modeHref(`/review?queue=${change.review_queue}&item=${change.current_finding_key}`)}>Open legal evidence <ArrowRight size={14} /></Link> : null}
        {change.kind === 'not_reproduced' && query.data.change_set.state === 'draft' ? <div className="evidence-update-disposition"><textarea value={notes[change.id] ?? ''} onChange={event => setNotes(current => ({ ...current, [change.id]: event.target.value }))} placeholder="Required reason based on the rerun and current legal source…" /><div><button disabled={decide.isPending} onClick={() => void disposition(change.id, 'retain', change.latest_decision?.id ?? null)}>Retain current</button><button disabled={decide.isPending} onClick={() => void disposition(change.id, 'investigate', change.latest_decision?.id ?? null)}>Investigate</button><button className="danger" disabled={decide.isPending} onClick={() => void disposition(change.id, 'retire', change.latest_decision?.id ?? null)}>Retire evidence</button></div></div> : null}
        {change.latest_decision ? <footer>{change.latest_decision.verdict} · {change.latest_decision.reviewer_name} · {change.latest_decision.comment}</footer> : null}
      </article>)}</section>
      {!changes.length ? <div className="review-empty"><CheckCircle2 /><h2>No evidence changes in this view</h2></div> : null}
    </>}
  </div></WorkspaceShell>
}
