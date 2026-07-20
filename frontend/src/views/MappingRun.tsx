'use client'
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Cloud, Cpu, Pause, Play, ShieldCheck, X } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import PipelineStepper from '@/components/clausechain/PipelineStepper'
import { MAPPING_STREAM } from '@/lib/clausechain/data'
import type { MappingClause } from '@/lib/clausechain/data'

const MODEL_ROUTES = [
  { stage: 'Embedding', model: 'Qwen3-Embedding-0.6B', type: 'local', detail: 'Multilingual dense retrieval' },
  { stage: 'Sparse retrieval', model: 'OpenSearch BM25', type: 'local', detail: 'Exact legal terms and citations' },
  { stage: 'Rerank', model: 'Qwen3-Reranker-0.6B', type: 'local', detail: 'Top-k clause evidence reranking' },
  { stage: 'Predicate extraction', model: 'Qwen2.5-7B-Instruct', type: 'local', detail: 'Constrained JSON tuple output' },
  { stage: 'OCR repair', model: 'PaddleOCR + Qwen2-VL', type: 'local', detail: 'Only for disagreement regions' },
  { stage: 'Hard-case escalation', model: 'optional external LLM', type: 'cloud', detail: 'Disabled unless reviewer allows' },
]

const GATE_LABELS = ['Source', 'Current', 'Text', 'Boundary', 'Retrieval', 'Predicate', 'Mapping', 'Conflict']

export default function MappingRun() {
  const [streamIdx, setStreamIdx] = useState(0)
  const [running, setRunning] = useState(false)
  const [paused, setPaused] = useState(false)
  const [autonomy, setAutonomy] = useState<'L0' | 'L1' | 'L2' | 'L3'>('L1')
  const [selectedRow, setSelectedRow] = useState<string | null>(null)

  const visible = MAPPING_STREAM.slice(0, streamIdx)
  const isDone = streamIdx >= MAPPING_STREAM.length
  const selected = visible.find((row) => row.id === selectedRow) ?? visible[visible.length - 1]

  useEffect(() => {
    if (!running || paused || isDone) return
    const delay = 950 + Math.random() * 450
    const timer = setTimeout(() => setStreamIdx((value) => value + 1), delay)
    return () => clearTimeout(timer)
  }, [isDone, paused, running, streamIdx])

  const stats = useMemo(() => {
    return {
      verified: visible.filter((row) => row.status === 'verified').length,
      rejected: visible.filter((row) => row.status === 'rejected').length,
      abstained: visible.filter((row) => row.abstained).length,
      counterEvidence: visible.reduce((sum, row) => sum + (row.counterEvidence ?? 0), 0),
      escalated: visible.filter((row) => row.escalated).length,
    }
  }, [visible])

  const gateCounts = GATE_LABELS.map((label, index) => ({
    label,
    passed: visible.filter((row) => row.gates[index] === 'pass' || row.gates[index] === 'warn').length,
    failed: visible.filter((row) => row.gates[index] === 'fail').length,
  }))

  const start = () => {
    if (isDone) setStreamIdx(0)
    setRunning(true)
    setPaused(false)
    setSelectedRow(null)
  }

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'Pipeline' }, { label: 'Mapping Run' }]}>
      <PipelineStepper activeId="predicate" />

      <div className="cc-page cc-pipeline-page">
        <div className="cc-page-header" style={{ marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 700, fontSize: 32, color: 'var(--cc-ink-950)', margin: 0, letterSpacing: '-0.02em' }}>
              Mapping Run
            </h1>
            <div style={{ fontSize: 14, color: 'var(--cc-ink-500)', marginTop: 6 }}>
              SG PDPA + stress cases → RDTII Pillars 6 &amp; 7 ·{' '}
              <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 12 }}>run-SG-PDPA-001</span>
            </div>
          </div>

          <div className="cc-actions">
            <div style={{ display: 'flex', gap: 4, background: 'var(--cc-ink-100)', borderRadius: 10, padding: 3 }}>
              {(['L0', 'L1', 'L2', 'L3'] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setAutonomy(level)}
                  style={{
                    padding: '4px 12px',
                    borderRadius: 6,
                    border: 'none',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    background: autonomy === level ? 'white' : 'transparent',
                    color: autonomy === level ? 'var(--cc-ink-900)' : 'var(--cc-ink-500)',
                    boxShadow: autonomy === level ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                    transition: 'all 150ms cubic-bezier(0.4,0,0.2,1)',
                  }}
                >
                  {level}
                </button>
              ))}
            </div>

            {!running || isDone ? (
              <button
                onClick={start}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 18px', height: 40, borderRadius: 10, border: 'none', fontSize: 14, fontWeight: 500, background: 'var(--cc-teal-600)', color: 'white', cursor: 'pointer' }}
              >
                <Play size={14} fill="white" stroke="none" /> Start mapping
              </button>
            ) : (
              <button
                onClick={() => setPaused((value) => !value)}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 18px', height: 40, borderRadius: 10, border: '1px solid var(--cc-ink-300)', fontSize: 14, fontWeight: 500, background: 'white', color: 'var(--cc-ink-900)', cursor: 'pointer' }}
              >
                {paused ? <Play size={14} /> : <Pause size={14} />} {paused ? 'Resume' : 'Pause'}
              </button>
            )}
          </div>
        </div>

        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--cc-ink-700)', marginBottom: 6 }}>
            <span>{!running ? 'Ready' : paused ? 'Paused' : isDone ? 'Complete' : 'Extracting predicates and verifying gates...'}</span>
            <span style={{ fontFamily: 'var(--cc-font-mono)', fontWeight: 600 }}>{streamIdx} / {MAPPING_STREAM.length}</span>
          </div>
          <div style={{ height: 7, background: 'var(--cc-ink-200)', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ height: '100%', background: isDone ? '#10B981' : 'var(--cc-teal-600)', borderRadius: 999, width: `${(streamIdx / MAPPING_STREAM.length) * 100}%`, transition: 'width 600ms ease' }} />
          </div>
        </div>

        <div className="cc-mapping-layout">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div className="cc-kpi-grid-five">
              {[
                { label: 'Verified', val: stats.verified, color: '#047857', bg: '#ECFDF5', border: '#10B98140' },
                { label: 'Rejected', val: stats.rejected, color: '#B91C1C', bg: '#FEF2F2', border: '#EF444440' },
                { label: 'Abstained', val: stats.abstained, color: '#1D4ED8', bg: '#EFF6FF', border: '#3B82F640' },
                { label: 'Counter-evidence', val: stats.counterEvidence, color: '#B45309', bg: '#FFFBEB', border: '#F59E0B40' },
                { label: 'Escalated', val: stats.escalated, color: '#52525B', bg: 'white', border: 'var(--cc-ink-200)' },
              ].map((card) => (
                <div key={card.label} style={{ padding: '14px 16px', background: card.bg, border: `1px solid ${card.border}`, borderRadius: 14 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: card.color, marginBottom: 6 }}>{card.label}</div>
                  <div style={{ fontFamily: 'var(--cc-font-display)', fontSize: 30, fontWeight: 700, color: card.color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{card.val}</div>
                </div>
              ))}
            </div>

            <div className="mapping-stream">
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--cc-ink-200)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <h3 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 600, fontSize: 16, margin: 0 }}>Clause + predicate stream</h3>
                {running && !isDone && !paused && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--cc-teal-600)' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--cc-teal-600)' }} />
                    Live
                  </span>
                )}
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 12, color: 'var(--cc-ink-500)' }}>{streamIdx} / {MAPPING_STREAM.length} processed</span>
              </div>

              <div className="cc-table-scroll">
              <div className="cc-mapping-stream-header" style={{ display: 'grid', gap: 12, padding: '8px 16px', background: 'var(--cc-ink-50)', borderBottom: '1px solid var(--cc-ink-200)' }}>
                {['Clause', 'Predicate / evidence', 'RDTII', '8 gates', 'Outcome'].map((heading) => (
                  <div key={heading} style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--cc-ink-500)' }}>{heading}</div>
                ))}
              </div>

              {visible.map((row) => (
                <MappingRow
                  key={row.id}
                  row={row}
                  selected={selectedRow === row.id}
                  onClick={() => setSelectedRow(selectedRow === row.id ? null : row.id)}
                />
              ))}
              </div>

              {visible.length === 0 && (
                <div style={{ padding: '56px 0', textAlign: 'center', color: 'var(--cc-ink-400)', fontSize: 13 }}>
                  Press <strong style={{ color: 'var(--cc-ink-600)' }}>Start mapping</strong> to begin predicate extraction and verification.
                </div>
              )}
            </div>

            {visible.some((row) => row.abstained) && (
              <div style={{ background: 'white', border: '1px solid var(--cc-ink-200)', borderRadius: 14, overflow: 'hidden', animation: 'cc-fade-in 300ms ease' }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--cc-ink-200)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <h3 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 600, fontSize: 14, margin: 0 }}>Abstention inspector</h3>
                  <span style={{ background: '#EFF6FF', color: '#1D4ED8', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999 }}>
                    {stats.abstained}
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--cc-ink-500)' }}>Blocked before export</span>
                </div>
                {visible.filter((row) => row.abstained).map((row) => (
                  <div key={row.id} style={{ padding: '10px 16px', borderBottom: '1px solid var(--cc-ink-100)', fontSize: 13 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 5 }}>
                      <span style={{ fontFamily: 'var(--cc-font-mono)', fontWeight: 700, color: 'var(--cc-ink-900)' }}>{row.ref}</span>
                      <span style={{ color: '#1D4ED8', fontWeight: 600, fontSize: 12, display: 'flex', alignItems: 'center', gap: 3 }}>
                        <ShieldCheck size={12} /> abstained at {row.rejectedGate ?? 'verification'}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--cc-ink-600)', paddingLeft: 8, borderLeft: '2px solid #DBEAFE' }}>
                      {row.text}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ background: 'white', border: '1px solid var(--cc-ink-200)', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--cc-ink-200)' }}>
                <h3 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 600, fontSize: 14, margin: 0 }}>Eight-gate throughput</h3>
              </div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {gateCounts.map((gate, index) => (
                  <div key={gate.label}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <span style={{ color: 'var(--cc-ink-700)' }}>G{index + 1} — {gate.label}</span>
                      <span style={{ fontFamily: 'var(--cc-font-mono)', fontWeight: 600, color: gate.failed > 0 ? '#B91C1C' : 'var(--cc-ink-900)' }}>
                        {streamIdx > 0 ? `${gate.passed}/${streamIdx}` : '-'}
                      </span>
                    </div>
                    <div style={{ height: 5, background: 'var(--cc-ink-100)', borderRadius: 999, overflow: 'hidden' }}>
                      <div style={{ height: '100%', background: gate.failed > 0 ? '#F59E0B' : 'var(--cc-teal-600)', borderRadius: 999, width: streamIdx > 0 ? `${(gate.passed / streamIdx) * 100}%` : '0%', transition: 'width 600ms ease' }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="routing-panel">
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--cc-ink-200)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <h3 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 600, fontSize: 14, margin: 0 }}>Model routing</h3>
                <span style={{ marginLeft: 'auto', background: '#ECFDF5', color: '#047857', fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 999 }}>Local first</span>
              </div>
              {MODEL_ROUTES.map((route, index) => (
                <div key={index} className="routing-row">
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--cc-ink-700)' }}>{route.stage}</div>
                    <div style={{ fontSize: 11, color: 'var(--cc-ink-500)' }}>{route.detail}</div>
                  </div>
                  <span className={`model-badge ${route.type === 'local' ? 'model-local' : 'model-cloud'}`}>
                    {route.type === 'cloud' ? <Cloud size={10} /> : <Cpu size={10} />}
                    {route.model}
                  </span>
                </div>
              ))}
            </div>

            {selected && (
              <div style={{ background: 'white', border: '1px solid var(--cc-ink-200)', borderRadius: 14, padding: 16, animation: 'cc-fade-in 250ms ease' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <span style={{ fontFamily: 'var(--cc-font-mono)', fontWeight: 700, color: 'var(--cc-ink-900)' }}>{selected.ref}</span>
                  {selected.status === 'verified' ? (
                    <span style={{ background: '#ECFDF5', color: '#047857', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999 }}>verified</span>
                  ) : (
                    <span style={{ background: '#FEF2F2', color: '#B91C1C', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999 }}>blocked</span>
                  )}
                </div>
                {selected.predicate ? (
                  <div className="cc-card-grid-2" style={{ gap: 8 }}>
                    {[
                      ['Subject', selected.predicate.subject],
                      ['Action', selected.predicate.action],
                      ['Modality', selected.predicate.modality],
                      ['Condition', selected.predicate.condition],
                      ['Exception', selected.predicate.exception],
                      ['Effect', selected.predicate.legalEffect],
                    ].map(([label, value]) => (
                      <div key={label} style={{ border: '1px solid var(--cc-ink-200)', borderRadius: 10, padding: 10, background: 'var(--cc-ink-50)' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--cc-ink-500)' }}>{label}</div>
                        <div style={{ fontSize: 12, lineHeight: 1.35, color: 'var(--cc-ink-900)', marginTop: 3 }}>{value}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 8, color: '#B45309', fontSize: 13, lineHeight: 1.45 }}>
                    <AlertTriangle size={15} /> Predicate incomplete; this row is routed to review and excluded from export.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </WorkspaceShell>
  )
}

function MappingRow({ row, selected, onClick }: { row: MappingClause; selected: boolean; onClick: () => void }) {
  return (
    <div
      className={`mapping-row ${row.status === 'rejected' ? 'mr-rejected' : ''}`}
      style={{
        background: selected ? 'var(--cc-teal-50)' : undefined,
      }}
      onClick={onClick}
    >
      <div>
        <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--cc-ink-900)' }}>{row.ref}</span>
        <div style={{ fontSize: 10, color: row.sourceStatus === 'binding_current' ? '#047857' : '#B45309', fontWeight: 600, marginTop: 1 }}>
          {row.sourceStatus?.replaceAll('_', ' ') ?? 'source pending'}
        </div>
      </div>
      <div style={{ overflow: 'hidden' }}>
        <div style={{ fontSize: 12, color: 'var(--cc-ink-700)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.text}</div>
        <div style={{ fontSize: 11, color: 'var(--cc-ink-500)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.predicate ? `${row.predicate.subject} · ${row.predicate.modality} · ${row.predicate.legalEffect}` : 'predicate incomplete / abstained'}
        </div>
      </div>
      <div>
        <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11, background: 'var(--cc-ink-100)', padding: '2px 6px', borderRadius: 4, color: 'var(--cc-ink-800)' }}>
          {row.status === 'verified' ? row.pillar : 'review'}
        </span>
        <div style={{ fontSize: 10, color: 'var(--cc-ink-500)', marginTop: 2 }}>{row.pillarLabel}</div>
      </div>
      <div>
        <div className="gate-dots" style={{ marginBottom: 3 }}>
          {row.gates.map((gate, index) => (
            <span key={`${row.id}-${index}`} className={`gate-dot ${gate}`} title={`G${index + 1}: ${gate} (${row.scores[index] ?? '-'})`} />
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
          {row.scores.slice(0, 4).map((score, index) => {
            const gate = row.gates[index]
            const color = gate === 'pass' ? '#10B981' : gate === 'warn' ? '#F59E0B' : '#EF4444'
            return (
              <span key={index} style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 9, color, background: `${color}20`, padding: '1px 4px', borderRadius: 3 }}>{score}</span>
            )
          })}
        </div>
      </div>
      <div>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '2px 8px',
          borderRadius: 999,
          fontSize: 11,
          fontWeight: 600,
          background: row.status === 'verified' ? '#ECFDF5' : row.abstained ? '#EFF6FF' : '#FEF2F2',
          color: row.status === 'verified' ? '#047857' : row.abstained ? '#1D4ED8' : '#B91C1C',
        }}>
          {row.status === 'verified' ? <ShieldCheck size={10} /> : <X size={10} />}
          {row.abstained ? 'abstain' : row.status}
        </span>
      </div>
    </div>
  )
}
