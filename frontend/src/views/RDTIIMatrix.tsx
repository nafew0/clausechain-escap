'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowUpRight, CheckCircle2, CircleDashed, FileText, Gavel, LoaderCircle, MinusCircle, PenLine, Scale, Server, X, XCircle } from 'lucide-react'

import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { TruthBadge } from '@/components/clausechain/TruthState'
import { ModePageHeader } from '@/components/workspace/ModePageHeader'
import { FinalRoundExportMenu } from '@/components/workspace/FinalRoundExportMenu'
import { useRunMode } from '@/components/workspace/RunModeTabs'
import { SnapshotBanner } from '@/components/workspace/SnapshotBanner'
import { useDecide, useSummary, useZone3Matrix } from '@/hooks/workspace'
import type { Zone3MatrixCell } from '@/services/workspace'
import { cn } from '@/lib/utils'
import { modeHref } from '@/lib/runMode'

type Zone3Score = 0 | 0.5 | 1

function scoreLabel(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—'
  return Number(value) % 1 === 0 ? String(Number(value)) : String(Number(value))
}

function indicatorShort(question: string | undefined) {
  const text = (question || '').replace(/^Does the law\s*/i, '').replace(/^Is there\s*/i, '')
  return text.length > 30 ? `${text.slice(0, 30).trimEnd()}…` : text || '—'
}

const STATE_ICON = {
  approved: <CheckCircle2 size={13} />,
  overridden: <PenLine size={13} />,
  pending: <CircleDashed size={13} />,
  evidence: <FileText size={13} />,
  absence: <MinusCircle size={13} />,
} as const

export default function RDTIIMatrix() {
  const [mode] = useRunMode()
  const local = mode === 'local'
  const matrix = useZone3Matrix(mode)
  const summary = useSummary()
  const decide = useDecide()
  const roles = summary.data?.reviewer_roles ?? []
  const canDecide = roles.some((role) => ['mapping_reviewer', 'admin'].includes(role))
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [override, setOverride] = useState(false)
  const [score, setScore] = useState<Zone3Score>(0)
  const [note, setNote] = useState('')

  const byKey = useMemo(() => new Map((matrix.data?.cells ?? []).map((cell) => [cell.score_key, cell])), [matrix.data])
  const selected = selectedKey ? byKey.get(selectedKey) ?? null : null

  const openCell = (cell: Zone3MatrixCell) => {
    setSelectedKey(cell.score_key)
    setOverride(false)
    setScore((Number(cell.deterministic ?? 0) as Zone3Score) ?? 0)
    setNote('')
  }

  const submit = async (verdict: 'approved' | 'overridden') => {
    if (!selected) return
    await decide.mutateAsync({
      domain: 'zone3',
      payload: {
        score_key: selected.score_key,
        verdict,
        score: verdict === 'overridden' ? score : (Number(selected.deterministic ?? 0) as Zone3Score),
        reasoning: note,
        expected_latest_decision_id: selected.latest_decision_id,
      },
    })
    setNote('')
    setOverride(false)
  }

  const header = <ModePageHeader
    modes={matrix.data?.modes}
    onModeChange={() => setSelectedKey(null)}
    eyebrow={<>{local ? <span className="z3-local-chip"><Server size={13} /> Local · open weights</span> : <TruthBadge state="live" />}{matrix.data?.snapshot ? <SnapshotBanner /> : null}</>}
    title={`RDTII indicator matrix${local ? ' · local' : ''}`}
    actions={<FinalRoundExportMenu mode={mode} disabled={!matrix.data?.snapshot} />}
    description={local ? 'The open-weights model’s own matrix: its Zone-3 proposals and your Local review decisions, from the Local snapshot. Scores are 0 / 0.5 / 1 at indicator level; Model comparison sets them beside the hybrid scores.' : 'Economies × indicators · engine-proposed, reviewer-decided, evidence-anchored. Scores are 0 / 0.5 / 1 at indicator level.'}
  />
  if (matrix.isPending) return <WorkspaceShell breadcrumbs={[{ label: 'RDTII Matrix' }]}><div className="cc-page z3-page">{header}<div className="run-page-state"><LoaderCircle size={28} /> Loading indicator scores…</div></div></WorkspaceShell>
  if (matrix.isError || !matrix.data) return <WorkspaceShell breadcrumbs={[{ label: 'RDTII Matrix' }]}><div className="cc-page z3-page">{header}<div className="run-page-state error"><XCircle size={28} /> The score matrix API is unavailable.</div></div></WorkspaceShell>
  const data = matrix.data

  const pillar2 = data.indicators.filter((indicator) => indicator.toUpperCase().startsWith('P2'))
  const pillar6 = data.indicators.filter((indicator) => indicator.toUpperCase().startsWith('P6'))
  const pillar7 = data.indicators.filter((indicator) => indicator.toUpperCase().startsWith('P7'))
  const orderedIndicators = [...pillar2, ...pillar6, ...pillar7]
  const cellFor = (economy: string, indicator: string) => data.cells.find((entry) => entry.economy === economy && entry.indicator === indicator)
  const questionFor = (indicator: string) => data.cells.find((entry) => entry.indicator === indicator)?.question
  const overrides = data.cells.filter((cell) => cell.state === 'overridden').length
  const divergences = data.cells.filter((cell) => cell.gold_divergence).length
  const evidenceCount = (economy: string) => data.cells.filter((cell) => cell.economy === economy).reduce((total, cell) => total + cell.evidence.length, 0)

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'RDTII Matrix' }]}>
      <div className="cc-page z3-page">
        {header}

        {local && !data.snapshot ? (
          <section className="run-empty-state"><Server size={22} /><strong>No Local snapshot yet</strong><p>Finish a Local run, then click <b>Refresh snapshot</b> on the <Link href="/runs?mode=local">Runs page (Local tab)</Link>. The open-weights model then scores every indicator, exactly like the hybrid matrix.</p></section>
        ) : null}

        <div className="z3-kpis" style={local && !data.snapshot ? { display: 'none' } : undefined}>
          <article data-data-card><span>Decided</span><strong className="ok">{data.counts.decided}<small> of {data.counts.total}</small></strong><p>named reviewer approvals & overrides</p></article>
          <article data-data-card><span>Awaiting reviewer</span><strong className="warn">{data.counts.pending}</strong><p>engine proposals — not effective yet</p></article>
          <article data-data-card><span>Overrides</span><strong className="info">{overrides}</strong><p>reviewer changed the engine&apos;s score</p></article>
          <article data-data-card><span>Gold divergences</span><strong className="alert">{divergences}</strong><p>flagged for human adjudication</p></article>
        </div>

        <div className="z3-layout" style={local && !data.snapshot ? { display: 'none' } : undefined}>
          <div className="z3-table-wrap" data-data-card>
            <table className="z3-table">
              <thead>
                <tr className="z3-pillar-row"><th />{pillar2.length ? <th colSpan={pillar2.length}>Pillar 2 · Public procurement</th> : null}{pillar6.length ? <th colSpan={pillar6.length}>Pillar 6 · Cross-border data policies</th> : null}{pillar7.length ? <th colSpan={pillar7.length}>Pillar 7 · Personal data protection</th> : null}</tr>
                <tr>
                  <th>Economy</th>
                  {orderedIndicators.map((indicator) => <th key={indicator} title={questionFor(indicator) || indicator}><b>{indicator}</b><i>{indicatorShort(questionFor(indicator))}</i></th>)}
                </tr>
              </thead>
              <tbody>
                {data.economies.map((economy) => (
                  <tr key={economy}>
                    <th scope="row"><strong>{economy}</strong><small>{evidenceCount(economy)} evidence rows</small></th>
                    {orderedIndicators.map((indicator) => {
                      const cell = cellFor(economy, indicator)
                      if (!cell) return <td key={indicator}><span className="z3-empty">n/a</span></td>
                      return (
                        <td key={indicator}>
                          <button
                            type="button"
                            onClick={() => openCell(cell)}
                            className={cn('z3-cell', `is-${cell.state}`, selected?.score_key === cell.score_key && 'is-selected', cell.blocked && 'is-blocked')}
                            title={`${economy} · ${indicator} — ${cell.state === 'pending' ? 'engine proposal awaiting reviewer decision' : `${cell.state} by ${cell.reviewer_name}`}`}
                          >
                            <span className="z3-cell-top">{STATE_ICON[cell.state]}<strong>{scoreLabel(cell.state === 'pending' ? cell.deterministic : cell.effective)}</strong></span>
                            <em>{cell.evidence.length} evidence</em>
                            {cell.flagged || cell.gold_divergence ? <AlertTriangle size={11} className="z3-flag" /> : null}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <footer className="z3-legend">
              <span className="is-approved">approved</span>
              <span className="is-overridden">override</span>
              <span className="is-pending">proposed — awaiting named reviewer</span>
              <span><AlertTriangle size={11} /> low agreement or gold divergence</span>
              <em>Click any cell to see the engine proposal, judge panel, reviewer decision and evidence.</em>
            </footer>
          </div>

          {selected ? (
            <aside className="z3-drawer" data-data-card aria-label={`${selected.economy} ${selected.indicator} details`}>
              <header>
                <div><span>{selected.economy} · {selected.indicator}</span><strong>{selected.question || 'Indicator question unavailable'}</strong></div>
                <button type="button" onClick={() => setSelectedKey(null)} aria-label="Close details"><X size={16} /></button>
              </header>

              <section>
                <h3><Scale size={13} /> Engine proposal</h3>
                <p className="z3-det"><b>{scoreLabel(selected.deterministic)}</b> {selected.deterministic_reason}</p>
                {selected.judge_scores ? <p className="z3-judges"><Gavel size={12} /> {selected.judge_scores} · α {String(selected.agreement_alpha ?? 'n/a')} · band {selected.score_band || 'n/a'}</p> : null}
                <p className="z3-gold">Master gold suggests <b>{scoreLabel(selected.master_gold as number | string | null)}</b>{selected.gold_divergence ? ' — diverges from the engine proposal' : ' — agrees with the engine proposal'}</p>
                {selected.gold_divergence ? <p className="z3-divergence"><AlertTriangle size={12} /> {selected.gold_divergence}</p> : null}
              </section>

              <section>
                <h3>{selected.state === 'pending' ? <CircleDashed size={13} /> : <CheckCircle2 size={13} />} Reviewer decision</h3>
                {selected.state === 'pending'
                  ? <p className="z3-pending-note">No named decision yet. The proposed score is not effective until a reviewer records one.</p>
                  : <p className="z3-decision">Effective <b>{scoreLabel(selected.effective)}</b> — {selected.state} by <b>{selected.reviewer_name}</b>{selected.reviewed_at ? ` · ${new Date(selected.reviewed_at).toLocaleString()}` : ''}{selected.reasoning ? <><br /><em>“{selected.reasoning}”</em></> : null}</p>}
              </section>

              <section>
                <h3>Evidence this score rests on ({selected.evidence.length})</h3>
                {selected.evidence.length ? (
                  <ul className="z3-evidence">
                    {selected.evidence.map((row) => (
                      <li key={row.stable_key}>
                        <div><strong>{row.law || 'Instrument unavailable'}</strong><span>{row.article || '—'}{row.tag ? ` · ${row.tag}` : ''}</span></div>
                        <div className="z3-evidence-links">
                          {row.finding_key ? <Link href={modeHref(`/match/${row.finding_key}?queue=${row.queue}`)}>Source Match <ArrowUpRight size={11} /></Link> : null}
                          <Link href={modeHref(`/review?queue=${row.queue}&item=${row.stable_key}`)}>Review <ArrowUpRight size={11} /></Link>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : <p className="z3-pending-note">No evidence rows in this update for this indicator (absence conclusions live in the Review Absence queue).</p>}
              </section>

              {canDecide ? (
                <section className="z3-decide">
                  <h3>{selected.state === 'pending' ? 'Record decision' : 'Overwrite decision'}</h3>
                  <div className="z3-decide-mode">
                    <button type="button" className={cn(!override && 'selected')} onClick={() => { setOverride(false); setScore(Number(selected.deterministic ?? 0) as Zone3Score) }}>Approve deterministic {scoreLabel(selected.deterministic)}</button>
                    <button type="button" className={cn(override && 'selected')} onClick={() => setOverride(true)}>Override</button>
                  </div>
                  {override ? <div className="z3-scores">{([0, 0.5, 1] as Zone3Score[]).map((value) => <button type="button" key={value} className={cn(score === value && 'selected')} onClick={() => setScore(value)}>{value}</button>)}</div> : null}
                  <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={override ? 'Reasoning (required for an override)…' : 'Reasoning / note (recorded in the immutable ledger)…'} />
                  <button type="button" className="z3-submit" disabled={decide.isPending || (override && !note.trim()) || Boolean(selected.blocked)} onClick={() => void submit(override ? 'overridden' : 'approved')}>
                    {decide.isPending ? 'Saving — waiting for authoritative receipt…' : override ? `Record override ${score}` : `Approve ${scoreLabel(selected.deterministic)}`}
                  </button>
                  {selected.state !== 'pending' ? <p className="z3-pending-note">Overwriting supersedes the previous decision in the append-only ledger; nothing is erased.</p> : null}
                </section>
              ) : <p className="z3-pending-note">Read-only access — scoring requires a mapping reviewer or admin role.</p>}
            </aside>
          ) : (
            <aside className="z3-drawer z3-drawer-empty" data-data-card><Scale size={20} /><p>Select a cell to see the engine proposal, the judge panel, the gold reference, the reviewer decision and the exact evidence rows behind it.</p></aside>
          )}
        </div>
      </div>
    </WorkspaceShell>
  )
}
