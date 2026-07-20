export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]
export interface JsonObject {
  [key: string]: JsonValue
}

export type WorkspaceQueue = 'new' | 'absence' | 'recall' | 'zone3' | 'known'
export type FindingQueue = Extract<WorkspaceQueue, 'new' | 'absence' | 'known'>
export type ReviewStage = 'citation' | 'mapping' | 'status'
export type FindingVerdict = 'approved' | 'rejected'
export type RecallVerdict =
  | 'REAL_MISS'
  | 'GOLD_WRONG'
  | 'GOLD_AMBIGUOUS'
  | 'CORRECT_ABSTENTION'
  | 'NEEDS_CORRECTION'
export type Zone3Verdict = 'approved' | 'overridden'
export type Zone3Score = 0 | 0.5 | 1
export type DecisionDomain = 'findings' | 'recall' | 'zone3'
export type FindingWriteOutcome = 'stage_recorded' | 'engine_decision_written'

export interface SnapshotIdentity {
  id: string
  schema_version: string
  generated_at: string
  imported_at: string
  source_hash: string
  bundle_hash: string
  engine_git_sha: string
  stale: boolean
}

export interface ReviewProgress {
  decided: number
  total: number
}

export interface WorkspaceSummary {
  snapshot: SnapshotIdentity
  counts: Record<string, number>
  refuter_status: string
  champion: JsonObject
  progress: Record<WorkspaceQueue, ReviewProgress>
  reviewer_roles: string[]
  runs?: RunRecord[]
}

export interface SnapshotArtifactMeta {
  key: string
  category: string
  source_path: string
  media_type: string
  byte_size: number
  sha256: string
  generated_at: string | null
  imported_at: string
}

export interface SnapshotArtifactDetail extends SnapshotArtifactMeta {
  raw_text: string
  parsed: JsonValue
}

export interface RawArtifactListResponse {
  snapshot: SnapshotIdentity
  results: SnapshotArtifactMeta[]
}

export interface RawArtifactResponse {
  snapshot: SnapshotIdentity
  artifact: SnapshotArtifactDetail
}

export interface OpsStats {
  schema_version: number
  generated_at: string
  acquisition: JsonObject[]
  eligibility: JsonObject[]
  extraction: JsonObject[]
}

export interface OpsStatsResponse {
  snapshot: SnapshotIdentity
  ops_stats: OpsStats
  artifact: SnapshotArtifactMeta
}

export interface ConfigSource extends SnapshotArtifactDetail { code?: string }
export interface WorkspaceConfigResponse {
  snapshot: SnapshotIdentity
  jurisdictions: ConfigSource[]
  seeds: ConfigSource
}

export interface LedgerEvent {
  id: string
  event_type: string
  domain: string
  key: string
  action: string
  stage?: string
  score?: string
  reviewer_name: string
  reviewer_role: string
  occurred_at: string
  authoritative_file_hash: string
  writer_receipt: JsonObject
  bundle_manifest?: JsonObject
  final_artifact_hashes?: JsonObject
  snapshot_id?: string | null
  supersedes_id: string | null
}

export type LedgerResponse = PaginatedResponse<LedgerEvent>

export interface GraphNode { id: string; labels: string[]; properties: JsonObject }
export interface GraphEdge { id: string; source: string; target: string; type: string; properties: JsonObject }
export interface KnowledgeGraphSummary {
  snapshot: SnapshotIdentity
  artifact: SnapshotArtifactMeta
  status: 'verified' | 'parity_failed' | 'unavailable'
  origin: string
  extracted_at: string | null
  schema_version: number | null
  checks: Record<string, boolean>
  counts: JsonObject
  expected: JsonObject
  reason: string | null
  node_count: number
  edge_count: number
  lenses: string[]
}

export interface KnowledgeGraphSubgraph {
  snapshot: SnapshotIdentity
  status: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  caps: { nodes: number; edges: number }
}

export interface FindingStageState {
  id: string
  decision: FindingVerdict
  reviewer_name: string
  reviewer_user_id: string
  reviewed_at: string
}

export interface FindingReviewState {
  decision: FindingVerdict | null
  correction_pending: boolean
  citation_checked: boolean
  mapping_checked: boolean
  status_checked: boolean
  citation_reviewer_name: string
  mapping_reviewer_name: string
  status_reviewer_name: string
  stages: Partial<Record<ReviewStage, FindingStageState>>
}

export interface LatestCorrection {
  id: string
  explanation: string
  requested_by: string
  requested_at: string
}

export interface DomainDecision {
  id: string
  verdict: RecallVerdict | Zone3Verdict
  reviewer_name: string
  reviewer_role: string
  reviewed_at: string
  authoritative_file_hash: string
  supersedes_id: string | null
  reasoning?: string
  official_source_url?: string
  score?: string
}

export interface ReviewItem {
  id: number
  position: number
  row: JsonValue[] | JsonObject
  stable_key: string
  finding_key: string | null
  blocked: boolean
  block_reason: string
  source_hash: string
  review_state?: FindingReviewState
  latest_correction?: LatestCorrection | null
  latest_decision?: DomainDecision | null
  approval_eligibility?: { eligible: boolean; reason: string }
}

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface ReviewQueueResponse extends PaginatedResponse<ReviewItem> {
  queue: WorkspaceQueue
  headers: string[]
  snapshot_id: string
  snapshot_hash: string
}

export interface ReviewQueueParams {
  page?: number
  page_size?: number
  undecided?: boolean
}

export interface EvidenceRow {
  finding_key: string
  row: JsonObject
  blocked: boolean
  proof_asset_url: string | null
  source_hash: string
}

export interface EvidenceDetail extends EvidenceRow {
  review_state: FindingReviewState
}

export interface RelatedEvidence extends Omit<EvidenceRow, 'source_hash'> {
  same_law: boolean
  same_indicator: boolean
}

export interface ReviewContext {
  queue: WorkspaceQueue
  stable_key: string
  snapshot: { id: string; source_hash: string; stale: boolean }
  indicator_criteria: JsonObject | null
  master_known: JsonObject[]
  related_evidence: RelatedEvidence[]
  zone3: {
    score_key: string
    deterministic_score: number | null
    effective_score: number | null
    source: 'deterministic' | 'reviewer'
    reviewer_name: string | null
    reviewed_at: string | null
  } | null
  approval_eligibility: { eligible: boolean; reason: string }
  score_semantics: {
    level: 'indicator'
    finding_has_independent_score: false
    allowed_scores: Zone3Score[]
    explanation: string
  }
}

export interface EvidenceParams {
  page?: number
  page_size?: number
  economy?: string
  indicator?: string
  pillar?: string | number
  tag?: string
  status?: string
  queue?: WorkspaceQueue
}

export type SourceMatchMode = 'exact' | 'anchor' | 'blocked'

export interface SourceMatchDetail {
  finding_key: string
  row: JsonObject
  blocked: boolean
  block_reason: string
  proof_asset_url: string | null
  proof_asset_available: boolean
  source_hash: string
  source_sha256: string
  match: {
    mode: SourceMatchMode
    label: string
    alignment_status: string | null
    alignment_score: number | null
    page_number: number | null
    anchor: string | null
    article_path: string[]
    span_ids: string[]
    bboxes: JsonValue[]
    verified_at: string | null
  }
  source: {
    official_url: string | null
    archived_copy: string | null
    access_date: string | null
    status: string | null
    status_evidence: string | null
    status_evidence_record: JsonObject | null
    citation_tier: string | null
    source_artifact_id: string | null
  }
  review_state: FindingReviewState
  navigation: {
    position: number
    total: number
    previous_key: string | null
    next_key: string | null
  }
}

export interface EngineAction {
  id: string
  kind: 'refresh' | 'replay' | 'run'
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  arguments: JsonObject
  requested_by: string
  requested_at: string
  started_at: string | null
  finished_at: string | null
  stdout: string
  result_hashes: JsonObject
  error: string
}

export interface RunRecord {
  run_name: string
  run_id: string | null
  country: string
  pillar: number
  generated_at: string | null
  rows_produced: number
  discovery_counts: { NEW: number; KNOWN: number }
  warnings: JsonValue[]
  warning_count: number
  model_version: string
  elapsed_seconds: number | null
  total_usd: number | null
  models: JsonObject
  pipeline_stats: JsonObject
  source_hash: string
}

export interface RunsResponse {
  results: RunRecord[]
  champion: JsonObject
  actions: EngineAction[]
  can_launch: boolean
}

export interface SubmissionParams extends EvidenceParams {
  q?: string
  review?: 'pending' | 'approved' | 'rejected'
}

export interface SubmissionRow {
  finding_key: string
  template: Record<string, JsonValue>
  row: JsonObject
  verification: {
    source_domain: string | null
    citation_tier: string | null
    match_mode: SourceMatchMode
    match_label: string
    page_or_anchor: string | number | null
    source_sha256: string
    access_date: string | null
    status: string | null
    gates: JsonObject[]
    gates_pass: boolean
    blocked: boolean
  }
  review_state: FindingReviewState
}

export interface SubmissionResponse extends PaginatedResponse<SubmissionRow> {
  template_columns: string[]
  snapshot: { id: string; source_hash: string; stale: boolean }
  final_artifacts: {
    available: boolean
    rows: number
    csv_sha256?: string | null
    json_sha256?: string | null
    identity_counts_match?: boolean
    error?: string
  }
  release: {
    id: string
    state: 'DRAFT' | 'REVIEWING' | 'READY' | 'FROZEN' | 'SUPERSEDED'
    snapshot_id: string | null
    bundle_hash: string
    created_at: string
    frozen_at: string | null
  } | null
}

export interface EngineActionResponse {
  results: EngineAction[]
}

export interface FindingDecisionInput {
  finding_key: string
  queue: FindingQueue
  review_stage: ReviewStage
  decision: FindingVerdict
  citation_checked?: boolean
  mapping_checked?: boolean
  status_checked?: boolean
  note?: string
  expected_latest_decision_id: string | null
}

export interface FindingDecisionResponse {
  decision_id: string
  authoritative_file_hash: string
  review_state: FindingReviewState
  reviewer_id: string
  outcome: FindingWriteOutcome
  engine_exported: boolean
}

export interface BulkFindingDecisionInput {
  finding_keys: string[]
  review_stage: ReviewStage
  citation_checked?: boolean
  mapping_checked?: boolean
  status_checked?: boolean
  note?: string
  expected_latest_decision_ids: Record<string, string | null>
}

export interface BulkFindingDecisionResponse {
  decision_ids: string[]
  authoritative_file_hash: string
  reviewer_id: string
  outcome: FindingWriteOutcome
  engine_exported: boolean
  review_states: Record<string, FindingReviewState>
}

export interface RecallDecisionInput {
  recall_key: string
  verdict: RecallVerdict
  reasoning?: string
  official_source_url?: string
  expected_latest_decision_id: string | null
}

export interface Zone3DecisionInput {
  score_key: string
  verdict: Zone3Verdict
  score: Zone3Score
  reasoning?: string
  expected_latest_decision_id: string | null
}

export interface DecisionWriteResponse {
  decision_id: string
  authoritative_file_hash: string
  reviewer_id: string
}

export interface CorrectionRequestInput {
  finding_key: string
  queue: FindingQueue
  explanation: string
  expected_latest_correction_id: string | null
}

export interface CorrectionRequestResponse {
  correction_request_id: string
  finding_key: string
  authoritative_file_hash: string
}

export interface FindingHistoryEntry {
  id: string
  stage: ReviewStage
  decision: FindingVerdict
  checks: { citation: boolean; mapping: boolean; status: boolean }
  note: string
  reviewer_name: string
  reviewer_role: string
  reviewed_at: string
  supersedes_id: string | null
  authoritative_file_hash: string
}

export interface CorrectionHistoryEntry {
  id: string
  explanation: string
  reviewer_name: string
  reviewed_at: string
  supersedes_id: string | null
  authoritative_file_hash: string
}

export interface FindingDecisionHistory {
  domain: 'findings'
  key: string
  results: FindingHistoryEntry[]
  corrections: CorrectionHistoryEntry[]
  effective_review: FindingReviewState
}

export interface DomainDecisionHistory {
  domain: 'recall' | 'zone3'
  key: string
  results: DomainDecision[]
}

export type DecisionHistory = FindingDecisionHistory | DomainDecisionHistory

export interface WorkspaceFixture {
  summary: WorkspaceSummary
  queues: Record<WorkspaceQueue, ReviewQueueResponse>
  evidence: EvidenceRow[]
  runs: RunsResponse
  references: {
    indicator_criteria: { headers: string[]; rows: (JsonValue[] | JsonObject)[] }
    master_known: { headers: string[]; rows: (JsonValue[] | JsonObject)[] }
  }
}

export type DecideRequest =
  | { domain: 'findings'; payload: FindingDecisionInput }
  | { domain: 'findings-bulk'; payload: BulkFindingDecisionInput }
  | { domain: 'recall'; payload: RecallDecisionInput }
  | { domain: 'zone3'; payload: Zone3DecisionInput }
  | { domain: 'correction'; payload: CorrectionRequestInput }

export type DecideResponse =
  | FindingDecisionResponse
  | BulkFindingDecisionResponse
  | DecisionWriteResponse
  | CorrectionRequestResponse

export function rowRecord(headers: string[], row: JsonValue[] | JsonObject): JsonObject {
  if (!Array.isArray(row)) return row
  return Object.fromEntries(headers.map((header, index) => [header, row[index] ?? null]))
}
