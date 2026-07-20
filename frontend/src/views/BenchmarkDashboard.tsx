'use client'
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Check, Gauge, Pause, Play, RefreshCw, ShieldCheck, X } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { BENCHMARK_METRICS, REGRESSION_CASES } from '@/lib/clausechain/data'
import type { BenchmarkMetric, RegressionCase } from '@/lib/clausechain/data'
import { TruthBadge } from '@/components/clausechain/TruthState'

const STATUS_CLASS: Record<BenchmarkMetric['status'], string> = {
  pass: 'bg-[#ECFDF5] text-[#047857]',
  watch: 'bg-[#FFFBEB] text-[#B45309]',
  fail: 'bg-[#FEF2F2] text-[#B91C1C]',
}

const REG_STATUS: Record<RegressionCase['status'], { label: string; className: string; icon: React.ReactNode }> = {
  caught: { label: 'Caught', className: 'bg-[#ECFDF5] text-[#047857]', icon: <Check size={12} /> },
  abstained: { label: 'Abstained', className: 'bg-[#EFF6FF] text-[#1D4ED8]', icon: <ShieldCheck size={12} /> },
  failed: { label: 'Failed', className: 'bg-[#FEF2F2] text-[#B91C1C]', icon: <X size={12} /> },
}

export default function BenchmarkDashboard() {
  const [running, setRunning] = useState(false)
  const [paused, setPaused] = useState(false)
  const [streamIdx, setStreamIdx] = useState(0)
  const max = BENCHMARK_METRICS.length + REGRESSION_CASES.length
  const metrics = BENCHMARK_METRICS.slice(0, Math.min(streamIdx, BENCHMARK_METRICS.length))
  const cases = REGRESSION_CASES.slice(0, Math.max(0, streamIdx - BENCHMARK_METRICS.length))
  const done = streamIdx >= max

  useEffect(() => {
    if (!running || paused || done) return
    const timer = setTimeout(() => setStreamIdx((value) => value + 1), 760)
    return () => clearTimeout(timer)
  }, [done, paused, running, streamIdx])

  const summary = useMemo(() => {
    const pass = metrics.filter((metric) => metric.status === 'pass').length
    const avgLift = metrics.length
      ? metrics.reduce((sum, metric) => sum + (metric.value - metric.baseline), 0) / metrics.length
      : 0
    const caught = cases.filter((item) => item.status === 'caught' || item.status === 'abstained').length
    return { pass, avgLift, caught }
  }, [cases, metrics])

  const start = () => {
    if (done) setStreamIdx(0)
    setRunning(true)
    setPaused(false)
  }

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'Benchmark' }]}>
      <div className="cc-page prototype-surface">
        <div className="cc-page-header">
          <div>
            <TruthBadge state="prototype" />
            <h1 className="cc-page-title text-[32px]">
              Benchmark Dashboard
            </h1>
            <p className="mt-1.5 text-cc-ink-500">
              Reproducible per-stage evaluation for the legal evidence compiler. Accuracy is measured before the demo claims it.
            </p>
          </div>
          <div className="cc-actions">
            {!running || done ? (
              <button
                onClick={start}
                className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-cc-teal-600 px-4 text-sm font-medium text-white transition-colors hover:bg-[#0E9F92]"
              >
                <Play size={14} fill="white" stroke="none" /> Start benchmark
              </button>
            ) : (
              <button
                onClick={() => setPaused((value) => !value)}
                className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-cc-ink-300 bg-white px-4 text-sm font-medium text-cc-ink-900 transition-colors hover:bg-cc-ink-50"
              >
                {paused ? <Play size={14} /> : <Pause size={14} />} {paused ? 'Resume' : 'Pause'}
              </button>
            )}
            <button
              onClick={() => {
                setStreamIdx(0)
                setRunning(false)
                setPaused(false)
              }}
              className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-cc-ink-300 bg-white px-4 text-sm font-medium text-cc-ink-900 transition-colors hover:bg-cc-ink-50"
            >
              <RefreshCw size={14} /> Reset
            </button>
          </div>
        </div>

        <div className="mb-6">
          <div className="mb-2 flex justify-between text-sm text-cc-ink-600">
            <span>{!running ? 'Ready' : paused ? 'Paused' : done ? 'Complete' : 'Streaming benchmark cases...'}</span>
            <span className="font-mono font-semibold">{streamIdx} / {max}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-cc-ink-200">
            <div
              className="h-full rounded-full bg-cc-teal-600 transition-all duration-500"
              style={{ width: `${(streamIdx / max) * 100}%` }}
            />
          </div>
        </div>

        <div className="cc-kpi-grid mb-6">
          {[
            { label: 'Metrics passed', value: `${summary.pass}/${metrics.length || BENCHMARK_METRICS.length}`, color: '#047857' },
            { label: 'Avg lift vs baseline', value: `${summary.avgLift.toFixed(1)} pts`, color: '#1D4ED8' },
            { label: 'Regression catches', value: `${summary.caught}/${cases.length || REGRESSION_CASES.length}`, color: '#B45309' },
            { label: 'Export blocker failures', value: cases.some((item) => item.status === 'failed') ? '1' : '0', color: '#B91C1C' },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-cc-ink-200 bg-white p-5">
              <p className="text-xs font-medium uppercase tracking-[0.06em] text-cc-ink-500">{item.label}</p>
              <p className="mt-1 text-[32px] font-bold leading-none tabular-nums" style={{ color: item.color, fontFamily: 'var(--cc-font-display)' }}>
                {item.value}
              </p>
            </div>
          ))}
        </div>

        <div className="cc-two-col">
          <section className="rounded-2xl border border-cc-ink-200 bg-white">
            <div className="flex items-center gap-3 border-b border-cc-ink-200 px-5 py-4">
              <Gauge size={17} className="text-cc-teal-600" />
              <h2 className="text-[17px] font-semibold text-cc-ink-950">Per-stage metrics</h2>
              <span className="ml-auto text-xs text-cc-ink-500">ClauseChain vs baseline</span>
            </div>
            <div className="divide-y divide-cc-ink-100">
              {metrics.map((metric) => (
                <MetricRow key={metric.id} metric={metric} />
              ))}
              {metrics.length === 0 && (
                <div className="py-20 text-center text-sm text-cc-ink-400">
                  Press <strong className="text-cc-ink-600">Start benchmark</strong> to stream reproducible results.
                </div>
              )}
            </div>
          </section>

          <aside className="flex flex-col gap-4">
            <div className="rounded-2xl border border-cc-ink-200 bg-white">
              <div className="flex items-center gap-2 border-b border-cc-ink-200 px-5 py-4">
                <AlertTriangle size={16} className="text-cc-warning" />
                <h2 className="text-[17px] font-semibold text-cc-ink-950">Regression stream</h2>
              </div>
              <div className="divide-y divide-cc-ink-100">
                {cases.map((item) => (
                  <RegressionRow key={item.id} item={item} />
                ))}
                {cases.length === 0 && (
                  <div className="px-5 py-12 text-center text-sm text-cc-ink-400">
                    Hard cases will stream after stage metrics finish.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-cc-ink-200 bg-cc-ink-50 p-5">
              <h2 className="mb-3 text-[17px] font-semibold text-cc-ink-950">What judges can reproduce</h2>
              <div className="flex flex-col gap-2 text-sm text-cc-ink-700">
                {[
                  'Versioned labeled test set for P6/P7 clauses',
                  'Per-stage scripts: discovery, authority, OCR, chunking, retrieval, tuple, mapping, citation',
                  'Confidence thresholds calibrated with abstention curves',
                  'Regression cases committed as blocking tests',
                ].map((item) => (
                  <div key={item} className="flex items-center gap-2">
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-[#ECFDF5] text-[#047857]">
                      <Check size={12} />
                    </span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </WorkspaceShell>
  )
}

function MetricRow({ metric }: { metric: BenchmarkMetric }) {
  const lowerIsBetter = metric.unit === 'CER' || metric.unit === 'WER'
  const scaleMax = lowerIsBetter ? Math.max(metric.value, metric.baseline, metric.target) : 100
  const valueWidth = Math.min(100, (metric.value / scaleMax) * 100)
  const baselineWidth = Math.min(100, (metric.baseline / scaleMax) * 100)
  const targetHit = lowerIsBetter ? metric.value <= metric.target : metric.value >= metric.target

  return (
    <div className="benchmark-metric-row px-5 py-4">
      <div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_CLASS[metric.status]}`}>{metric.status}</span>
          <span className="font-mono text-[11px] text-cc-ink-500">{metric.stage}</span>
        </div>
        <p className="mt-1 text-sm font-semibold text-cc-ink-950">{metric.label}</p>
        <p className="mt-1 text-xs leading-relaxed text-cc-ink-500">{metric.detail}</p>
      </div>
      <div className="flex flex-col justify-center gap-2">
        <div>
          <div className="mb-1 flex justify-between text-[11px] text-cc-ink-500">
            <span>ClauseChain</span>
            <span className={targetHit ? 'text-[#047857]' : 'text-[#B45309]'}>target {metric.target}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-cc-ink-100">
            <div className="h-full rounded-full bg-cc-teal-600 transition-all duration-500" style={{ width: `${valueWidth}%` }} />
          </div>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-[11px] text-cc-ink-500">
            <span>Baseline</span>
            <span>{metric.baseline}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-cc-ink-100">
            <div className="h-full rounded-full bg-cc-ink-300 transition-all duration-500" style={{ width: `${baselineWidth}%` }} />
          </div>
        </div>
      </div>
      <div className="text-right">
        <p className="font-mono text-[22px] font-bold text-cc-ink-950">{metric.value}</p>
        <p className="font-mono text-[11px] text-cc-ink-500">{metric.unit}</p>
      </div>
    </div>
  )
}

function RegressionRow({ item }: { item: RegressionCase }) {
  const status = REG_STATUS[item.status]
  return (
    <div className="px-5 py-4">
      <div className="mb-2 flex items-center gap-2">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.className}`}>
          {status.icon} {status.label}
        </span>
        <span className="font-mono text-[11px] text-cc-ink-500">{item.jurisdiction} · {item.stage}</span>
      </div>
      <h3 className="text-sm font-semibold text-cc-ink-950">{item.title}</h3>
      <p className="mt-1 text-xs leading-relaxed text-cc-ink-600">{item.failureMode}</p>
      <p className="mt-2 text-xs font-medium text-cc-teal-600">{item.expectedCatch}</p>
    </div>
  )
}
