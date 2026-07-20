'use client'

import { BookOpenCheck, FileClock, ShieldAlert } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, TruthBadge } from '@/components/clausechain/TruthState'
import { useLedger } from '@/hooks/workspace'

export default function PipelineLedger() {
  const query = useLedger()
  return <WorkspaceShell breadcrumbs={[{ label: 'Audit Ledger' }]}><div className="cc-page ledger-live"><div className="cc-page-header"><div><TruthBadge state="live" /><h1 className="cc-page-title text-[32px] mt-3">Authoritative audit ledger</h1><p className="text-cc-ink-500 mt-1.5">Append-only decisions, named reviewers, writer receipts and release manifests from PostgreSQL.</p></div><div className="ops-total"><BookOpenCheck size={20} /><strong>{query.data?.count ?? '—'}</strong><span>audit events</span></div></div>
    {query.isError || !query.data ? <PageUnavailable title={query.isPending ? 'Loading the audit ledger…' : 'Audit ledger is unavailable'} /> : <div className="ops-table-wrap"><table><thead><tr>{['Time','Event','Domain / key','Reviewer','Action','Authoritative receipt','Supersedes'].map(value => <th key={value}>{value}</th>)}</tr></thead><tbody>{query.data.results.map(event => <tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString()}</td><td><span className="ledger-event-type"><FileClock size={13} />{event.event_type.replaceAll('_', ' ')}</span></td><td><b>{event.domain}</b><code title={event.key}>{event.key.slice(0, 18)}{event.key.length > 18 ? '…' : ''}</code></td><td><b>{event.reviewer_name || '—'}</b><small>{event.reviewer_role}</small></td><td><b>{event.stage ? `${event.stage} · ` : ''}{event.action}</b>{event.score ? <small>score {event.score}</small> : null}</td><td>{event.authoritative_file_hash ? <code title={event.authoritative_file_hash}>{event.authoritative_file_hash.slice(0, 16)}…</code> : <span className="muted"><ShieldAlert size={12} /> No file hash</span>}</td><td>{event.supersedes_id ? <code>{event.supersedes_id.slice(0, 8)}…</code> : '—'}</td></tr>)}</tbody></table></div>}
  </div></WorkspaceShell>
}
