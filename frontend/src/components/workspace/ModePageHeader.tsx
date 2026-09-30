'use client'

import type { ReactNode } from 'react'

import { PageModeTabs } from '@/components/workspace/RunModeTabs'
import type { RunMode, RunModeInfo } from '@/types/workspace'

/**
 * The top of every mode-aware workspace page: the Hybrid | Local tabs, then the
 * eyebrow chips, title and lede. Pages render this instead of their own header so
 * the tabs and the title land in the same place on every page.
 */
export function ModePageHeader({ eyebrow, title, description, actions, children, modes, onModeChange }: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  /** Extra lines under the description. */
  children?: ReactNode
  /** Mode labels and model names from the API; without them the tabs show plain labels. */
  modes?: RunModeInfo[]
  onModeChange?: (mode: RunMode) => void
}) {
  return (
    <div className="mode-page-top">
      <PageModeTabs modes={modes} onChange={onModeChange} />
      <div className="cc-page-header">
        <div>
          {eyebrow ? <div className="truth-chiprow">{eyebrow}</div> : null}
          <h1 className="cc-page-title text-[32px] mt-3">{title}</h1>
          {description ? <p className="text-cc-ink-500 mt-1.5">{description}</p> : null}
          {children}
        </div>
        {actions ? <div className="cc-actions">{actions}</div> : null}
      </div>
    </div>
  )
}
