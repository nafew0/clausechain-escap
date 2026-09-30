'use client'

import { useEffect, useRef, useState } from 'react'
import { Braces, ChevronDown, Download, FileSpreadsheet, FileText, LoaderCircle } from 'lucide-react'

import { downloadFinalRoundExport } from '@/services/workspace'
import type { FinalRoundExportType, RunMode } from '@/types/workspace'

const FORMATS: { type: FinalRoundExportType; label: string; detail: string; icon: typeof FileText }[] = [
  {
    type: 'xlsx',
    label: 'Excel workbook',
    detail: "ESCAP's final-round template, filled in: Output Data, Coverage Matrix and Indicator Scores.",
    icon: FileSpreadsheet,
  },
  {
    type: 'csv',
    label: 'CSV',
    detail: 'One row per provision: the 15 template columns, then the provenance, review and score columns. UTF-8.',
    icon: FileText,
  },
  {
    type: 'json',
    label: 'JSON',
    detail: 'The same rows with a column dictionary, every indicator score and the export manifest.',
    icon: Braces,
  },
]

async function failureMessage(error: unknown) {
  // Blob responses carry the API's JSON error as a blob too.
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (data instanceof Blob) {
    try {
      const body = JSON.parse(await data.text()) as { detail?: string; type?: string }
      return body.detail ?? body.type ?? 'Export failed.'
    } catch {
      return 'Export failed.'
    }
  }
  return 'Export failed.'
}

/** Header "Export" menu: the current results of one mode in ESCAP's final-round template. */
export function FinalRoundExportMenu({ mode, disabled = false }: { mode: RunMode; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<FinalRoundExportType | null>(null)
  const [error, setError] = useState('')
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const download = async (type: FinalRoundExportType) => {
    setBusy(type)
    setError('')
    try {
      await downloadFinalRoundExport(type, mode)
      setOpen(false)
    } catch (caught) {
      setError(await failureMessage(caught))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="final-export" ref={root}>
      <button
        type="button"
        className="final-export-toggle"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        title={disabled ? `No ${mode} results to export yet` : 'Download the current results in the final-round template'}
        onClick={() => setOpen((value) => !value)}
      >
        <Download size={15} /> Export <ChevronDown size={14} />
      </button>
      {open ? (
        <div className="final-export-menu" role="menu" aria-label="Export current results">
          <header>
            <strong>Export current {mode === 'local' ? 'Local' : 'Hybrid'} results</strong>
            <span>Approved and awaiting-review provisions with every indicator score, as they stand now. Rejected findings are left out.</span>
          </header>
          {FORMATS.map(({ type, label, detail, icon: Icon }) => (
            <button type="button" role="menuitem" key={type} onClick={() => void download(type)} disabled={busy !== null}>
              {busy === type ? <LoaderCircle size={18} className="spin" /> : <Icon size={18} />}
              <span>
                <b>{label} <em>.{type}{busy === type ? ' · building…' : ''}</em></b>
                <small>{detail}</small>
              </span>
            </button>
          ))}
          {error ? <p className="final-export-error" role="alert">{error}</p> : null}
        </div>
      ) : null}
    </div>
  )
}
