'use client'
import { useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Copy, Download, PackageCheck } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import PipelineStepper from '@/components/clausechain/PipelineStepper'
import { EVIDENCE_AUDIT_CASE, MAPPING_STREAM, SOURCE_STATUS_EDGES } from '@/lib/clausechain/data'

type Tab = 'records' | 'json' | 'csv' | 'provenance'

interface ExportRecord {
  record_id: string
  jurisdiction: string
  framework: string
  rdtii_indicator: string
  citation: {
    instrument_id: string
    title: string
    section: string
    page: number
    url: string
    char_offset: string
    span_sha256: string
  }
  source_status: {
    source_id: string
    status: string
    binding: boolean
    current: boolean
    authority_rank: number
  }
  legal_predicate: {
    subject: string
    action: string
    object: string
    modality: string
    condition: string
    exception: string
    legal_effect: string
  }
  verification_gates: Array<{ id: string; label: string; status: string; score: string }>
  counter_evidence: Array<{ source_id: string; relation: string; resolution: string }>
  status: string
  model: string
}

function toCsv(records: ExportRecord[]) {
  const header = ['record_id', 'jurisdiction', 'rdtii_indicator', 'section', 'source_status', 'span_sha256', 'predicate_subject', 'predicate_action', 'predicate_condition', 'predicate_exception', 'gate_summary', 'status']
  const rows = records.map((record) => [
    record.record_id,
    record.jurisdiction,
    record.rdtii_indicator,
    record.citation.section,
    record.source_status.status,
    record.citation.span_sha256,
    record.legal_predicate.subject,
    record.legal_predicate.action,
    `"${record.legal_predicate.condition.replace(/"/g, '""')}"`,
    `"${record.legal_predicate.exception.replace(/"/g, '""')}"`,
    record.verification_gates.map((gate) => `${gate.id}:${gate.status}`).join('|'),
    record.status,
  ])
  return [header.join(','), ...rows.map((row) => row.join(','))].join('\n')
}

export default function ExportOutput() {
  const [tab, setTab] = useState<Tab>('records')
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['run-SG-PDPA-001:SG s 26(1)']))

  const records = useMemo<ExportRecord[]>(() => {
    const primary = EVIDENCE_AUDIT_CASE
    const verified = MAPPING_STREAM.filter((row) => row.status === 'verified' && row.predicate)
    return verified.map((row, index) => ({
      record_id: `run-SG-PDPA-001:${row.ref}`,
      jurisdiction: row.ref.startsWith('TH') ? 'TH' : row.ref.startsWith('BD') ? 'BD' : 'SG',
      framework: 'RDTII',
      rdtii_indicator: row.predicate?.rdtiiIndicator ?? row.pillar,
      citation: {
        instrument_id: row.ref.startsWith('SG') ? primary.docId : row.ref.startsWith('TH') ? 'TH-PDPA-2019' : 'BD-PDPA-DEMO',
        title: row.ref.startsWith('SG') ? primary.title : row.ref.startsWith('TH') ? 'Personal Data Protection Act B.E. 2562' : 'Bangladesh data protection instrument',
        section: row.ref,
        page: row.ref === 'SG s 26(1)' ? primary.page : 1 + index,
        url: row.ref.startsWith('SG') ? primary.sourceUrl : row.ref.startsWith('TH') ? 'https://ratchakitcha.soc.go.th/pdpa-2019.pdf' : 'https://bdlaws.minlaw.gov.bd',
        char_offset: row.ref === 'SG s 26(1)' ? primary.charOffset : '[demo-offset]',
        span_sha256: row.ref === 'SG s 26(1)' ? primary.spanHash : `${row.id.toUpperCase()}-${index}A91`,
      },
      source_status: {
        source_id: row.ref.startsWith('SG') ? primary.sourceStatus.id : row.ref.startsWith('TH') ? 'TH-PDPA-CURRENT' : 'BD-CURRENT-DEMO',
        status: row.sourceStatus ?? 'binding_current',
        binding: row.sourceStatus !== 'context_only' && row.sourceStatus !== 'requires_review',
        current: row.sourceStatus === 'binding_current',
        authority_rank: row.sourceStatus === 'binding_current' ? 1 : 3,
      },
      legal_predicate: {
        subject: row.predicate?.subject ?? '',
        action: row.predicate?.action ?? '',
        object: row.predicate?.object ?? '',
        modality: row.predicate?.modality ?? '',
        condition: row.predicate?.condition ?? '',
        exception: row.predicate?.exception ?? '',
        legal_effect: row.predicate?.legalEffect ?? '',
      },
      verification_gates: (row.gatesV2 ?? primary.gatesV2).map((gate, gateIndex) => ({
        id: gate.id,
        label: gate.label,
        status: row.gates[gateIndex] ?? gate.status,
        score: row.scores[gateIndex] ?? gate.score,
      })),
      counter_evidence: row.ref === 'SG s 26(1)'
        ? primary.counterEvidence.map((item) => ({ source_id: item.sourceId, relation: item.relation, resolution: item.resolution }))
        : [],
      status: row.status,
      model: row.model,
    }))
  }, [])

  const payload = {
    run_id: 'run-SG-PDPA-001',
    generated_at: '2026-05-23T09:45:00Z',
    framework: 'RDTII',
    framework_scope: ['Pillar 6', 'Pillar 7'],
    provenance_bundle: {
      manifest_sha256: 'BUNDLE-8E3A91F0',
      ledger_entries: records.length,
      graph_edges: SOURCE_STATUS_EDGES.length,
      export_policy: 'only verified or human-approved records are exportable',
    },
    records,
  }

  const json = JSON.stringify(payload, null, 2)
  const csv = toCsv(records)
  const provenance = JSON.stringify({
    manifest: payload.provenance_bundle,
    source_graph_edges: SOURCE_STATUS_EDGES,
    span_hashes: records.map((record) => ({ record_id: record.record_id, span_sha256: record.citation.span_sha256 })),
  }, null, 2)

  const currentText = tab === 'json' ? json : tab === 'csv' ? csv : tab === 'provenance' ? provenance : ''

  const copyCurrent = () => {
    navigator.clipboard.writeText(currentText).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  const download = (name: string, content: string) => {
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'Pipeline' }, { label: 'Export Output' }]}>
      <PipelineStepper activeId="export" />

      <div className="cc-page cc-pipeline-page">
        <div className="cc-page-header" style={{ alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 700, fontSize: 24, color: 'var(--cc-ink-950)', margin: 0 }}>
              Export Output
            </h1>
            <div style={{ fontSize: 13, color: 'var(--cc-ink-500)', marginTop: 4 }}>
              <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 12 }}>run-SG-PDPA-001</span>
              {' '}· evidence-based RDTII export · predicate + source-status schema
            </div>
          </div>
          <div className="cc-actions">
            {[
              ['JSON', 'run-SG-PDPA-001.json', json],
              ['CSV', 'run-SG-PDPA-001.csv', csv],
              ['Bundle', 'run-SG-PDPA-001.provenance.json', provenance],
            ].map(([label, name, content]) => (
              <button
                key={name}
                onClick={() => download(name, content)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 14px', height: 36, borderRadius: 10, fontSize: 13, fontWeight: 500, border: '1px solid var(--cc-ink-300)', background: 'white', color: 'var(--cc-ink-800)', cursor: 'pointer' }}
              >
                <Download size={13} /> {label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 18px', background: '#ECFDF5', border: '1px solid #A7F3D0', borderRadius: 10, marginBottom: 20, flexWrap: 'wrap' }}>
          <span style={{ width: 22, height: 22, borderRadius: '50%', background: '#10B981', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
            <PackageCheck size={13} color="white" />
          </span>
          <div style={{ fontSize: 13, color: '#065F46' }}>
            <strong>Export policy passed</strong> — {records.length} verified records · {SOURCE_STATUS_EDGES.length} graph edges · span hashes attached · blocked/abstained rows excluded.
          </div>
        </div>

        <div className="cc-kpi-grid-five" style={{ gap: 14, marginBottom: 24 }}>
          {[
            ['Records', records.length, 'var(--cc-ink-900)'],
            ['P6/P7 records', records.filter((record) => record.rdtii_indicator.startsWith('6') || record.rdtii_indicator.startsWith('7')).length, '#047857'],
            ['Source graph edges', SOURCE_STATUS_EDGES.length, '#1D4ED8'],
            ['Span hashes', records.length, '#0F766E'],
            ['Abstained excluded', MAPPING_STREAM.filter((row) => row.abstained).length, '#B45309'],
          ].map(([label, value, color]) => (
            <div key={String(label)} style={{ background: 'white', border: '1px solid var(--cc-ink-200)', borderRadius: 12, padding: '16px 18px' }}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--cc-ink-500)', marginBottom: 6 }}>{label}</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: String(color), fontFamily: 'var(--cc-font-display)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
            </div>
          ))}
        </div>

        <div className="cc-export-tabs">
          {(['records', 'json', 'csv', 'provenance'] as Tab[]).map((item) => (
            <button
              key={item}
              onClick={() => setTab(item)}
              style={{
                padding: '10px 18px',
                fontSize: 13,
                fontWeight: tab === item ? 600 : 400,
                color: tab === item ? 'var(--cc-teal-600)' : 'var(--cc-ink-500)',
                background: 'none',
                border: 'none',
                borderBottom: tab === item ? '2px solid var(--cc-teal-600)' : '2px solid transparent',
                cursor: 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {item === 'provenance' ? 'Bundle' : item}
            </button>
          ))}
          {tab !== 'records' && (
            <button
              onClick={copyCurrent}
              style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', height: 32, borderRadius: 8, fontSize: 12, fontWeight: 500, border: '1px solid var(--cc-ink-200)', background: 'white', color: copied ? '#10B981' : 'var(--cc-ink-700)', cursor: 'pointer' }}
            >
              {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
            </button>
          )}
        </div>

        {tab === 'records' ? (
          <div className="cc-table-scroll" style={{ border: '1px solid var(--cc-ink-200)', borderTop: 'none', borderRadius: '0 0 14px 14px', overflow: 'auto', background: 'white' }}>
            <div className="cc-export-record-row" style={{ padding: '10px 20px', background: 'var(--cc-ink-50)', borderBottom: '1px solid var(--cc-ink-200)', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--cc-ink-500)' }}>
              <span>Record</span>
              <span>Indicator</span>
              <span>Predicate</span>
              <span>Source</span>
              <span>Gates</span>
              <span>Span hash</span>
            </div>
            {records.map((record) => {
              const open = expanded.has(record.record_id)
              return (
                <div key={record.record_id} style={{ borderBottom: '1px solid var(--cc-ink-100)' }}>
                  <button
                    onClick={() => setExpanded((prev) => {
                      const next = new Set(prev)
                      if (next.has(record.record_id)) {
                        next.delete(record.record_id)
                      } else {
                        next.add(record.record_id)
                      }
                      return next
                    })}
                    className="cc-export-record-row"
                    style={{ width: '100%', padding: '14px 20px', alignItems: 'start', border: 'none', background: 'white', cursor: 'pointer', textAlign: 'left' }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontFamily: 'var(--cc-font-mono)', fontSize: 12, color: 'var(--cc-ink-900)' }}>
                      {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      {record.citation.section}
                    </span>
                    <span style={{ width: 'fit-content', borderRadius: 999, background: '#F0FDFA', color: '#0F766E', padding: '2px 8px', fontFamily: 'var(--cc-font-mono)', fontSize: 12, fontWeight: 700 }}>{record.rdtii_indicator}</span>
                    <span style={{ fontSize: 13, color: 'var(--cc-ink-800)', lineHeight: 1.45 }}>
                      {record.legal_predicate.subject} · {record.legal_predicate.modality} · {record.legal_predicate.legal_effect}
                    </span>
                    <span style={{ fontSize: 12, color: record.source_status.binding ? '#047857' : '#B45309', fontWeight: 700 }}>{record.source_status.status}</span>
                    <span style={{ display: 'flex', gap: 3, paddingTop: 3 }}>
                      {record.verification_gates.map((gate) => (
                        <span key={gate.id} title={`${gate.id}: ${gate.status}`} className={`gate-dot ${gate.status === 'fail' ? 'fail' : gate.status === 'warn' ? 'warn' : 'pass'}`} />
                      ))}
                    </span>
                    <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11, color: 'var(--cc-ink-600)' }}>{record.citation.span_sha256}</span>
                  </button>
                  {open && (
                    <div className="cc-export-details">
                      <div style={{ border: '1px solid var(--cc-ink-200)', borderRadius: 12, background: 'var(--cc-ink-50)', padding: 12 }}>
                        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--cc-ink-500)', marginBottom: 8 }}>Citation object</p>
                        <pre style={{ margin: 0, fontSize: 11, lineHeight: 1.55, whiteSpace: 'pre-wrap', fontFamily: 'var(--cc-font-mono)', color: 'var(--cc-ink-800)' }}>{JSON.stringify(record.citation, null, 2)}</pre>
                      </div>
                      <div style={{ border: '1px solid var(--cc-ink-200)', borderRadius: 12, background: 'var(--cc-ink-50)', padding: 12 }}>
                        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--cc-ink-500)', marginBottom: 8 }}>Counter-evidence</p>
                        <pre style={{ margin: 0, fontSize: 11, lineHeight: 1.55, whiteSpace: 'pre-wrap', fontFamily: 'var(--cc-font-mono)', color: 'var(--cc-ink-800)' }}>{JSON.stringify(record.counter_evidence, null, 2)}</pre>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div style={{ border: '1px solid var(--cc-ink-200)', borderTop: 'none', borderRadius: '0 0 14px 14px', overflow: 'hidden', background: '#0F1117' }}>
            <pre style={{ margin: 0, padding: '20px 24px', overflowX: 'auto', maxHeight: 640, overflowY: 'auto', fontSize: 12, lineHeight: 1.7, fontFamily: 'var(--cc-font-mono)', color: '#E2E8F0' }}>
              {currentText}
            </pre>
          </div>
        )}
      </div>
    </WorkspaceShell>
  )
}
