'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { forceCenter, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from 'd3-force'
import { AlertTriangle, ExternalLink, GitBranch, Network, ShieldCheck } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PageUnavailable, SnapshotBanner, TruthBadge } from '@/components/clausechain/TruthState'
import { useKnowledgeGraph, useKnowledgeSubgraph } from '@/hooks/workspace'
import type { GraphNode } from '@/types/workspace'

const LENSES = [
  ['sg-pdpa-p6-i4', 'Why SG PDPA s.26 → P6-I4?'], ['p7-i5', 'Evidence supporting P7-I5'],
  ['new-baseline', 'NEW versus ESCAP baseline'], ['cross-references', 'Cross-references & targets'],
] as const
const COLORS: Record<string, string> = { Instrument: '#1D6FB8', Section: '#0F766E', Provision: '#14B8A6', SourceArtifact: '#7C3AED', VerifiedFinding: '#D97706', Indicator: '#2563EB', Baseline: '#64748B', CitationProof: '#059669' }
type Positioned = GraphNode & SimulationNodeDatum & { x: number; y: number }

export default function KnowledgeGraph() {
  const summary = useKnowledgeGraph()
  const [lens, setLens] = useState('')
  const [economy, setEconomy] = useState('')
  const [indicator, setIndicator] = useState('')
  const [law, setLaw] = useState('')
  const [findingKey, setFindingKey] = useState('')
  const [relationship, setRelationship] = useState('')
  const graph = useKnowledgeSubgraph({
    lens: lens || undefined,
    economy: economy || undefined,
    indicator: indicator || undefined,
    law: law || undefined,
    finding_key: findingKey || undefined,
    relationship: relationship || undefined,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const layout = useForceLayout(graph.data?.nodes ?? [], graph.data?.edges ?? [])
  const selected = graph.data?.nodes.find(node => node.id === selectedId) ?? null
  const status = summary.data?.status
  return (
    <WorkspaceShell breadcrumbs={[{ label: 'Knowledge Graph' }]}>
      <div className="cc-page graph-page">
        <div className="cc-page-header"><div><TruthBadge state="readonly" label={status === 'verified' ? 'READ-ONLY · VERIFIED NEO4J SNAPSHOT' : 'READ-ONLY · NEO4J SNAPSHOT'} /><h1 className="cc-page-title text-[32px] mt-3">Legal provenance knowledge graph</h1><p className="text-cc-ink-500 mt-1.5">Neo4j mirror for audit paths and cross-references—not an unmeasured retrieval-lift claim.</p></div></div>
        {summary.isError || !summary.data ? (
          <PageUnavailable title={summary.isPending ? 'Loading Neo4j snapshot metadata…' : 'Knowledge graph metadata is unavailable'} />
        ) : (
          <>
            <SnapshotBanner snapshot={summary.data.snapshot} />
            <section className={`graph-verification ${status}`}><div>{status === 'verified' ? <ShieldCheck /> : <AlertTriangle />}<span><strong>{status === 'verified' ? 'Neo4j parity verified' : status === 'parity_failed' ? 'Neo4j parity failed' : 'Neo4j snapshot unavailable'}</strong><small>Schema {summary.data.schema_version ?? 'n/a'} · {summary.data.node_count} exported nodes · {summary.data.edge_count} relationships</small></span></div><code>{summary.data.artifact.sha256}</code>{summary.data.reason ? <p>{summary.data.reason}</p> : null}</section>
            {status === 'unavailable' ? (
              <PageUnavailable title="Neo4j was unavailable during snapshot import" detail={summary.data.reason ?? undefined} />
            ) : (
              <>
                <div className="graph-toolbar">
                  <label>Economy<select value={economy} onChange={event => setEconomy(event.target.value)}><option value="">All</option><option>Singapore</option><option>Malaysia</option><option>Australia</option></select></label>
                  <label>Indicator<input value={indicator} onChange={event => setIndicator(event.target.value)} placeholder="e.g. P6-I4" /></label>
                  <label>Instrument<input value={law} onChange={event => setLaw(event.target.value)} placeholder="Law title" /></label>
                  <label>Finding<input value={findingKey} onChange={event => setFindingKey(event.target.value)} placeholder="Finding key" /></label>
                  <label>Relationship<select value={relationship} onChange={event => setRelationship(event.target.value)}><option value="">All</option>{['HAS_SECTION','HAS_PROVISION','MAPS_TO','EVIDENCED_BY','KNOWN_AS','NEW_RELATIVE_TO','CROSS_REFERENCES','AMENDS','REPEALS','SUPERSEDES','EXCEPTION_TO','QUALIFIES'].map(value => <option key={value}>{value}</option>)}</select></label>
                  <button onClick={() => { setLens(''); setEconomy(''); setIndicator(''); setLaw(''); setFindingKey(''); setRelationship('') }}>Reset view</button>
                </div>
                <div className="graph-lenses">{LENSES.map(([key, label]) => <button className={lens === key ? 'active' : ''} onClick={() => setLens(key)} key={key}><GitBranch size={14} />{label}</button>)}</div>
                {graph.isError || !graph.data ? (
                  <PageUnavailable title={graph.isPending ? 'Resolving graph lens…' : 'The stored subgraph could not be read'} />
                ) : (
                  <div className="graph-workspace">
                    <section className="graph-canvas" aria-label="Knowledge graph visualization"><svg viewBox="0 0 900 560" role="img" aria-label={`${layout.nodes.length} nodes and ${layout.edges.length} relationships`}><g>{layout.edges.map(edge => <line key={edge.id} x1={edge.source.x} y1={edge.source.y} x2={edge.target.x} y2={edge.target.y} className={`edge edge-${edge.type.toLowerCase()}`}><title>{edge.type}</title></line>)}</g><g>{layout.nodes.map(node => <g role="button" tabIndex={0} aria-label={`${node.labels.join(', ')} ${node.id}`} onClick={() => setSelectedId(node.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setSelectedId(node.id) }} className={selectedId === node.id ? 'node selected' : 'node'} key={node.id} transform={`translate(${node.x},${node.y})`}><circle r={selectedId === node.id ? 11 : 8} fill={COLORS[node.labels[0]] ?? '#64748B'} /><text x="12" y="4">{nodeLabel(node)}</text></g>)}</g></svg><div className="graph-legend">{Object.entries(COLORS).map(([label, color]) => <span key={label}><i style={{ background: color }} />{label}</span>)}</div></section>
                    <aside className="graph-inspector">{selected ? <><span>{selected.labels.join(' · ')}</span><h2>{nodeLabel(selected)}</h2><dl>{Object.entries(selected.properties).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>{selected.properties.finding_key ? <Link href={`/match/${String(selected.properties.finding_key)}`}>Open Source Match <ExternalLink size={13} /></Link> : null}</> : <><Network size={28} /><h2>Select a node</h2><p>Inspect exact allowlisted properties and follow a finding to Source Match where available.</p></>}</aside>
                  </div>
                )}
                <section className="graph-table"><h2>Accessible node and edge table</h2><div className="ops-table-wrap"><table><thead><tr><th>Kind</th><th>ID</th><th>Label / relationship</th><th>Details</th></tr></thead><tbody>{(graph.data?.nodes ?? []).map(node => <tr key={node.id}><td>Node</td><td><code>{node.id}</code></td><td>{node.labels.join(', ')}</td><td>{nodeLabel(node)}</td></tr>)}{(graph.data?.edges ?? []).map(edge => <tr key={edge.id}><td>Edge</td><td><code>{edge.source} → {edge.target}</code></td><td>{edge.type}</td><td>{Object.entries(edge.properties).map(([key, value]) => `${key}: ${String(value)}`).join(' · ') || '—'}</td></tr>)}</tbody></table></div></section>
              </>
            )}
          </>
        )}
      </div>
    </WorkspaceShell>
  )
}

function useForceLayout(nodes: GraphNode[], edges: { id: string; source: string; target: string; type: string }[]) {
  return useMemo(() => {
    const positioned: Positioned[] = nodes.map((node, index) => ({ ...node, x: 450 + Math.cos(index * 2.399) * (80 + index % 180), y: 280 + Math.sin(index * 2.399) * (80 + index % 180) }))
    const links = edges.map(edge => ({ ...edge }))
    const simulation = forceSimulation<Positioned>(positioned).randomSource(() => 0.42).force('link', forceLink<Positioned, typeof links[number]>(links).id(node => node.id).distance(72).strength(.45)).force('charge', forceManyBody().strength(-150)).force('center', forceCenter(450, 280)).force('x', forceX(450).strength(.04)).force('y', forceY(280).strength(.04)).stop()
    for (let index = 0; index < 150; index += 1) simulation.tick()
    const byId = new Map(positioned.map(node => [node.id, node]))
    return { nodes: positioned.map(node => ({ ...node, x: Math.max(25, Math.min(875, node.x ?? 450)), y: Math.max(25, Math.min(535, node.y ?? 280)) })), edges: edges.flatMap(edge => { const source = byId.get(edge.source); const target = byId.get(edge.target); return source && target ? [{ ...edge, source, target }] : [] }) }
  }, [nodes, edges])
}
function nodeLabel(node: GraphNode) { const p = node.properties; return String(p.article_section ?? p.law_name ?? p.indicator ?? p.law ?? p.official_domain ?? node.id).slice(0, 60) }
