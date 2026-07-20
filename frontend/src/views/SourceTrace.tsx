'use client'
import { useState, useRef, useEffect } from 'react'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import PipelineStepper from '@/components/clausechain/PipelineStepper'
import { TRACE_HIGHLIGHTS, TraceHighlight } from '@/lib/clausechain/data'
import { TruthBadge } from '@/components/clausechain/TruthState'

// ── Segment types ────────────────────────────────────────────
interface Seg    { text: string; highlightId?: string }
interface SrcSeg { text: string; style?: 'heading' | 'sub' | 'part' | 'secnum'; highlightId?: string }

// ── Extracted-text segments (left panel) ─────────────────────
const EXTRACTED_SEGMENTS: Seg[] = [
  { text: 'DIGITAL SECURITY ACT, 2018\n\nGovernment of Bangladesh · Act No. 46 of 2018\n\n' },
  { text: "Part I — Preliminary\n\n§2 — Definitions\n\nIn this Act, unless the context otherwise requires: ‘personal data’ means any information relating to an identified or identifiable natural person; ‘digital security’ means protective measures for digital infrastructure.\n\n" },
  { text: '§3(1) — Agency mandate\n\n',                                                                                   highlightId: 'th-006' },
  { text: 'The Digital Security Agency shall be responsible for the protection of critical digital infrastructure and national security against digital threats and cyberattacks.',                                                                                                                                                                           highlightId: 'th-006' },
  { text: '\n\nPart II — Personal Data Obligations\n\n§12(3) — Lawful basis\n\n',                                         highlightId: 'th-002' },
  { text: 'No person shall process personal data without the explicit consent of the data subject, except as provided under sections 14, 15 and 18 of this Act.',                                                                                                                                                                                           highlightId: 'th-002' },
  { text: '\n\n§14(1) — Purpose limitation\n\n',                                                                          highlightId: 'th-003' },
  { text: 'Data collected for a specific purpose shall not be used for any other purpose without the express consent of the data subject, unless required by law.',                                                                                                                                                                                         highlightId: 'th-003' },
  { text: '\n\n§21(1) — Data subject rights\n\n',                                                                         highlightId: 'th-004' },
  { text: 'A data subject shall have the right to obtain confirmation of whether personal data concerning them is being processed, and where that is the case, access to that data.',                                                                                                                                                                       highlightId: 'th-004' },
  { text: '\n\nPart V — Crimes and Punishments\n\n§26(1) — Data localization\n\n',                                        highlightId: 'th-001' },
  { text: "Any person who, intentionally or knowingly without lawful authority, collects, sells, takes possession of, supplies or uses any person's identity-related information, shall not save such data, including biometric information, photographs, financial records or registry information, outside the geographic boundaries of Bangladesh.",         highlightId: 'th-001' },
  { text: '\n\n§29(1) — Conditional transfer\n\n',                                                                        highlightId: 'th-008' },
  { text: 'Cross-border transfer of personal data may be permitted subject to the prior approval of the competent authority and the existence of adequate safeguards.',                                                                                                                                                                                     highlightId: 'th-008' },
  { text: '\n\n§33(2) — Hacking offences\n\n',                                                                            highlightId: 'th-007' },
  { text: 'Any person who commits hacking or any illegal access to a computer system with intent to commit another offence under this Act shall be punished accordingly.',                                                                                                                                                                                  highlightId: 'th-007' },
  { text: '\n\n§35(1) — Breach notification\n\n',                                                                         highlightId: 'th-005' },
  { text: 'The controller shall notify the supervisory authority of a personal data breach without undue delay and, where feasible, not later than seventy-two hours after having become aware of it.',                                                                                                                                                     highlightId: 'th-005' },
  { text: '\n\n[End of mapped clauses — remaining sections pending classification]\n' },
]

// ── Source-document segments (right panel) ────────────────────
const SOURCE_SEGMENTS: SrcSeg[] = [
  { text: 'DIGITAL SECURITY ACT, 2018',                                   style: 'heading' },
  { text: "Government of the People's Republic of Bangladesh",            style: 'sub' },
  { text: '\nPart I — Preliminary\n',                                     style: 'part' },
  { text: "Section 2. Definitions. — In this Act, unless the context otherwise requires, the following expressions shall have the meanings hereinafter assigned to them…\n\n" },
  { text: 'Section 3.',  style: 'secnum' }, { text: ' (1) ', style: 'secnum' },
  { text: 'The Digital Security Agency shall be responsible for the protection of critical digital infrastructure and national security against digital threats and cyberattacks.',                                                                                                                                                                           highlightId: 'th-006' },
  { text: '\n\nPart II — Personal Data Obligations\n',                    style: 'part' },
  { text: 'Section 12.', style: 'secnum' }, { text: ' (3) ' },
  { text: 'No person shall process personal data without the explicit consent of the data subject, except as provided under sections 14, 15 and 18 of this Act.',                                                                                                                                                                                           highlightId: 'th-002' },
  { text: '\nSection 14.', style: 'secnum' }, { text: ' (1) ' },
  { text: 'Data collected for a specific purpose shall not be used for any other purpose without the express consent of the data subject, unless required by law.',                                                                                                                                                                                         highlightId: 'th-003' },
  { text: '\nSection 21.', style: 'secnum' }, { text: ' (1) ' },
  { text: 'A data subject shall have the right to obtain confirmation of whether personal data concerning them is being processed, and where that is the case, access to that data.',                                                                                                                                                                       highlightId: 'th-004' },
  { text: '\n\nPart V — Crimes and Punishments\n',                        style: 'part' },
  { text: 'Section 26.', style: 'secnum' }, { text: ' (1) ' },
  { text: "Any person who, intentionally or knowingly without lawful authority, collects, sells, takes possession of, supplies or uses any person's identity-related information, shall not save such data, including biometric information, photographs, financial records or registry information, outside the geographic boundaries of Bangladesh.",         highlightId: 'th-001' },
  { text: '\nSection 29.', style: 'secnum' }, { text: ' (1) ' },
  { text: 'Cross-border transfer of personal data may be permitted subject to the prior approval of the competent authority and the existence of adequate safeguards.',                                                                                                                                                                                     highlightId: 'th-008' },
  { text: '\nSection 33.', style: 'secnum' }, { text: ' (2) ' },
  { text: 'Any person who commits hacking or any illegal access to a computer system with intent to commit another offence under this Act shall be punished accordingly.',                                                                                                                                                                                  highlightId: 'th-007' },
  { text: '\nSection 35.', style: 'secnum' }, { text: ' (1) ' },
  { text: 'The controller shall notify the supervisory authority of a personal data breach without undue delay and, where feasible, not later than seventy-two hours after having become aware of it.',                                                                                                                                                     highlightId: 'th-005' },
]

// ── Span popover ──────────────────────────────────────────────
function SpanPopover({ highlight: h, onClose }: { highlight: TraceHighlight; onClose: () => void }) {
  const GATE_NAMES = ['Span Match', 'NLI Entailment', 'Struct. Plausibility']
  const GATE_VALS =
    h.confidence > 0.9 ? ['exact', '0.94', 'pass']
    : h.confidence > 0.7 ? ['exact', h.confidence.toFixed(2), 'pass']
    : ['fuzzy·2', h.confidence.toFixed(2), 'pass']

  return (
    <span
      className="span-popover"
      style={{ top: '120%', left: 0, zIndex: 30 }}
      onClick={e => e.stopPropagation()}
    >
      {/* Header */}
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ width: 10, height: 10, borderRadius: 2, background: h.color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--cc-ink-950)' }}>
          {h.pillar} — {h.textLabel}
        </span>
        <button
          style={{ marginLeft: 'auto', width: 24, height: 24, border: 'none', background: 'none', cursor: 'pointer', color: 'var(--cc-ink-500)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}
          onClick={onClose}
        >
          ✕
        </button>
      </span>

      {/* Verbatim snippet */}
      <span style={{ display: 'block', fontSize: 11, color: 'var(--cc-ink-600)', background: 'var(--cc-ink-50)', padding: '6px 8px', borderRadius: 6, marginBottom: 10, fontFamily: 'var(--cc-font-mono)', lineHeight: 1.6 }}>
        {h.extractedText.slice(0, 120)}…
      </span>

      {/* CVR gates */}
      <span style={{ display: 'block', marginBottom: 8 }}>
        {GATE_NAMES.map((name, i) => (
          <span key={i} className="mini-gate">
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981', flexShrink: 0 }} />
            <span style={{ flex: 1, color: 'var(--cc-ink-700)', fontSize: 11 }}>Gate {i + 1} · {name}</span>
            <span style={{ fontSize: 11, color: 'var(--cc-ink-900)', fontWeight: 600, fontFamily: 'var(--cc-font-mono)' }}>{GATE_VALS[i]}</span>
          </span>
        ))}
      </span>

      {/* Metadata grid */}
      <span style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 11 }}>
        {[
          { label: 'Reference',  value: h.ref,                    color: undefined },
          { label: 'Confidence', value: String(h.confidence),     color: h.confidence > 0.8 ? '#10B981' : '#F59E0B' },
          { label: 'Page',       value: String(h.page),           color: undefined },
          { label: 'Match type', value: h.matchType,              color: undefined },
        ].map(item => (
          <span key={item.label} style={{ display: 'block' }}>
            <span style={{ display: 'block', color: 'var(--cc-ink-500)', marginBottom: 2 }}>{item.label}</span>
            <span style={{ display: 'block', fontFamily: 'var(--cc-font-mono)', color: item.color ?? 'var(--cc-ink-900)', fontWeight: 600 }}>{item.value}</span>
          </span>
        ))}
      </span>
    </span>
  )
}

// ── Main component ────────────────────────────────────────────
export default function SourceTrace() {
  const [activeSpan,   setActiveSpan]   = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [showPopover,  setShowPopover]  = useState<string | null>(null)
  const leftRef  = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)

  // Synchronized scroll — both panels jump to the active span
  useEffect(() => {
    if (!activeSpan) return
    ;[leftRef, rightRef].forEach(ref => {
      if (!ref.current) return
      const el = ref.current.querySelector(`[data-span="${activeSpan}"]`)
      if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }, [activeSpan])

  const filtered   = TRACE_HIGHLIGHTS.filter(h => !activeFilter || h.pillar === activeFilter)
  const isVisible  = (id: string) => filtered.some(h => h.id === id)
  const getH       = (id: string) => TRACE_HIGHLIGHTS.find(h => h.id === id)

  const handleSpanClick = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (activeSpan === id) { setActiveSpan(null); setShowPopover(null) }
    else                   { setActiveSpan(id);   setShowPopover(id)   }
  }

  const coverage = {
    total:    TRACE_HIGHLIGHTS.length,
    verified: TRACE_HIGHLIGHTS.filter(h => h.status === 'verified').length,
    pending:  TRACE_HIGHLIGHTS.filter(h => h.status === 'pending').length,
    fuzzy:    TRACE_HIGHLIGHTS.filter(h => h.matchType === 'fuzzy').length,
  }
  const pillars = Array.from(new Set(TRACE_HIGHLIGHTS.map(h => h.pillar)))

  // helper: background for a span
  const spanBg = (h: TraceHighlight, alpha: string) =>
    h.status === 'pending'
      ? `repeating-linear-gradient(45deg,${h.color}20 0,${h.color}20 3px,transparent 3px,transparent 6px)`
      : h.color + alpha

  return (
    <WorkspaceShell breadcrumbs={[{ label: 'Pipeline' }, { label: 'Source Trace' }]}>
      <PipelineStepper activeId="verify" />

      <div
        className="cc-page cc-pipeline-page prototype-surface"
        onClick={() => { setShowPopover(null); setActiveSpan(null) }}
      >
        {/* ── Page header ── */}
        <div className="cc-page-header" style={{ alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <TruthBadge state="prototype" />
            <h1 style={{ fontFamily: 'var(--cc-font-display)', fontWeight: 700, fontSize: 22, color: 'var(--cc-ink-950)', margin: 0 }}>
              Source Trace
            </h1>
            <div style={{ fontSize: 13, color: 'var(--cc-ink-500)', marginTop: 4 }}>
              Digital Security Act 2018 ·{' '}
              <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 12 }}>BD-DSA-2018</span>
              {' '}· {coverage.verified} verified · {coverage.pending} pending · {coverage.fuzzy} fuzzy-matched
            </div>
          </div>
          <div className="cc-actions">
            <button style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 14px', height: 36, borderRadius: 10, fontSize: 13, fontWeight: 500, border: '1px solid var(--cc-ink-300)', background: 'white', color: 'var(--cc-ink-800)', cursor: 'pointer' }}>
              Export trace
            </button>
            <button style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 14px', height: 36, borderRadius: 10, fontSize: 13, fontWeight: 500, border: '1px solid var(--cc-ink-300)', background: 'white', color: 'var(--cc-ink-800)', cursor: 'pointer' }}>
              Open in audit view →
            </button>
          </div>
        </div>

        {/* ── Coverage summary bar ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', background: 'white', border: '1px solid var(--cc-ink-200)', borderRadius: 10, marginBottom: 14, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--cc-ink-700)' }}>
            {coverage.total} clauses mapped across {pillars.length} indicators
          </div>
          <div style={{ flex: '1 1 180px', height: 6, background: 'var(--cc-ink-200)', borderRadius: 999, overflow: 'hidden', margin: '0 8px' }}>
            <div style={{ display: 'flex', height: '100%' }}>
              <div style={{ width: `${(coverage.verified / coverage.total) * 100}%`, background: '#10B981', transition: 'width 400ms ease' }} />
              <div style={{ width: `${(coverage.pending  / coverage.total) * 100}%`, background: '#F59E0B', transition: 'width 400ms ease' }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 12, flexWrap: 'wrap' }}>
            {[{ c: '#10B981', l: 'Verified' }, { c: '#F59E0B', l: 'Pending' }, { c: 'var(--cc-ink-400)', l: 'Fuzzy' }].map(x => (
              <span key={x.l} style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--cc-ink-600)' }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: x.c }} />
                {x.l}
              </span>
            ))}
          </div>
        </div>

        {/* ── Pillar filter bar ── */}
        <div className="legend-bar" style={{ marginBottom: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--cc-ink-500)', marginRight: 4 }}>Filter by indicator:</span>
          <button
            className={`legend-item${!activeFilter ? ' active' : ''}`}
            style={{ background: 'var(--cc-ink-100)', color: 'var(--cc-ink-700)', borderColor: !activeFilter ? 'var(--cc-ink-500)' : 'transparent' }}
            onClick={e => { e.stopPropagation(); setActiveFilter(null) }}
          >
            All <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11, marginLeft: 4 }}>{TRACE_HIGHLIGHTS.length}</span>
          </button>
          {TRACE_HIGHLIGHTS.map(h => (
            <button
              key={h.id}
              className={`legend-item${activeFilter === h.pillar ? ' active' : ''}`}
              style={{ background: h.color + '20', color: h.color, borderColor: activeFilter === h.pillar ? h.color : 'transparent' }}
              onClick={e => { e.stopPropagation(); setActiveFilter(activeFilter === h.pillar ? null : h.pillar) }}
            >
              <span className="legend-dot" style={{ background: h.color }} />
              {h.pillar} · {h.textLabel}
            </button>
          ))}
        </div>

        {/* ── Status pattern legend ── */}
        <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--cc-ink-500)', marginBottom: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 20, height: 10, background: 'rgba(15,181,167,0.25)', border: '1.5px solid #0FB5A7', borderRadius: 2, display: 'inline-block' }} />
            Solid fill = verified
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 20, height: 10, background: 'repeating-linear-gradient(45deg,rgba(245,158,11,0.2) 0,rgba(245,158,11,0.2) 3px,transparent 3px,transparent 6px)', border: '1.5px dashed #F59E0B', borderRadius: 2, display: 'inline-block' }} />
            Hatched = pending
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 20, height: 10, background: 'repeating-linear-gradient(135deg,rgba(107,114,128,0.2) 0,rgba(107,114,128,0.2) 3px,transparent 3px,transparent 6px)', border: '1.5px dashed var(--cc-ink-400)', borderRadius: 2, display: 'inline-block' }} />
            Striped = fuzzy OCR match
          </span>
        </div>

        {/* ── Dual panels ── */}
        <div className="trace-layout" onClick={e => e.stopPropagation()}>

          {/* Left — extracted text */}
          <div className="trace-panel" ref={leftRef}>
            <div className="trace-panel-header">
              Extracted text (Crawl4AI + Docling)
            </div>
            <div className="trace-text-body">
              {EXTRACTED_SEGMENTS.map((seg, i) => {
                if (!seg.highlightId) {
                  return (
                    <span key={i} style={{ color: seg.text.startsWith('\n') ? 'var(--cc-ink-500)' : 'inherit', whiteSpace: 'pre-wrap' }}>
                      {seg.text}
                    </span>
                  )
                }
                const h = getH(seg.highlightId)
                if (!h) return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{seg.text}</span>
                if (!isVisible(seg.highlightId)) {
                  return <span key={i} style={{ color: 'var(--cc-ink-500)', opacity: 0.5, whiteSpace: 'pre-wrap' }}>{seg.text}</span>
                }

                return (
                  <span
                    key={i}
                    className={`trace-span${activeSpan === seg.highlightId ? ' active' : ''}`}
                    data-span={seg.highlightId}
                    style={{
                      background:    spanBg(h, '25'),
                      borderBottom:  `2px solid ${h.color}`,
                      color:         'inherit',
                      position:      'relative',
                      cursor:        'pointer',
                      whiteSpace:    'pre-wrap',
                    }}
                    onClick={e => handleSpanClick(seg.highlightId!, e)}
                  >
                    {seg.text}
                    {showPopover === seg.highlightId && (
                      <SpanPopover
                        highlight={h}
                        onClose={() => { setShowPopover(null); setActiveSpan(null) }}
                      />
                    )}
                  </span>
                )
              })}
            </div>
          </div>

          {/* Divider */}
          <div className="trace-panel-divider" />

          {/* Right — source document */}
          <div className="trace-panel" ref={rightRef}>
            <div className="trace-panel-header">
              Source document (official text)
              <span style={{ marginLeft: 'auto', fontFamily: 'var(--cc-font-mono)', fontSize: 10, fontWeight: 400, letterSpacing: 0, textTransform: 'none', color: 'var(--cc-ink-400)' }}>
                bdlaws.minlaw.gov.bd
              </span>
            </div>
            <div className="trace-source-body">
              {SOURCE_SEGMENTS.map((seg, i) => {
                if (seg.style === 'heading') return <h2 key={i} style={{ textAlign: 'center', fontSize: 16, margin: '0 0 4px', fontFamily: 'var(--cc-font-display)' }}>{seg.text}</h2>
                if (seg.style === 'sub')     return <p  key={i} style={{ textAlign: 'center', fontSize: 13, color: 'var(--cc-ink-500)', margin: '0 0 20px' }}>{seg.text}</p>
                if (seg.style === 'part')    return <div key={i} style={{ fontWeight: 700, fontSize: 14, margin: '16px 0 8px', whiteSpace: 'pre-wrap' }}>{seg.text}</div>
                if (seg.style === 'secnum')  return <strong key={i}>{seg.text}</strong>
                if (!seg.highlightId)        return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{seg.text}</span>

                const h = getH(seg.highlightId)
                if (!h) return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{seg.text}</span>
                if (!isVisible(seg.highlightId)) {
                  return <span key={i} style={{ opacity: 0.4, whiteSpace: 'pre-wrap' }}>{seg.text}</span>
                }

                const isFuzzy = h.matchType === 'fuzzy'
                return (
                  <span
                    key={i}
                    data-span={seg.highlightId}
                    className={`trace-bbox${isFuzzy ? ' fuzzy' : ''}${activeSpan === seg.highlightId ? ' active' : ''}`}
                    style={{
                      background:   spanBg(h, '28'),
                      borderBottom: `2px solid ${h.color}`,
                      color:        'inherit',
                      cursor:       'pointer',
                      whiteSpace:   'pre-wrap',
                    }}
                    onClick={e => {
                      e.stopPropagation()
                      setActiveSpan(activeSpan === seg.highlightId ? null : seg.highlightId!)
                      setShowPopover(null)
                    }}
                  >
                    {seg.text}
                  </span>
                )
              })}
            </div>
          </div>
        </div>

        {/* ── Active span detail bar ── */}
        {activeSpan && (() => {
          const h = getH(activeSpan)
          if (!h) return null
          return (
            <div style={{
              marginTop:     14,
              padding:       '14px 20px',
              background:    'white',
              border:        `1px solid ${h.color}60`,
              borderRadius:  12,
              display:       'flex',
              alignItems:    'center',
              gap:           16,
            }}>
              <span style={{ width: 12, height: 12, borderRadius: 3, background: h.color, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--cc-ink-900)' }}>
                  {h.pillar} — {h.textLabel} ·{' '}
                  <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 12 }}>{h.ref}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--cc-ink-600)', marginTop: 2 }}>
                  Page {h.page} · confidence{' '}
                  <span style={{ fontFamily: 'var(--cc-font-mono)', fontWeight: 700, color: h.confidence > 0.8 ? '#10B981' : '#F59E0B' }}>
                    {h.confidence}
                  </span>
                  {' '}· match:{' '}
                  <span style={{ fontFamily: 'var(--cc-font-mono)' }}>{h.matchType}</span>
                  {h.matchType === 'fuzzy' && (
                    <span style={{ color: '#F59E0B', marginLeft: 4 }}>⚠ OCR approximate — bbox may sit slightly off source</span>
                  )}
                </div>
              </div>

              <div style={{ flex: 1 }} />

              <span style={{
                display:        'inline-flex',
                alignItems:     'center',
                gap:            4,
                fontSize:       11,
                fontWeight:     600,
                padding:        '2px 8px',
                borderRadius:   999,
                background:     h.status === 'verified' ? '#ECFDF5' : '#FFFBEB',
                color:          h.status === 'verified' ? '#047857' : '#B45309',
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
                {h.status}
              </span>

              <button style={{
                display:      'flex',
                alignItems:   'center',
                gap:          6,
                padding:      '5px 12px',
                borderRadius: 8,
                border:       '1px solid var(--cc-ink-300)',
                background:   'white',
                fontSize:     12,
                fontWeight:   500,
                color:        'var(--cc-ink-800)',
                cursor:       'pointer',
              }}>
                Open audit card →
              </button>

              <button
                onClick={() => { setActiveSpan(null); setShowPopover(null) }}
                style={{
                  width:          28,
                  height:         28,
                  borderRadius:   6,
                  border:         '1px solid var(--cc-ink-200)',
                  background:     'white',
                  cursor:         'pointer',
                  display:        'flex',
                  alignItems:     'center',
                  justifyContent: 'center',
                  fontSize:       14,
                  color:          'var(--cc-ink-500)',
                }}
              >
                ✕
              </button>
            </div>
          )
        })()}
      </div>
    </WorkspaceShell>
  )
}
