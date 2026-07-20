export const ANALYTICS_COLOR_SCHEMES = {
  default: {
    label: 'Signature Mix',
    colors: ['#2563eb', '#0f766e', '#f97316', '#8b5cf6', '#ef4444', '#14b8a6'],
  },
  warm: {
    label: 'Warm',
    colors: ['#f97316', '#fb923c', '#f59e0b', '#ef4444', '#fda4af'],
  },
  cool: {
    label: 'Cool',
    colors: ['#0f766e', '#14b8a6', '#2563eb', '#38bdf8', '#6366f1'],
  },
  monochrome: {
    label: 'Monochrome',
    colors: ['#0f172a', '#334155', '#64748b', '#94a3b8', '#cbd5e1'],
  },
  pastel: {
    label: 'Pastel',
    colors: ['#7dd3fc', '#86efac', '#fdba74', '#f9a8d4', '#c4b5fd'],
  },
  vibrant: {
    label: 'Vibrant',
    colors: ['#2563eb', '#7c3aed', '#f43f5e', '#f97316', '#22c55e'],
  },
}

export function getAnalyticsColors(scheme = 'default'): string[] {
  return (ANALYTICS_COLOR_SCHEMES as Record<string, { label: string; colors: string[] } | undefined>)[scheme]?.colors ?? ANALYTICS_COLOR_SCHEMES.default.colors
}
