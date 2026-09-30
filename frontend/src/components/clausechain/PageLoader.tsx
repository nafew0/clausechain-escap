'use client'

import { useEffect, useId, useState } from 'react'

import { cn } from '@/lib/utils'

/**
 * The ClauseChain loading state: the mark assembles itself (the check draws, the
 * chain links in, its nodes pop), with "Loading" and a percentage that climbs
 * towards 99 while the page waits. The percentage is indicative only.
 *
 * variant "screen" fills the viewport (route changes, sign-in check);
 * "page" fills a page's content area; "compact" sits inside a panel.
 */
export function PageLoader({
  label,
  variant = 'page',
  className,
}: {
  label?: string
  variant?: 'screen' | 'page' | 'compact'
  className?: string
}) {
  const id = useId().replace(/:/g, '')
  const [percent, setPercent] = useState(4)

  useEffect(() => {
    const timer = window.setInterval(() => {
      // Fast at first, then slower as it nears the end; never reaches 100 by itself.
      setPercent((value) => Math.min(99, value + Math.max(0.35, (97 - value) * 0.075)))
    }, 110)
    return () => window.clearInterval(timer)
  }, [])

  const shown = Math.floor(percent)
  const caption = label?.replace(/[.…]+$/, '')

  return (
    <div
      className={cn('cc-loader', `cc-loader-${variant}`, className)}
      role="status"
      aria-live="polite"
      aria-label={`${caption || 'Loading'} ${shown}%`}
    >
      <div className="cc-loader-card">
        <svg className="cc-loader-mark" viewBox="0 0 167 96" aria-hidden="true">
          <defs>
            <linearGradient id={`${id}-tile`} x1="12" x2="88" y1="12" y2="88" gradientUnits="userSpaceOnUse">
              <stop stopColor="#0FB5A7" />
              <stop offset="1" stopColor="#2563EB" />
            </linearGradient>
            <linearGradient id={`${id}-shine`} x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#fff" stopOpacity="0" />
              <stop offset="0.5" stopColor="#fff" stopOpacity="0.45" />
              <stop offset="1" stopColor="#fff" stopOpacity="0" />
            </linearGradient>
            <clipPath id={`${id}-clip`}>
              <rect x="8" y="8" width="80" height="80" rx="18" />
            </clipPath>
          </defs>
          <g className="cc-loader-tile">
            <rect x="8" y="8" width="80" height="80" rx="18" fill={`url(#${id}-tile)`} />
            <g clipPath={`url(#${id}-clip)`}>
              <rect className="cc-loader-shine" x="-40" y="0" width="40" height="96" fill={`url(#${id}-shine)`} />
            </g>
            <path className="cc-loader-check" d="M33 51.5l10.4 10.2L64 36" pathLength={1}
              fill="none" stroke="#fff" strokeWidth="7.5" strokeLinecap="round" strokeLinejoin="round" />
            <path className="cc-loader-bar" d="M25 73h46" pathLength={1}
              stroke="#fff" strokeWidth="6" strokeLinecap="round" opacity=".78" />
          </g>
          <path className="cc-loader-chain" d="M99 36h36M117 36v40h36" pathLength={1}
            fill="none" stroke="#0FB5A7" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
          <circle className="cc-loader-node n1" cx="99" cy="36" r="6" fill="#0FB5A7" />
          <circle className="cc-loader-node n2" cx="135" cy="36" r="6" fill="#0FB5A7" />
          <circle className="cc-loader-node n3" cx="153" cy="76" r="6" fill="#2563EB" />
        </svg>
        <div className="cc-loader-readout">
          <span className="cc-loader-word">Loading</span>
          <span className="cc-loader-percent">{shown}%</span>
        </div>
        <div className="cc-loader-track" aria-hidden="true">
          <span style={{ width: `${shown}%` }} />
        </div>
        {caption ? <p className="cc-loader-caption">{caption}</p> : null}
      </div>
    </div>
  )
}
