import { Database, FlaskConical, LockKeyhole } from 'lucide-react'
import type { SnapshotIdentity } from '@/types/workspace'

export type TruthState = 'live' | 'readonly' | 'prototype'

export function TruthBadge({ state, label }: { state: TruthState; label?: string }) {
  const copy = label ?? (state === 'live' ? 'LIVE — ENGINE DATA' : state === 'readonly' ? 'READ-ONLY · Editing available soon' : 'PROTOTYPE — SAMPLE DATA')
  const Icon = state === 'live' ? Database : state === 'readonly' ? LockKeyhole : FlaskConical
  return <span className={`truth-badge truth-${state}`} data-truth-state={state}><Icon size={12} />{copy}</span>
}

export function SnapshotBanner({ snapshot }: { snapshot: SnapshotIdentity }) {
  return <div className="snapshot-banner"><div><Database size={15} /><strong>Immutable snapshot</strong><code>{snapshot.source_hash.slice(0, 16)}…</code></div><span>Generated {new Date(snapshot.generated_at).toLocaleString()} · imported {new Date(snapshot.imported_at).toLocaleString()}</span>{snapshot.stale ? <b>STALE</b> : null}</div>
}

export function PageUnavailable({ title, detail }: { title: string; detail?: string }) {
  return <section className="truth-unavailable" role="alert"><strong>{title}</strong><p>{detail ?? 'The authoritative API is unavailable. No sample data has been substituted.'}</p></section>
}
