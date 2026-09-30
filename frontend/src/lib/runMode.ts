import type { RunMode } from '@/types/workspace'

/**
 * The model backend whose workspace the current page shows: `?mode=local` in the
 * URL, else hybrid. Read at call time so the API client and the query cache
 * always follow the tab the user is on; the two workspaces never share a request
 * or a cache entry.
 */
export function currentRunMode(): RunMode {
  if (typeof window === 'undefined') return 'hybrid'
  return new URLSearchParams(window.location.search).get('mode') === 'local' ? 'local' : 'hybrid'
}

/** Keep the Local tab when following a workspace link. */
export function withMode(href: string, mode: RunMode) {
  if (mode !== 'local' || href.startsWith('http')) return href
  return `${href}${href.includes('?') ? '&' : '?'}mode=local`
}

/** A workspace link in the workspace the user is on now. */
export function modeHref(href: string) {
  return withMode(href, currentRunMode())
}
