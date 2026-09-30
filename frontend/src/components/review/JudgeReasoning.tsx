'use client'

import { useState } from 'react'
import { Maximize2 } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/** Older Zone-3 runs stored each judge's reason cut to this many characters. */
const RECORDED_LIMIT = 160

const PERSONA_LABEL: Record<string, string> = {
  strict: 'Strict reader',
  escap: 'ESCAP methodology',
  skeptical: 'Skeptical peer',
}

interface Judge {
  persona: string
  label: string
  score: string
  reason: string
  cut: boolean
}

function parseJudges(reasoning: string, scores: string): Judge[] {
  const scoreBy = new Map(
    scores
      .split(',')
      .map((part) => part.split(':').map((value) => value.trim()))
      .filter((pair) => pair.length === 2 && pair[0])
      .map(([persona, score]) => [persona.toLowerCase(), score])
  )
  return reasoning
    .split('||')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const colon = part.indexOf(':')
      const persona = colon > 0 ? part.slice(0, colon).trim() : ''
      const reason = (colon > 0 ? part.slice(colon + 1) : part).trim()
      const key = persona.toLowerCase()
      return {
        persona,
        label: PERSONA_LABEL[key] ?? (persona || 'Judge'),
        score: scoreBy.get(key) ?? '',
        reason,
        // Cut on write, mid-sentence: the text simply stops at the old limit.
        cut: reason.length >= RECORDED_LIMIT && !/[.!?)"'”’]$/.test(reason),
      }
    })
}

/** The judge panel's reasoning: a short preview per judge, the full text in a popup. */
export function JudgeReasoning({ reasoning, scores }: { reasoning: string; scores: string }) {
  const [open, setOpen] = useState(false)
  const judges = parseJudges(reasoning, scores)
  if (!judges.length) return <p>—</p>
  const anyCut = judges.some((judge) => judge.cut)

  return (
    <>
      <ul className="review-judges">
        {judges.map((judge) => (
          <li key={`${judge.persona}-${judge.reason.slice(0, 24)}`}>
            <span className="review-judge-head">
              <b>{judge.label}</b>
              {judge.score ? <em>score {judge.score}</em> : null}
            </span>
            <p className="review-judge-preview">{judge.reason}{judge.cut ? '…' : ''}</p>
          </li>
        ))}
      </ul>
      <button type="button" className="review-readmore" onClick={() => setOpen(true)}>
        <Maximize2 size={13} /> Read full reasoning
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto border border-[var(--cc-ink-200)] bg-white shadow-[0_24px_64px_rgba(10,10,11,0.18)]">
          <DialogHeader>
            <DialogTitle>Judge reasoning</DialogTitle>
            <DialogDescription>
              Three independent model judges scored this indicator before review. Their scores are
              advisory; the named reviewer decides the indicator score.
            </DialogDescription>
          </DialogHeader>
          <ol className="review-judge-full">
            {judges.map((judge) => (
              <li key={`${judge.persona}-full`}>
                <span className="review-judge-head">
                  <b>{judge.label}</b>
                  {judge.score ? <em>score {judge.score}</em> : null}
                </span>
                <p>{judge.reason}{judge.cut ? '…' : ''}</p>
              </li>
            ))}
          </ol>
          {anyCut ? (
            <p className="review-judge-note">
              When this score was recorded, each judge&apos;s reason was saved only up to {RECORDED_LIMIT}{' '}
              characters, so the reasons marked … stop there. Scores recorded from now on keep the full text.
            </p>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  )
}
