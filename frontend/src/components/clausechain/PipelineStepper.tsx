'use client'
import Link from 'next/link'
import { Check, Zap } from 'lucide-react'

const STEPS = [
  { id: 'discover',  label: 'Discovery',    href: '/pipeline/crawl' },
  { id: 'acquire',   label: 'Acquisition',  href: '/pipeline/harvest' },
  { id: 'authority', label: 'Authority',    href: '/source-status' },
  { id: 'extract',   label: 'Extraction',   href: '/pipeline/extract' },
  { id: 'structure', label: 'Structure',    href: '/pipeline/extract' },
  { id: 'retrieve',  label: 'Retrieval',    href: '/pipeline/map' },
  { id: 'predicate', label: 'Predicate',    href: '/pipeline/map' },
  { id: 'map',       label: 'Map',          href: '/pipeline/map' },
  { id: 'verify',    label: 'Verify',       href: '/pipeline/trace' },
  { id: 'audit',     label: 'Audit/Export', href: '/pipeline/export' },
]

interface PipelineStepperProps {
  activeId: string
}

export default function PipelineStepper({ activeId }: PipelineStepperProps) {
  const aliases: Record<string, string> = {
    harvest: 'acquire',
    separate: 'structure',
    convert: 'extract',
    ocr: 'extract',
    embed: 'retrieve',
    export: 'audit',
  }
  const normalizedActiveId = aliases[activeId] ?? activeId
  const activeIdx = STEPS.findIndex(s => s.id === normalizedActiveId)

  return (
    <div className="pipeline-stepper">
      <div className="stepper-run-badge">
        <Zap size={11} />
        run-SG-PDPA-001
      </div>
      <div className="stepper-track">
        {STEPS.map((step, i) => {
          const status = i < activeIdx ? 'done' : i === activeIdx ? 'active' : 'queued'
          const clickable = status === 'done' && !!step.href

          const inner = (
            <>
              <div className="ss-circle">
                {status === 'done'
                  ? <Check size={11} strokeWidth={3} />
                  : <span>{i + 1}</span>}
              </div>
              <span className="ss-label">{step.label}</span>
            </>
          )

          return (
            <span key={step.id} style={{ display: 'contents' }}>
              {clickable && step.href ? (
                <Link
                  href={step.href}
                  className={`stepper-step ss-${status} ss-clickable`}
                  style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 7 }}
                >
                  {inner}
                </Link>
              ) : (
                <div className={`stepper-step ss-${status}`}>
                  {inner}
                </div>
              )}
              {i < STEPS.length - 1 && (
                <div className={`ss-connector ${status === 'done' ? 'ss-connector-done' : ''}`} />
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}
