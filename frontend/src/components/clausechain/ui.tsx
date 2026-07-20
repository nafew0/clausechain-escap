'use client'
import { Check, X, AlertTriangle, Clock, Minus, ShieldCheck } from 'lucide-react'
import type { ClauseStatus, Gate, VerificationGateV2 } from '@/lib/clausechain/data'

// ─── Status chip ────────────────────────────────────────────
const STATUS_STYLES: Record<ClauseStatus, string> = {
  verified: 'bg-[#ECFDF5] text-[#047857]',
  partial:  'bg-[#ECFDF5] text-[#047857]',
  pending:  'bg-[#FFFBEB] text-[#B45309]',
  rejected: 'bg-[#FEF2F2] text-[#B91C1C]',
  conflict: 'bg-[#FEF2F2] text-[#B91C1C]',
  none:     'bg-cc-ink-100 text-cc-ink-600',
}
const STATUS_LABELS: Record<ClauseStatus, string> = {
  verified: 'Verified', partial: 'Partial', pending: 'Pending',
  rejected: 'Rejected', conflict: 'Conflict', none: 'None',
}

export function StatusChip({ status }: { status: ClauseStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${STATUS_STYLES[status]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {STATUS_LABELS[status]}
    </span>
  )
}

// ─── Hash badge ──────────────────────────────────────────────
export function HashBadge({ hash }: { hash: string }) {
  const short = hash.slice(0, 8)

  const copy = () => {
    navigator.clipboard.writeText(hash).catch(() => {})
  }

  return (
    <button
      onClick={copy}
      title={hash}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-cc-ink-100 text-cc-ink-700 text-xs font-mono border border-transparent hover:bg-cc-ink-50 hover:border-cc-ink-200 hover:text-cc-ink-900 transition-colors"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-cc-teal-600 opacity-60" />
      {short}
    </button>
  )
}

// ─── Confidence bar ──────────────────────────────────────────
export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.85 ? 'var(--cc-success)' : value >= 0.70 ? 'var(--cc-warning)' : 'var(--cc-danger)'

  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 h-1.5 bg-cc-ink-200 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-[13px] font-semibold text-cc-ink-900 tabular-nums min-w-[38px] text-right">
        {value.toFixed(2)}
      </span>
    </div>
  )
}

// ─── Verification chain gates ────────────────────────────────
const GATE_ICON = {
  pass: <Check size={10} />,
  fail: <X size={10} />,
  warn: <AlertTriangle size={10} />,
  abstain: <Clock size={10} />,
}
const GATE_COLOR = {
  pass: 'var(--cc-success)',
  fail: 'var(--cc-danger)',
  warn: 'var(--cc-warning)',
  abstain: 'var(--cc-info)',
}

export function VerificationChain({ gates }: { gates: Gate[] }) {
  return (
    <div className="cc-vchain">
      {gates.map((gate) => (
        <div
          key={gate.name}
          className="flex flex-col gap-1 p-2.5 bg-white border border-cc-ink-200 rounded-md"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold tracking-[0.04em] uppercase text-cc-ink-500">
              {gate.name}
            </span>
            <span
              className="w-[18px] h-[18px] rounded-full grid place-items-center text-white"
              style={{ background: GATE_COLOR[gate.status] }}
            >
              {GATE_ICON[gate.status]}
            </span>
          </div>
          <span className="font-mono text-[13px] font-semibold text-cc-ink-900">{gate.value}</span>
          <span className="text-xs text-cc-ink-600">{gate.detail}</span>
        </div>
      ))}
    </div>
  )
}

export function VerificationChainV2({ gates }: { gates: VerificationGateV2[] }) {
  return (
    <div className="cc-vchain cc-vchain-v2">
      {gates.map((gate) => (
        <div
          key={gate.id}
          className={`flex flex-col gap-1 p-2.5 bg-white border rounded-md ${
            gate.status === 'fail'
              ? 'border-[#FECACA]'
              : gate.status === 'warn' || gate.status === 'abstain'
                ? 'border-[#FDE68A]'
                : 'border-cc-ink-200'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold tracking-[0.05em] uppercase text-cc-ink-500">
              {gate.id} · {gate.label}
            </span>
            <span
              className="w-[18px] h-[18px] rounded-full grid place-items-center text-white shrink-0"
              style={{ background: GATE_COLOR[gate.status] }}
            >
              {GATE_ICON[gate.status]}
            </span>
          </div>
          <span className="font-mono text-[12px] font-semibold text-cc-ink-900">{gate.score}</span>
          <span className="text-[11px] leading-snug text-cc-ink-600">{gate.detail}</span>
        </div>
      ))}
    </div>
  )
}

const TRUST_TONE: Record<'pass' | 'warn' | 'fail' | 'info', string> = {
  pass: 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]',
  warn: 'bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]',
  fail: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
  info: 'bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]',
}

export function TrustBadge({ label, tone = 'pass' }: { label: string; tone?: 'pass' | 'warn' | 'fail' | 'info' }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${TRUST_TONE[tone]}`}>
      {tone === 'fail' ? <X size={11} /> : tone === 'warn' ? <AlertTriangle size={11} /> : <ShieldCheck size={11} />}
      {label}
    </span>
  )
}

// ─── KPI card ────────────────────────────────────────────────
interface KPICardProps {
  label: string
  value: string | number
  sub?: string
  delta?: { value: string; dir: 'up' | 'down' | 'neutral' }
  color?: string
}

export function KPICard({ label, value, sub, delta, color }: KPICardProps) {
  return (
    <div className="flex flex-col gap-2 p-6 bg-white border border-cc-ink-200 rounded-2xl">
      <span className="text-xs font-medium tracking-[0.06em] uppercase text-cc-ink-500">{label}</span>
      <span
        className="font-bold text-[44px] leading-none tracking-[-0.025em] tabular-nums"
        style={{ fontFamily: 'var(--cc-font-display)', color: color ?? 'var(--cc-ink-950)' }}
      >
        {value}
      </span>
      <div className="flex items-center gap-2 text-[13px] text-cc-ink-500">
        {delta && (
          <span
            className={`inline-flex items-center gap-0.5 font-medium tabular-nums ${
              delta.dir === 'up' ? 'text-[var(--cc-success)]' : delta.dir === 'down' ? 'text-[var(--cc-danger)]' : 'text-cc-ink-500'
            }`}
          >
            {delta.value}
          </span>
        )}
        {sub && <span>{sub}</span>}
      </div>
    </div>
  )
}

// ─── Pillar bar ───────────────────────────────────────────────
interface PillarSegment { verified: number; pending: number; rejected: number }

export function PillarBar({ segments }: { segments: PillarSegment }) {
  const total = segments.verified + segments.pending + segments.rejected || 1
  return (
    <div className="flex gap-0.5 h-1.5 rounded-full overflow-hidden bg-cc-ink-200">
      <div className="h-full rounded-full" style={{ width: `${(segments.verified / total) * 100}%`, background: 'var(--cc-success)' }} />
      <div className="h-full rounded-full" style={{ width: `${(segments.pending / total) * 100}%`, background: 'var(--cc-warning)' }} />
      <div className="h-full rounded-full" style={{ width: `${(segments.rejected / total) * 100}%`, background: 'var(--cc-danger)' }} />
    </div>
  )
}

// ─── Pillar coverage stack ────────────────────────────────────
interface PillarCovItem { pillar: string; label: string; verified: number; total: number; mandatory: boolean }

export function PillarCoverageStack({ items }: { items: PillarCovItem[] }) {
  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => {
        const pct = item.total > 0 ? Math.round((item.verified / item.total) * 100) : 0
        return (
          <div key={item.pillar} className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] font-semibold text-cc-ink-900 bg-cc-ink-100 px-2 py-0.5 rounded">
                  P{item.pillar}
                </span>
                <span className="text-[13px] text-cc-ink-700">{item.label}</span>
                {!item.mandatory && (
                  <span className="text-[10px] text-cc-ink-500 opacity-70">bonus</span>
                )}
              </div>
              <span className="font-mono text-[12px] text-cc-ink-600 tabular-nums">{pct}%</span>
            </div>
            <div className="cc-progress">
              <div style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Section divider ─────────────────────────────────────────
export function Divider() {
  return <div className="h-px bg-cc-ink-200 w-full" />
}

// ─── Empty state ──────────────────────────────────────────────
export function EmptyState({ title, sub, icon }: { title: string; sub?: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center py-16 gap-3">
      <div className="text-cc-ink-300">{icon ?? <Minus size={32} />}</div>
      <p className="text-[17px] font-semibold text-cc-ink-900">{title}</p>
      {sub && <p className="text-sm text-cc-ink-500 max-w-[360px]">{sub}</p>}
    </div>
  )
}
