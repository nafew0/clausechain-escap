'use client'
import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ExternalLink,
  FileText,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ConfidenceBar, HashBadge, TrustBadge, VerificationChainV2 } from '@/components/clausechain/ui'
import { EVIDENCE_AUDIT_CASE, JURISDICTIONS, SOURCE_STATUS_EDGES } from '@/lib/clausechain/data'
import { TruthBadge } from '@/components/clausechain/TruthState'

interface Props {
  country: string
  docId: string
}

const badgeToneClass = {
  pass: 'bg-[#ECFDF5] text-[#047857]',
  warn: 'bg-[#FFFBEB] text-[#B45309]',
  fail: 'bg-[#FEF2F2] text-[#B91C1C]',
  info: 'bg-[#EFF6FF] text-[#1D4ED8]',
}

export default function DocumentWorkspace({ country, docId }: Props) {
  const audit = EVIDENCE_AUDIT_CASE
  const j =
    JURISDICTIONS.find((x) => x.code === country.toUpperCase()) ??
    JURISDICTIONS.find((x) => x.code === audit.jurisdictionCode) ??
    JURISDICTIONS[0]

  const [reviewState, setReviewState] = useState<'ready' | 'approved' | 'rejected'>('ready')
  const [selectedCounter, setSelectedCounter] = useState(audit.counterEvidence[0]?.id ?? '')

  const selectedCounterEvidence = useMemo(
    () => audit.counterEvidence.find((item) => item.id === selectedCounter) ?? audit.counterEvidence[0],
    [audit.counterEvidence, selectedCounter]
  )

  const statusLabel = reviewState === 'approved' ? 'Human reviewed' : reviewState === 'rejected' ? 'Rejected for revision' : 'Ready for review'

  return (
    <WorkspaceShell
      breadcrumbs={[
        { label: 'Evidence Audit' },
        { label: j.name, href: `/jurisdictions/${j.code.toLowerCase()}` },
        { label: docId || audit.docId },
      ]}
    >
      <div
        className="grid gap-4 p-4 prototype-surface"
        style={{ gridTemplateColumns: 'minmax(360px, 0.96fr) minmax(340px, 0.9fr) minmax(440px, 1.05fr)', height: 'calc(100vh - 56px)', overflow: 'hidden' }}
      >
        <section className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-cc-ink-200 bg-white">
          <div className="border-b border-cc-ink-200 px-5 py-4">
            <TruthBadge state="prototype" />
            <div className="mb-2 flex items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-[#ECFDF5] px-2.5 py-1 text-[11px] font-medium text-[#047857]">
                <ShieldCheck size={12} /> Official source
              </span>
              <span className="font-mono text-[11px] rounded bg-cc-ink-100 px-2 py-1 text-cc-ink-800">{audit.citation}</span>
            </div>
            <h1 className="text-[21px] font-semibold tracking-[-0.01em] text-cc-ink-950" style={{ fontFamily: 'var(--cc-font-display)' }}>
              Source Text
            </h1>
            <p className="mt-1 text-sm text-cc-ink-500">
              {audit.title} · {audit.language} · page {audit.page}
            </p>
          </div>

          <div className="flex flex-wrap gap-2 border-b border-cc-ink-100 px-5 py-3">
            {audit.trustBadges.map((badge) => (
              <TrustBadge key={badge.label} label={badge.label} tone={badge.tone} />
            ))}
          </div>

          <div className="flex-1 overflow-y-auto bg-[#FBFBFA] px-6 py-6">
            <div className="cc-paper min-h-[660px]">
              <div className="mb-6 text-center">
                <p className="text-[12px] uppercase tracking-[0.12em] text-cc-ink-500">Republic of Singapore</p>
                <h2 className="mt-2 text-[22px] font-bold" style={{ fontFamily: 'serif' }}>
                  Personal Data Protection Act 2012
                </h2>
                <p className="mt-1 text-[13px] text-cc-ink-500">Current consolidated text · Singapore Statutes Online</p>
              </div>

              {audit.sourceParagraphs.map((paragraph, index) => {
                const highlighted = paragraph.includes(audit.highlightedSpan)
                return (
                  <p key={paragraph} className={`my-3 text-justify ${index === 0 ? 'font-bold uppercase tracking-[0.05em] text-cc-ink-700' : ''}`}>
                    {highlighted ? (
                      <>
                        {paragraph.slice(0, paragraph.indexOf(audit.highlightedSpan))}
                        <span className="cc-clause-highlight">{audit.highlightedSpan}</span>
                        {paragraph.slice(paragraph.indexOf(audit.highlightedSpan) + audit.highlightedSpan.length)}
                      </>
                    ) : (
                      paragraph
                    )}
                  </p>
                )
              })}

              <div className="absolute bottom-5 right-8 font-mono text-[11px] text-cc-ink-500">
                span {audit.charOffset} · bbox {audit.bbox}
              </div>
            </div>
          </div>
        </section>

        <section className="flex min-w-0 flex-col gap-3 overflow-y-auto">
          <div className="rounded-2xl border border-cc-ink-200 bg-white p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Extracted legal node</p>
                <h2 className="mt-1 text-[19px] font-semibold text-cc-ink-950">{audit.legalNode.title}</h2>
              </div>
              <span className="rounded-full bg-cc-teal-50 px-2.5 py-1 font-mono text-[11px] font-semibold text-cc-teal-600">
                {audit.legalNode.nodeId}
              </span>
            </div>
            <div className="rounded-xl border border-cc-ink-200 bg-cc-ink-50 p-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Rule unit</p>
              <p className="mt-2 text-sm leading-relaxed text-cc-ink-900">{audit.legalNode.ruleUnit}</p>
            </div>
          </div>

          <InfoList title="Definitions" icon={<FileText size={14} />} items={audit.legalNode.definitions} />
          <InfoList title="Conditions" icon={<CheckCircle2 size={14} />} items={audit.legalNode.conditions} />
          <InfoList title="Exceptions / Permitted paths" icon={<GitBranch size={14} />} items={audit.legalNode.exceptions} />

          <div className="rounded-2xl border border-cc-ink-200 bg-white p-5">
            <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Source graph links</p>
            <div className="flex flex-col gap-2">
              {SOURCE_STATUS_EDGES.slice(0, 3).map((edge) => (
                <div key={edge.id} className="rounded-xl border border-cc-ink-200 bg-cc-ink-50 p-3">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-mono font-semibold text-cc-ink-900">{edge.from}</span>
                    <span className="rounded bg-white px-2 py-0.5 font-mono text-[10px] text-cc-teal-600">{edge.relation}</span>
                    <span className="font-mono font-semibold text-cc-ink-900">{edge.to}</span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-cc-ink-500">{edge.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-cc-ink-200 bg-white">
          <div className="border-b border-cc-ink-200 px-5 py-4">
            <div className="mb-2 flex items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${badgeToneClass[reviewState === 'rejected' ? 'fail' : reviewState === 'approved' ? 'pass' : 'info']}`}>
                {reviewState === 'rejected' ? <X size={12} /> : <Check size={12} />} {statusLabel}
              </span>
              <HashBadge hash={audit.spanHash} />
            </div>
            <h2 className="text-[21px] font-semibold tracking-[-0.01em] text-cc-ink-950">Predicate, Mapping & Gates</h2>
            <p className="mt-1 text-sm text-cc-ink-500">Every claim must survive source, text, structure, mapping, citation, and conflict gates.</p>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-5">
            <div className="mb-5 rounded-2xl border border-cc-ink-200 bg-cc-ink-50 p-4">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Legal predicate tuple</p>
                <span className="rounded-full bg-white px-2.5 py-1 font-mono text-[11px] font-semibold text-cc-teal-600">
                  RDTII {audit.predicate.rdtiiIndicator}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Subject', audit.predicate.subject],
                  ['Action', audit.predicate.action],
                  ['Object', audit.predicate.object],
                  ['Modality', audit.predicate.modality],
                  ['Condition', audit.predicate.condition],
                  ['Exception', audit.predicate.exception],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-cc-ink-200 bg-white p-3">
                    <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">{label}</p>
                    <p className="mt-1 text-[13px] leading-snug text-cc-ink-900">{value}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3">
                <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Mapping confidence</p>
                <ConfidenceBar value={audit.predicate.confidence} />
              </div>
            </div>

            <div className="mb-5">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Eight-gate verification</p>
                <span className="text-xs font-medium text-[#B45309]">1 warning · no blocking failure</span>
              </div>
              <VerificationChainV2 gates={audit.gatesV2} />
            </div>

            <div className="mb-5 rounded-2xl border border-cc-ink-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2">
                <AlertTriangle size={15} className="text-cc-warning" />
                <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Counter-evidence</p>
              </div>
              <div className="mb-3 flex gap-2">
                {audit.counterEvidence.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setSelectedCounter(item.id)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                      selectedCounter === item.id ? 'bg-cc-teal-50 text-cc-teal-600' : 'bg-cc-ink-100 text-cc-ink-600 hover:text-cc-ink-900'
                    }`}
                  >
                    {item.sourceId}
                  </button>
                ))}
              </div>
              {selectedCounterEvidence && (
                <div className="rounded-xl border border-cc-ink-200 bg-cc-ink-50 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded bg-white px-2 py-0.5 font-mono text-[10px] text-cc-ink-700">{selectedCounterEvidence.relation}</span>
                    <span className="text-xs font-medium text-cc-ink-900">{selectedCounterEvidence.citation}</span>
                  </div>
                  <p className="text-xs leading-relaxed text-cc-ink-600">{selectedCounterEvidence.text}</p>
                  <p className="mt-2 text-xs font-medium text-cc-teal-600">{selectedCounterEvidence.resolution}</p>
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-cc-ink-200 bg-cc-ink-50 p-4">
              <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.06em] text-cc-ink-500">Reviewable citation</p>
              <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                {[
                  ['Citation', audit.citation],
                  ['Page', String(audit.page)],
                  ['Char offset', audit.charOffset],
                  ['Span hash', audit.spanHash],
                  ['Source status', audit.sourceStatus.status],
                  ['Authority rank', String(audit.sourceStatus.authorityRank)],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="font-medium text-cc-ink-500">{label}</dt>
                    <dd className="mt-0.5 break-all text-cc-ink-900">{value}</dd>
                  </div>
                ))}
              </div>
              <a
                href={audit.sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-cc-teal-600 hover:underline"
              >
                <ExternalLink size={12} /> Open canonical source
              </a>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 border-t border-cc-ink-200 bg-cc-ink-50 px-4 py-3">
            <button
              onClick={() => setReviewState('approved')}
              className="flex h-10 items-center justify-center gap-1.5 rounded-[10px] bg-cc-teal-600 text-sm font-medium text-white transition-colors hover:bg-[#0E9F92]"
            >
              <Check size={14} /> Approve
            </button>
            <button className="flex h-10 items-center justify-center gap-1.5 rounded-[10px] border border-cc-ink-300 bg-white text-sm font-medium text-cc-ink-900 transition-colors hover:bg-cc-ink-50">
              <RefreshCw size={14} /> Re-run
            </button>
            <button
              onClick={() => setReviewState('rejected')}
              className="flex h-10 items-center justify-center gap-1.5 rounded-[10px] border border-cc-danger bg-white text-sm font-medium text-cc-danger transition-colors hover:bg-cc-danger-bg"
            >
              <X size={14} /> Reject
            </button>
          </div>
        </section>
      </div>
    </WorkspaceShell>
  )
}

function InfoList({ title, icon, items }: { title: string; icon: React.ReactNode; items: string[] }) {
  return (
    <div className="rounded-2xl border border-cc-ink-200 bg-white p-5">
      <div className="mb-3 flex items-center gap-2 text-cc-ink-500">
        {icon}
        <p className="text-[11px] font-medium uppercase tracking-[0.06em]">{title}</p>
      </div>
      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <div key={item} className="rounded-xl border border-cc-ink-200 bg-cc-ink-50 px-3 py-2 text-[13px] leading-snug text-cc-ink-800">
            {item}
          </div>
        ))}
      </div>
    </div>
  )
}
