'use client'

import { useState } from 'react'
import { Database } from 'lucide-react'

import { useSummary } from '@/hooks/workspace'
import { cn } from '@/lib/utils'

function snapshotTime(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(parsed)
}

// Renders as a compact status chip everywhere (the old full-width banner is
// retired); the `compact` prop is kept so existing call sites stay valid.
export function SnapshotBanner({ className, compact: _compact = false }: { className?: string; compact?: boolean }) {
  const summary = useSummary()
  const [open, setOpen] = useState(false)

  if (summary.isPending) {
    return (
      <span className={cn('snapshot-chip-wrap', className)}>
        <span className="snapshot-chip is-loading" aria-label="Loading snapshot status"><Database size={15} /><span>Snapshot</span></span>
      </span>
    )
  }
  if (summary.isError || !summary.data) {
    return (
      <span className={cn('snapshot-chip-wrap', className)}>
        <button type="button" className="snapshot-chip is-error" aria-expanded={open} title="Snapshot status" onClick={() => setOpen(value => !value)}>
          <Database size={15} /><span>Snapshot</span><b>OFFLINE</b>
        </button>
        {open ? (
          <span role="alert" className="snapshot-pop">
            Snapshot status unavailable. Do not make review decisions until the API reconnects.
          </span>
        ) : null}
      </span>
    )
  }

  const { snapshot, champion } = summary.data
  const championStatus = String(champion.status ?? 'UNKNOWN').toUpperCase()
  const warning = snapshot.stale || championStatus === 'FAIL'
  const warningReason = snapshot.stale
    ? 'This snapshot is stale.'
    : championStatus === 'FAIL'
      ? 'Reviewer sign-offs are still in progress.'
      : ''

  return (
    <span className={cn('snapshot-chip-wrap', className)}>
      <button
        type="button"
        className={cn('snapshot-chip', warning ? 'is-warning' : 'is-ok', snapshot.mode === 'local' && 'is-local')}
        aria-expanded={open}
        title="Data snapshot status"
        onClick={() => setOpen(value => !value)}
      >
        <Database size={15} /><span>{snapshot.mode === 'local' ? 'Local snapshot' : 'Snapshot'}</span><b>{snapshot.stale ? 'STALE' : snapshot.bundle_hash.slice(0, 8)}</b>
      </button>
      {open ? (
        <span role={warning ? 'alert' : 'status'} className="snapshot-pop">
          <span>Data as of {snapshotTime(snapshot.generated_at)}</span>
          <span className="font-mono">bundle {snapshot.bundle_hash.slice(0, 8)}</span>
          {warningReason ? <span>{warningReason}</span> : null}
        </span>
      ) : null}
    </span>
  )
}
