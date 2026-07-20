// ===========================================================
// ClauseChain — Mock Data & Types
// ===========================================================

export type ClauseStatus = 'verified' | 'pending' | 'rejected' | 'partial' | 'conflict' | 'none'

export interface CoverageStats {
  verified: number
  pending: number
  rejected: number
  total: number
}

export interface Jurisdiction {
  code: string
  name: string
  flag: string
  languages: string[]
  instruments: number
  clauses: number
  verified: number
  pending: number
  rejected: number
  conflicts: number
  lastSync: string
  lastSyncRel: string
  coverage: Record<string, CoverageStats>
}

export interface Document {
  id: string
  title: string
  type: 'Act' | 'Amendment' | 'Regulation' | 'Guideline'
  languages: string[]
  pages: number
  clauses: number
  verified: number
  pending: number
  rejected: number
  conflicts: number
  updated: string
  updatedRel: string
  sourceUrl: string
  sourceHash: string
  authority: string
  binding?: boolean
}

export interface Gate {
  name: string
  kind: string
  status: 'pass' | 'fail' | 'warn'
  value: string
  detail: string
}

export interface Classification {
  clauseId: string
  sectionNumber: string
  title: string
  pillar: string
  pillarLabel: string
  status: ClauseStatus
  confidence: number
  hash: string
  verbatimSpan: string
  principalRule: string
  exceptions: string[]
  conditions: string[]
  gates: Gate[]
  provenance: {
    instrument: string
    section: string
    page: number
    charOffset: string
    bbox: string
    retrievedAt: string
    sourceUrl: string
    sha256: string
  }
}

export interface RejectedClassification {
  clauseId: string
  sectionNumber: string
  title: string
  proposedPillar: string
  proposedPillarLabel: string
  status: ClauseStatus
  failedGate: string
  verbatimSpan: string
  gates: Gate[]
}

export interface OutlineSection {
  id: string
  type: string
  number: string
  title: string
  status: ClauseStatus
  pillar?: string | null
  active?: boolean
  conflict?: boolean
  rejectionGate?: string
}

export interface OutlinePart {
  type: string
  number: string
  title: string
  children: OutlineSection[]
}

export interface DocumentDetail {
  id: string
  title: string
  jurisdiction: string
  jurisdictionCode: string
  language: string
  sourceUrl: string
  sourceHash: string
  lastProcessed: string
  lastProcessedRel: string
  pages: number
  outline: OutlinePart[]
  classification: Classification
  rejected: RejectedClassification
}

export interface ActivityEvent {
  id: string
  type: 'verified' | 'rejected' | 'ingested' | 'conflict' | 'crawl'
  desc: string
  hash: string
  ts: string
  href: { page: string; country?: string; doc?: string }
}

export interface PipelineJob {
  id: string
  stage: string
  name: string
  progress: number
  status: string
}

export interface LedgerEntry {
  entryNo: number
  type: string
  desc: string
  ownHash: string
  prevHash: string
  ts: string
  actor: string
}

export interface RdtiiPillar {
  name: string
  mandatory: boolean
  sub: Record<string, string>
}

export type MatrixCell = {
  status: ClauseStatus
  count: number
  conflict: boolean
} | null

export type VerificationGateStatus = 'pass' | 'warn' | 'fail' | 'abstain'

export interface LegalPredicateTuple {
  subject: string
  action: string
  object: string
  modality: 'shall' | 'shall not' | 'may' | 'must' | 'must not'
  condition: string
  exception: string
  legalEffect: string
  rdtiiIndicator: string
  confidence: number
}

export interface SourceStatus {
  id: string
  title: string
  jurisdiction: string
  kind: 'official_statute' | 'amendment' | 'consolidated_text' | 'guideline' | 'draft' | 'unofficial_translation'
  binding: boolean
  current: boolean
  authorityRank: number
  status: 'binding_current' | 'binding_historical' | 'context_only' | 'draft' | 'translation_only' | 'requires_review'
  url: string
  effectiveDate: string
  confidence: number
  note: string
}

export interface VerificationGateV2 {
  id: string
  label: string
  category: 'source' | 'text' | 'structure' | 'retrieval' | 'predicate' | 'mapping' | 'citation' | 'conflict'
  status: VerificationGateStatus
  score: string
  detail: string
}

export interface CounterEvidence {
  id: string
  sourceId: string
  citation: string
  relation: 'qualifies' | 'conflicts_with' | 'context_only' | 'superseded_by'
  severity: 'low' | 'medium' | 'high'
  text: string
  resolution: string
}

export interface EvidenceLedgerEdge {
  id: string
  from: string
  to: string
  relation: 'supports' | 'qualifies' | 'amends' | 'supersedes' | 'conflicts_with' | 'non_binding_context_for' | 'requires_review'
  status: 'accepted' | 'review' | 'rejected'
  hash: string
  detail: string
}

export interface BenchmarkMetric {
  id: string
  label: string
  stage: string
  value: number
  baseline: number
  target: number
  unit: '%' | 'CER' | 'WER' | 'F1' | 'recall@20'
  status: 'pass' | 'watch' | 'fail'
  detail: string
}

export interface RegressionCase {
  id: string
  title: string
  jurisdiction: string
  stage: string
  failureMode: string
  expectedCatch: string
  status: 'caught' | 'abstained' | 'failed'
  severity: 'low' | 'medium' | 'high'
}

export interface EvidenceAuditCase {
  docId: string
  title: string
  jurisdiction: string
  jurisdictionCode: string
  language: string
  sourceUrl: string
  sourceHash: string
  sourceStatus: SourceStatus
  citation: string
  page: number
  charOffset: string
  bbox: string
  spanHash: string
  highlightedSpan: string
  sourceParagraphs: string[]
  legalNode: {
    nodeId: string
    type: string
    title: string
    ruleUnit: string
    definitions: string[]
    conditions: string[]
    exceptions: string[]
    linkedNodes: string[]
  }
  predicate: LegalPredicateTuple
  gatesV2: VerificationGateV2[]
  counterEvidence: CounterEvidence[]
  trustBadges: Array<{
    label: string
    tone: 'pass' | 'warn' | 'fail' | 'info'
  }>
}

// ---- Data ----

export const RDTII_PILLARS: Record<string, RdtiiPillar> = {
  '6': {
    name: 'Cross-Border Data Policies',
    mandatory: true,
    sub: {
      '6.1': 'Data localization requirement',
      '6.2': 'Conditional cross-border transfer',
      '6.3': 'Adequacy / whitelist mechanism',
      '6.4': 'Data subject consent for transfer',
    },
  },
  '7': {
    name: 'Personal Data Protection',
    mandatory: true,
    sub: {
      '7.1': 'Lawful basis for processing',
      '7.2': 'Purpose limitation',
      '7.3': 'Data subject rights',
      '7.4': 'Breach notification',
      '7.5': 'DPO / accountability',
    },
  },
  '8': {
    name: 'Cybersecurity Obligations',
    mandatory: false,
    sub: {
      '8.1': 'Critical infrastructure designation',
      '8.2': 'Incident reporting',
    },
  },
  '9': {
    name: 'Digital Identity',
    mandatory: false,
    sub: {
      '9.1': 'National e-ID framework',
      '9.2': 'Authentication standards',
    },
  },
  '12': {
    name: 'Online Content Governance',
    mandatory: false,
    sub: {
      '12.1': 'Content removal regime',
      '12.2': 'Intermediary liability',
    },
  },
}

export const EIGHT_VERIFICATION_GATES: VerificationGateV2[] = [
  {
    id: 'G1',
    label: 'Official source',
    category: 'source',
    status: 'pass',
    score: 'rank 1',
    detail: 'Source is hosted on Singapore Statutes Online / AGC.',
  },
  {
    id: 'G2',
    label: 'Current law status',
    category: 'source',
    status: 'pass',
    score: '0.98',
    detail: 'Consolidated text selected over amendment PDFs and guidance.',
  },
  {
    id: 'G3',
    label: 'OCR / text integrity',
    category: 'text',
    status: 'pass',
    score: '0 edits',
    detail: 'HTML source requires no OCR; span hash matches extraction.',
  },
  {
    id: 'G4',
    label: 'Section boundary',
    category: 'structure',
    status: 'pass',
    score: 'F1 0.96',
    detail: 'Section 26 and subsection boundary preserved.',
  },
  {
    id: 'G5',
    label: 'Retrieval support',
    category: 'retrieval',
    status: 'pass',
    score: 'rank 1/20',
    detail: 'Hybrid dense+sparse retrieval returned this clause first.',
  },
  {
    id: 'G6',
    label: 'Predicate completeness',
    category: 'predicate',
    status: 'pass',
    score: '7/7',
    detail: 'Subject, action, object, modality, condition, exception, and effect found.',
  },
  {
    id: 'G7',
    label: 'RDTII mapping',
    category: 'mapping',
    status: 'pass',
    score: '0.93',
    detail: 'Predicate entails Pillar 6.2 conditional cross-border transfer.',
  },
  {
    id: 'G8',
    label: 'Conflict check',
    category: 'conflict',
    status: 'warn',
    score: '1 context',
    detail: 'Guideline found, but downgraded to non-binding context.',
  },
]

export const SOURCE_STATUS_NODES: SourceStatus[] = [
  {
    id: 'SG-PDPA-2012',
    title: 'Personal Data Protection Act 2012',
    jurisdiction: 'SG',
    kind: 'official_statute',
    binding: true,
    current: false,
    authorityRank: 1,
    status: 'binding_historical',
    url: 'https://sso.agc.gov.sg/Act/PDPA2012',
    effectiveDate: '2012-10-15',
    confidence: 0.96,
    note: 'Official statute, but not the selected consolidated current text.',
  },
  {
    id: 'SG-PDPA-2020-AMEND',
    title: 'Personal Data Protection (Amendment) Act 2020',
    jurisdiction: 'SG',
    kind: 'amendment',
    binding: true,
    current: true,
    authorityRank: 1,
    status: 'binding_current',
    url: 'https://sso.agc.gov.sg/Acts-Supp/40-2020',
    effectiveDate: '2021-02-01',
    confidence: 0.94,
    note: 'Binding amendment; applied through consolidated text.',
  },
  {
    id: 'SG-PDPA-CONSOLIDATED',
    title: 'PDPA 2012, current consolidated version',
    jurisdiction: 'SG',
    kind: 'consolidated_text',
    binding: true,
    current: true,
    authorityRank: 1,
    status: 'binding_current',
    url: 'https://sso.agc.gov.sg/Act/PDPA2012',
    effectiveDate: '2025-01-02',
    confidence: 0.99,
    note: 'Selected as the primary source for citations and exports.',
  },
  {
    id: 'SG-PDPC-GUIDE-XFER',
    title: 'PDPC Advisory Guidelines on Key Concepts',
    jurisdiction: 'SG',
    kind: 'guideline',
    binding: false,
    current: true,
    authorityRank: 3,
    status: 'context_only',
    url: 'https://www.pdpc.gov.sg/help-and-resources',
    effectiveDate: '2024-03-01',
    confidence: 0.91,
    note: 'Useful explanation, but cannot override statutory text.',
  },
  {
    id: 'SG-AI-DATA-DRAFT',
    title: 'Draft consultation paper on data transfer safeguards',
    jurisdiction: 'SG',
    kind: 'draft',
    binding: false,
    current: false,
    authorityRank: 5,
    status: 'draft',
    url: 'https://www.pdpc.gov.sg/consultations',
    effectiveDate: '2025-09-10',
    confidence: 0.78,
    note: 'Tracked for context only; excluded from legal conclusions.',
  },
  {
    id: 'SG-PDPA-UNOFFICIAL-ZH',
    title: 'Unofficial Chinese translation of PDPA transfer rules',
    jurisdiction: 'SG',
    kind: 'unofficial_translation',
    binding: false,
    current: true,
    authorityRank: 6,
    status: 'translation_only',
    url: 'https://example.org/sg-pdpa-translation',
    effectiveDate: '2025-01-02',
    confidence: 0.68,
    note: 'Translation can support multilingual review but cannot be cited as authority.',
  },
]

export const SOURCE_STATUS_EDGES: EvidenceLedgerEdge[] = [
  {
    id: 'edge-001',
    from: 'SG-PDPA-2020-AMEND',
    to: 'SG-PDPA-2012',
    relation: 'amends',
    status: 'accepted',
    hash: '8F0A1C2B',
    detail: '2020 amendment updates PDPA obligations and is applied to the consolidated text.',
  },
  {
    id: 'edge-002',
    from: 'SG-PDPA-CONSOLIDATED',
    to: 'SG-PDPA-2012',
    relation: 'supersedes',
    status: 'accepted',
    hash: '12C4AE99',
    detail: 'Current consolidated version supersedes older standalone text for citation.',
  },
  {
    id: 'edge-003',
    from: 'SG-PDPC-GUIDE-XFER',
    to: 'SG-PDPA-CONSOLIDATED',
    relation: 'non_binding_context_for',
    status: 'accepted',
    hash: 'A91E3BC4',
    detail: 'Guideline explains transfer obligation but is not treated as controlling law.',
  },
  {
    id: 'edge-004',
    from: 'SG-AI-DATA-DRAFT',
    to: 'SG-PDPA-CONSOLIDATED',
    relation: 'requires_review',
    status: 'review',
    hash: 'F44A09D1',
    detail: 'Draft consultation mentions safeguards; excluded until enacted.',
  },
  {
    id: 'edge-005',
    from: 'SG-PDPA-UNOFFICIAL-ZH',
    to: 'SG-PDPA-CONSOLIDATED',
    relation: 'non_binding_context_for',
    status: 'accepted',
    hash: 'C0E229FA',
    detail: 'Translation is only supporting context for bilingual reviewer QA.',
  },
]

export const EVIDENCE_AUDIT_CASE: EvidenceAuditCase = {
  docId: 'SG-PDPA-2012',
  title: 'Personal Data Protection Act 2012 (current consolidated text)',
  jurisdiction: 'Singapore',
  jurisdictionCode: 'SG',
  language: 'English',
  sourceUrl: 'https://sso.agc.gov.sg/Act/PDPA2012',
  sourceHash: 'b5c6d7e8f9012a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f70819a2b3',
  sourceStatus: SOURCE_STATUS_NODES[2],
  citation: 'PDPA 2012, s 26(1)',
  page: 41,
  charOffset: '[43112, 43356]',
  bbox: '[94, 312, 544, 392]',
  spanHash: '6B3F4E29C8A1D7F0',
  highlightedSpan:
    'An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act to ensure that organisations provide a standard of protection to personal data so transferred that is comparable to that under this Act.',
  sourceParagraphs: [
    'Part VI — Transfer of Personal Data Outside Singapore',
    '26.—(1) An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act to ensure that organisations provide a standard of protection to personal data so transferred that is comparable to that under this Act.',
    '(2) The Commission may, by notice in writing, require an organisation to show how it complies with the transfer limitation obligation.',
    '(3) This section is to be read with any regulations prescribing comparable protection, contractual safeguards, consent requirements, or other permitted transfer mechanisms.',
  ],
  legalNode: {
    nodeId: 'node-sg-pdpa-s26-1',
    type: 'operative_rule',
    title: 'Transfer limitation obligation',
    ruleUnit: 'Conditional cross-border transfer regime: default prohibition lifted only when prescribed comparable-protection requirements are met.',
    definitions: ['organisation', 'personal data', 'transfer', 'country or territory outside Singapore'],
    conditions: ['recipient is outside Singapore', 'requirements are prescribed under the Act', 'comparable protection is provided'],
    exceptions: ['transfers satisfying prescribed requirements', 'permitted safeguards under applicable regulations'],
    linkedNodes: ['PDPA s 2 definitions', 'PDPA regulations on transfer limitation', 'PDPC advisory guideline context'],
  },
  predicate: {
    subject: 'organisation',
    action: 'transfer personal data outside Singapore',
    object: 'personal data',
    modality: 'shall not',
    condition: 'except in accordance with requirements prescribed under the Act',
    exception: 'transfer allowed where comparable protection is ensured',
    legalEffect: 'conditional cross-border transfer, not absolute localization',
    rdtiiIndicator: '6.2',
    confidence: 0.93,
  },
  gatesV2: EIGHT_VERIFICATION_GATES,
  counterEvidence: [
    {
      id: 'ce-001',
      sourceId: 'SG-PDPC-GUIDE-XFER',
      citation: 'PDPC advisory guidance, transfer limitation chapter',
      relation: 'context_only',
      severity: 'low',
      text: 'Guidance paraphrases comparable protection mechanisms but is not binding statutory authority.',
      resolution: 'Shown to reviewer as context; excluded from primary citation.',
    },
    {
      id: 'ce-002',
      sourceId: 'SG-AI-DATA-DRAFT',
      citation: 'Draft consultation paper, safeguards section',
      relation: 'superseded_by',
      severity: 'medium',
      text: 'Draft text proposes additional safeguards but is not enacted.',
      resolution: 'Marked draft; cannot change the RDTII classification.',
    },
  ],
  trustBadges: [
    { label: 'Official binding source', tone: 'pass' },
    { label: 'Current consolidated text', tone: 'pass' },
    { label: 'Exact citation verified', tone: 'pass' },
    { label: 'OCR not required', tone: 'info' },
    { label: 'Guideline downgraded', tone: 'warn' },
    { label: 'Human review ready', tone: 'pass' },
  ],
}

export const BENCHMARK_METRICS: BenchmarkMetric[] = [
  { id: 'bm-01', label: 'Discovery recall@20', stage: 'Discovery', value: 94.2, baseline: 81.5, target: 90, unit: 'recall@20', status: 'pass', detail: 'Known laws retrieved in top 20 official-source results.' },
  { id: 'bm-02', label: 'Authority accuracy', stage: 'Authority', value: 96.8, baseline: 84.1, target: 92, unit: '%', status: 'pass', detail: 'Binding/current source selected over guidelines, drafts, and translations.' },
  { id: 'bm-03', label: 'Current-law-status accuracy', stage: 'Authority', value: 94.9, baseline: 79.6, target: 90, unit: '%', status: 'pass', detail: 'Amended and consolidated sources resolved correctly.' },
  { id: 'bm-04', label: 'OCR CER', stage: 'Extraction', value: 1.8, baseline: 4.7, target: 2.5, unit: 'CER', status: 'pass', detail: 'Character error rate on Bengali/Thai scanned pages.' },
  { id: 'bm-05', label: 'OCR WER', stage: 'Extraction', value: 3.9, baseline: 8.6, target: 5, unit: 'WER', status: 'pass', detail: 'Word error rate after legal-term risk repair.' },
  { id: 'bm-06', label: 'Section-boundary F1', stage: 'Structure', value: 91.6, baseline: 78.4, target: 88, unit: 'F1', status: 'pass', detail: 'Rule and exception boundaries preserved.' },
  { id: 'bm-07', label: 'Retrieval recall@20', stage: 'Retrieval', value: 95.7, baseline: 86.2, target: 92, unit: 'recall@20', status: 'pass', detail: 'Hybrid dense+sparse plus reranker retrieval.' },
  { id: 'bm-08', label: 'Tuple field accuracy', stage: 'Predicate', value: 88.3, baseline: 73.8, target: 85, unit: '%', status: 'pass', detail: 'Subject, action, condition, exception, and legal effect scored independently.' },
  { id: 'bm-09', label: 'Classification macro-F1', stage: 'Mapping', value: 84.7, baseline: 70.5, target: 82, unit: 'F1', status: 'pass', detail: 'Pillar/sub-pillar classification over P6/P7 clauses.' },
  { id: 'bm-10', label: 'Citation accuracy', stage: 'Citation', value: 97.4, baseline: 88.9, target: 95, unit: '%', status: 'pass', detail: 'URL, section, span hash, and page/offset agreement.' },
  { id: 'bm-11', label: 'Abstention precision', stage: 'Verification', value: 89.1, baseline: 62.4, target: 84, unit: '%', status: 'pass', detail: 'High-risk outputs routed to humans instead of being exported.' },
]

export const REGRESSION_CASES: RegressionCase[] = [
  {
    id: 'reg-01',
    title: 'Exception lost during chunking',
    jurisdiction: 'SG',
    stage: 'Structure',
    failureMode: 'The main prohibition is separated from the comparable-protection exception.',
    expectedCatch: 'Predicate completeness gate warns and abstains from absolute localization classification.',
    status: 'caught',
    severity: 'high',
  },
  {
    id: 'reg-02',
    title: 'Guideline treated as law',
    jurisdiction: 'SG',
    stage: 'Authority',
    failureMode: 'PDPC advisory guidance is selected as the controlling source.',
    expectedCatch: 'Authority resolver downgrades source to context-only.',
    status: 'caught',
    severity: 'high',
  },
  {
    id: 'reg-03',
    title: 'OCR flips "shall not"',
    jurisdiction: 'BD',
    stage: 'Extraction',
    failureMode: 'Bengali scan or English OCR drops negation in an operative clause.',
    expectedCatch: 'Legal-term risk repair forces secondary OCR/VLM review.',
    status: 'caught',
    severity: 'high',
  },
  {
    id: 'reg-04',
    title: 'Outdated amendment selected',
    jurisdiction: 'TH',
    stage: 'Authority',
    failureMode: 'Historical amendment PDF is cited instead of current consolidated text.',
    expectedCatch: 'Current-law-status gate fails and requires human review.',
    status: 'abstained',
    severity: 'medium',
  },
  {
    id: 'reg-05',
    title: 'Retention misread as transfer',
    jurisdiction: 'BD',
    stage: 'Mapping',
    failureMode: 'Domestic retention period is mapped to cross-border data transfer.',
    expectedCatch: 'Predicate/rule-unit gate rejects due missing cross-border object.',
    status: 'caught',
    severity: 'medium',
  },
]

export const JURISDICTIONS: Jurisdiction[] = [
  {
    code: 'BD',
    name: 'Bangladesh',
    flag: '🇧🇩',
    languages: ['English', 'Bengali'],
    instruments: 4,
    clauses: 287,
    verified: 198,
    pending: 41,
    rejected: 36,
    conflicts: 3,
    lastSync: '2026-05-20T08:42:00Z',
    lastSyncRel: '12m ago',
    coverage: {
      '6': { verified: 18, pending: 4, rejected: 3, total: 28 },
      '7': { verified: 22, pending: 6, rejected: 5, total: 36 },
      '8': { verified: 4, pending: 1, rejected: 0, total: 8 },
    },
  },
  {
    code: 'TH',
    name: 'Thailand',
    flag: '🇹🇭',
    languages: ['Thai', 'English'],
    instruments: 3,
    clauses: 312,
    verified: 241,
    pending: 38,
    rejected: 28,
    conflicts: 1,
    lastSync: '2026-05-20T06:18:00Z',
    lastSyncRel: '2h ago',
    coverage: {
      '6': { verified: 22, pending: 3, rejected: 2, total: 28 },
      '7': { verified: 30, pending: 4, rejected: 2, total: 36 },
      '8': { verified: 6, pending: 1, rejected: 0, total: 8 },
    },
  },
  {
    code: 'SG',
    name: 'Singapore',
    flag: '🇸🇬',
    languages: ['English'],
    instruments: 5,
    clauses: 418,
    verified: 387,
    pending: 18,
    rejected: 13,
    conflicts: 0,
    lastSync: '2026-05-19T22:05:00Z',
    lastSyncRel: '11h ago',
    coverage: {
      '6': { verified: 26, pending: 1, rejected: 1, total: 28 },
      '7': { verified: 34, pending: 1, rejected: 1, total: 36 },
      '8': { verified: 7, pending: 1, rejected: 0, total: 8 },
      '9': { verified: 3, pending: 0, rejected: 0, total: 5 },
    },
  },
]

export const DOCUMENTS: Record<string, Document[]> = {
  BD: [
    {
      id: 'BD-DSA-2018',
      title: 'Digital Security Act 2018',
      type: 'Act',
      languages: ['English', 'Bengali'],
      pages: 42,
      clauses: 96,
      verified: 78,
      pending: 12,
      rejected: 6,
      conflicts: 1,
      updated: '2026-05-20T08:42:00Z',
      updatedRel: '12m ago',
      sourceUrl: 'https://bdlaws.minlaw.gov.bd/act-1261.html',
      sourceHash: 'a3f57c2eb19d44e9b1c2f8a47b9e2c0d6f4d3a8e7c5b9a1f3e2d8c4b6a5f9c2',
      authority: 'Primary',
    },
    {
      id: 'BD-PDPA-2023D',
      title: 'Personal Data Protection Act 2023 (Draft)',
      type: 'Amendment',
      languages: ['Bengali', 'English'],
      pages: 28,
      clauses: 74,
      verified: 51,
      pending: 16,
      rejected: 7,
      conflicts: 2,
      updated: '2026-05-19T14:22:00Z',
      updatedRel: '1d ago',
      sourceUrl: 'https://dpdt.portal.gov.bd/draft-pdpa-2023.pdf',
      sourceHash: 'b8e91f24c3da55fa7d8e9c1b3a6f5d2e0c4b7a8f1d3e5c7b9a2f4d6e8c0a3b5',
      authority: 'Primary',
    },
    {
      id: 'BD-ICTA-2006',
      title: 'Information & Communication Technology Act 2006',
      type: 'Act',
      languages: ['English', 'Bengali'],
      pages: 58,
      clauses: 84,
      verified: 56,
      pending: 8,
      rejected: 20,
      conflicts: 0,
      updated: '2026-05-18T11:00:00Z',
      updatedRel: '2d ago',
      sourceUrl: 'https://bdlaws.minlaw.gov.bd/act-950.html',
      sourceHash: 'c2d8e5f1b7a3946c0e2f5a8b1d4c7e9f2a5b8d1c4e7f0a3b6c9d2e5f8a1b4c7',
      authority: 'Primary',
    },
    {
      id: 'BD-BTRA-GL-2024',
      title: 'BTRC Guidelines on Data Storage (2024)',
      type: 'Guideline',
      languages: ['English'],
      pages: 12,
      clauses: 33,
      verified: 13,
      pending: 5,
      rejected: 3,
      conflicts: 0,
      updated: '2026-05-15T09:32:00Z',
      updatedRel: '5d ago',
      sourceUrl: 'https://btrc.gov.bd/guidelines/data-storage-2024.pdf',
      sourceHash: 'd9e0a1b2c3d4e5f60718293a4b5c6d7e8f9012a3b4c5d6e7f80192a3b4c5d6',
      authority: 'Subordinate',
      binding: false,
    },
  ],
  TH: [
    {
      id: 'TH-PDPA-2019',
      title: 'Personal Data Protection Act B.E. 2562 (2019)',
      type: 'Act',
      languages: ['Thai', 'English'],
      pages: 64,
      clauses: 112,
      verified: 96,
      pending: 11,
      rejected: 5,
      conflicts: 0,
      updated: '2026-05-20T06:18:00Z',
      updatedRel: '2h ago',
      sourceUrl: 'https://pdpc.or.th/pdpa-2019-en.pdf',
      sourceHash: 'e1f2a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f7081920a3b4c5d6e7',
      authority: 'Primary',
    },
    {
      id: 'TH-CCA-2017',
      title: 'Computer Crime Act B.E. 2550 (2007, amended 2017)',
      type: 'Amendment',
      languages: ['Thai'],
      pages: 38,
      clauses: 102,
      verified: 78,
      pending: 16,
      rejected: 8,
      conflicts: 1,
      updated: '2026-05-19T16:00:00Z',
      updatedRel: '1d ago',
      sourceUrl: 'https://ratchakitcha.soc.go.th/cca-2017.pdf',
      sourceHash: 'f2a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f7081920a3b4c5d6e7f8',
      authority: 'Amending',
    },
    {
      id: 'TH-ETDA-2020',
      title: 'ETDA Royal Decrees on Electronic Transactions',
      type: 'Regulation',
      languages: ['Thai', 'English'],
      pages: 21,
      clauses: 98,
      verified: 67,
      pending: 11,
      rejected: 15,
      conflicts: 0,
      updated: '2026-05-18T20:00:00Z',
      updatedRel: '2d ago',
      sourceUrl: 'https://etda.or.th/royal-decrees-2020.pdf',
      sourceHash: 'a4b5c6d7e8f9012a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f7081920',
      authority: 'Subordinate',
    },
  ],
  SG: [
    {
      id: 'SG-PDPA-2012',
      title: 'Personal Data Protection Act 2012 (as amended)',
      type: 'Act',
      languages: ['English'],
      pages: 88,
      clauses: 134,
      verified: 128,
      pending: 4,
      rejected: 2,
      conflicts: 0,
      updated: '2026-05-19T22:05:00Z',
      updatedRel: '11h ago',
      sourceUrl: 'https://sso.agc.gov.sg/Act/PDPA2012',
      sourceHash: 'b5c6d7e8f9012a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f70819a2b3',
      authority: 'Primary',
    },
    {
      id: 'SG-CSA-2018',
      title: 'Cybersecurity Act 2018',
      type: 'Act',
      languages: ['English'],
      pages: 62,
      clauses: 88,
      verified: 81,
      pending: 4,
      rejected: 3,
      conflicts: 0,
      updated: '2026-05-19T18:30:00Z',
      updatedRel: '14h ago',
      sourceUrl: 'https://sso.agc.gov.sg/Act/CSA2018',
      sourceHash: 'c6d7e8f9012a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f70819a2b3c4',
      authority: 'Primary',
    },
    {
      id: 'SG-MAS-2020',
      title: 'MAS Notice on Cross-Border Data Transfers',
      type: 'Regulation',
      languages: ['English'],
      pages: 18,
      clauses: 64,
      verified: 60,
      pending: 3,
      rejected: 1,
      conflicts: 0,
      updated: '2026-05-15T10:12:00Z',
      updatedRel: '5d ago',
      sourceUrl: 'https://mas.gov.sg/notice-data-transfer-2020.pdf',
      sourceHash: 'd7e8f9012a3b4c5d6e7f8091a2b3c4d5e6f70819a2b3c4d5e6f70819a2b3c4d5',
      authority: 'Subordinate',
    },
  ],
}

export const DOC_DETAIL_BDDSA: DocumentDetail = {
  id: 'BD-DSA-2018',
  title: 'Digital Security Act 2018',
  jurisdiction: 'Bangladesh',
  jurisdictionCode: 'BD',
  language: 'English (with Bengali parallel text)',
  sourceUrl: 'https://bdlaws.minlaw.gov.bd/act-1261.html',
  sourceHash: 'a3f57c2eb19d44e9b1c2f8a47b9e2c0d6f4d3a8e7c5b9a1f3e2d8c4b6a5f9c2',
  lastProcessed: '2026-05-20T08:42:00Z',
  lastProcessedRel: '12m ago',
  pages: 42,
  outline: [
    {
      type: 'part', number: 'I', title: 'Preliminary',
      children: [
        { id: 's1', type: 'section', number: '1', title: 'Short title and commencement', status: 'verified', pillar: null },
        { id: 's2', type: 'section', number: '2', title: 'Definitions', status: 'verified', pillar: null },
      ],
    },
    {
      type: 'part', number: 'II', title: 'Digital Security Agency',
      children: [
        { id: 's5', type: 'section', number: '5', title: 'Establishment of Agency', status: 'verified', pillar: '8.1' },
        { id: 's8', type: 'section', number: '8', title: 'Powers of the Director General', status: 'verified', pillar: '8.1' },
      ],
    },
    {
      type: 'part', number: 'V', title: 'Crimes and Punishments',
      children: [
        { id: 's24', type: 'section', number: '24', title: 'Identity fraud', status: 'verified', pillar: '7.1' },
        { id: 's25', type: 'section', number: '25', title: 'Publishing offensive information', status: 'pending', pillar: '12.1' },
        { id: 's26', type: 'section', number: '26', title: 'Punishment for publishing identity-related information', active: true, status: 'verified', pillar: '6.1' },
        { id: 's27', type: 'section', number: '27', title: 'Cyber-terrorism', status: 'verified', pillar: '8.2' },
        { id: 's28', type: 'section', number: '28', title: 'Hurting religious values', status: 'rejected', pillar: null, rejectionGate: 'Gate 2 (NLI Entailment)' },
        { id: 's29', type: 'section', number: '29', title: 'Defamation', status: 'pending', pillar: '12.1' },
        { id: 's30', type: 'section', number: '30', title: 'Identity-related crimes with computer', status: 'verified', pillar: '7.1' },
        { id: 's31', type: 'section', number: '31', title: 'Disturbing law and order', status: 'verified', pillar: null },
        { id: 's32', type: 'section', number: '32', title: 'Breach of secrecy', status: 'verified', pillar: '7.2' },
        { id: 's33', type: 'section', number: '33', title: 'Hacking offences', status: 'verified', pillar: '8.2', conflict: true },
        { id: 's34', type: 'section', number: '34', title: 'Illegal entry into critical infrastructure', status: 'verified', pillar: '8.1' },
      ],
    },
    {
      type: 'part', number: 'VI', title: 'Investigation, Trial and Appeal',
      children: [
        { id: 's40', type: 'section', number: '40', title: 'Investigation procedure', status: 'pending', pillar: null },
        { id: 's43', type: 'section', number: '43', title: 'Search, seizure and arrest', status: 'rejected', pillar: null, rejectionGate: 'Gate 3 (Structural Plausibility)' },
      ],
    },
  ],
  classification: {
    clauseId: 's26',
    sectionNumber: '26(1)',
    title: 'Punishment for publishing identity-related information',
    pillar: '6.1',
    pillarLabel: 'Pillar 6.1 — Data Localization Requirement',
    status: 'verified',
    confidence: 0.94,
    hash: 'a3f57c2eb19d44e9b1c2f8a47b9e2c0d6f4d3a8e7c5b9a1f3e2d8c4b6a5f9c2',
    verbatimSpan:
      "Any person who, intentionally or knowingly without lawful authority, collects, sells, takes possession of, supplies or uses any person's identity-related information, shall not save such data, including biometric information, photographs, financial records or registry information, outside the geographic boundaries of Bangladesh.",
    principalRule:
      'Identity-related personal data — including biometric, photographic, financial and registry data — must be stored within the geographic boundaries of Bangladesh.',
    exceptions: [
      'Lawful authority of a competent court or tribunal',
      'Express written consent of the data subject for a specified purpose',
    ],
    conditions: [
      'Storage facility must be physically located in Bangladesh',
      'Cross-border processing requires prior approval from the Digital Security Agency',
    ],
    gates: [
      { name: 'Span Match', kind: 'lexical', status: 'pass', value: 'exact', detail: '0 edits · source matched character-for-character' },
      { name: 'NLI Entailment', kind: 'semantic', status: 'pass', value: '0.94', detail: 'DeBERTa-v3 entailment score, threshold 0.70' },
      { name: 'Structural Plausibility', kind: 'structural', status: 'pass', value: 'passed', detail: '§26(1) exists in instrument · predicates present' },
    ],
    provenance: {
      instrument: 'BD-DSA-2018',
      section: '§26(1)',
      page: 14,
      charOffset: '[12453, 12527]',
      bbox: '[72, 248, 540, 286]',
      retrievedAt: '2026-05-20T08:42:11Z',
      sourceUrl: 'https://bdlaws.minlaw.gov.bd/act-1261/section-46556.html',
      sha256: 'a3f57c2eb19d44e9b1c2f8a47b9e2c0d6f4d3a8e7c5b9a1f3e2d8c4b6a5f9c2',
    },
  },
  rejected: {
    clauseId: 's28',
    sectionNumber: '28',
    title: 'Hurting religious values',
    proposedPillar: '12.1',
    proposedPillarLabel: 'Pillar 12.1 — Content removal regime',
    status: 'rejected',
    failedGate: 'Gate 2 (NLI Entailment)',
    verbatimSpan:
      'Whoever publishes or broadcasts any propaganda or campaign against any religion through any website or any electronic form which hurts the religious value or sentiment, shall be punished with imprisonment for a term not exceeding ten (10) years…',
    gates: [
      { name: 'Span Match', kind: 'lexical', status: 'pass', value: 'exact', detail: '0 edits · source matched' },
      { name: 'NLI Entailment', kind: 'semantic', status: 'fail', value: '0.15', detail: 'Below 0.70 threshold · span does not entail claim' },
      { name: 'Structural Plausibility', kind: 'structural', status: 'fail', value: '0 predicates', detail: 'No content-removal operative predicates found' },
    ],
  },
}

export const ACTIVITY: ActivityEvent[] = [
  { id: 'a1', type: 'verified', desc: 'SG PDPA s 26(1) verified for Pillar 6.2 with predicate tuple', hash: '6b3f…d7f0', ts: '2m ago', href: { page: 'doc', country: 'SG', doc: 'SG-PDPA-2012' } },
  { id: 'a2', type: 'rejected', desc: 'Guideline-only transfer claim blocked by official-source gate', hash: '7e91…44fa', ts: '4m ago', href: { page: 'doc', country: 'SG', doc: 'SG-PDPA-2012' } },
  { id: 'a3', type: 'ingested', desc: 'Authority graph selected Singapore current consolidated text', hash: 'd7e8…c4d5', ts: '12m ago', href: { page: 'jurisdiction', country: 'SG' } },
  { id: 'a4', type: 'conflict', desc: 'Draft transfer safeguard source downgraded before mapping', hash: '9bca…2c1f', ts: '28m ago', href: { page: 'doc', country: 'SG', doc: 'SG-PDPA-2012' } },
  { id: 'a5', type: 'verified', desc: 'Thai PDPA section verified as conditional transfer regime', hash: 'e1f2…d6e7', ts: '41m ago', href: { page: 'doc', country: 'TH', doc: 'TH-PDPA-2019' } },
  { id: 'a6', type: 'rejected', desc: 'BD scan abstained after OCR negation risk on “shall not”', hash: 'c2d8…b4c7', ts: '1h ago', href: { page: 'doc', country: 'BD', doc: 'BD-ICTA-2006' } },
  { id: 'a7', type: 'ingested', desc: 'OCR pass complete: TH-CCA-2017 (38 pages, Thai)', hash: 'f2a3…81f8', ts: '2h ago', href: { page: 'doc', country: 'TH', doc: 'TH-CCA-2017' } },
  { id: 'a8', type: 'verified', desc: 'SG-PDPA §26 verified for Pillar 6.2 (Adequacy)', hash: 'b5c6…2b3', ts: '3h ago', href: { page: 'doc', country: 'SG', doc: 'SG-PDPA-2012' } },
  { id: 'a9', type: 'crawl', desc: 'Re-crawl started: bdlaws.minlaw.gov.bd (4 documents)', hash: '—', ts: '5h ago', href: { page: 'jurisdiction', country: 'BD' } },
]

export const PIPELINE_JOBS: PipelineJob[] = [
  { id: 'j1', stage: 'Discovery', name: 'sso.agc.gov.sg — PDPA current text', progress: 96, status: 'running' },
  { id: 'j2', stage: 'Authority', name: 'SG source graph · guideline downgrade', progress: 88, status: 'running' },
  { id: 'j3', stage: 'OCR', name: 'BD scanned circular · negation risk regions', progress: 71, status: 'running' },
  { id: 'j4', stage: 'Verifier', name: 'Eight-gate queue · 18 pending', progress: 22, status: 'running' },
]

export const LIVE_LOG = [
  { ts: '08:42:11', lvl: 'ok', text: 'Gate 8 warning resolved · guideline downgraded to context-only' },
  { ts: '08:42:09', lvl: 'ok', text: 'Gate 7 passed · s 26(1) ⇒ RDTII 6.2 conditional transfer' },
  { ts: '08:42:07', lvl: 'info', text: 'Tuple extracted · modality=shall not · exception=comparable protection' },
  { ts: '08:42:04', lvl: 'info', text: 'Reranker selected SG-PDPA-CONSOLIDATED rank 1/20' },
  { ts: '08:41:58', lvl: 'err', text: 'ABSTAIN BD scan · OCR risk: "shall not" negation confidence 0.58' },
  { ts: '08:41:52', lvl: 'info', text: 'Qwen3 embedding + sparse BM25 retrieval · query=cross-border transfer' },
  { ts: '08:41:47', lvl: 'warn', text: 'Authority resolver: PDPC guideline is non-binding context' },
  { ts: '08:41:33', lvl: 'info', text: 'Loaded SG-PDPA-CONSOLIDATED · HTML · current consolidated text' },
]

export const LEDGER_ENTRIES: LedgerEntry[] = [
  { entryNo: 18429, type: 'VERIFIED', desc: '§26(1) of BD-DSA-2018 verified for Pillar 6.1', ownHash: 'a3f57c2e…b9c2', prevHash: '9bca31d7…2c1f', ts: '2026-05-20T08:42:11Z', actor: 'system' },
  { entryNo: 18428, type: 'REJECTED', desc: '§28 of BD-DSA-2018 rejected · Gate 2 NLI=0.15', ownHash: '7e91a8d2…44fa', prevHash: '5dc41e93…7eaa', ts: '2026-05-20T08:41:58Z', actor: 'system' },
  { entryNo: 18427, type: 'INGESTED', desc: 'MAS Notice 626 (SG) ingested · 18 pages', ownHash: 'd7e8f901…c4d5', prevHash: 'c2d8e5f1…b4c7', ts: '2026-05-20T08:30:14Z', actor: 'system' },
  { entryNo: 18426, type: 'CONFLICT', desc: 'Conflict logged: BD-DSA §33 vs. BD-ICTA §54', ownHash: '9bca31d7…2c1f', prevHash: '8aa72c4e…d109', ts: '2026-05-20T08:14:08Z', actor: 'system' },
  { entryNo: 18425, type: 'HUMAN_EDIT', desc: 'Reviewer edited verbatim_span on TH-PDPA §28', ownHash: '5dc41e93…7eaa', prevHash: '4cb30d82…6e99', ts: '2026-05-20T08:00:22Z', actor: 'n.tan@un-pdpa' },
  { entryNo: 18424, type: 'VERIFIED', desc: 'TH-PDPA §28 verified for Pillar 6.2', ownHash: 'e1f2a3b4…d6e7', prevHash: '3ba20c71…5d88', ts: '2026-05-20T07:55:01Z', actor: 'system' },
  { entryNo: 18423, type: 'REJECTED', desc: 'BD-ICTA §57 rejected · Gate 1 Span Match', ownHash: '8aa72c4e…d109', prevHash: '2a91fb60…4c77', ts: '2026-05-20T06:18:33Z', actor: 'system' },
  { entryNo: 18422, type: 'INGESTED', desc: 'TH-CCA-2017 OCR complete · 38 pages (Thai)', ownHash: 'f2a3b4c5…81f8', prevHash: '1f80ea59…3b66', ts: '2026-05-20T05:55:00Z', actor: 'system' },
  { entryNo: 18421, type: 'CRAWL', desc: 'Re-crawl scheduled: bdlaws.minlaw.gov.bd', ownHash: '4cb30d82…6e99', prevHash: '0e7fd948…2a55', ts: '2026-05-20T03:00:00Z', actor: 'system' },
  { entryNo: 18420, type: 'VERIFIED', desc: 'SG-PDPA §26 verified for Pillar 6.2', ownHash: 'b5c6d7e8…2b3', prevHash: '0e7fd948…2a55', ts: '2026-05-20T01:14:11Z', actor: 'system' },
]

export const REJECTIONS = {
  total: 77,
  byGate: [
    { gate: 'G1 — Official source', count: 8, pct: 10, color: '#2563EB' },
    { gate: 'G2 — Current law status', count: 11, pct: 14, color: '#0EA5E9' },
    { gate: 'G3 — OCR / text integrity', count: 18, pct: 23, color: '#F59E0B' },
    { gate: 'G4 — Section boundary', count: 9, pct: 12, color: '#7C3AED' },
    { gate: 'G5 — Retrieval support', count: 6, pct: 8, color: '#14B8A6' },
    { gate: 'G6 — Predicate completeness', count: 14, pct: 18, color: '#EF4444' },
    { gate: 'G7 — RDTII mapping', count: 7, pct: 9, color: '#DB2777' },
    { gate: 'G8 — Conflict check', count: 4, pct: 6, color: '#64748B' },
  ],
  recent: [
    { clauseId: 'BD-SCAN-2019-p4', proposedPillar: 'Pillar 6.1', failedGate: 'G3 (OCR negation)', score: '0.58' },
    { clauseId: 'SG-PDPC-GUIDE-XFER', proposedPillar: 'Pillar 6.2', failedGate: 'G1 (Authority)', score: 'rank 3' },
    { clauseId: 'TH-PDPA-§28', proposedPillar: 'Pillar 6.1', failedGate: 'G6 (Exception lost)', score: '5/7' },
    { clauseId: 'BD-RETENTION-§21', proposedPillar: 'Pillar 6.2', failedGate: 'G7 (Wrong predicate)', score: '0.33' },
    { clauseId: 'SG-AI-DATA-DRAFT', proposedPillar: 'Pillar 7.5', failedGate: 'G2 (Draft)', score: '0.41' },
  ],
}

export const SEED_REGISTRY: Record<string, { url: string; status: 'ok' | 'warn' | 'err' }[]> = {
  BD: [
    { url: 'https://bdlaws.minlaw.gov.bd', status: 'ok' },
    { url: 'https://dpdt.portal.gov.bd', status: 'ok' },
    { url: 'https://btrc.gov.bd', status: 'warn' },
    { url: 'https://bcc.gov.bd', status: 'ok' },
  ],
  TH: [
    { url: 'https://ratchakitcha.soc.go.th', status: 'ok' },
    { url: 'https://pdpc.or.th', status: 'ok' },
    { url: 'https://etda.or.th', status: 'ok' },
  ],
  SG: [
    { url: 'https://sso.agc.gov.sg', status: 'ok' },
    { url: 'https://pdpc.gov.sg', status: 'ok' },
    { url: 'https://mci.gov.sg', status: 'ok' },
  ],
}

export const SAMPLE_CONFLICT = {
  clause: 'Cross-border transfer of biometric data',
  sources: [
    {
      label: 'A',
      instrument: 'BD-DSA-2018',
      title: 'Digital Security Act 2018',
      authority: 'Primary',
      date: '2018-10-08',
      verbatim: 'Any person…shall not save such data…outside the geographic boundaries of Bangladesh.',
      classification: 'Pillar 6.1 — Data Localization Requirement',
      hash: 'a3f57c2e…b9c2',
    },
    {
      label: 'B',
      instrument: 'BD-PDPA-2023D',
      title: 'Personal Data Protection Act 2023 (Draft)',
      authority: 'Amending',
      date: '2023-08-14',
      verbatim: 'A data controller may transfer personal data outside Bangladesh provided the recipient jurisdiction offers an adequate level of protection…',
      classification: 'Pillar 6.2 — Conditional Cross-Border Transfer',
      hash: 'b8e91f24…a3b5',
    },
  ],
  recommendation: {
    winner: 'B',
    rationale: 'Amending instrument with a later effective date (2023-08-14 > 2018-10-08) supersedes the original prohibition for affected provisions.',
  },
}

// ===========================================================
// Pipeline Data Types (Pages 6–10)
// ===========================================================

export interface PipelineStep {
  id: string
  label: string
  status: 'done' | 'active' | 'queued' | 'failed'
  completedAt?: string
  pages?: number
  docs?: number
  progress?: number
}

export interface PipelineRun {
  id: string
  name: string
  jurisdiction: string
  startedAt: string
  status: 'active' | 'complete' | 'failed'
  currentStep: string
  steps: PipelineStep[]
}

export interface CrawlItem {
  id: string
  url: string
  status: 'fetched' | 'skipped' | 'blocked'
  type: string
  size: string
  confidence: number | null
  ts: string
  note?: string
  authority?: 'official' | 'government' | 'context' | 'blocked'
  resolver?: string
}

export interface HarvestedDoc {
  id: string
  type: string
  title: string
  url: string
  pages: number | null
  size: string
  lang: string
  jurisdiction: string
  confidence: number
  flags: string[]
  keep: boolean
}

export interface OcrCandidate {
  model: string
  text: string
  confidence: number
}

export interface OcrRegion {
  id: string
  status: 'agree' | 'disagree'
  lang: string
  confidence: number
  editDistance?: number
  qwen: string
  tesseract: string
  resolved?: string
  candidateA?: OcrCandidate
  candidateB?: OcrCandidate
}

export interface OcrConsensus {
  docId: string
  docTitle: string
  page: number
  totalRegions: number
  agreed: number
  disagreed: number
  regions: OcrRegion[]
}

export interface MappingClause {
  id: string
  ref: string
  text: string
  pillar: string
  pillarLabel: string
  gates: ('pass' | 'warn' | 'fail')[]
  scores: string[]
  status: 'verified' | 'rejected'
  ts: string
  model: string
  escalated?: boolean
  rejectedGate?: string
  predicate?: LegalPredicateTuple
  gatesV2?: VerificationGateV2[]
  abstained?: boolean
  counterEvidence?: number
  sourceStatus?: string
}

export interface TraceHighlight {
  id: string
  pillar: string
  color: string
  textLabel: string
  ref: string
  page: number
  status: 'verified' | 'pending'
  confidence: number
  matchType: 'exact' | 'fuzzy' | 'approximate'
  extractedText: string
}

// ===========================================================
// Pipeline Data (Pages 6–10)
// ===========================================================

export const PIPELINE_RUNS: PipelineRun[] = [
  {
    id: 'run-BD-001',
    name: 'Bangladesh · Full re-ingest',
    jurisdiction: 'BD',
    startedAt: '2026-05-23T09:12:00Z',
    status: 'active',
    currentStep: 'separate',
    steps: [
      { id: 'discover', label: 'Discover',  status: 'done',   completedAt: '2026-05-23T09:14:32Z', pages: 52 },
      { id: 'harvest',  label: 'Harvest',   status: 'done',   completedAt: '2026-05-23T09:18:44Z', docs: 14  },
      { id: 'separate', label: 'Separate',  status: 'active', progress: 67 },
      { id: 'convert',  label: 'Convert',   status: 'queued' },
      { id: 'ocr',      label: 'OCR',       status: 'queued' },
      { id: 'embed',    label: 'Embed',     status: 'queued' },
      { id: 'map',      label: 'Map',       status: 'queued' },
      { id: 'verify',   label: 'Verify',    status: 'queued' },
    ],
  },
]

export const CRAWL_STREAM: CrawlItem[] = [
  { id: 'cs-01', url: 'https://sso.agc.gov.sg/Act/PDPA2012',              status: 'fetched',  type: 'html',        size: '312 KB', confidence: 0.99, ts: '09:12:04', authority: 'official', resolver: 'current consolidated statute' },
  { id: 'cs-02', url: 'https://sso.agc.gov.sg/Acts-Supp/40-2020',         status: 'fetched',  type: 'html',        size: '94 KB',  confidence: 0.94, ts: '09:12:05', authority: 'official', resolver: 'amendment applied' },
  { id: 'cs-03', url: 'https://www.pdpc.gov.sg/help-and-resources',       status: 'fetched',  type: 'html',        size: '188 KB', confidence: 0.87, ts: '09:12:07', authority: 'context', resolver: 'guideline downgraded' },
  { id: 'cs-04', url: 'https://pdpc.gov.sg/consultations/draft-safeguards', status: 'fetched', type: 'html',        size: '72 KB',  confidence: 0.64, ts: '09:12:08', authority: 'context', resolver: 'draft excluded' },
  { id: 'cs-05', url: 'https://bdlaws.minlaw.gov.bd/act-1261.html',       status: 'fetched',  type: 'html',        size: '142 KB', confidence: 0.96, ts: '09:12:11', authority: 'official', resolver: 'binding statute' },
  { id: 'cs-06', url: 'https://btrc.gov.bd/circulars/2019-data.pdf',      status: 'fetched',  type: 'scanned-pdf', size: '4.7 MB', confidence: 0.72, ts: '09:12:14', authority: 'government', resolver: 'OCR risk queued' },
  { id: 'cs-07', url: 'https://ratchakitcha.soc.go.th/pdpa-2019.pdf',     status: 'fetched',  type: 'scanned-pdf', size: '6.5 MB', confidence: 0.82, ts: '09:12:16', authority: 'official', resolver: 'Thai official gazette' },
  { id: 'cs-08', url: 'https://pdpc.or.th/pdpa-summary-en.pdf',           status: 'fetched',  type: 'native-pdf',  size: '1.2 MB', confidence: 0.58, ts: '09:12:18', authority: 'context', resolver: 'translation/context only' },
  { id: 'cs-09', url: 'https://moca.gov.bd/login.php',                    status: 'blocked',  type: 'login-wall',  size: '—',      confidence: null, ts: '09:12:21', note: 'Login-walled — needs manual retrieval', authority: 'blocked', resolver: 'manual acquisition' },
  { id: 'cs-10', url: 'https://bcc.gov.bd/captcha-gate/',                 status: 'blocked',  type: 'captcha',     size: '—',      confidence: null, ts: '09:12:24', note: 'CAPTCHA detected — cannot bypass', authority: 'blocked', resolver: 'blocked by policy' },
  { id: 'cs-11', url: 'https://example.org/sg-pdpa-translation',          status: 'fetched',  type: 'html',        size: '51 KB',  confidence: 0.44, ts: '09:12:28', authority: 'context', resolver: 'unofficial translation' },
  { id: 'cs-12', url: 'https://dpdt.portal.gov.bd/draft-pdpa-2023.pdf',   status: 'fetched',  type: 'native-pdf',  size: '1.4 MB', confidence: 0.71, ts: '09:12:31', authority: 'context', resolver: 'draft tracked, not cited' },
]

export const HARVESTED_DOCS: HarvestedDoc[] = [
  { id: 'hd-001', type: 'native-pdf',  title: 'Digital Security Act 2018',                url: 'https://bdlaws.minlaw.gov.bd/act-1261.pdf',          pages: 42,  size: '2.1 MB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.97, flags: [],               keep: true  },
  { id: 'hd-002', type: 'native-pdf',  title: 'Personal Data Protection Act 2023 (Draft)',url: 'https://dpdt.portal.gov.bd/draft-pdpa-2023.pdf',     pages: 28,  size: '1.4 MB',  lang: 'Bengali · English', jurisdiction: 'BD', confidence: 0.94, flags: ['draft'],         keep: true  },
  { id: 'hd-003', type: 'native-pdf',  title: 'ICT Act 2006',                             url: 'https://bdlaws.minlaw.gov.bd/act-950.pdf',           pages: 58,  size: '3.2 MB',  lang: 'English · Bengali', jurisdiction: 'BD', confidence: 0.88, flags: [],               keep: true  },
  { id: 'hd-004', type: 'scanned-pdf', title: 'BTRC Data Circular 2019 (scanned)',        url: 'https://btrc.gov.bd/circulars/2019-data.pdf',        pages: 8,   size: '4.7 MB',  lang: 'Bengali',           jurisdiction: 'BD', confidence: 0.72, flags: [],               keep: true  },
  { id: 'hd-005', type: 'scanned-pdf', title: 'Ministry Gazette 2022 — Amendments',       url: 'https://mopa.gov.bd/gazette/2022-amend.pdf',         pages: 12,  size: '6.1 MB',  lang: 'Bengali',           jurisdiction: 'BD', confidence: 0.61, flags: [],               keep: false },
  { id: 'hd-006', type: 'html',        title: 'BTRC Guidelines — Data Storage 2024',      url: 'https://btrc.gov.bd/guidelines/data-storage-2024',   pages: null, size: '118 KB', lang: 'English',           jurisdiction: 'BD', confidence: 0.91, flags: [],               keep: true  },
  { id: 'hd-007', type: 'html',        title: 'DPDT Press Release (March 2024)',           url: 'https://dpdt.portal.gov.bd/press/2024-03.html',      pages: null, size: '42 KB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.41, flags: ['press-release'], keep: false },
  { id: 'hd-008', type: 'html',        title: 'Bangladesh Law Commission — Data Policy',  url: 'https://blc.gov.bd/data-policy.html',                pages: null, size: '78 KB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.68, flags: [],               keep: true  },
  { id: 'hd-009', type: 'docx',        title: 'DSA Implementation Guidelines (Word)',     url: 'https://moca.gov.bd/docs/dsa-impl.docx',             pages: 18,  size: '890 KB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.85, flags: ['guideline'],     keep: true  },
  { id: 'hd-010', type: 'markdown',    title: 'BTRC — Summary of Data Requirements',      url: 'https://btrc.gov.bd/summary.md',                     pages: null, size: '24 KB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.76, flags: [],               keep: true  },
  { id: 'hd-011', type: 'table',       title: 'RDTII Indicator Mapping Table (CSV)',       url: 'https://dpdt.portal.gov.bd/rdtii-bd.csv',            pages: null, size: '12 KB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.93, flags: [],               keep: true  },
  { id: 'hd-012', type: 'html',        title: 'Digital Literacy Manual 2023',             url: 'https://ictd.gov.bd/manual-2023.html',               pages: null, size: '312 KB', lang: 'Bengali · English', jurisdiction: 'BD', confidence: 0.34, flags: ['irrelevant'],    keep: false },
  { id: 'hd-013', type: 'other',       title: 'BTRC Logo Pack (ZIP)',                     url: 'https://btrc.gov.bd/assets/logo.zip',                pages: null, size: '1.2 MB', lang: '—',                 jurisdiction: 'BD', confidence: 0.08, flags: ['irrelevant'],    keep: false },
  { id: 'hd-014', type: 'native-pdf',  title: 'Bangladesh E-Commerce Policy 2024',       url: 'https://moca.gov.bd/ecom-policy-2024.pdf',           pages: 24,  size: '1.1 MB',  lang: 'English',           jurisdiction: 'BD', confidence: 0.79, flags: [],               keep: true  },
]

export const OCR_CONSENSUS: OcrConsensus = {
  docId: 'BD-DSA-2018', docTitle: 'Digital Security Act 2018',
  page: 14, totalRegions: 48, agreed: 44, disagreed: 4,
  regions: [
    { id: 'r1',  status: 'agree',    lang: 'en', confidence: 0.99, qwen: 'Any person who, intentionally or knowingly without lawful authority,', tesseract: 'Any person who, intentionally or knowingly without lawful authority,' },
    { id: 'r2',  status: 'disagree', lang: 'en', confidence: 0.77, editDistance: 1, qwen: 'collects, sells, takes possession of, supplies or uses any', tesseract: 'col1ects, sells, takes possession of, supplies or uses any', resolved: 'collects, sells, takes possession of, supplies or uses any', candidateA: { model: 'Qwen2-VL', text: 'collects', confidence: 0.94 }, candidateB: { model: 'Tesseract', text: 'col1ects', confidence: 0.61 } },
    { id: 'r3',  status: 'agree',    lang: 'en', confidence: 0.98, qwen: "person's identity-related information, shall not save such data,", tesseract: "person's identity-related information, shall not save such data," },
    { id: 'r4',  status: 'disagree', lang: 'en', confidence: 0.77, editDistance: 2, qwen: 'including biometric information, photographs, financial records', tesseract: 'including biometric infomation, photographs, financial records', resolved: 'including biometric information, photographs, financial records', candidateA: { model: 'Qwen2-VL', text: 'information', confidence: 0.96 }, candidateB: { model: 'Tesseract', text: 'infomation', confidence: 0.58 } },
    { id: 'r5',  status: 'agree',    lang: 'en', confidence: 0.97, qwen: 'or registry information, outside the geographic boundaries of Bangladesh.', tesseract: 'or registry information, outside the geographic boundaries of Bangladesh.' },
    { id: 'r6',  status: 'agree',    lang: 'bn', confidence: 0.89, qwen: 'যে কোনো ব্যক্তি যিনি ইচ্ছাকৃতভাবে বা জেনেশুনে বৈধ কর্তৃত্ব ব্যতীত', tesseract: 'যে কোনো ব্যক্তি যিনি ইচ্ছাকৃতভাবে বা জেনেশুনে বৈধ কর্তৃত্ব ব্যতীত' },
    { id: 'r7',  status: 'disagree', lang: 'bn', confidence: 0.79, editDistance: 1, qwen: 'সংগ্রহ করে, বিক্রয় করে, দখলে নেয়, সরবরাহ করে বা ব্যবহার করে', tesseract: 'সংগ্ৰহ করে, বিক্রয় করে, দখলে নেয়, সরবরাহ করে বা ব্যবহার করে', resolved: 'সংগ্রহ করে, বিক্রয় করে, দখলে নেয়, সরবরাহ করে বা ব্যবহার করে', candidateA: { model: 'Qwen2-VL', text: 'সংগ্রহ', confidence: 0.91 }, candidateB: { model: 'Tesseract', text: 'সংগ্ৰহ', confidence: 0.67 } },
    { id: 'r8',  status: 'agree',    lang: 'bn', confidence: 0.93, qwen: 'কোনো ব্যক্তির পরিচয়-সংক্রান্ত তথ্য, বাংলাদেশের ভৌগোলিক সীমানার বাইরে সংরক্ষণ করবেন না।', tesseract: 'কোনো ব্যক্তির পরিচয়-সংক্রান্ত তথ্য, বাংলাদেশের ভৌগোলিক সীমানার বাইরে সংরক্ষণ করবেন না।' },
    { id: 'r9',  status: 'disagree', lang: 'bn', confidence: 0.71, editDistance: 3, qwen: 'আইনগত কর্তৃপক্ষ ছাড়া বায়োমেট্রিক তথ্য সংগ্রহ করা নিষিদ্ধ।', tesseract: 'আইনগত কর্তৃপক্ষ ছাড়া বাযোমেট্রিক তথ্য সংগ্রহ করা নিষিদ্ধ।', resolved: 'আইনগত কর্তৃপক্ষ ছাড়া বায়োমেট্রিক তথ্য সংগ্রহ করা নিষিদ্ধ।', candidateA: { model: 'Qwen2-VL', text: 'বায়োমেট্রিক', confidence: 0.88 }, candidateB: { model: 'Tesseract', text: 'বাযোমেট্রিক', confidence: 0.54 } },
    { id: 'r10', status: 'agree',    lang: 'en', confidence: 0.96, qwen: 'Punishment: imprisonment for a term not exceeding seven (7) years', tesseract: 'Punishment: imprisonment for a term not exceeding seven (7) years' },
  ],
}

export const MAPPING_STREAM: MappingClause[] = [
  {
    id: 'ms-001',
    ref: 'SG s 26(1)',
    text: EVIDENCE_AUDIT_CASE.highlightedSpan,
    pillar: '6.2',
    pillarLabel: 'Conditional cross-border transfer',
    gates: ['pass','pass','pass','pass','pass','pass','pass','warn'],
    scores: ['rank1','0.98','0 edits','0.96','1/20','7/7','0.93','context'],
    status: 'verified',
    ts: '09:22:01',
    model: 'Qwen2.5-7B-Instruct',
    predicate: EVIDENCE_AUDIT_CASE.predicate,
    gatesV2: EVIDENCE_AUDIT_CASE.gatesV2,
    counterEvidence: 1,
    sourceStatus: 'binding_current',
  },
  {
    id: 'ms-002',
    ref: 'SG s 24',
    text: 'An organisation shall protect personal data in its possession or under its control by making reasonable security arrangements.',
    pillar: '7.5',
    pillarLabel: 'Security / accountability obligation',
    gates: ['pass','pass','pass','pass','pass','pass','pass','pass'],
    scores: ['rank1','0.97','0 edits','0.94','2/20','7/7','0.89','none'],
    status: 'verified',
    ts: '09:22:04',
    model: 'Qwen2.5-7B-Instruct',
    predicate: {
      subject: 'organisation',
      action: 'protect personal data',
      object: 'personal data in possession or control',
      modality: 'shall',
      condition: 'reasonable security arrangements are required',
      exception: 'none detected',
      legalEffect: 'domestic data protection accountability obligation',
      rdtiiIndicator: '7.5',
      confidence: 0.89,
    },
    gatesV2: EIGHT_VERIFICATION_GATES.map((g) => ({ ...g, status: 'pass', score: g.id === 'G7' ? '0.89' : g.score })),
    counterEvidence: 0,
    sourceStatus: 'binding_current',
  },
  {
    id: 'ms-003',
    ref: 'SG guideline 7.3',
    text: 'The advisory guideline explains how organisations may use contractual clauses for overseas transfers.',
    pillar: '6.2',
    pillarLabel: 'Conditional cross-border transfer',
    gates: ['fail','warn','pass','pass','pass','pass','warn','pass'],
    scores: ['rank3','context','0 edits','0.91','4/20','6/7','0.77','context'],
    status: 'rejected',
    ts: '09:22:08',
    model: 'Qwen2.5-7B-Instruct',
    rejectedGate: 'G1',
    abstained: true,
    counterEvidence: 1,
    sourceStatus: 'context_only',
  },
  {
    id: 'ms-004',
    ref: 'TH s 28',
    text: 'Personal data may be transferred to a foreign country where the destination country has adequate data protection standards, except where exemptions apply.',
    pillar: '6.2',
    pillarLabel: 'Conditional cross-border transfer',
    gates: ['pass','pass','warn','warn','pass','pass','pass','warn'],
    scores: ['rank1','0.92','CER 2.4','0.86','3/20','7/7','0.88','exception'],
    status: 'verified',
    ts: '09:22:11',
    model: 'Qwen2.5-7B-Instruct',
    predicate: {
      subject: 'data controller',
      action: 'transfer personal data abroad',
      object: 'personal data',
      modality: 'may',
      condition: 'destination country has adequate protection standards',
      exception: 'statutory exemptions may apply',
      legalEffect: 'conditional cross-border transfer regime',
      rdtiiIndicator: '6.2',
      confidence: 0.88,
    },
    gatesV2: EIGHT_VERIFICATION_GATES.map((g) => g.id === 'G3' || g.id === 'G4' || g.id === 'G8' ? { ...g, status: 'warn', score: g.id === 'G3' ? 'CER 2.4' : g.score } : { ...g, status: 'pass' }),
    counterEvidence: 1,
    sourceStatus: 'binding_current',
  },
  {
    id: 'ms-005',
    ref: 'BD scan p4',
    text: 'OCR candidate reads "shall transfer" while the visual model reads "shall not transfer" in a Bengali scanned circular.',
    pillar: '6.1',
    pillarLabel: 'Possible localization / transfer restriction',
    gates: ['pass','warn','fail','warn','pass','warn','warn','warn'],
    scores: ['gov','review','0.58','0.71','6/20','5/7','0.61','open'],
    status: 'rejected',
    ts: '09:22:14',
    model: 'PaddleOCR + Qwen2-VL',
    rejectedGate: 'G3',
    abstained: true,
    escalated: true,
    counterEvidence: 2,
    sourceStatus: 'requires_review',
  },
  {
    id: 'ms-006',
    ref: 'SG s 20',
    text: 'An organisation shall inform the individual of the purposes for which personal data will be collected, used or disclosed.',
    pillar: '7.2',
    pillarLabel: 'Notice / purpose limitation',
    gates: ['pass','pass','pass','pass','pass','pass','pass','pass'],
    scores: ['rank1','0.98','0 edits','0.95','2/20','7/7','0.91','none'],
    status: 'verified',
    ts: '09:22:17',
    model: 'Qwen2.5-7B-Instruct',
    counterEvidence: 0,
    sourceStatus: 'binding_current',
  },
  {
    id: 'ms-007',
    ref: 'SG s 26(1) alt',
    text: 'A naive classifier proposes absolute data localization because the first phrase says "shall not transfer".',
    pillar: '6.1',
    pillarLabel: 'Data localization requirement',
    gates: ['pass','pass','pass','pass','pass','fail','fail','warn'],
    scores: ['rank1','0.98','0 edits','0.96','1/20','exception','0.34','context'],
    status: 'rejected',
    ts: '09:22:20',
    model: 'Qwen2.5-7B-Instruct',
    rejectedGate: 'G6',
    abstained: true,
    counterEvidence: 1,
    sourceStatus: 'binding_current',
  },
  {
    id: 'ms-008',
    ref: 'BD retention §21',
    text: 'The controller shall retain personal data only for the period necessary for the stated purpose.',
    pillar: '7.2',
    pillarLabel: 'Retention / purpose limitation',
    gates: ['pass','pass','pass','pass','pass','pass','pass','pass'],
    scores: ['rank1','0.93','CER 1.2','0.90','5/20','7/7','0.86','none'],
    status: 'verified',
    ts: '09:22:24',
    model: 'Qwen2.5-7B-Instruct',
    counterEvidence: 0,
    sourceStatus: 'binding_current',
  },
]

export const TRACE_HIGHLIGHTS: TraceHighlight[] = [
  { id: 'th-001', pillar: '6.1', color: '#0FB5A7', textLabel: 'Data Localization',       ref: '§26(1)', page: 14, status: 'verified', confidence: 0.94, matchType: 'exact',       extractedText: "Any person who, intentionally or knowingly without lawful authority, collects, sells, takes possession of, supplies or uses any person's identity-related information, shall not save such data, including biometric information, photographs, financial records or registry information, outside the geographic boundaries of Bangladesh." },
  { id: 'th-002', pillar: '7.1', color: '#2563EB', textLabel: 'Lawful Basis',            ref: '§12(3)', page: 8,  status: 'verified', confidence: 0.96, matchType: 'exact',       extractedText: 'No person shall process personal data without the explicit consent of the data subject, except as provided under sections 14, 15 and 18 of this Act.' },
  { id: 'th-003', pillar: '7.2', color: '#7C3AED', textLabel: 'Purpose Limitation',      ref: '§14(1)', page: 9,  status: 'verified', confidence: 0.92, matchType: 'exact',       extractedText: 'Data collected for a specific purpose shall not be used for any other purpose without the express consent of the data subject, unless required by law.' },
  { id: 'th-004', pillar: '7.3', color: '#DB2777', textLabel: 'Data Subject Rights',     ref: '§21(1)', page: 12, status: 'verified', confidence: 0.94, matchType: 'exact',       extractedText: 'A data subject shall have the right to obtain confirmation of whether personal data concerning them is being processed, and where that is the case, access to that data.' },
  { id: 'th-005', pillar: '7.4', color: '#F59E0B', textLabel: 'Breach Notification',     ref: '§35(1)', page: 19, status: 'verified', confidence: 0.88, matchType: 'exact',       extractedText: 'The controller shall notify the supervisory authority of a personal data breach without undue delay and, where feasible, not later than seventy-two hours after having become aware of it.' },
  { id: 'th-006', pillar: '8.1', color: '#10B981', textLabel: 'Critical Infrastructure', ref: '§3(1)',  page: 2,  status: 'verified', confidence: 0.89, matchType: 'exact',       extractedText: 'The Digital Security Agency shall be responsible for the protection of critical digital infrastructure and national security against digital threats and cyberattacks.' },
  { id: 'th-007', pillar: '8.2', color: '#059669', textLabel: 'Incident Reporting',      ref: '§33(2)', page: 18, status: 'verified', confidence: 0.78, matchType: 'fuzzy',       extractedText: 'Any person who commits hacking or any illegal access to a computer system with intent to commit another offence under this Act shall be punished accordingly.' },
  { id: 'th-008', pillar: '6.2', color: '#06B6D4', textLabel: 'Conditional Transfer',    ref: '§29(1)', page: 15, status: 'pending',  confidence: 0.67, matchType: 'approximate', extractedText: 'Cross-border transfer of personal data may be permitted subject to the prior approval of the competent authority and the existence of adequate safeguards.' },
]

export function makeMatrixData(): Record<string, Record<string, MatrixCell>> {
  return {
    BD: {
      '6.1': { status: 'verified', count: 7, conflict: false },
      '6.2': { status: 'partial', count: 4, conflict: false },
      '6.3': { status: 'rejected', count: 2, conflict: false },
      '6.4': { status: 'verified', count: 5, conflict: false },
      '7.1': { status: 'verified', count: 6, conflict: false },
      '7.2': { status: 'verified', count: 4, conflict: false },
      '7.3': { status: 'pending', count: 3, conflict: false },
      '7.4': { status: 'partial', count: 3, conflict: false },
      '7.5': { status: 'rejected', count: 1, conflict: false },
      '8.1': { status: 'verified', count: 3, conflict: false },
      '8.2': { status: 'conflict', count: 4, conflict: true },
    },
    TH: {
      '6.1': { status: 'verified', count: 5, conflict: false },
      '6.2': { status: 'verified', count: 7, conflict: false },
      '6.3': { status: 'verified', count: 3, conflict: false },
      '6.4': { status: 'verified', count: 6, conflict: false },
      '7.1': { status: 'verified', count: 8, conflict: false },
      '7.2': { status: 'verified', count: 6, conflict: false },
      '7.3': { status: 'verified', count: 5, conflict: false },
      '7.4': { status: 'verified', count: 4, conflict: false },
      '7.5': { status: 'partial', count: 3, conflict: false },
      '8.1': { status: 'verified', count: 4, conflict: false },
      '8.2': { status: 'conflict', count: 5, conflict: true },
    },
    SG: {
      '6.1': { status: 'verified', count: 8, conflict: false },
      '6.2': { status: 'verified', count: 9, conflict: false },
      '6.3': { status: 'verified', count: 6, conflict: false },
      '6.4': { status: 'verified', count: 7, conflict: false },
      '7.1': { status: 'verified', count: 9, conflict: false },
      '7.2': { status: 'verified', count: 7, conflict: false },
      '7.3': { status: 'verified', count: 8, conflict: false },
      '7.4': { status: 'verified', count: 6, conflict: false },
      '7.5': { status: 'verified', count: 5, conflict: false },
      '8.1': { status: 'verified', count: 5, conflict: false },
      '8.2': { status: 'verified', count: 6, conflict: false },
      '9.1': { status: 'verified', count: 3, conflict: false },
      '9.2': { status: 'pending', count: 1, conflict: false },
    },
  }
}
