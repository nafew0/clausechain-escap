'use client'

import { AlertTriangle, Database, ShieldCheck } from 'lucide-react'

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

export function SnapshotBanner({ className }: { className?: string }) {
  const summary = useSummary()

  if (summary.isPending) {
    return (
      <div className={cn('h-10 animate-pulse border-b border-slate-200 bg-slate-100', className)} />
    )
  }
  if (summary.isError || !summary.data) {
    return (
      <div
        role="alert"
        className={cn(
          'flex min-h-10 items-center gap-2 border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs font-medium text-rose-800',
          className
        )}
      >
        <AlertTriangle size={14} aria-hidden="true" />
        Snapshot status unavailable. Do not make review decisions until the API reconnects.
      </div>
    )
  }

  const { snapshot, champion } = summary.data
  const championStatus = String(champion.status ?? 'UNKNOWN').toUpperCase()
  const warning = snapshot.stale || championStatus === 'FAIL'
  const Icon = warning ? AlertTriangle : championStatus === 'PASS' ? ShieldCheck : Database
  const warningReason = snapshot.stale
    ? 'This snapshot is stale.'
    : championStatus === 'FAIL'
      ? 'Champion validation is not yet passing.'
      : ''

  return (
    <div
      role={warning ? 'alert' : 'status'}
      className={cn(
        'flex min-h-10 flex-wrap items-center gap-x-2 gap-y-1 border-b px-4 py-2 text-xs font-medium',
        warning
          ? 'border-amber-200 bg-amber-50 text-amber-900'
          : 'border-emerald-200 bg-emerald-50 text-emerald-900',
        className
      )}
    >
      <Icon size={14} aria-hidden="true" />
      <span>Data as of {snapshotTime(snapshot.generated_at)}</span>
      <span aria-hidden="true">·</span>
      <span className="font-mono">bundle {snapshot.bundle_hash.slice(0, 8)}</span>
      {warningReason ? (
        <>
          <span aria-hidden="true">·</span>
          <span>{warningReason}</span>
        </>
      ) : null}
    </div>
  )
}
