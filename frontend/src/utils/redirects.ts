const DEFAULT_REDIRECT = '/dashboard'

export function getSafeRedirect(value: unknown, fallback = DEFAULT_REDIRECT): string {
  const target = typeof value === 'string' ? value.trim() : ''

  if (!target || !target.startsWith('/') || target.startsWith('//') || target.includes('\\')) {
    return fallback
  }

  try {
    const normalized = new URL(target, window.location.origin)
    if (normalized.origin !== window.location.origin) {
      return fallback
    }
    return `${normalized.pathname}${normalized.search}${normalized.hash}`
  } catch {
    return fallback
  }
}
