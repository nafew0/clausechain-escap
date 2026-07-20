'use client'
import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Check,
  FileText,
  GitBranch,
  Languages,
  Network,
  Pause,
  Play,
  ShieldCheck,
} from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import PipelineStepper from '@/components/clausechain/PipelineStepper'
import { HashBadge, TrustBadge } from '@/components/clausechain/ui'
import { SOURCE_STATUS_EDGES, SOURCE_STATUS_NODES } from '@/lib/clausechain/data'
import type { SourceStatus } from '@/lib/clausechain/data'
import { TruthBadge } from '@/components/clausechain/TruthState'

const NODE_ICON: Record<SourceStatus['kind'], React.ReactNode> = {
  official_statute: <ShieldCheck size={16} />,
  amendment: <GitBranch size={16} />,
  consolidated_text: <FileText size={16} />,
  guideline: <Network size={16} />,
  draft: <AlertTriangle size={16} />,
  unofficial_translation: <Languages size={16} />,
}

const STATUS_STYLE: Record<SourceStatus['status'], string> = {
  binding_current: 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]',
  binding_historical: 'bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]',
  context_only: 'bg-[#F4F4F5] text-cc-ink-700 border-cc-ink-200',
  draft: 'bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]',
  translation_only: 'bg-[#F5F3FF] text-[#6D28D9] border-[#DDD6FE]',
  requires_review: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
}

export default function SourceStatusGraph() {
  const [running, setRunning] = useState(false)
  const [paused, setPaused] = useState(false)
  const [step, setStep] = useState(0)

  const maxStep = SOURCE_STATUS_NODES.length + SOURCE_STATUS_EDGES.length
  const visibleNodes = SOURCE_STATUS_NODES.slice(0, Math.min(step, SOURCE_STATUS_NODES.length))
  const visibleEdges = SOURCE_STATUS_EDGES.slice(0, Math.max(0, step - SOURCE_STATUS_NODES.length))
  const selectedSource = SOURCE_STATUS_NODES.find((node) => node.id === 'SG-PDPA-CONSOLIDATED')
  const downgraded = visibleNodes.filter((node) => !node.binding)

  useEffect(() => {
    if (!running || paused || step >= maxStep) return
    const timer = setTimeout(() => setStep((value) => value + 1), 850)
    return () => clearTimeout(timer)
  }, [maxStep, paused, running, step])

  const statusCounts = {
    binding: visibleNodes.filter((node) => node.binding).length,
    current: visibleNodes.filter((node) => node.current).length,
    context: visibleNodes.filter((node) => !node.binding).length,
    review: visibleEdges.filter((edge) => edge.status === 'review').length,
  }

  const start = () => {
    if (step >= maxStep) setStep(0)
    setRunning(true)
    setPaused(false)
  }

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'Source Status' }]}>
      <PipelineStepper activeId="authority" />

      <div className="cc-page prototype-surface">
        <div className="cc-page-header">
          <div>
            <TruthBadge state="prototype" />
            <h1 className="cc-page-title text-[32px]">
              Source Status Graph
            </h1>
            <p className="mt-1.5 text-cc-ink-500">
              Authority resolver selects current binding law, keeps guidance as context, and blocks drafts from controlling outputs.
            </p>
          </div>
          <div className="cc-actions">
            {!running || step >= maxStep ? (
              <button
                onClick={start}
                className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-cc-teal-600 px-4 text-sm font-medium text-white transition-colors hover:bg-[#0E9F92]"
              >
                <Play size={14} fill="white" stroke="none" /> Run resolver
              </button>
            ) : (
              <button
                onClick={() => setPaused((value) => !value)}
                className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-cc-ink-300 bg-white px-4 text-sm font-medium text-cc-ink-900 transition-colors hover:bg-cc-ink-50"
              >
                {paused ? <Play size={14} /> : <Pause size={14} />} {paused ? 'Resume' : 'Pause'}
              </button>
            )}
          </div>
        </div>

        <div className="cc-kpi-grid mb-6">
          {[
            { label: 'Binding sources', value: statusCounts.binding, color: '#047857' },
            { label: 'Current sources', value: statusCounts.current, color: '#0F766E' },
            { label: 'Context only', value: statusCounts.context, color: '#B45309' },
            { label: 'Needs review', value: statusCounts.review, color: '#B91C1C' },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-cc-ink-200 bg-white p-5">
              <p className="text-xs font-medium uppercase tracking-[0.06em] text-cc-ink-500">{item.label}</p>
              <p className="mt-1 text-[34px] font-bold leading-none tabular-nums" style={{ color: item.color, fontFamily: 'var(--cc-font-display)' }}>
                {item.value}
              </p>
            </div>
          ))}
        </div>

        <div className="cc-two-col">
          <section className="rounded-2xl border border-cc-ink-200 bg-white p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-[18px] font-semibold text-cc-ink-950">Resolver graph</h2>
                <p className="text-sm text-cc-ink-500">Nodes appear first, then legal relationships are evaluated.</p>
              </div>
              <span className="font-mono text-xs text-cc-ink-500">{step} / {maxStep}</span>
            </div>

            <div className="cc-source-node-grid">
              {visibleNodes.map((node) => (
                <div
                  key={node.id}
                  className={`source-node min-h-[188px] rounded-2xl border p-4 ${node.id === 'SG-PDPA-CONSOLIDATED' ? 'border-cc-teal-200 bg-cc-teal-50' : 'border-cc-ink-200 bg-white'}`}
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <span className={`grid h-9 w-9 place-items-center rounded-xl ${node.binding ? 'bg-[#ECFDF5] text-[#047857]' : 'bg-cc-ink-100 text-cc-ink-600'}`}>
                      {NODE_ICON[node.kind]}
                    </span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${STATUS_STYLE[node.status]}`}>
                      {node.status.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <h3 className="text-[14px] font-semibold leading-snug text-cc-ink-950">{node.title}</h3>
                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-cc-ink-500">{node.note}</p>
                  <div className="mt-3 flex items-center justify-between gap-2 text-xs">
                    <span className="font-mono text-cc-ink-500">rank {node.authorityRank}</span>
                    <span className="font-mono font-semibold text-cc-ink-900">{node.confidence.toFixed(2)}</span>
                  </div>
                </div>
              ))}

              {visibleNodes.length === 0 && (
                  <div className="py-20 text-center text-sm text-cc-ink-400" style={{ gridColumn: '1 / -1' }}>
                  Press <strong className="text-cc-ink-600">Run resolver</strong> to simulate source authority detection.
                </div>
              )}
            </div>

            {visibleEdges.length > 0 && (
              <div className="mt-5 rounded-2xl border border-cc-ink-200 bg-cc-ink-50 p-4">
                <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Relationship edges</p>
                <div className="cc-table-scroll">
                <div className="grid gap-2">
                  {visibleEdges.map((edge) => (
                    <div key={edge.id} className="cc-status-edge-row evidence-graph-edge grid grid-cols-[1fr_150px_1fr_88px] items-center gap-3 rounded-xl border border-cc-ink-200 bg-white px-3 py-2 text-xs">
                      <span className="truncate font-mono text-cc-ink-800">{edge.from}</span>
                      <span className="rounded bg-cc-teal-50 px-2 py-1 text-center font-mono text-[10px] font-semibold text-cc-teal-600">{edge.relation}</span>
                      <span className="truncate font-mono text-cc-ink-800">{edge.to}</span>
                      <HashBadge hash={edge.hash} />
                    </div>
                  ))}
                </div>
                </div>
              </div>
            )}
          </section>

          <aside className="flex flex-col gap-4">
            <div className="rounded-2xl border border-cc-teal-200 bg-cc-teal-50 p-5">
              <div className="mb-3 flex items-center gap-2 text-cc-teal-600">
                <ShieldCheck size={17} />
                <h2 className="text-[17px] font-semibold text-cc-ink-950">Selected controlling source</h2>
              </div>
              {selectedSource ? (
                <>
                  <p className="text-sm font-semibold text-cc-ink-950">{selectedSource.title}</p>
                  <p className="mt-2 text-sm leading-relaxed text-cc-ink-600">{selectedSource.note}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <TrustBadge label="Binding" tone="pass" />
                    <TrustBadge label="Current" tone="pass" />
                    <TrustBadge label="Rank 1 authority" tone="pass" />
                  </div>
                </>
              ) : null}
            </div>

            <div className="rounded-2xl border border-cc-ink-200 bg-white p-5">
              <h2 className="mb-3 text-[17px] font-semibold text-cc-ink-950">Resolver decisions</h2>
              <div className="flex flex-col gap-3">
                {[
                  ['Official legal portal detected', step > 0] as const,
                  ['Amendment relationship applied', visibleEdges.some((edge) => edge.relation === 'amends')] as const,
                  ['Current consolidated text selected', visibleNodes.some((node) => node.id === 'SG-PDPA-CONSOLIDATED')] as const,
                  ['Guideline downgraded to context', downgraded.some((node) => node.kind === 'guideline')] as const,
                  ['Draft excluded from legal conclusion', downgraded.some((node) => node.kind === 'draft')] as const,
                ].map(([label, done]) => (
                  <div key={String(label)} className="flex items-center gap-2 text-sm">
                    <span className={`grid h-5 w-5 place-items-center rounded-full ${done ? 'bg-[#ECFDF5] text-[#047857]' : 'bg-cc-ink-100 text-cc-ink-400'}`}>
                      {done ? <Check size={12} /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                    </span>
                    <span className={done ? 'text-cc-ink-900' : 'text-cc-ink-500'}>{label}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-[#FDE68A] bg-[#FFFBEB] p-5">
              <div className="mb-2 flex items-center gap-2 text-[#B45309]">
                <AlertTriangle size={16} />
                <h2 className="text-[17px] font-semibold text-cc-ink-950">Conflict policy</h2>
              </div>
              <p className="text-sm leading-relaxed text-cc-ink-700">
                Binding current law wins over guidance. Drafts and unofficial translations are never exported as controlling authority, even when semantically similar.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </WorkspaceShell>
  )
}
