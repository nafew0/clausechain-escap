'use client'
import { useState, useMemo } from 'react'
import { Check, X, AlertTriangle, Clock, Download, Filter } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { CellDrilldownModal, ExportModal } from '@/components/clausechain/modals'
import { JURISDICTIONS, RDTII_PILLARS, makeMatrixData } from '@/lib/clausechain/data'
import type { MatrixCell } from '@/lib/clausechain/data'
import { TruthBadge } from '@/components/clausechain/TruthState'

type Mode = 'status' | 'confidence' | 'citations'

const STATUS_ICON: Record<string, React.ReactNode> = {
  verified: <Check size={14} />,
  partial:  <Check size={14} />,
  pending:  <Clock size={14} />,
  rejected: <X size={14} />,
  conflict: <AlertTriangle size={14} />,
}

const CELL_CLASS: Record<string, string> = {
  verified: 'cc-cell-verified',
  partial:  'cc-cell-partial',
  pending:  'cc-cell-pending',
  rejected: 'cc-cell-rejected',
  conflict: 'cc-cell-conflict',
  none:     'cc-cell-none',
}

const CONFIDENCE_MAP: Record<string, number> = {
  verified: 0.94, partial: 0.82, pending: 0.65, rejected: 0.15, conflict: 0.78,
}

export default function RDTIIMatrix() {
  const matrix = useMemo(() => makeMatrixData(), [])
  const [mode, setMode] = useState<Mode>('status')
  const [jurFilter, setJurFilter] = useState(new Set(['BD', 'TH', 'SG']))
  const [pillarFilter, setPillarFilter] = useState(new Set(['6', '7']))
  const [drilldown, setDrilldown] = useState<Parameters<typeof CellDrilldownModal>[0]['data']>(null)
  const [exportOpen, setExportOpen] = useState(false)

  const visibleJurisdictions = JURISDICTIONS.filter((j) => jurFilter.has(j.code))

  const columns = useMemo(() => {
    const cols: Array<{ pillar: string; sub: string; label: string; name: string }> = []
    ;(Object.keys(RDTII_PILLARS) as Array<keyof typeof RDTII_PILLARS>).forEach((pk) => {
      if (!pillarFilter.has(pk)) return
      const pillar = RDTII_PILLARS[pk]
      Object.entries(pillar.sub).forEach(([sk, name]) => {
        cols.push({ pillar: pk, sub: sk, label: sk, name: name as string })
      })
    })
    return cols
  }, [pillarFilter])

  // Tally for summary stats
  const tally = useMemo(() => {
    let v = 0, p = 0, r = 0, c = 0, total = 0
    visibleJurisdictions.forEach((j) => {
      columns.forEach((col) => {
        const cell = matrix[j.code]?.[col.sub] as MatrixCell
        total++
        if (!cell) return
        if (cell.conflict) c++
        else if (cell.status === 'verified' || cell.status === 'partial') v++
        else if (cell.status === 'pending') p++
        else if (cell.status === 'rejected') r++
      })
    })
    return { v, p, r, c, total }
  }, [matrix, visibleJurisdictions, columns])

  const toggleJur = (code: string) =>
    setJurFilter((s) => {
      const n = new Set(s)
      if (n.has(code)) {
        n.delete(code)
      } else {
        n.add(code)
      }
      return n
    })
  const togglePillar = (pk: string) =>
    setPillarFilter((s) => {
      const n = new Set(s)
      if (n.has(pk)) {
        n.delete(pk)
      } else {
        n.add(pk)
      }
      return n
    })

  // Group header spans
  const groups = useMemo(() => {
    const result: Array<{ pk: string; span: number; name: string }> = []
    let i = 0
    while (i < columns.length) {
      const pk = columns[i].pillar
      let span = 0
      while (i + span < columns.length && columns[i + span].pillar === pk) span++
      result.push({ pk, span, name: RDTII_PILLARS[pk as keyof typeof RDTII_PILLARS]?.name ?? '' })
      i += span
    }
    return result
  }, [columns])

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'RDTII Matrix' }]}>
      <div className="cc-page prototype-surface">
        {/* Header */}
        <div className="cc-page-header">
          <div>
            <TruthBadge state="prototype" />
            <h1
              className="cc-page-title leading-[1.15] text-cc-ink-950"
              style={{ fontFamily: 'var(--cc-font-display)', fontSize: 32 }}
            >
              <span className="cc-gradient-text">RDTII Matrix</span>
            </h1>
            <p className="text-cc-ink-500 mt-1.5">Jurisdictions × sub-criteria · evidence-graded · audit-ready · hash-anchored</p>
          </div>
          <div className="cc-actions">
            <button className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-white border border-cc-ink-300 text-cc-ink-900 hover:bg-cc-ink-50 transition-colors">
              <Filter size={14} /> View
            </button>
            <button
              onClick={() => setExportOpen(true)}
              className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-cc-teal-600 text-white hover:bg-[#0E9F92] transition-colors"
            >
              <Download size={14} /> Export
            </button>
          </div>
        </div>

        {/* Filter strip */}
        <div className="cc-filter-strip bg-white border border-cc-ink-200 rounded-2xl px-4 py-3 mb-4">
          {/* Jurisdiction chips */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium tracking-[0.06em] uppercase text-cc-ink-500">Jurisdictions</span>
            {JURISDICTIONS.map((j) => (
              <FilterChip key={j.code} active={jurFilter.has(j.code)} onClick={() => toggleJur(j.code)}>
                <span className="text-[13px]">{j.flag}</span> {j.code}
              </FilterChip>
            ))}
          </div>
          <div className="w-px h-6 bg-cc-ink-200" />
          {/* Pillar chips */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium tracking-[0.06em] uppercase text-cc-ink-500">Pillars</span>
            {(Object.entries(RDTII_PILLARS) as Array<[string, { name: string; mandatory: boolean; sub: Record<string, string> }]>).map(([pk, p]) => (
              <FilterChip key={pk} active={pillarFilter.has(pk)} onClick={() => togglePillar(pk)} dim={!p.mandatory}>
                P{pk} {!p.mandatory && <span className="text-[10px] opacity-70">bonus</span>}
              </FilterChip>
            ))}
          </div>
          <div className="flex-1" />
          {/* Mode toggle */}
          <div className="flex bg-cc-ink-50 border border-cc-ink-200 rounded-lg p-1">
            {(['status', 'confidence', 'citations'] as Mode[]).map((k) => (
              <button
                key={k}
                onClick={() => setMode(k)}
                className={`h-7 px-3 text-xs font-medium rounded-md transition-colors capitalize ${
                  mode === k
                    ? 'bg-white text-cc-ink-900 shadow-sm'
                    : 'text-cc-ink-600 hover:text-cc-ink-900'
                }`}
              >
                {k}
              </button>
            ))}
          </div>
        </div>

        {/* Summary stats */}
        <div className="cc-kpi-grid mb-4">
          {[
            { label: 'Verified', value: `${Math.round((tally.v / Math.max(tally.total, 1)) * 100)}%`, sub: `${tally.v} of ${tally.total} sub-criteria`, color: 'var(--cc-success)' },
            { label: 'Pending review', value: String(tally.p), sub: 'awaiting analyst', color: 'var(--cc-warning)' },
            { label: 'Conflicts', value: String(tally.c), sub: 'cross-source disagreement', color: 'var(--cc-danger)' },
            { label: 'Rejected by CVR', value: String(tally.r), sub: 'anti-hallucination saves', color: 'var(--cc-ink-700)' },
          ].map(({ label, value, sub, color }) => (
            <div key={label} className="bg-white border border-cc-ink-200 rounded-2xl p-5">
              <p className="text-xs font-medium tracking-[0.06em] uppercase text-cc-ink-500 mb-1">{label}</p>
              <p
                className="font-bold text-[32px] leading-none tracking-[-0.02em] tabular-nums"
                style={{ fontFamily: 'var(--cc-font-display)', color }}
              >
                {value}
              </p>
              <p className="text-xs text-cc-ink-500 mt-1">{sub}</p>
            </div>
          ))}
        </div>

        {/* Matrix */}
        <div className="cc-matrix-wrap">
          <div className="cc-matrix-scroll">
            <table className="cc-matrix">
              <thead>
                {/* Pillar group header */}
                <tr>
                  <th
                    className="sticky left-0 z-[3] bg-white min-w-[200px] text-left border-b-2 border-cc-ink-200 px-4 py-3"
                    style={{ borderRight: '2px solid var(--cc-ink-200)', borderBottom: '1px solid var(--cc-ink-100)' }}
                  >
                    <span className="text-[13px] font-semibold text-cc-ink-900">Jurisdiction</span>
                  </th>
                  {groups.map((g) => (
                    <th
                      key={g.pk}
                      colSpan={g.span}
                      className="bg-[#F7F7F8] text-center border-b-2 border-cc-ink-200 px-2 py-3 text-[10px] font-semibold tracking-[0.08em] uppercase text-cc-ink-500"
                    >
                      Pillar {g.pk} · {g.name}
                    </th>
                  ))}
                </tr>
                {/* Sub-criterion headers */}
                <tr>
                  <th
                    className="sticky left-0 z-[3] bg-white px-4 py-3 text-left border-b border-cc-ink-100"
                    style={{ borderRight: '2px solid var(--cc-ink-200)' }}
                  />
                  {columns.map((c) => (
                    <th
                      key={c.sub}
                      title={c.name}
                      className="bg-cc-ink-50 text-center px-2 py-3 min-w-[88px] border-b border-cc-ink-100 sticky top-0 z-[2]"
                    >
                      <div className="font-mono font-semibold text-[12px] text-cc-ink-900">{c.label}</div>
                      <div
                        className="text-[10px] text-cc-ink-500 mt-0.5 font-normal tracking-normal lowercase max-w-[88px] overflow-hidden text-ellipsis whitespace-nowrap"
                      >
                        {c.name}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleJurisdictions.map((j) => (
                  <tr key={j.code}>
                    <th
                      className="sticky left-0 z-[1] bg-white px-4 py-3 text-left font-medium text-sm text-cc-ink-900 min-w-[200px]"
                      style={{ borderRight: '2px solid var(--cc-ink-200)' }}
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="text-[18px]">{j.flag}</span>
                        <div>
                          <div>{j.name}</div>
                          <div className="font-mono text-[11px] text-cc-ink-500 font-normal">
                            {j.code} · {j.instruments} instruments
                          </div>
                        </div>
                      </div>
                    </th>
                    {columns.map((col) => {
                      const cell = matrix[j.code]?.[col.sub] as MatrixCell
                      const status = cell?.status ?? 'none'
                      const cls = CELL_CLASS[status] ?? 'cc-cell-none'

                      let content: React.ReactNode = null
                      if (!cell) {
                        content = <span className="text-[18px] text-cc-ink-300">—</span>
                      } else if (mode === 'status') {
                        content = STATUS_ICON[status] ?? null
                      } else if (mode === 'confidence') {
                        const conf = CONFIDENCE_MAP[status]
                        content = conf != null ? (
                          <span className="font-mono text-[13px] font-semibold tabular-nums">{conf.toFixed(2)}</span>
                        ) : null
                      } else {
                        content = <span className="font-mono text-[13px] font-semibold tabular-nums">{cell.count}</span>
                      }

                      return (
                        <td
                          key={col.sub}
                          className={`cc-matrix-cell ${cls}`}
                          onClick={() =>
                            setDrilldown({ jurisdiction: j, pillar: col.pillar, sub: col.sub, name: col.name, cell })
                          }
                        >
                          <div className="cc-cell-inner">
                            {content}
                            {mode !== 'citations' && cell && (
                              <span className="font-mono text-[10px] opacity-70">{cell.count}</span>
                            )}
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mt-4 flex-wrap">
          {[
            { cls: 'cc-cell-verified', label: 'Verified' },
            { cls: 'cc-cell-partial',  label: 'Partial' },
            { cls: 'cc-cell-pending',  label: 'Pending review' },
            { cls: 'cc-cell-rejected', label: 'Rejected' },
            { cls: 'cc-cell-conflict', label: 'Conflict' },
            { cls: 'cc-cell-none',     label: 'Not covered' },
          ].map(({ cls: c, label }) => (
            <div key={label} className="flex items-center gap-1.5 text-xs text-cc-ink-700">
              <span className={`${c} block w-4.5 h-3 rounded-sm`} style={{ width: 18, height: 12 }} />
              {label}
            </div>
          ))}
          <div className="flex-1" />
          <span className="font-mono text-xs text-cc-ink-500">Click any cell to see the underlying classifications</span>
        </div>
      </div>

      <CellDrilldownModal
        open={!!drilldown}
        onClose={() => setDrilldown(null)}
        data={drilldown}
      />
      <ExportModal open={exportOpen} onClose={() => setExportOpen(false)} />
    </WorkspaceShell>
  )
}

function FilterChip({
  active,
  onClick,
  children,
  dim,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  dim?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors"
      style={{
        background: active ? 'var(--cc-teal-50)' : '#fff',
        borderColor: active ? 'var(--cc-teal-200)' : 'var(--cc-ink-300)',
        color: active ? 'var(--cc-teal-600)' : 'var(--cc-ink-700)',
        opacity: !active && dim ? 0.6 : 1,
        fontWeight: active ? 600 : 500,
      }}
    >
      {children}
    </button>
  )
}
