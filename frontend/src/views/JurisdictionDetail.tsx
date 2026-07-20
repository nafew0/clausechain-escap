'use client'
import { useState } from 'react'
import Link from 'next/link'
import { Plus, RefreshCw, ExternalLink } from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { PillarCoverageStack } from '@/components/clausechain/ui'
import { AddDocumentModal } from '@/components/clausechain/modals'
import { JURISDICTIONS, DOCUMENTS, SEED_REGISTRY, RDTII_PILLARS } from '@/lib/clausechain/data'

interface Props { country: string }

export default function JurisdictionDetail({ country }: Props) {
  const code = country.toUpperCase()
  const j = JURISDICTIONS.find((x) => x.code === code) ?? JURISDICTIONS[0]
  const docs = DOCUMENTS[j.code] ?? []
  const seeds = SEED_REGISTRY[j.code] ?? []

  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(new Set<string>())
  const [addDocOpen, setAddDocOpen] = useState(false)

  const filtered = docs.filter((d) => {
    if (filter !== 'all' && d.type !== filter) return false
    if (q && !(d.title + ' ' + d.id).toLowerCase().includes(q.toLowerCase())) return false
    return true
  })

  const toggleSelect = (id: string) => {
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) {
        n.delete(id)
      } else {
        n.add(id)
      }
      return n
    })
  }

  const SEED_STATUS_COLOR: Record<string, string> = {
    ok: 'var(--cc-success)',
    warn: 'var(--cc-warning)',
    down: 'var(--cc-danger)',
  }

  return (
    <WorkspaceShell
      breadcrumbs={[
        { label: 'Jurisdictions', href: '/jurisdictions' },
        { label: j.name },
      ]}
    >
      <div className="cc-page">
        {/* Header */}
        <div className="cc-page-header mb-8">
          <div className="flex items-center gap-4">
            <span className="text-[44px] leading-none">{j.flag}</span>
            <div>
              <h1
              className="cc-page-title leading-[1.1] text-cc-ink-950"
              style={{ fontFamily: 'var(--cc-font-display)', fontSize: 36 }}
            >
                {j.name}
              </h1>
              <p className="text-cc-ink-500 mt-1">
                {j.languages.join(' · ')} · synced {j.lastSyncRel} · {j.instruments} instruments · {j.clauses} clauses
              </p>
            </div>
          </div>
          <div className="cc-actions mt-1">
            <button className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-white border border-cc-ink-300 text-cc-ink-900 hover:bg-cc-ink-50 transition-colors">
              <RefreshCw size={14} /> Re-crawl seeds
            </button>
            <button
              onClick={() => setAddDocOpen(true)}
              className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-cc-teal-600 text-white hover:bg-[#0E9F92] transition-colors"
            >
              <Plus size={14} /> Add document
            </button>
          </div>
        </div>

        {/* Top stats row */}
        <div className="cc-three-col mb-8">
          {/* RDTII Coverage */}
          <div className="bg-white border border-cc-ink-200 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-[17px] text-cc-ink-950">RDTII coverage</h3>
              <span className="text-sm text-cc-ink-500">Pillar 6 & 7 mandatory</span>
            </div>
            <PillarCoverageStack
              items={Object.entries(j.coverage).map(([pk, stats]) => ({
                pillar: pk,
                label: RDTII_PILLARS[pk as keyof typeof RDTII_PILLARS]?.name ?? pk,
                verified: stats.verified,
                total: stats.total,
                mandatory: RDTII_PILLARS[pk as keyof typeof RDTII_PILLARS]?.mandatory ?? false,
              }))}
            />
          </div>

          {/* Status */}
          <div className="bg-white border border-cc-ink-200 rounded-2xl p-6 flex flex-col gap-4">
            <h3 className="font-semibold text-[17px] text-cc-ink-950">Status</h3>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Verified', value: j.verified, color: 'var(--cc-success)' },
                { label: 'Pending', value: j.pending, color: 'var(--cc-warning)' },
                { label: 'Rejected', value: j.rejected, color: 'var(--cc-danger)' },
                { label: 'Conflicts', value: j.conflicts, color: j.conflicts > 0 ? 'var(--cc-danger)' : 'var(--cc-ink-400)' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-cc-ink-50 rounded-xl p-3">
                  <div
                    className="font-semibold text-2xl tabular-nums mb-0.5"
                    style={{ fontFamily: 'var(--cc-font-display)', color }}
                  >
                    {value}
                  </div>
                  <div className="text-[11px] tracking-[0.04em] uppercase text-cc-ink-500">{label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Source health */}
          <div className="bg-white border border-cc-ink-200 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-[17px] text-cc-ink-950">Source health</h3>
              <span className="text-sm text-cc-ink-500">{seeds.length} seeds</span>
            </div>
            <div className="flex flex-col gap-2">
              {seeds.map((s) => (
                <div
                  key={s.url}
                  className="flex items-center gap-2 px-3 py-2 bg-cc-ink-50 border border-cc-ink-200 rounded-[10px] text-xs font-mono"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: SEED_STATUS_COLOR[s.status] ?? 'var(--cc-ink-400)' }}
                  />
                  <span className="flex-1 text-cc-ink-700 truncate">{s.url}</span>
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-cc-ink-400 hover:text-cc-ink-900">
                    <ExternalLink size={11} />
                  </a>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Documents table */}
        <div className="cc-doc-controls">
          <h2
            className="font-semibold text-[22px] leading-snug tracking-[-0.01em] text-cc-ink-950"
            style={{ fontFamily: 'var(--cc-font-display)' }}
          >
            Documents
          </h2>
          <div className="flex-1" />
          {selected.size > 0 && (
            <div className="flex items-center gap-1 px-3 py-1 bg-cc-teal-50 rounded-full text-cc-teal-600 text-sm">
              <span>{selected.size} selected</span>
              <button className="px-2 py-0.5 text-xs hover:bg-cc-teal-100 rounded-full transition-colors">Re-process</button>
              <button className="px-2 py-0.5 text-xs hover:bg-cc-teal-100 rounded-full transition-colors">Export</button>
              <button className="px-2 py-0.5 text-xs text-cc-danger hover:bg-cc-danger-bg rounded-full transition-colors">Remove</button>
            </div>
          )}
          <input
            placeholder="Search documents…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="h-8 px-3 text-[13px] border border-cc-ink-300 rounded-[10px] w-56 focus:outline-none focus:border-cc-teal-500 focus:ring-2 focus:ring-cc-teal-50 bg-white text-cc-ink-900"
          />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-8 px-2 text-[13px] border border-cc-ink-300 rounded-[10px] focus:outline-none focus:border-cc-teal-500 bg-white text-cc-ink-900"
          >
            <option value="all">All types</option>
            <option value="Act">Act</option>
            <option value="Amendment">Amendment</option>
            <option value="Regulation">Regulation</option>
            <option value="Guideline">Guideline</option>
          </select>
        </div>

        <div className="cc-table-scroll bg-white border border-cc-ink-200 rounded-2xl overflow-hidden">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-cc-ink-50 border-b border-cc-ink-200">
                <th className="w-9 px-4 py-3" />
                <th className="text-left px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500">Document</th>
                <th className="text-left px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500 w-[130px]">Type</th>
                <th className="text-left px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500 w-[110px]">Language</th>
                <th className="text-right px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500 w-[90px]">Clauses</th>
                <th className="text-right px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500 w-[90px]">Verified</th>
                <th className="text-right px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500 w-[90px]">Conflicts</th>
                <th className="text-left px-4 py-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-cc-ink-500 w-[110px]">Updated</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr
                  key={d.id}
                  className={`border-b border-cc-ink-100 hover:bg-cc-ink-50 transition-colors ${selected.has(d.id) ? 'bg-cc-teal-50' : ''}`}
                >
                  <td className="px-4 py-3.5">
                    <input
                      type="checkbox"
                      checked={selected.has(d.id)}
                      onChange={() => toggleSelect(d.id)}
                      className="accent-cc-teal-600"
                    />
                  </td>
                  <td className="px-4 py-3.5">
                    <Link
                      href={`/jurisdictions/${j.code.toLowerCase()}/documents/${d.id}`}
                      className="font-medium text-sm text-cc-ink-900 hover:text-cc-teal-600 transition-colors"
                    >
                      {d.title}
                    </Link>
                    <p className="text-xs text-cc-ink-500 font-mono mt-0.5">{d.id}</p>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className="text-xs font-medium bg-cc-ink-100 text-cc-ink-900 px-2 py-0.5 rounded">{d.type}</span>
                  </td>
                  <td className="px-4 py-3.5 text-sm text-cc-ink-700">{d.languages.join(', ')}</td>
                  <td className="px-4 py-3.5 text-sm text-right font-mono text-cc-ink-900 tabular-nums">{d.clauses}</td>
                  <td className="px-4 py-3.5 text-sm text-right font-mono tabular-nums" style={{ color: 'var(--cc-success)' }}>
                    {d.verified}
                  </td>
                  <td className="px-4 py-3.5 text-sm text-right font-mono tabular-nums" style={{ color: d.conflicts > 0 ? 'var(--cc-danger)' : 'var(--cc-ink-400)' }}>
                    {d.conflicts}
                  </td>
                  <td className="px-4 py-3.5 text-sm text-cc-ink-500">{d.updatedRel}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-sm text-cc-ink-500">
                    No documents match the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <AddDocumentModal open={addDocOpen} onClose={() => setAddDocOpen(false)} jurisdiction={j.name} />
    </WorkspaceShell>
  )
}
