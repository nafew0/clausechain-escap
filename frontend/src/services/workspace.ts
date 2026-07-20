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
  BulkFindingDecisionInput,
  BulkFindingDecisionResponse,
  CorrectionRequestInput,
  CorrectionRequestResponse,
  DecisionHistory,
  DecisionWriteResponse,
  EvidenceDetail,
  EvidenceParams,
  EvidenceRow,
  EngineAction,
  EngineActionResponse,
  FindingDecisionInput,
  FindingDecisionResponse,
  PaginatedResponse,
  RecallDecisionInput,
  ReviewQueueParams,
  ReviewQueueResponse,
  ReviewContext,
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

export async function getRuns(): Promise<RunsResponse> {
  if (WORKSPACE_FIXTURE_MODE) return (await loadWorkspaceFixture()).runs
  const { data } = await api.get<RunsResponse>('/workspace/runs/')
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

export async function launchEngineAction(
  kind: 'replay' | 'refresh' | 'run',
  payload: { economy?: string; pillar?: 6 | 7 } = {}
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
