'use client'

import { useMemo, useState } from 'react'
import { Check, Copy, Download, FileJson2, Search } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, SnapshotBanner, TruthBadge } from '@/components/clausechain/TruthState'
import { useRawArtifact, useRawArtifacts } from '@/hooks/workspace'
import { downloadRawArtifact } from '@/services/workspace'
import type { JsonValue, SnapshotArtifactMeta } from '@/types/workspace'

const CATEGORY: Record<string, string> = { review_payload: 'Review Payload', evidence: 'Evidence', runs: 'Runs', operations: 'Operations', configuration: 'Configuration', validation: 'Validation', manifests: 'Manifests' }

export default function RawDataExplorer() {
  const list = useRawArtifacts()
  const [selected, setSelected] = useState<{ snapshotId: string; key: string } | null>(null)
  const [queryState, setQueryState] = useState<{ snapshotId: string; value: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const snapshotId = list.data?.snapshot.id ?? ''
  const selectedKey = selected?.snapshotId === snapshotId && list.data?.results.some(item => item.key === selected.key) ? selected.key : list.data?.results[0]?.key ?? null
  const query = queryState?.snapshotId === snapshotId ? queryState.value : ''
  const detail = useRawArtifact(selectedKey)
  const grouped = useMemo(() => (list.data?.results ?? []).reduce<Record<string, SnapshotArtifactMeta[]>>((result, item) => { (result[item.category] ??= []).push(item); return result }, {}), [list.data])
  const raw = detail.data?.artifact.raw_text ?? ''
  const visibleLines = useMemo(() => {
    const lines = raw.split('\n')
    const needle = query.trim().toLocaleLowerCase()
    return needle ? lines.filter(line => line.toLocaleLowerCase().includes(needle)) : lines
  }, [query, raw])
  const copy = async () => { await navigator.clipboard.writeText(raw); setCopied(true); window.setTimeout(() => setCopied(false), 1300) }
  const download = async () => { if (!selectedKey) return; const blob = await downloadRawArtifact(selectedKey); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${selectedKey}${detail.data?.artifact.media_type === 'application/yaml' ? '.yaml' : '.json'}`; anchor.click(); URL.revokeObjectURL(url) }
  return <WorkspaceShell breadcrumbs={[{ label: 'Raw Data' }]}><div className="cc-page raw-explorer"><div className="cc-page-header"><div><TruthBadge state="live" /><h1 className="cc-page-title text-[32px] mt-3">Immutable raw data</h1><p className="text-cc-ink-500 mt-1.5">Exact stored engine inputs, validation reports and configuration—inspectable, never editable.</p></div></div>{list.isError || !list.data ? <PageUnavailable title={list.isPending ? 'Loading artifact manifest…' : 'Raw artifact manifest is unavailable'} /> : <><SnapshotBanner snapshot={list.data.snapshot} /><div className="raw-layout"><aside>{Object.entries(grouped).map(([category, items]) => <section key={category}><h2>{CATEGORY[category] ?? category}</h2>{items.map(item => <button className={selectedKey === item.key ? 'active' : ''} onClick={() => { setSelected({ snapshotId, key: item.key }); setQueryState({ snapshotId, value: '' }) }} key={item.key}><FileJson2 size={14} /><span><strong>{item.key}</strong><small>{formatBytes(item.byte_size)} · {item.sha256.slice(0, 8)}…</small></span></button>)}</section>)}</aside><main>{detail.isError || !detail.data ? <PageUnavailable title={detail.isPending ? 'Loading selected artifact…' : 'Selected artifact is unavailable'} /> : <><header className="raw-artifact-header"><div><span>{CATEGORY[detail.data.artifact.category] ?? detail.data.artifact.category}</span><h2>{detail.data.artifact.key}</h2><p>{detail.data.artifact.source_path}</p></div><div><button onClick={() => void copy()}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}</button><button onClick={() => void download()}><Download size={14} />Download exact file</button></div></header><dl className="raw-meta"><div><dt>SHA-256</dt><dd><code>{detail.data.artifact.sha256}</code></dd></div><div><dt>Size</dt><dd>{formatBytes(detail.data.artifact.byte_size)}</dd></div><div><dt>Media type</dt><dd>{detail.data.artifact.media_type}</dd></div></dl><label className="raw-search"><Search size={15} /><input value={query} onChange={event => setQueryState({ snapshotId, value: event.target.value })} placeholder="Filter raw lines…" /><span>{visibleLines.length.toLocaleString()} lines</span></label><section className="raw-structured"><h3>Structured preview</h3><StructuredPreview value={detail.data.artifact.parsed} /></section><section className="raw-source"><h3>Exact source{query ? ' · filtered lines' : ''}</h3><VirtualRawText key={`${selectedKey ?? 'none'}:${query}`} lines={visibleLines} /></section></>}</main></div></>}</div></WorkspaceShell>
}

const RAW_LINE_HEIGHT = 20
const RAW_VIEWPORT_HEIGHT = 520
const RAW_OVERSCAN = 24

function VirtualRawText({ lines }: { lines: string[] }) {
  const [scrollTop, setScrollTop] = useState(0)
  const start = Math.max(0, Math.floor(scrollTop / RAW_LINE_HEIGHT) - RAW_OVERSCAN)
  const visibleCount = Math.ceil(RAW_VIEWPORT_HEIGHT / RAW_LINE_HEIGHT) + RAW_OVERSCAN * 2
  const end = Math.min(lines.length, start + visibleCount)
  return <div className="raw-virtual" role="region" aria-label="Virtualized exact source text" tabIndex={0} onScroll={event => setScrollTop(event.currentTarget.scrollTop)}><pre style={{ height: `${Math.max(1, lines.length) * RAW_LINE_HEIGHT}px` }}>{lines.slice(start, end).map((line, index) => <code key={start + index} style={{ top: `${(start + index) * RAW_LINE_HEIGHT}px` }}><span aria-hidden="true">{start + index + 1}</span>{line || ' '}</code>)}</pre></div>
}

function StructuredPreview({ value }: { value: JsonValue }) {
  const rows = Array.isArray(value) ? value.slice(0, 100) : value && typeof value === 'object' ? Object.entries(value).slice(0, 100).map(([key, item]) => ({ key, value: item })) : [{ value }]
  return <div className="structured-preview">{rows.map((row, index) => <div key={index}><code>{JSON.stringify(row).slice(0, 600)}</code></div>)}{Array.isArray(value) && value.length > 100 ? <p>Preview capped at 100 records; the exact source and download remain complete.</p> : null}</div>
}
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB` }
