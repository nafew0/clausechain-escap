// Reader-facing wording for the engine's release-readiness report.
// The engine speaks in internal contract terms; the UI translates them into
// plain reviewer language without changing their meaning.

export function readinessLabel(status: unknown): string {
  return String(status) === 'PASS' ? 'READY' : 'PENDING SIGN-OFFS'
}

const FRIENDLY: Array<[RegExp, string]> = [
  [/^(\d+)-page extraction gold lacks named human sign-off$/i,
    '$1-page extraction reference set awaiting reviewer sign-off'],
  [/^(\d+) recall misses await adjudication\/repair$/i,
    '$1 recall checks awaiting reviewer adjudication'],
  [/^candidate findings still require named human decisions$/i,
    'Evidence rows awaiting named reviewer decisions'],
  [/^(\d+) Zone-3 scores await explicit approval\/override$/i,
    '$1 indicator scores awaiting reviewer approval'],
  [/^approval-only submission replay has not produced final artifacts$/i,
    'Final dataset is generated after reviewer approvals (replay pending)'],
]

export function friendlyFailure(raw: unknown): string {
  const text = String(raw)
  for (const [pattern, replacement] of FRIENDLY) {
    if (pattern.test(text)) return text.replace(pattern, replacement)
  }
  return text
}
