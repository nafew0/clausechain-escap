'use client'

import { useState } from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  Coins,
  Gauge,
  LoaderCircle,
  Play,
  RotateCcw,
  TerminalSquare,
  XCircle,
} from 'lucide-react'
import { LazyMotion, MotionConfig, domAnimation, m } from 'motion/react'

import { useAuth } from '@/contexts/AuthContext'
import { useLaunchEngineAction, useRuns } from '@/hooks/workspace'
import { cn } from '@/lib/utils'
import { friendlyFailure, readinessLabel } from '@/lib/readiness'
import type { EngineAction, JsonValue, RunRecord } from '@/types/workspace'

const COUNTRY_NAMES: Record<string, string> = { SG: 'Singapore', MY: 'Malaysia', MA: 'Malaysia', AU: 'Australia' }

function duration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return 'not recorded'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes}m ${Math.round(seconds % 60)}s`
}

function warningText(value: JsonValue) {
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function ActionState({ action }: { action: EngineAction }) {
  const Icon = action.status === 'succeeded' ? CheckCircle2 : action.status === 'failed' ? XCircle : action.status === 'running' ? LoaderCircle : Clock3
  return (
    <article className={cn('run-action', `state-${action.status}`)}>
      <Icon size={17} />
      <div><strong>{action.kind}</strong><span>{action.requested_by} · {new Date(action.requested_at).toLocaleString()}</span></div>
      <em>{action.status}</em>
      {action.stdout || action.error ? <pre>{action.error || action.stdout}</pre> : null}
    </article>
  )
}

function RunCard({ run, index }: { run: RunRecord; index: number }) {
  const [warningsOpen, setWarningsOpen] = useState(false)
  const pipeline = run.pipeline_stats
  return (
    <m.article className="run-card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .045 }}>
      <header><div><span>{COUNTRY_NAMES[run.country] ?? run.country}</span><h2>Pillar {run.pillar}</h2></div><code>{run.run_id ?? run.run_name}</code></header>
      <div className="run-metrics">
        <div><strong>{run.rows_produced}</strong><span>rows</span></div>
        <div><strong>{run.discovery_counts.NEW}</strong><span>NEW</span></div>
        <div><strong>{run.discovery_counts.KNOWN}</strong><span>KNOWN</span></div>
        <div className={cn(run.warning_count && 'warn')}><strong>{run.warning_count}</strong><span>warnings</span></div>
      </div>
      <dl>
        <div><dt><Coins size={13} /> Measured cost</dt><dd>{run.total_usd === null ? 'not recorded' : `$${run.total_usd.toFixed(4)}`}</dd></div>
        <div><dt><Clock3 size={13} /> Elapsed</dt><dd>{duration(run.elapsed_seconds)}</dd></div>
        <div><dt><Gauge size={13} /> Screened / mapped</dt><dd>{String(pipeline.screened_in ?? '—')} / {String(pipeline.mapped ?? '—')}</dd></div>
      </dl>
      <section className="run-model"><span>Model route</span><code>{run.model_version || 'not recorded in findings'}</code></section>
      <button className="run-warning-toggle" onClick={() => setWarningsOpen((open) => !open)} disabled={!run.warning_count}>
        <AlertTriangle size={14} /> Full warnings ({run.warning_count}) {warningsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {warningsOpen ? <div className="run-warning-list">{run.warnings.map((warning, warningIndex) => <p key={warningIndex}>{warningText(warning)}</p>)}</div> : null}
      <footer><span>{run.generated_at ? new Date(run.generated_at).toLocaleString() : 'time unavailable'}</span><code>{run.source_hash.slice(0, 10)}…</code></footer>
    </m.article>
  )
}

export default function RunsWorkbench() {
  const query = useRuns()
  const launch = useLaunchEngineAction()
  const { user } = useAuth()
  const [economy, setEconomy] = useState('Singapore')
  const [pillar, setPillar] = useState<6 | 7>(6)
  const champion = query.data?.champion
  const failures = Array.isArray(champion?.failures) ? champion.failures : []

  const queueRun = () => {
    if (!window.confirm(`Queue a real ${economy} Pillar ${pillar} engine run? This may incur model cost.`)) return
    launch.mutate({ kind: 'run', payload: { economy, pillar } })
  }

  if (query.isPending) return <div className="run-page-state"><LoaderCircle size={28} /> Loading immutable run history…</div>
  if (query.isError || !query.data) return <div className="run-page-state error"><XCircle size={28} /> Run history API is unavailable.</div>

  return (
    <LazyMotion features={domAnimation}>
      <MotionConfig reducedMotion="user">
        <div className="runs-workbench">
          <header className="runs-header"><div><span><Activity size={14} /> Recorded engine execution</span><h1>Run history</h1><p>Six imported run envelopes. These are completed records—not simulated live progress.</p></div></header>
          <section className={cn('runs-champion', String(champion?.status).toUpperCase() === 'PASS' ? 'pass' : 'fail')}>
            {String(champion?.status).toUpperCase() === 'PASS' ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
            <div><strong>Release readiness: {readinessLabel(champion?.status)}</strong>{failures.length ? <p>{failures.map(f => friendlyFailure(f)).join(' · ')}</p> : null}</div>
          </section>
          {user?.is_superuser ? <section className="run-launch"><div><Play size={18} /><span><strong>Launch a real pipeline run</strong><small>Queued for the dedicated allowlisted worker; one run executes at a time.</small></span></div><select value={economy} onChange={(event) => setEconomy(event.target.value)}><option>Singapore</option><option>Malaysia</option><option>Australia</option></select><select value={pillar} onChange={(event) => setPillar(Number(event.target.value) as 6 | 7)}><option value={6}>Pillar 6</option><option value={7}>Pillar 7</option></select><button onClick={queueRun} disabled={launch.isPending}><Play size={14} /> Queue run</button></section> : null}
          <section className="run-grid">{query.data.results.map((run, index) => <RunCard key={run.run_name} run={run} index={index} />)}</section>
          <section className="run-actions"><header><div><TerminalSquare size={18} /><span><strong>Engine worker actions</strong><small>Authoritative queued/running/done states with captured output.</small></span></div>{user?.is_superuser ? <button onClick={() => launch.mutate({ kind: 'refresh' })} disabled={launch.isPending}><RotateCcw size={14} /> Refresh snapshot</button> : null}</header>{query.data.actions.length ? query.data.actions.map((action) => <ActionState action={action} key={action.id} />) : <p className="run-empty">No engine actions have been queued from the app.</p>}</section>
        </div>
      </MotionConfig>
    </LazyMotion>
  )
}
