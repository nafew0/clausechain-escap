'use client'

import { ExternalLink, FileSearch, Files, ScanText, ShieldCheck } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, SnapshotBanner, TruthBadge } from '@/components/clausechain/TruthState'
import { useOpsStats } from '@/hooks/workspace'
import type { JsonObject, JsonValue } from '@/types/workspace'

type Mode = 'acquisition' | 'eligibility' | 'extraction'
const TITLE: Record<Mode, string> = { acquisition: 'Source Acquisition', eligibility: 'Corpus Eligibility', extraction: 'Extraction' }
const ICON = { acquisition: Files, eligibility: ShieldCheck, extraction: ScanText }
const text = (value: JsonValue | undefined, fallback = '—') => value === null || value === undefined || value === '' ? fallback : String(value)
const entries = (value: JsonValue | undefined) => value && typeof value === 'object' && !Array.isArray(value) ? Object.entries(value as JsonObject) : []
const sum = (value: JsonValue | undefined) => entries(value).reduce((total, [, count]) => total + Number(count ?? 0), 0)

export default function OpsScreen({ mode }: { mode: Mode }) {
  const query = useOpsStats()
  const Icon = ICON[mode]
  const rows = query.data?.ops_stats[mode] ?? []
  return <WorkspaceShell breadcrumbs={[{ label: 'Pipeline' }, { label: TITLE[mode] }]}><div className="cc-page ops-screen">
    <div className="cc-page-header"><div><TruthBadge state="live" /><h1 className="cc-page-title text-[32px] mt-3">{TITLE[mode]}</h1><p className="text-cc-ink-500 mt-1.5">Engine-exported operational facts from the immutable graph store.</p></div><div className="ops-total"><Icon size={20} /><strong>{rows.length}</strong><span>{mode === 'acquisition' ? 'artifacts' : 'instruments'}</span></div></div>
    {query.isError || !query.data ? <PageUnavailable title={query.isPending ? 'Loading engine operations…' : `${TITLE[mode]} data is unavailable`} /> : <><SnapshotBanner snapshot={query.data.snapshot} />
      {mode === 'acquisition' ? <Acquisition rows={rows} /> : mode === 'eligibility' ? <Eligibility rows={rows} /> : <Extraction rows={rows} />}
    </>}
  </div></WorkspaceShell>
}

function Acquisition({ rows }: { rows: JsonObject[] }) {
  const groups = rows.reduce<Record<string, JsonObject[]>>((result, row) => { const key = text(row.economy, 'Cross-economy'); (result[key] ??= []).push(row); return result }, {})
  return <div className="ops-groups">{Object.entries(groups).map(([economy, values]) => <section key={economy}><div className="truth-section-heading"><div><span>Source archive</span><h2>{economy}</h2></div><b>{values.length} immutable artifacts</b></div><div className="ops-table-wrap"><table><thead><tr>{['Type','Official source','Domain','Size','Accessed','SHA-256','Status evidence'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{values.map(row => <tr key={text(row.id)}><td><b>{text(row.source_type)}</b><small>{text(row.mime_type)}</small></td><td><a href={text(row.source_url, '#')} target="_blank" rel="noreferrer">{text(row.retrieved_url ?? row.source_url).slice(0, 55)} <ExternalLink size={11} /></a></td><td>{text(row.domain)}</td><td>{Number(row.bytes ?? 0).toLocaleString()} B</td><td>{row.accessed_at ? new Date(String(row.accessed_at)).toLocaleDateString() : '—'}</td><td><code title={text(row.sha256)}>{text(row.sha256).slice(0, 12)}…</code></td><td>{text(row.status_evidence)}</td></tr>)}</tbody></table></div></section>)}</div>
}

function Eligibility({ rows }: { rows: JsonObject[] }) {
  return <div className="ops-card-grid">{rows.map(row => { const reasons = entries(row.ineligible_reasons); return <article className="truth-data-card" data-data-card key={`${text(row.economy)}-${text(row.instrument)}`}><header><div><span>{text(row.economy)}</span><h2>{text(row.instrument)}</h2></div><FileSearch size={18} /></header><div className="ops-metrics"><div><strong>{text(row.units)}</strong><span>units</span></div><div><strong>{text(row.evidence_eligible)}</strong><span>eligible</span></div><div><strong>{Number(row.units ?? 0) - Number(row.evidence_eligible ?? 0)}</strong><span>quarantined</span></div></div><section><b>Legal status</b><div className="ops-chips">{entries(row.legal_status).map(([key, value]) => <span key={key}>{key} · {text(value)}</span>)}</div></section><section><b>Quarantine reasons</b>{reasons.length ? <ul>{reasons.map(([key, value]) => <li key={key}>{key} · {text(value)}</li>)}</ul> : <p>No quarantined units.</p>}</section></article> })}</div>
}

function Extraction({ rows }: { rows: JsonObject[] }) {
  return <div className="ops-card-grid">{rows.map(row => <article className="truth-data-card" data-data-card key={`${text(row.economy)}-${text(row.instrument)}`}><header><div><span>{text(row.economy)}</span><h2>{text(row.instrument)}</h2></div><ScanText size={18} /></header><div className="ops-metrics"><div><strong>{text(row.units)}</strong><span>units</span></div><div><strong>{sum(row.alignment)}</strong><span>aligned records</span></div><div><strong>{row.mean_ocr_confidence == null ? 'N/A' : Number(row.mean_ocr_confidence).toFixed(3)}</strong><span>mean OCR confidence</span></div></div><section><b>Extraction methods</b><div className="ops-chips">{entries(row.methods).map(([key, value]) => <span key={key}>{key} · {text(value)}</span>)}</div></section><section><b>Alignment</b><div className="ops-chips">{entries(row.alignment).map(([key, value]) => <span className={key === 'unaligned-review' ? 'warn' : ''} key={key}>{key} · {text(value)}</span>)}</div></section></article>)}</div>
}
