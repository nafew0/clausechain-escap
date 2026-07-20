'use client'
import { useState } from 'react'
import { X, Plus, Shield, Download } from 'lucide-react'
import { StatusChip, HashBadge, VerificationChain, ConfidenceBar } from './ui'
import type { Classification, MatrixCell } from '@/lib/clausechain/data'
import { RDTII_PILLARS } from '@/lib/clausechain/data'

// ─── Base Modal wrapper ───────────────────────────────────────
function ModalBase({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  wide = false,
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  children: React.ReactNode
  footer?: React.ReactNode
  wide?: boolean
}) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center p-6"
      style={{ background: 'rgba(10,10,11,0.32)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        className={`bg-white rounded-2xl shadow-2xl w-full max-h-[90vh] overflow-auto ${wide ? 'max-w-4xl' : 'max-w-2xl'}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-7 pt-6 pb-2">
          <div>
            <h2 className="text-xl font-semibold text-cc-ink-950">{title}</h2>
            {subtitle && <p className="text-sm text-cc-ink-500 mt-1">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-cc-ink-500 hover:bg-cc-ink-100 hover:text-cc-ink-900 transition-colors mt-0.5"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-7 pb-7 pt-4">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex justify-end gap-2 px-7 py-4 border-t border-cc-ink-200 bg-cc-ink-50 rounded-b-2xl">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Base Drawer wrapper ──────────────────────────────────────
function DrawerBase({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'rgba(10,10,11,0.32)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        className="w-[520px] max-w-[92vw] h-full bg-white border-l border-cc-ink-200 flex flex-col"
        style={{ animation: 'drawerIn 240ms cubic-bezier(0.4,0,0.2,1)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <style>{`@keyframes drawerIn{from{transform:translateX(40px);opacity:0}to{transform:translateX(0);opacity:1}}`}</style>
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-cc-ink-200 shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-cc-ink-950">{title}</h2>
            {subtitle && <p className="text-xs text-cc-ink-500 mt-1">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-cc-ink-500 hover:bg-cc-ink-100 transition-colors mt-0.5">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 px-6 py-3 border-t border-cc-ink-200 bg-cc-ink-50 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Btn helpers ──────────────────────────────────────────────
function BtnPrimary({ onClick, children }: { onClick?: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-cc-teal-600 text-white hover:bg-[#0E9F92] transition-colors"
    >
      {children}
    </button>
  )
}
function BtnSecondary({ onClick, children }: { onClick?: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-white text-cc-ink-900 border border-cc-ink-300 hover:bg-cc-ink-50 hover:border-cc-ink-400 transition-colors"
    >
      {children}
    </button>
  )
}

// ─── 1. Add Jurisdiction ──────────────────────────────────────
export function AddJurisdictionModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [country, setCountry] = useState('Vietnam')
  const [seedUrls, setSeedUrls] = useState(['https://moj.gov.vn', 'https://www.mic.gov.vn'])

  return (
    <ModalBase
      open={open}
      onClose={onClose}
      title="Add jurisdiction"
      subtitle="Bring a new country into the workspace and trigger initial discovery."
      footer={
        <>
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <BtnPrimary onClick={onClose}>Add jurisdiction</BtnPrimary>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Country</label>
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="w-full border border-cc-ink-300 rounded-[10px] px-3 py-2 text-sm text-cc-ink-900 bg-white focus:outline-none focus:border-cc-teal-500 focus:ring-2 focus:ring-cc-teal-50"
            >
              {['Vietnam', 'Indonesia', 'Malaysia', 'India', 'Nepal', 'Sri Lanka'].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Display name</label>
            <input
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="w-full border border-cc-ink-300 rounded-[10px] px-3 py-2 text-sm text-cc-ink-900 focus:outline-none focus:border-cc-teal-500 focus:ring-2 focus:ring-cc-teal-50"
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Source URLs</label>
          {seedUrls.map((url, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-2 px-3 py-2 bg-cc-ink-50 border border-cc-ink-200 rounded-[10px] text-sm font-mono text-cc-ink-700">
                <span className="w-2 h-2 rounded-full bg-cc-success shrink-0" />
                {url}
              </div>
              <button
                onClick={() => setSeedUrls(seedUrls.filter((_, j) => j !== i))}
                className="p-2 text-cc-ink-400 hover:text-cc-danger hover:bg-cc-danger-bg rounded-lg transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          ))}
          <button
            onClick={() => setSeedUrls([...seedUrls, ''])}
            className="self-start inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-medium bg-white border border-cc-ink-300 text-cc-ink-700 hover:bg-cc-ink-50 transition-colors mt-1"
          >
            <Plus size={12} /> Add URL
          </button>
        </div>

        <div className="flex items-start gap-2 px-3 py-2.5 bg-cc-info-bg rounded-[10px] text-sm text-[#1D4ED8]">
          <Shield size={14} className="mt-0.5 shrink-0" />
          <span>
            ClauseChain respects <code className="font-mono text-xs">robots.txt</code> and rate-limits to ≤ 2 req/s with an identifying user-agent.
          </span>
        </div>
      </div>
    </ModalBase>
  )
}

// ─── 2. Add Document ──────────────────────────────────────────
export function AddDocumentModal({
  open,
  onClose,
  jurisdiction,
}: {
  open: boolean
  onClose: () => void
  jurisdiction?: string
}) {
  const [tab, setTab] = useState<'crawl' | 'url' | 'upload'>('crawl')

  return (
    <ModalBase
      open={open}
      onClose={onClose}
      title="Add document"
      subtitle="Three ways to ingest a new regulatory instrument."
      footer={
        <>
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <BtnPrimary onClick={onClose}>Start ingestion</BtnPrimary>
        </>
      }
    >
      {/* Tabs */}
      <div className="flex gap-1 border-b border-cc-ink-200 mb-5">
        {(['crawl', 'url', 'upload'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3.5 py-2.5 text-sm font-medium border-b-2 mb-[-1px] transition-colors capitalize ${
              tab === t
                ? 'text-cc-teal-600 border-cc-teal-600'
                : 'text-cc-ink-600 border-transparent hover:text-cc-ink-900'
            }`}
          >
            {t === 'crawl' ? 'Crawl registry' : t === 'url' ? 'Direct URL' : 'Upload PDF'}
          </button>
        ))}
      </div>

      {tab === 'crawl' && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-cc-ink-600">Select from discovered documents in the seed registry for {jurisdiction ?? 'this jurisdiction'}.</p>
          {['PDPA 2019 — Primary', 'NDPC Act 2022 — Amendment', 'Data Privacy Guidelines'].map((doc) => (
            <label key={doc} className="flex items-center gap-3 px-3 py-2.5 border border-cc-ink-200 rounded-[10px] cursor-pointer hover:bg-cc-ink-50 transition-colors">
              <input type="checkbox" className="accent-cc-teal-600" />
              <span className="text-sm text-cc-ink-900">{doc}</span>
            </label>
          ))}
        </div>
      )}

      {tab === 'url' && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Document URL</label>
            <input
              placeholder="https://…"
              className="w-full border border-cc-ink-300 rounded-[10px] px-3 py-2 text-sm text-cc-ink-900 font-mono focus:outline-none focus:border-cc-teal-500 focus:ring-2 focus:ring-cc-teal-50"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Authority tier</label>
            <select className="w-full border border-cc-ink-300 rounded-[10px] px-3 py-2 text-sm text-cc-ink-900 bg-white focus:outline-none focus:border-cc-teal-500">
              <option>Primary legislation</option>
              <option>Amending instrument</option>
              <option>Regulation</option>
              <option>Guideline (non-binding)</option>
            </select>
          </div>
        </div>
      )}

      {tab === 'upload' && (
        <div className="border-2 border-dashed border-cc-ink-300 rounded-xl p-12 flex flex-col items-center gap-3 text-center">
          <Download size={28} className="text-cc-ink-300" />
          <p className="text-sm font-medium text-cc-ink-900">Drop PDF or HTML here</p>
          <p className="text-xs text-cc-ink-500">Max 50 MB · Encrypted at rest · SHA-256 anchored on ingest</p>
          <button className="mt-2 inline-flex items-center gap-2 h-9 px-4 rounded-[10px] text-sm font-medium bg-white border border-cc-ink-300 text-cc-ink-700 hover:bg-cc-ink-50 transition-colors">
            Choose file
          </button>
        </div>
      )}
    </ModalBase>
  )
}

// ─── 3. Citation Detail Drawer ────────────────────────────────
export function CitationDetailDrawer({
  open,
  onClose,
  classification,
}: {
  open: boolean
  onClose: () => void
  classification: Classification | null
}) {
  if (!classification) return null

  return (
    <DrawerBase
      open={open}
      onClose={onClose}
      title={`§${classification.sectionNumber} — ${classification.title}`}
      subtitle={`${classification.pillarLabel} · ${classification.clauseId}`}
      footer={
        <>
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
          <BtnPrimary onClick={onClose}>Re-verify</BtnPrimary>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3 flex-wrap">
          <StatusChip status={classification.status} />
          <span className="font-mono text-xs bg-cc-ink-100 text-cc-ink-900 px-2 py-0.5 rounded">
            P{classification.pillar}
          </span>
          <ConfidenceBar value={classification.confidence} />
        </div>

        {/* Verbatim span */}
        <div>
          <p className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-500 mb-2">Verbatim span</p>
          <div className="cc-verbatim">{classification.verbatimSpan}</div>
        </div>

        {/* Gates */}
        <div>
          <p className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-500 mb-2">CVR Gates</p>
          <VerificationChain gates={classification.gates} />
        </div>

        {/* Principal rule */}
        <div>
          <p className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-500 mb-2">Principal rule</p>
          <p className="text-sm text-cc-ink-900">{classification.principalRule}</p>
        </div>

        {/* Hash */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-cc-ink-500">Clause hash</span>
          <HashBadge hash={classification.hash} />
        </div>

        {/* Provenance */}
        <div className="grid grid-cols-2 gap-3 p-4 bg-cc-ink-50 border border-cc-ink-200 rounded-[10px] font-mono text-xs">
          <div>
            <dt className="text-cc-ink-500 font-medium">Source</dt>
            <dd className="text-cc-ink-900 break-all mt-0.5">{classification.provenance.sourceUrl}</dd>
          </div>
          <div>
            <dt className="text-cc-ink-500 font-medium">SHA-256</dt>
            <dd className="text-cc-ink-900 break-all mt-0.5">{classification.provenance.sha256}</dd>
          </div>
          <div>
            <dt className="text-cc-ink-500 font-medium">Retrieved</dt>
            <dd className="text-cc-ink-900 mt-0.5">{classification.provenance.retrievedAt}</dd>
          </div>
          <div>
            <dt className="text-cc-ink-500 font-medium">Instrument</dt>
            <dd className="text-cc-ink-900 mt-0.5">{classification.provenance.instrument}</dd>
          </div>
        </div>
      </div>
    </DrawerBase>
  )
}

// ─── 4. RDTII Cell Drilldown ──────────────────────────────────
interface CellDrilldownProps {
  open: boolean
  onClose: () => void
  data: { jurisdiction: { name: string; flag: string }; pillar: string; sub: string; name: string; cell: MatrixCell } | null
}

export function CellDrilldownModal({ open, onClose, data }: CellDrilldownProps) {
  if (!data) return null
  const { jurisdiction, pillar, sub, name, cell } = data
  const pillarInfo = RDTII_PILLARS[pillar as keyof typeof RDTII_PILLARS]

  return (
    <ModalBase
      open={open}
      onClose={onClose}
      title={`${sub} · ${name}`}
      subtitle={`Pillar ${pillar}: ${pillarInfo?.name} — ${jurisdiction.flag} ${jurisdiction.name}`}
      footer={<BtnSecondary onClick={onClose}>Close</BtnSecondary>}
    >
      {cell ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <StatusChip status={cell.status} />
            <span className="text-sm text-cc-ink-600">{cell.count} citation{cell.count !== 1 ? 's' : ''}</span>
            {cell.conflict && (
              <span className="text-xs font-medium text-cc-danger bg-cc-danger-bg px-2.5 py-0.5 rounded-full">
                Conflict detected
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-500">Sub-criterion definition</p>
            <p className="text-sm text-cc-ink-700">{name}</p>
          </div>

          {/* Placeholder classification rows */}
          <div className="border border-cc-ink-200 rounded-xl overflow-hidden">
            <div className="grid grid-cols-[1fr_auto_auto] gap-4 px-4 py-2 bg-cc-ink-50 border-b border-cc-ink-200 text-xs font-semibold tracking-[0.06em] uppercase text-cc-ink-500">
              <span>Document / Clause</span>
              <span>Confidence</span>
              <span>Status</span>
            </div>
            {Array.from({ length: Math.min(cell.count, 3) }).map((_, i) => (
              <div key={i} className="grid grid-cols-[1fr_auto_auto] gap-4 px-4 py-3 border-b last:border-b-0 border-cc-ink-100 items-center">
                <span className="text-sm text-cc-ink-900 font-mono">§{20 + i * 6 + 1}({i + 1})</span>
                <span className="text-sm font-mono text-cc-ink-700">{(0.78 + i * 0.06).toFixed(2)}</span>
                <StatusChip status={cell.status} />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="py-8 text-center text-sm text-cc-ink-500">No coverage for this sub-criterion.</div>
      )}
    </ModalBase>
  )
}

// ─── 5. Export ────────────────────────────────────────────────
export function ExportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [format, setFormat] = useState<'json' | 'csv' | 'pdf'>('json')

  return (
    <ModalBase
      open={open}
      onClose={onClose}
      title="Export workspace"
      subtitle="Download the RDTII classification matrix with full audit trail."
      footer={
        <>
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <BtnPrimary onClick={onClose}><Download size={14} /> Export {format.toUpperCase()}</BtnPrimary>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-500">Format</p>
          {(['json', 'csv', 'pdf'] as const).map((f) => (
            <label
              key={f}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl border cursor-pointer transition-colors ${
                format === f ? 'border-cc-teal-600 bg-cc-teal-50' : 'border-cc-ink-200 hover:bg-cc-ink-50'
              }`}
            >
              <input
                type="radio"
                name="format"
                value={f}
                checked={format === f}
                onChange={() => setFormat(f)}
                className="accent-cc-teal-600"
              />
              <div>
                <p className="text-sm font-medium text-cc-ink-900 uppercase">{f}</p>
                <p className="text-xs text-cc-ink-500">
                  {f === 'json'
                    ? 'Full structured data with hashes, gates, provenance'
                    : f === 'csv'
                    ? 'Spreadsheet-ready matrix summary'
                    : 'Human-readable audit report (UN submission format)'}
                </p>
              </div>
            </label>
          ))}
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-500">Include</p>
          {['All 3 jurisdictions', 'Mandatory pillars only (P6, P7)', 'Rejected classifications + CVR audit', 'Merkle provenance chain'].map((opt) => (
            <label key={opt} className="flex items-center gap-2 text-sm text-cc-ink-700 cursor-pointer">
              <input type="checkbox" defaultChecked className="accent-cc-teal-600" />
              {opt}
            </label>
          ))}
        </div>
      </div>
    </ModalBase>
  )
}

// ─── 6. Reject Classification ─────────────────────────────────
export function RejectModal({
  open,
  onClose,
  clauseId,
}: {
  open: boolean
  onClose: () => void
  clauseId?: string
}) {
  const [reason, setReason] = useState('')

  return (
    <ModalBase
      open={open}
      onClose={onClose}
      title="Reject classification"
      subtitle={clauseId ? `Clause ${clauseId}` : undefined}
      footer={
        <>
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <button
            onClick={onClose}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] text-sm font-medium bg-cc-danger text-white hover:opacity-90 transition-opacity"
          >
            Confirm rejection
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Rejection reason</label>
          <select className="w-full border border-cc-ink-300 rounded-[10px] px-3 py-2 text-sm bg-white text-cc-ink-900 focus:outline-none focus:border-cc-teal-500">
            <option>Span mismatch — verbatim quote not found in source</option>
            <option>NLI score below threshold (0.70)</option>
            <option>Section does not exist in current instrument version</option>
            <option>Operative predicate absent</option>
            <option>Manual analyst override</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium tracking-[0.04em] uppercase text-cc-ink-600">Analyst notes</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Optional: additional context for audit trail"
            className="w-full border border-cc-ink-300 rounded-[10px] px-3 py-2 text-sm text-cc-ink-900 resize-none focus:outline-none focus:border-cc-teal-500 focus:ring-2 focus:ring-cc-teal-50"
          />
        </div>
      </div>
    </ModalBase>
  )
}

// ─── 7. Ledger Entry ─────────────────────────────────────────
export function LedgerEntryModal({
  open,
  onClose,
  entry,
}: {
  open: boolean
  onClose: () => void
  entry: { entryNo: number | string; type: string; desc: string; ownHash: string; prevHash: string; ts: string; actor: string } | null
}) {
  if (!entry) return null
  return (
    <ModalBase
      open={open}
      onClose={onClose}
      title={`Entry ${entry.entryNo}`}
      subtitle={entry.desc}
      footer={<BtnSecondary onClick={onClose}>Close</BtnSecondary>}
    >
      <div className="grid grid-cols-2 gap-4 p-4 bg-cc-ink-50 border border-cc-ink-200 rounded-xl font-mono text-xs">
        {[
          ['Entry #', entry.entryNo],
          ['Type', entry.type],
          ['Actor', entry.actor],
          ['Timestamp', entry.ts],
          ['Own hash', entry.ownHash],
          ['Prev hash', entry.prevHash],
        ].map(([k, v]) => (
          <div key={k} className="col-span-1">
            <dt className="text-cc-ink-500 font-medium">{k}</dt>
            <dd className="text-cc-ink-900 break-all mt-0.5">{v}</dd>
          </div>
        ))}
      </div>
    </ModalBase>
  )
}
