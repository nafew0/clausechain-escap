import { rowRecord } from '@/types/workspace'
import type {
  DecisionHistory,
  EvidenceDetail,
  EvidenceParams,
  EvidenceRow,
  PaginatedResponse,
  ReviewQueueParams,
  ReviewQueueResponse,
  ReviewContext,
  SourceMatchDetail,
  SourceMatchMode,
  SubmissionParams,
  SubmissionResponse,
  WorkspaceFixture,
  WorkspaceQueue,
} from '@/types/workspace'

export const WORKSPACE_FIXTURE_MODE =
  process.env.NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE?.trim() === '1'

function assertDevelopmentFixtureMode() {
  if (!WORKSPACE_FIXTURE_MODE) {
    throw new Error('Workspace fixture mode is not enabled.')
  }
  if (process.env.NODE_ENV !== 'development') {
    throw new Error('Workspace fixtures are forbidden outside development.')
  }
}

let fixturePromise: Promise<WorkspaceFixture> | null = null

export async function loadWorkspaceFixture(): Promise<WorkspaceFixture> {
  assertDevelopmentFixtureMode()
  fixturePromise ??= import('./fixtures/current.json').then(
    (module) => module.default as unknown as WorkspaceFixture
  )
  return fixturePromise
}

function pageSlice<T>(rows: T[], page = 1, pageSize = 50): PaginatedResponse<T> {
  const safeSize = Math.min(Math.max(pageSize, 1), 200)
  const safePage = Math.max(page, 1)
  const start = (safePage - 1) * safeSize
  return {
    count: rows.length,
    next: start + safeSize < rows.length ? `fixture:page:${safePage + 1}` : null,
    previous: safePage > 1 ? `fixture:page:${safePage - 1}` : null,
    results: rows.slice(start, start + safeSize),
  }
}

export async function fixtureReviewQueue(
  queue: WorkspaceQueue,
  params: ReviewQueueParams = {}
): Promise<ReviewQueueResponse> {
  const fixture = await loadWorkspaceFixture()
  const source = fixture.queues[queue]
  let results = [...source.results]
  if (params.undecided) {
    results = results.filter((item) => {
      if (item.review_state) return item.review_state.decision === null
      return !item.latest_decision
    })
  }
  if (queue === 'new') {
    const verdictIndex = source.headers.indexOf('Refuter verdict')
    const rank: Record<string, number> = { SPLIT: 0, KEEP: 1, REJECT: 2 }
    if (verdictIndex >= 0) {
      results.sort((left, right) => {
        const leftRow = Array.isArray(left.row) ? left.row : []
        const rightRow = Array.isArray(right.row) ? right.row : []
        return (
          (rank[String(leftRow[verdictIndex] ?? '').toUpperCase()] ?? 3) -
            (rank[String(rightRow[verdictIndex] ?? '').toUpperCase()] ?? 3) ||
          left.position - right.position
        )
      })
    }
  }
  const page = pageSlice(results, params.page, params.page_size)
  return { ...source, ...page }
}

export async function fixtureReviewContext(
  queue: WorkspaceQueue,
  stableKey: string
): Promise<ReviewContext> {
  const fixture = await loadWorkspaceFixture()
  const source = fixture.queues[queue]
  const item = source.results.find((candidate) => candidate.stable_key === stableKey)
  if (!item) throw new Error(`Fixture review item not found: ${queue}/${stableKey}`)
  const record = rowRecord(source.headers, item.row)
  const economy = String(record['Economy'] ?? '')
  const indicator = String(record['Indicator'] ?? record['Indicator ID'] ?? '')
  const law = String(
    record['Law/instrument'] ??
      record['Configured governing instrument'] ??
      record['Master act/instrument'] ??
      ''
  )
  const criteriaSheet = fixture.references.indicator_criteria
  const criteria = criteriaSheet.rows
    .map((row) => rowRecord(criteriaSheet.headers, row))
    .find((row) => String(row['Indicator'] ?? '') === indicator) ?? null
  const knownSheet = fixture.references.master_known
  const masterKnown = knownSheet.rows
    .map((row) => rowRecord(knownSheet.headers, row))
    .filter(
      (row) =>
        String(row['Economy'] ?? '') === economy &&
        String(row['Indicator'] ?? '') === indicator
    )
  const related = fixture.evidence
    .filter(
      ({ row }) =>
        (String(row['Economy'] ?? '') === economy &&
          String(row['Indicator ID'] ?? '') === indicator) ||
        (Boolean(law) && String(row['Law Name'] ?? '') === law)
    )
    .map((evidence) => ({
      ...evidence,
      same_law: Boolean(law) && String(evidence.row['Law Name'] ?? '') === law,
      same_indicator:
        String(evidence.row['Economy'] ?? '') === economy &&
        String(evidence.row['Indicator ID'] ?? '') === indicator,
    }))
  const zoneSource = fixture.queues.zone3
  const zoneItem = zoneSource.results.find((candidate) => {
    const row = rowRecord(zoneSource.headers, candidate.row)
    return row['Economy'] === economy && row['Indicator'] === indicator
  })
  const zoneRecord = zoneItem ? rowRecord(zoneSource.headers, zoneItem.row) : null
  const evidence = item.finding_key
    ? fixture.evidence.find((candidate) => candidate.finding_key === item.finding_key)
    : null
  const isAbsence = queue === 'absence'
  const eligible =
    !fixture.summary.snapshot.stale &&
    !item.blocked &&
    (queue === 'recall' ||
      queue === 'zone3' ||
      Boolean(
        evidence &&
          evidence.row['Status'] === 'in_force' &&
          evidence.row['status_evidence'] &&
          evidence.row['status_evidence_record'] &&
          (isAbsence
            ? evidence.row['search_coverage_manifest']
            : evidence.row['citation_proof'])
      ))
  return {
    queue,
    stable_key: stableKey,
    snapshot: {
      id: fixture.summary.snapshot.id,
      source_hash: fixture.summary.snapshot.source_hash,
      stale: fixture.summary.snapshot.stale,
    },
    indicator_criteria: criteria,
    master_known: masterKnown,
    related_evidence: related,
    zone3: zoneItem && zoneRecord
      ? {
          score_key: zoneItem.stable_key,
          deterministic_score: Number(zoneRecord['Deterministic score'] ?? 0),
          effective_score: Number(zoneRecord['Deterministic score'] ?? 0),
          source: 'deterministic',
          reviewer_name: null,
          reviewed_at: null,
        }
      : null,
    approval_eligibility: {
      eligible,
      reason: eligible ? '' : item.block_reason || 'Currentness, proof, or coverage is incomplete.',
    },
    score_semantics: {
      level: 'indicator',
      finding_has_independent_score: false,
      allowed_scores: [0, 0.5, 1],
      explanation:
        'A finding is an evidence row. The 0, 0.5, or 1 score is decided once at indicator level, using all approved evidence and the methodology.',
    },
  }
}

function equalFilter(actual: unknown, expected: string | undefined) {
  return !expected || String(actual ?? '').toLocaleLowerCase() === expected.toLocaleLowerCase()
}

export async function fixtureEvidence(
  params: EvidenceParams = {}
): Promise<PaginatedResponse<EvidenceRow>> {
  const fixture = await loadWorkspaceFixture()
  const rows = fixture.evidence.filter(({ row }) => {
    const pillar = params.pillar === undefined ? '' : String(params.pillar)
    return (
      equalFilter(row['Economy'], params.economy) &&
      equalFilter(row['Indicator ID'], params.indicator) &&
      equalFilter(row['Discovery Tag'], params.tag) &&
      equalFilter(row['Status'], params.status) &&
      (!pillar || String(row['Indicator ID'] ?? '').startsWith(`P${pillar}-`))
    )
  })
  return pageSlice(rows, params.page, params.page_size)
}

export async function fixtureEvidenceRow(findingKey: string): Promise<EvidenceDetail> {
  const fixture = await loadWorkspaceFixture()
  const evidence = fixture.evidence.find((row) => row.finding_key === findingKey)
  if (!evidence) throw new Error(`Fixture evidence row not found: ${findingKey}`)
  const reviewItem = Object.values(fixture.queues)
    .flatMap((queue) => queue.results)
    .find((item) => item.finding_key === findingKey)
  return {
    ...evidence,
    review_state: reviewItem?.review_state ?? {
      decision: null,
      correction_pending: false,
      citation_checked: false,
      mapping_checked: false,
      status_checked: false,
      citation_reviewer_name: '',
      mapping_reviewer_name: '',
      status_reviewer_name: '',
      stages: {},
    },
  }
}

export async function fixtureSourceMatch(
  findingKey: string,
  params: EvidenceParams = {}
): Promise<SourceMatchDetail> {
  await loadWorkspaceFixture()
  const evidence = await fixtureEvidenceRow(findingKey)
  const proof = (evidence.row['citation_proof'] ?? {}) as Record<string, unknown>
  const alignment = String(proof.alignment_status ?? '')
  const mode = evidence.blocked || ['unaligned', 'ambiguous', 'review'].includes(alignment)
    ? 'blocked'
    : alignment === 'anchor' ? 'anchor' : alignment === 'exact' ? 'exact' : 'blocked'
  const filtered = (await fixtureEvidence(params)).results
  const index = Math.max(0, filtered.findIndex((row) => row.finding_key === findingKey))
  const sourceArtifact = String(evidence.row['source_artifact_id'] ?? evidence.source_hash)
  return {
    ...evidence,
    blocked: mode === 'blocked',
    block_reason: mode === 'blocked' ? 'A complete citation proof is not available.' : '',
    proof_asset_url: mode === 'exact' ? evidence.proof_asset_url : null,
    proof_asset_available: Boolean(mode === 'exact' && evidence.proof_asset_url),
    source_sha256: String(proof.source_sha256 ?? sourceArtifact).replace(/^sha256:/, ''),
    match: {
      mode,
      label: mode === 'exact' ? 'VERBATIM · exact' : mode === 'anchor' ? 'VERBATIM · anchor' : 'blocked',
      alignment_status: alignment || null,
      alignment_score: Number(proof.alignment_score ?? 0) || null,
      page_number: Number(proof.page_number ?? 0) || null,
      anchor: String(proof.anchor ?? '') || null,
      article_path: Array.isArray(proof.article_path) ? proof.article_path.map(String) : [],
      span_ids: Array.isArray(proof.span_ids) ? proof.span_ids.map(String) : [],
      bboxes: Array.isArray(proof.bboxes) ? proof.bboxes as never[] : [],
      verified_at: String(proof.verified_at ?? '') || null,
    },
    source: {
      official_url: String(evidence.row['Source URL'] ?? '') || null,
      archived_copy: String(evidence.row['archived_copy'] ?? '') || null,
      access_date: String(evidence.row['access_date'] ?? '') || null,
      status: String(evidence.row['Status'] ?? '') || null,
      status_evidence: String(evidence.row['status_evidence'] ?? '') || null,
      status_evidence_record: (evidence.row['status_evidence_record'] ?? null) as never,
      citation_tier: String(evidence.row['citation_tier'] ?? '') || null,
      source_artifact_id: sourceArtifact || null,
    },
    navigation: {
      position: index + 1,
      total: filtered.length || 1,
      previous_key: index > 0 ? filtered[index - 1].finding_key : null,
      next_key: index + 1 < filtered.length ? filtered[index + 1].finding_key : null,
    },
  }
}

export async function fixtureSubmission(
  params: SubmissionParams = {}
): Promise<SubmissionResponse> {
  const fixture = await loadWorkspaceFixture()
  let rows = (await fixtureEvidence(params)).results
  const query = params.q?.trim().toLocaleLowerCase()
  if (query) {
    rows = rows.filter(({ row }) =>
      ['Law Name', 'Article / Section', 'Verbatim Snippet', 'Indicator ID', 'Economy']
        .map((field) => String(row[field] ?? ''))
        .join(' ')
        .toLocaleLowerCase()
        .includes(query)
    )
  }
  const templateColumns = [
    'Economy', 'Law Name', 'Law Number / Ref', 'Last Amended', 'Indicator ID',
    'Article / Section', 'Discovery Tag', 'Location Reference', 'Verbatim Snippet',
    'Mapping Rationale', 'Source URL', 'Confidence', 'Notes',
  ]
  const results = rows.map((evidence) => {
    const proof = (evidence.row['citation_proof'] ?? {}) as Record<string, unknown>
    const gates = Array.isArray(proof.gate_results) ? proof.gate_results as never[] : []
    const mode: SourceMatchMode = evidence.blocked ? 'blocked' : proof.alignment_status === 'anchor' ? 'anchor' : proof.alignment_status === 'exact' ? 'exact' : 'blocked'
    const reviewItem = Object.values(fixture.queues).flatMap((queue) => queue.results).find((item) => item.finding_key === evidence.finding_key)
    return {
      finding_key: evidence.finding_key,
      template: Object.fromEntries(templateColumns.map((name) => [name, evidence.row[name] ?? null])),
      row: evidence.row,
      verification: {
        source_domain: null,
        citation_tier: String(evidence.row['citation_tier'] ?? '') || null,
        match_mode: mode,
        match_label: mode === 'exact' ? 'VERBATIM · exact' : mode === 'anchor' ? 'VERBATIM · anchor' : 'blocked',
        page_or_anchor: String(proof.page_number ?? proof.anchor ?? '') || null,
        source_sha256: String(proof.source_sha256 ?? evidence.source_hash),
        access_date: String(evidence.row['access_date'] ?? '') || null,
        status: String(evidence.row['Status'] ?? '') || null,
        gates,
        gates_pass: gates.length > 0,
        blocked: mode === 'blocked',
      },
      review_state: reviewItem?.review_state ?? {
        decision: null, correction_pending: false, citation_checked: false,
        mapping_checked: false, status_checked: false, citation_reviewer_name: '',
        mapping_reviewer_name: '', status_reviewer_name: '', stages: {},
      },
    }
  })
  const page = pageSlice(results, params.page, params.page_size)
  return {
    ...page,
    template_columns: templateColumns,
    snapshot: { id: fixture.summary.snapshot.id, source_hash: fixture.summary.snapshot.source_hash, stale: fixture.summary.snapshot.stale },
    final_artifacts: { available: false, rows: 0 },
    release: null,
  }
}

export async function fixtureDecisionHistory(
  domain: 'findings' | 'recall' | 'zone3',
  key: string
): Promise<DecisionHistory> {
  if (domain === 'findings') {
    const evidence = await fixtureEvidenceRow(key)
    return {
      domain,
      key,
      results: [],
      corrections: [],
      effective_review: evidence.review_state,
    }
  }
  await loadWorkspaceFixture()
  return { domain, key, results: [] }
}

export function rejectFixtureWrite(): never {
  throw new Error(
    'Development fixture mode is read-only. Disable NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE and use the API to record a review.'
  )
}
