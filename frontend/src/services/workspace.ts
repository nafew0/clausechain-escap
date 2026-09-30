import api from '@/services/api'
import {
  WORKSPACE_FIXTURE_MODE,
  fixtureDecisionHistory,
  fixtureEvidence,
  fixtureEvidenceRow,
  fixtureReviewQueue,
  fixtureReviewContext,
  fixtureSourceMatch,
  fixtureSubmission,
  loadWorkspaceFixture,
  rejectFixtureWrite,
} from '@/lib/workspace/fixture'
import type {
  ActionDocumentsResponse,
  BulkFindingDecisionInput,
  BulkFindingDecisionResponse,
  CorrectionRequestInput,
  CorrectionRequestResponse,
  DecisionHistory,
  DecisionWriteResponse,
  EvidenceDetail,
  EvidenceChangeSetResponse,
  EvidenceParams,
  EvidenceRow,
  EngineAction,
  EngineActionResponse,
  FindingDecisionInput,
  FindingDecisionResponse,
  FinalRoundExportType,
  PaginatedResponse,
  RecallDecisionInput,
  ReviewQueueParams,
  ReviewQueueResponse,
  ReviewContext,
  EngineActionEventsPage,
  RunMode,
  RunModeInfo,
  RunsResponse,
  SourceMatchDetail,
  SubmissionParams,
  SubmissionResponse,
  WorkspaceQueue,
  WorkspaceSummary,
  OpsStatsResponse,
  WorkspaceConfigResponse,
  LedgerResponse,
  RawArtifactListResponse,
  RawArtifactResponse,
  KnowledgeGraphSummary,
  KnowledgeGraphSubgraph,
  Zone3DecisionInput,
} from '@/types/workspace'

function queryParams<T extends object>(values: T) {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, value]) => value !== undefined && value !== null && value !== '')
      .map(([key, value]) => [key, typeof value === 'boolean' ? (value ? '1' : '0') : value])
  )
}

export async function getReviewContext(
  queue: WorkspaceQueue,
  stableKey: string
): Promise<ReviewContext> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureReviewContext(queue, stableKey)
  const { data } = await api.get<ReviewContext>(
    `/workspace/review-context/${queue}/${stableKey}/`
  )
  return data
}

export async function getSummary(): Promise<WorkspaceSummary> {
  if (WORKSPACE_FIXTURE_MODE) return (await loadWorkspaceFixture()).summary
  const { data } = await api.get<WorkspaceSummary>('/workspace/summary/')
  return data
}

export async function getEvidenceChanges(params: { kind?: string; economy?: string } = {}): Promise<EvidenceChangeSetResponse> {
  const { data } = await api.get<EvidenceChangeSetResponse>('/workspace/registry/changes/', { params: queryParams(params) })
  return data
}

export async function decideEvidenceChange(changeId: string, payload: {
  verdict: 'retain' | 'retire' | 'investigate'
  comment: string
  expected_latest_decision_id: string | null
}) {
  const { data } = await api.post(`/workspace/registry/changes/${changeId}/decision/`, payload)
  return data
}

export async function publishEvidenceChanges() {
  const { data } = await api.post('/workspace/registry/publish/', {})
  return data
}

export async function getOpsStats(): Promise<OpsStatsResponse> {
  const { data } = await api.get<OpsStatsResponse>('/workspace/ops-stats/')
  return data
}

export async function getWorkspaceConfig(): Promise<WorkspaceConfigResponse> {
  const { data } = await api.get<WorkspaceConfigResponse>('/workspace/config/')
  return data
}

export async function getLedger(page = 1): Promise<LedgerResponse> {
  const { data } = await api.get<LedgerResponse>('/workspace/ledger/', { params: { page, page_size: 100 } })
  return data
}

export async function getRawArtifacts(): Promise<RawArtifactListResponse> {
  const { data } = await api.get<RawArtifactListResponse>('/workspace/raw/')
  return data
}

export async function getRawArtifact(key: string): Promise<RawArtifactResponse> {
  const { data } = await api.get<RawArtifactResponse>(`/workspace/raw/${key}/`)
  return data
}

export async function downloadRawArtifact(key: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/workspace/raw/${key}/download/`, { responseType: 'blob' })
  return data
}

export async function getKnowledgeGraph(): Promise<KnowledgeGraphSummary> {
  const { data } = await api.get<KnowledgeGraphSummary>('/workspace/knowledge-graph/')
  return data
}

export async function getKnowledgeSubgraph(params: Record<string, string | undefined> = {}): Promise<KnowledgeGraphSubgraph> {
  const { data } = await api.get<KnowledgeGraphSubgraph>('/workspace/knowledge-graph/subgraph/', { params: queryParams(params) })
  return data
}

export async function getReviewQueue(
  queue: WorkspaceQueue,
  params: ReviewQueueParams = {}
): Promise<ReviewQueueResponse> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureReviewQueue(queue, params)
  const { data } = await api.get<ReviewQueueResponse>(`/workspace/review/${queue}/`, {
    params: queryParams(params),
  })
  return data
}

/** Every item in a queue. The API pages at 200; the Review page searches, filters and
 * steps through the whole queue, so it loads all pages (the first, then the rest together). */
export async function getFullReviewQueue(queue: WorkspaceQueue): Promise<ReviewQueueResponse> {
  const pageSize = 200
  const first = await getReviewQueue(queue, { page: 1, page_size: pageSize })
  const pages = Math.ceil(first.count / pageSize)
  if (pages <= 1) return first
  const rest = await Promise.all(
    Array.from({ length: pages - 1 }, (_, index) =>
      getReviewQueue(queue, { page: index + 2, page_size: pageSize })
    )
  )
  const seen = new Set<string>()
  const results = [first, ...rest]
    .flatMap((page) => page.results)
    .filter((item) => !seen.has(item.stable_key) && Boolean(seen.add(item.stable_key)))
  return { ...first, next: null, previous: null, results }
}

export async function getEvidence(
  params: EvidenceParams = {}
): Promise<PaginatedResponse<EvidenceRow>> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureEvidence(params)
  const { data } = await api.get<PaginatedResponse<EvidenceRow>>('/workspace/evidence/', {
    params: queryParams(params),
  })
  return data
}

export async function getEvidenceRow(findingKey: string): Promise<EvidenceDetail> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureEvidenceRow(findingKey)
  const { data } = await api.get<EvidenceDetail>(`/workspace/evidence/${findingKey}/`)
  return data
}

export async function getSourceMatch(
  findingKey: string,
  params: EvidenceParams = {}
): Promise<SourceMatchDetail> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureSourceMatch(findingKey, params)
  const { data } = await api.get<SourceMatchDetail>(
    `/workspace/source-match/${findingKey}/`,
    { params: queryParams(params) }
  )
  return data
}

export async function getProofAsset(assetUrl: string): Promise<Blob> {
  const { data } = await api.get<Blob>(assetUrl.replace(/^\/api/, ''), {
    responseType: 'blob',
  })
  return data
}

export async function getRuns(mode: RunMode = 'hybrid'): Promise<RunsResponse> {
  if (WORKSPACE_FIXTURE_MODE) {
    const runs = (await loadWorkspaceFixture()).runs
    return mode === 'hybrid' ? runs : { ...runs, mode, results: [], actions: [], champion: {} }
  }
  const { data } = await api.get<RunsResponse>('/workspace/runs/', { params: { mode } })
  return data
}

export async function getSubmission(
  params: SubmissionParams = {}
): Promise<SubmissionResponse> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureSubmission(params)
  const { data } = await api.get<SubmissionResponse>('/workspace/submission/', {
    params: queryParams(params),
  })
  return data
}

export async function getEngineActions(): Promise<EngineActionResponse> {
  if (WORKSPACE_FIXTURE_MODE) return { results: [] }
  const { data } = await api.get<EngineActionResponse>('/workspace/engine/actions/')
  return data
}

export async function getEngineActionEvents(actionId: string, after = 0): Promise<EngineActionEventsPage> {
  const { data } = await api.get<EngineActionEventsPage>(`/workspace/engine/actions/${actionId}/events/`, {
    params: { after },
  })
  return data
}

/** Runs → Sources: download + read + index an economy's documents, or clear its downloads. */
export async function launchSourcesAction(
  payload: { economy: string; operation: 'build' | 'clear'; pillar?: 2 | 6 | 7 }
): Promise<EngineAction> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<EngineAction>('/workspace/engine/sources/', payload)
  return data
}

export async function getActionDocuments(actionId: string): Promise<ActionDocumentsResponse> {
  const { data } = await api.get<ActionDocumentsResponse>(`/workspace/engine/actions/${actionId}/documents/`)
  return data
}

/** The Run Record's "every document downloaded" list, as CSV. */
export async function downloadActionDocuments(actionId: string): Promise<void> {
  const response = await api.get<Blob>(`/workspace/engine/actions/${actionId}/documents/`, {
    params: { export: 'csv' },
    responseType: 'blob',
  })
  const href = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = `documents_downloaded_${actionId.slice(0, 8)}.csv`
  anchor.click()
  URL.revokeObjectURL(href)
}

/** The current results in ESCAP's final-round template, built on request; saves it and returns the file name. */
export async function downloadFinalRoundExport(type: FinalRoundExportType, mode: RunMode): Promise<string> {
  const response = await api.get<Blob>('/workspace/export/final-round/', {
    params: { type, mode },
    responseType: 'blob',
  })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? `ClauseChain_RDTII_FinalRound.${type}`
  const href = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(href)
  return filename
}

export async function cancelEngineAction(actionId: string): Promise<EngineAction> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<EngineAction>(`/workspace/engine/actions/${actionId}/cancel/`)
  return data
}

export async function cancelAllEngineActions(
  mode: RunMode
): Promise<{ mode: RunMode; cancelled: number; stopping: number; cleared: number }> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post('/workspace/engine/actions/cancel-all/', { mode })
  return data
}

export async function launchEngineAction(
  kind: 'replay' | 'refresh' | 'run',
  payload: { economy?: string; pillar?: 2 | 6 | 7; mode?: RunMode } = {}
): Promise<EngineAction> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<EngineAction>(`/workspace/engine/${kind}/`, payload)
  return data
}

export async function getDecisionHistory(
  domain: 'findings' | 'recall' | 'zone3',
  key: string
): Promise<DecisionHistory> {
  if (WORKSPACE_FIXTURE_MODE) return fixtureDecisionHistory(domain, key)
  const { data } = await api.get<DecisionHistory>(
    `/workspace/decisions/${domain}/${key}/history/`
  )
  return data
}

export async function decideFinding(
  payload: FindingDecisionInput
): Promise<FindingDecisionResponse> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<FindingDecisionResponse>(
    '/workspace/decisions/findings/',
    payload
  )
  return data
}

export async function decideFindingsBulk(
  payload: BulkFindingDecisionInput
): Promise<BulkFindingDecisionResponse> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<BulkFindingDecisionResponse>(
    '/workspace/decisions/findings/bulk/',
    payload
  )
  return data
}

export async function decideRecall(
  payload: RecallDecisionInput
): Promise<DecisionWriteResponse> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<DecisionWriteResponse>(
    '/workspace/decisions/recall/',
    payload
  )
  return data
}

export interface Zone3MatrixEvidence {
  /** null for local-mode rows: unreviewed run output has no review item yet */
  finding_key: string | null
  stable_key: string
  queue: 'new' | 'known' | 'absence' | null
  law: string
  article: string
  tag: string
  blocked: boolean
  snippet?: string
  source_url?: string | null
  confidence?: string | number | null
  absence?: boolean
}

export interface Zone3MatrixCell {
  economy: string
  indicator: string
  score_key: string
  question?: string
  deterministic: number | null
  deterministic_reason?: string
  master_gold?: number | string | null
  gold_divergence?: string | null
  judge_scores?: string
  judge_reasoning?: string
  agreement_alpha?: number | string | null
  score_band?: string
  flagged: boolean
  /** hybrid: reviewer states; local: evidence found / absence concluded (unscored) */
  state: 'pending' | 'approved' | 'overridden' | 'evidence' | 'absence'
  effective: number | null
  reviewer_name: string
  reviewed_at: string | null
  reasoning: string
  latest_decision_id: string | null
  blocked: boolean
  evidence: Zone3MatrixEvidence[]
  absence_rows?: Zone3MatrixEvidence[]
}

export interface Zone3MatrixRun {
  run_id: string | null
  country: string
  pillar: number
  generated_at: string | null
  action_id: string
}

export interface Zone3MatrixResponse {
  mode: RunMode
  modes: RunModeInfo[]
  snapshot: { generated_at: string; bundle_hash: string; stale: boolean } | null
  runs?: Zone3MatrixRun[]
  economies: string[]
  indicators: string[]
  counts: {
    total: number
    decided: number
    pending: number
    with_evidence?: number
    absence?: number
    evidence_rows?: number
  }
  score_semantics: { explanation: string; allowed_scores: number[] }
  cells: Zone3MatrixCell[]
}

export async function getZone3Matrix(mode: RunMode = 'hybrid'): Promise<Zone3MatrixResponse> {
  const { data } = await api.get<Zone3MatrixResponse>('/workspace/zone3-matrix/', {
    params: { mode },
  })
  return data
}

export async function decideZone3(
  payload: Zone3DecisionInput
): Promise<DecisionWriteResponse> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<DecisionWriteResponse>(
    '/workspace/decisions/zone3/',
    payload
  )
  return data
}

export async function requestCorrection(
  payload: CorrectionRequestInput
): Promise<CorrectionRequestResponse> {
  if (WORKSPACE_FIXTURE_MODE) return rejectFixtureWrite()
  const { data } = await api.post<CorrectionRequestResponse>(
    '/workspace/corrections/',
    payload
  )
  return data
}
