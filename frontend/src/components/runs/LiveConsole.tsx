'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ChevronRight, TerminalSquare } from 'lucide-react'

import { getEngineActionEvents } from '@/services/workspace'
import type { EngineActionEvent } from '@/types/workspace'
import { cn } from '@/lib/utils'

type Filter = 'all' | 'pipeline' | 'llm' | 'problems'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Everything' },
  { id: 'pipeline', label: 'Pipeline steps' },
  { id: 'llm', label: 'Model calls' },
  { id: 'problems', label: 'Rejections & warnings' },
]

const POLL_MS = 1500

function matches(event: EngineActionEvent, filter: Filter) {
  if (filter === 'llm') return event.stage === 'llm'
  if (filter === 'pipeline') return event.stage !== 'llm'
  if (filter === 'problems') return event.level !== 'info' || event.stage === 'gate' || event.stage === 'recall'
  return true
}

/** Live run console: polls the action's events while it runs, keeps the full history after. */
export function LiveConsole({ actionId, live }: { actionId: string; live: boolean }) {
  const [events, setEvents] = useState<EngineActionEvent[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [openSeq, setOpenSeq] = useState<number | null>(null)
  const [follow, setFollow] = useState(true)
  const lastSeq = useRef(0)
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const page = await getEngineActionEvents(actionId, lastSeq.current)
        if (cancelled) return
        if (page.events.length) {
          lastSeq.current = page.last_seq
          setEvents((current) => [...current, ...page.events])
        }
        const stillRunning = page.status === 'queued' || page.status === 'running'
        if (page.more || stillRunning) timer = setTimeout(poll, page.more ? 0 : POLL_MS)
      } catch {
        if (!cancelled && live) timer = setTimeout(poll, POLL_MS * 2)
      }
    }
    void poll()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [actionId, live])

  const visible = useMemo(() => events.filter((event) => matches(event, filter)), [events, filter])

  useEffect(() => {
    if (follow && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
  }, [visible, follow])

  const summary = useMemo(() => {
    const indicator = [...events].reverse().find((event) => event.stage === 'indicator')
    return {
      indicator: indicator ? `${indicator.label} ${indicator.message}` : null,
      calls: events.filter((event) => event.stage === 'llm' && event.message.startsWith('←')).length,
      findings: events.filter((event) => event.stage === 'finding').length,
      rejected: events.filter((event) => event.stage === 'gate').length,
      done: events.find((event) => event.stage === 'done')?.message ?? null,
    }
  }, [events])

  return (
    <section className="live-console">
      <header>
        <span><TerminalSquare size={13} /> {live ? 'Live run log' : 'Run log'}</span>
        <em>{summary.done ?? summary.indicator ?? (live ? 'waiting for the first step…' : 'no events recorded')}</em>
        <small>{summary.calls} model calls · {summary.findings} findings · {summary.rejected} rejected</small>
      </header>
      <nav>
        {FILTERS.map((option) => (
          <button key={option.id} type="button" className={cn(filter === option.id && 'active')} onClick={() => setFilter(option.id)}>{option.label}</button>
        ))}
      </nav>
      <div
        className="live-console-lines"
        ref={scroller}
        onScroll={(event) => {
          const box = event.currentTarget
          setFollow(box.scrollHeight - box.scrollTop - box.clientHeight < 40)
        }}
      >
        {visible.map((event) => (
          <div key={event.seq} className={cn('live-line', `lvl-${event.level}`, `stage-${event.stage}`)}>
            <button type="button" onClick={() => setOpenSeq(openSeq === event.seq ? null : event.seq)} disabled={!event.detail}>
              <time>{new Date(event.ts).toLocaleTimeString()}</time>
              <b>{event.stage}</b>
              {event.label ? <i>{event.label}</i> : null}
              <span>{event.message}</span>
              {event.detail ? <ChevronRight size={12} className={cn(openSeq === event.seq && 'open')} /> : null}
            </button>
            {openSeq === event.seq && event.detail ? <pre>{event.detail}</pre> : null}
          </div>
        ))}
      </div>
      {!follow ? <button type="button" className="live-console-latest" onClick={() => setFollow(true)}><ArrowDown size={12} /> Jump to latest</button> : null}
    </section>
  )
}
