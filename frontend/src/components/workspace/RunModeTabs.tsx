'use client'

import { Fragment, useCallback, useEffect, useState, type ReactNode } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { Cloud, Server } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { RunMode, RunModeInfo } from '@/types/workspace'

const MODE_ICON = { hybrid: Cloud, local: Server } as const

/** Fired after a same-page mode switch so the sidebar links follow it. */
const MODE_EVENT = 'clausechain:run-mode'

const FALLBACK_MODES: RunModeInfo[] = [
  { id: 'hybrid', label: 'Hybrid', models: '' },
  { id: 'local', label: 'Local', models: '' },
]

/** The run mode lives in the URL (?mode=local) so a tab is linkable and survives reloads. */
export function useRunMode(): [RunMode, (mode: RunMode) => void] {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const mode: RunMode = searchParams.get('mode') === 'local' ? 'local' : 'hybrid'
  const setMode = useCallback((next: RunMode) => {
    const params = new URLSearchParams(searchParams.toString())
    if (next === 'hybrid') params.delete('mode')
    else params.set('mode', next)
    const query = params.toString()
    // Same-page searchParams update: the History API integrates with
    // useSearchParams; router.replace no-ops for query-only changes in prod builds.
    window.history.replaceState(null, '', query ? `${pathname}?${query}` : pathname)
    window.dispatchEvent(new Event(MODE_EVENT))
  }, [pathname, searchParams])
  return [mode, setMode]
}

/**
 * The mode for components outside a Suspense boundary (the sidebar): read from
 * the URL after mount and on every switch, so no page needs useSearchParams.
 */
export function useUrlMode(): RunMode {
  const [mode, setMode] = useState<RunMode>('hybrid')
  useEffect(() => {
    const read = () => setMode(new URLSearchParams(window.location.search).get('mode') === 'local' ? 'local' : 'hybrid')
    read()
    window.addEventListener('popstate', read)
    window.addEventListener(MODE_EVENT, read)
    return () => {
      window.removeEventListener('popstate', read)
      window.removeEventListener(MODE_EVENT, read)
    }
  }, [])
  return mode
}

export { withMode } from '@/lib/runMode'

/**
 * The same page for either workspace. Keyed by mode, so switching tabs remounts
 * it: every query refetches from the other workspace and no state carries over.
 */
export function ModeRoute({ children }: { children: ReactNode }) {
  const [mode] = useRunMode()
  return <Fragment key={mode}>{children}</Fragment>
}

/** The Hybrid | Local tab bar at the top of a mode-aware page. */
export function PageModeTabs({ modes, onChange }: { modes?: RunModeInfo[]; onChange?: (mode: RunMode) => void }) {
  const [mode, setMode] = useRunMode()
  return (
    <div className="page-mode-tabs">
      <RunModeTabs mode={mode} onChange={(next) => { onChange?.(next); setMode(next) }} modes={modes} />
    </div>
  )
}

export function LocalChip({ label = 'Local · open weights' }: { label?: string }) {
  return <span className="z3-local-chip"><Server size={13} /> {label}</span>
}

export function RunModeTabs({ mode, onChange, modes }: {
  mode: RunMode
  onChange: (mode: RunMode) => void
  modes?: RunModeInfo[]
}) {
  const options = modes?.length ? modes : FALLBACK_MODES
  const active = options.find((option) => option.id === mode)
  return (
    <div className="run-mode-bar">
      <div className="run-mode-tabs" role="tablist" aria-label="Model backend">
        {options.map((option) => {
          const Icon = MODE_ICON[option.id]
          return (
            <button
              key={option.id}
              type="button"
              role="tab"
              aria-selected={mode === option.id}
              className={cn(mode === option.id && 'active')}
              onClick={() => onChange(option.id)}
            >
              <Icon size={14} />
              <span>{option.label}</span>
              <small>{option.id === 'hybrid' ? 'cloud' : 'open weights'}</small>
            </button>
          )
        })}
      </div>
      {active?.models ? <p className="run-mode-models">{active.models}</p> : null}
    </div>
  )
}
