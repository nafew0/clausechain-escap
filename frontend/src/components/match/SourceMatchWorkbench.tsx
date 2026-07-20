'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  FileArchive,
  FileCheck2,
  Focus,
  Link2,
  LoaderCircle,
  LockKeyhole,
  Minus,
  Plus,
  ScanSearch,
  ShieldAlert,
} from 'lucide-react'
import { LazyMotion, MotionConfig, domAnimation, m } from 'motion/react'

import { useProofAsset, useSourceMatch } from '@/hooks/workspace'
import { cn } from '@/lib/utils'
import type { EvidenceParams, JsonObject, WorkspaceQueue } from '@/types/workspace'

const FILTER_KEYS = ['economy', 'indicator', 'pillar', 'tag', 'status'] as const
const QUEUES = new Set<WorkspaceQueue>(['new', 'absence', 'recall', 'zone3', 'known'])

function display(value: unknown, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function filtersFrom(search: URLSearchParams): EvidenceParams {
  const result: EvidenceParams = {}
  for (const key of FILTER_KEYS) {
    const value = search.get(key)
    if (value) result[key] = value
  }
  const queue = search.get('queue') as WorkspaceQueue | null
  if (queue && QUEUES.has(queue)) result.queue = queue
  return result
}

function retainedQuery(search: URLSearchParams) {
  const params = new URLSearchParams()
  for (const key of [...FILTER_KEYS, 'queue'] as const) {
    const value = search.get(key)
    if (value) params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

function HighlightedContext({ context, snippet }: { context: string; snippet: string }) {
  const index = context.toLocaleLowerCase().indexOf(snippet.toLocaleLowerCase())
  if (!snippet || index < 0) return <p>{context || snippet || 'Archived source context is unavailable.'}</p>
  return (
    <p>
      {context.slice(0, index)}
      <mark>{context.slice(index, index + snippet.length)}</mark>
      {context.slice(index + snippet.length)}
    </p>
  )
}

function HashBadge({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }
  return (
    <button className="match-hash" onClick={() => void copy()} title={value}>
      {copied ? <Check size={14} /> : <Clipboard size={14} />}
      <span>SHA-256</span>
      <code>{value.slice(0, 10)}…{value.slice(-8)}</code>
    </button>
  )
}

function ProofImage({ url, alt }: { url: string; alt: string }) {
  const proof = useProofAsset(url)
  const [zoom, setZoom] = useState(1)
  const objectUrl = useMemo(
    () => proof.data ? URL.createObjectURL(proof.data) : '',
    [proof.data]
  )

  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [objectUrl])

  if (proof.isPending) return <div className="match-proof-loading"><LoaderCircle size={26} /><span>Loading authenticated proof image…</span></div>
  if (proof.isError || !objectUrl) return <div className="match-proof-error"><ShieldAlert size={24} /><strong>Proof image could not be loaded</strong><span>The archived file remains unavailable; do not approve from this view.</span></div>
  return (
    <div className="match-image-stage">
      <div className="match-zoom-controls" aria-label="Proof image zoom">
        <button onClick={() => setZoom((value) => Math.max(.7, value - .2))} aria-label="Zoom out"><Minus size={16} /></button>
        <span>{Math.round(zoom * 100)}%</span>
        <button onClick={() => setZoom((value) => Math.min(2.6, value + .2))} aria-label="Zoom in"><Plus size={16} /></button>
        <button onClick={() => setZoom(1)} aria-label="Reset zoom"><Focus size={16} /></button>
      </div>
      <div className="match-image-scroll">
        <m.img
          src={objectUrl}
          alt={alt}
          animate={{ scale: zoom }}
          transition={{ type: 'spring', stiffness: 280, damping: 30 }}
          style={{ transformOrigin: 'top center' }}
        />
      </div>
    </div>
  )
}

function sourceFact(record: JsonObject | null) {
  if (!record) return ''
  return display(record.fact_text ?? record.text ?? record.resolution_rule, '')
}

export default function SourceMatchWorkbench({ findingKey }: { findingKey: string }) {
  const search = useSearchParams()
  const filters = useMemo(() => filtersFrom(search), [search])
  const query = useSourceMatch(findingKey, filters)
  const suffix = retainedQuery(search)

  if (query.isPending) return <div className="match-page-state"><LoaderCircle size={30} /><h1>Opening source proof…</h1></div>
  if (query.isError || !query.data) return <div className="match-page-state error"><ShieldAlert size={30} /><h1>Source Match unavailable</h1><p>The evidence API could not load this finding. Return to Review and try again.</p><Link href="/review">Back to Review</Link></div>

  const data = query.data
  const row = data.row
  const exactSnippet = display(row['Verbatim Snippet'], '')
  const rawContext = display(row.raw_context, '')
  const statusRecord = data.source.status_evidence_record
  const proofMissing = data.match.mode === 'exact' && (!data.proof_asset_url || !data.proof_asset_available)
  const anchorProofMissing = data.match.mode === 'anchor' && (
    !data.source.archived_copy ||
    !data.match.anchor ||
    !rawContext ||
    !exactSnippet ||
    !rawContext.toLocaleLowerCase().includes(exactSnippet.toLocaleLowerCase())
  )
  const backHref = filters.queue ? `/review?queue=${filters.queue}` : '/review'
  const linkFor = (key: string | null) => key ? `/match/${key}${suffix}` : '#'

  return (
    <LazyMotion features={domAnimation}>
      <MotionConfig reducedMotion="user">
        <div className="match-workbench">
          <header className="match-page-header">
            <div>
              <Link href={backHref}><ArrowLeft size={16} /> Review queue</Link>
              <span className={cn('match-mode-badge', `mode-${data.match.mode}`)}>
                {data.match.mode === 'blocked' ? <LockKeyhole size={13} /> : <CheckCircle2 size={13} />}
                {data.match.label}
              </span>
              {data.source.citation_tier ? <span className="match-tier">{data.source.citation_tier}</span> : null}
            </div>
            <nav className="match-sequence" aria-label="Source Match navigation">
              <span>{data.navigation.position} of {data.navigation.total}</span>
              <Link aria-disabled={!data.navigation.previous_key} className={cn(!data.navigation.previous_key && 'disabled')} href={linkFor(data.navigation.previous_key)}><ArrowLeft size={16} /> Previous</Link>
              <Link aria-disabled={!data.navigation.next_key} className={cn(!data.navigation.next_key && 'disabled')} href={linkFor(data.navigation.next_key)}>Next <ArrowRight size={16} /></Link>
            </nav>
          </header>

          <section className="match-source-strip">
            <HashBadge value={data.source_sha256} />
            <div><span>Official source</span>{data.source.official_url ? <a href={data.source.official_url} target="_blank" rel="noreferrer">Open government source <ExternalLink size={13} /></a> : <strong>Unavailable</strong>}</div>
            <div><span>Archived copy</span><strong title={data.source.archived_copy ?? ''}><FileArchive size={13} /> {data.source.archived_copy ? data.source.archived_copy.split('/').pop() : 'Not archived'}</strong></div>
            <div><span>Accessed</span><strong>{display(data.source.access_date)}</strong></div>
            <div className="match-status"><span>Legal status</span><strong><CheckCircle2 size={13} /> {display(data.source.status)}</strong><small>{display(data.source.status_evidence)}</small></div>
          </section>

          <main className="match-columns">
            <m.article className="match-claim-card" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
              <span className="match-eyebrow">CLAUSECHAIN CLAIM</span>
              <h1>{display(row['Law Name'])}</h1>
              <div className="match-claim-meta"><span>{display(row.Economy)}</span><span>{display(row['Indicator ID'])}</span><span>{display(row['Article / Section'])}</span></div>
              <blockquote><mark>{exactSnippet || 'No affirmative evidence snippet.'}</mark></blockquote>
              <section><h2>Why it maps</h2><p>{display(row['Mapping Rationale'])}</p></section>
              <dl className="match-proof-facts">
                <div><dt>Location</dt><dd>{data.match.page_number ? `Page ${data.match.page_number}` : display(data.match.anchor)}</dd></div>
                <div><dt>Hierarchy</dt><dd>{data.match.article_path.length ? data.match.article_path.join(' › ') : display(row['Article / Section'])}</dd></div>
                <div><dt>Alignment</dt><dd>{display(data.match.alignment_status)}{data.match.alignment_score !== null ? ` · ${Math.round(data.match.alignment_score * 100)}%` : ''}</dd></div>
                <div><dt>Verified</dt><dd>{data.match.verified_at ? new Date(data.match.verified_at).toLocaleString() : 'Pending technical verification'}</dd></div>
              </dl>
              <section className="match-status-fact"><h2>Status evidence</h2><p>{sourceFact(statusRecord) || display(data.source.status_evidence)}</p>{statusRecord?.fact_url ? <a href={display(statusRecord.fact_url)} target="_blank" rel="noreferrer">Verify status fact <ExternalLink size={13} /></a> : null}</section>
            </m.article>

            <m.section className={cn('match-proof-card', `mode-${data.match.mode}`)} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}>
              <header><div><span className="match-eyebrow">ARCHIVED SOURCE PROOF</span><h2>{data.match.mode === 'exact' ? 'Government page image' : data.match.mode === 'anchor' ? 'Official HTML anchor context' : 'Technical block'}</h2></div><ScanSearch size={22} /></header>
              {data.match.mode === 'blocked' ? (
                <div className="match-block-panel"><ShieldAlert size={32} /><h3>This row cannot be verified here</h3><p>{data.block_reason}</p><span>No approval should be made until the citation proof is repaired and a new immutable snapshot is imported.</span></div>
              ) : anchorProofMissing ? (
                <div className="match-proof-error"><ShieldAlert size={24} /><strong>Archived HTML anchor proof is unavailable</strong><span>The archived source, anchor, context, and exact quote could not all be reconciled. Do not approve from this view.</span></div>
              ) : data.match.mode === 'anchor' ? (
                <div className="match-anchor-proof"><div className="match-anchor-label"><Link2 size={15} /><code>{display(data.match.anchor)}</code><span>Exact source characters</span></div><HighlightedContext context={rawContext} snippet={exactSnippet} /></div>
              ) : proofMissing ? (
                <div className="match-proof-error"><ShieldAlert size={24} /><strong>Proof PNG is missing from the archive</strong><span>The claim remains visible, but the visual proof gate is not satisfied.</span></div>
              ) : (
                <ProofImage url={data.proof_asset_url!} alt={`Highlighted official source page for ${display(row['Law Name'])} ${display(row['Article / Section'])}`} />
              )}
              <footer><FileCheck2 size={15} /><span>Quote display is sourced from the immutable consolidated evidence row. The image is the engine-rendered C6 proof asset.</span></footer>
            </m.section>
          </main>
        </div>
      </MotionConfig>
    </LazyMotion>
  )
}
