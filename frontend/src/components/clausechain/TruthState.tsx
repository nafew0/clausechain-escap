'use client'

import { useState } from 'react'
import { Database, FlaskConical, LockKeyhole } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SnapshotIdentity } from '@/types/workspace'

export type TruthState = 'live' | 'readonly' | 'prototype'

export function TruthBadge({ state, label }: { state: TruthState; label?: string }) {
  const copy = label ?? (state === 'live' ? 'LIVE — ENGINE DATA' : state === 'readonly' ? 'READ-ONLY · Editing available soon' : 'PROTOTYPE — SAMPLE DATA')
  const Icon = state === 'live' ? Database : state === 'readonly' ? LockKeyhole : FlaskConical
  return <span className={`truth-badge truth-${state}`} data-truth-state={state}><Icon size={12} />{copy}</span>
}

export function SnapshotBanner({ snapshot }: { snapshot: SnapshotIdentity }) {
  const [open, setOpen] = useState(false)
  const stale = Boolean(snapshot.stale)
  return (
    <span className="snapshot-chip-wrap">
      <button
        type="button"
        className={cn('snapshot-chip', stale ? 'is-warning' : 'is-ok', snapshot.mode === 'local' && 'is-local')}
        aria-expanded={open}
        title="Immutable snapshot"
        onClick={() => setOpen(value => !value)}
      >
        <Database size={15} /><span>{snapshot.mode === 'local' ? 'Local snapshot' : 'Snapshot'}</span><b>{stale ? 'STALE' : snapshot.source_hash.slice(0, 8)}</b>
      </button>
      {open ? (
        <span role="status" className="snapshot-pop">
          <span>Immutable snapshot <span className="font-mono">{snapshot.source_hash.slice(0, 16)}…</span></span>
          <span>Generated {new Date(snapshot.generated_at).toLocaleString()}</span>
          <span>Imported {new Date(snapshot.imported_at).toLocaleString()}</span>
          {stale ? <span>This snapshot is stale.</span> : null}
        </span>
      ) : null}
    </span>
  )
}

export function PageUnavailable({ title, detail }: { title: string; detail?: string }) {
  return <section className="truth-unavailable" role="alert"><strong>{title}</strong><p>{detail ?? 'The authoritative API is unavailable. No sample data has been substituted.'}</p></section>
}
