/** Model A (hybrid) vs Model B (local): the final template's "Engine Comparison" sheet. */

export interface ComparisonScope { economy: string; pillar: string; model_a: boolean; model_b: boolean }

export interface EngineCard {
  label: string
  mode: 'hybrid' | 'local'
  source: string
  in_snapshot: boolean
  name: string
  run_id: string | null
  models: string[]
  started_at: string | null
  finished_at: string | null
  elapsed_seconds: number | null
  total_usd: number | null
  documents_fetched: number
  corpus_fingerprint: string | null
  rows: number
  evidence: number
  absences: number
  calls: number
}

export interface ComparisonSide {
  indicator: string | null
  article: string | null
  snippet: string
  rationale: string
  confidence: number | string | null
  tag: string | null
  source_url: string | null
  finding_key: string
}

export interface ComparisonRow {
  number: number
  law: string | null
  article: string | null
  indicator: string | null
  found_by: 'Both' | 'Model A only' | 'Model B only'
  indicator_differs: boolean
  citation_differs: boolean
  quote_differs: boolean
  how: string
  model_a: ComparisonSide | null
  model_b: ComparisonSide | null
  in_snapshot: boolean
}

export interface ComparisonDetail {
  economy: string
  pillar: string
  model_a: EngineCard | null
  model_b: EngineCard | null
  same_corpus: boolean
  counts: {
    provisions: number
    both: number
    model_a_only: number
    model_b_only: number
    indicator_differs: number
    citation_differs: number
    quote_differs: number
    agreement_pct: number | null
  }
  rows: ComparisonRow[]
  by_indicator: { indicator: string; model_a: number; model_b: number; agreement: string }[]
  scores: ScoreComparison[]
}

export interface ScoreSide {
  deterministic: number | string | null
  effective: number | null
  state: string
  master_gold: number | string | null
  judge_scores: string | null
  flagged: boolean
  evidence: number
}

export interface ScoreComparison {
  indicator: string
  question: string | null
  model_a?: ScoreSide
  model_b?: ScoreSide
  deterministic_agrees: boolean | null
  effective_agrees: boolean | null
}

export interface ComparisonResponse {
  scopes: ComparisonScope[]
  selected: ComparisonDetail | null
  models: Record<string, string>
}
