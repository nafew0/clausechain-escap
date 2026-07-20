import {
  Activity,
  BookOpen,
  Braces,
  ClipboardCheck,
  FileCheck2,
  FileText,
  Gauge,
  Globe,
  LayoutDashboard,
  Layers,
  Network,
  Share2,
  ShieldCheck,
  Table2,
  Wifi,
  GitBranch,
  type LucideIcon,
} from 'lucide-react'

export type WorkspaceNavState = 'live' | 'readonly' | 'prototype'

export interface WorkspaceNavItem {
  href: string
  icon: LucideIcon
  label: string
  state: WorkspaceNavState
  section: 'workspace' | 'pipeline'
}

export const WORKSPACE_NAV_ITEMS: WorkspaceNavItem[] = [
  { href: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', state: 'live', section: 'workspace' },
  { href: '/review', icon: ClipboardCheck, label: 'Review', state: 'live', section: 'workspace' },
  { href: '/submission', icon: FileCheck2, label: 'RDTII Dataset', state: 'live', section: 'workspace' },
  { href: '/runs', icon: Activity, label: 'Runs', state: 'live', section: 'workspace' },
  { href: '/jurisdictions/sg/documents/SG-PDPA-2012', icon: ShieldCheck, label: 'Evidence Audit', state: 'prototype', section: 'workspace' },
  { href: '/source-status', icon: Network, label: 'Source Status', state: 'prototype', section: 'workspace' },
  { href: '/benchmark', icon: Gauge, label: 'Benchmark', state: 'prototype', section: 'workspace' },
  { href: '/matrix', icon: Table2, label: 'RDTII Matrix', state: 'prototype', section: 'workspace' },
  { href: '/ledger', icon: BookOpen, label: 'Ledger', state: 'live', section: 'workspace' },
  { href: '/raw-data', icon: Braces, label: 'Raw Data', state: 'live', section: 'workspace' },
  { href: '/knowledge-graph', icon: Share2, label: 'Knowledge Graph', state: 'readonly', section: 'workspace' },
  { href: '/jurisdictions', icon: Globe, label: 'Source Library', state: 'readonly', section: 'workspace' },
  { href: '/pipeline/crawl', icon: Wifi, label: 'Source Acquisition', state: 'live', section: 'pipeline' },
  { href: '/pipeline/harvest', icon: Layers, label: 'Corpus Eligibility', state: 'live', section: 'pipeline' },
  { href: '/pipeline/extract', icon: FileText, label: 'Extraction', state: 'live', section: 'pipeline' },
  { href: '/pipeline/trace', icon: GitBranch, label: 'Source Trace', state: 'prototype', section: 'pipeline' },
]

export const PUBLIC_NAV_ITEMS = [
  { href: '/#overview', label: 'Overview' },
  { href: '/#evidence-flow', label: 'Evidence flow' },
  { href: '/#verification', label: 'Verification' },
  { href: '/#architecture', label: 'Architecture' },
] as const

export function workspaceItemIsActive(pathname: string, href: string) {
  if (href === '/jurisdictions') {
    return pathname === href || /^\/jurisdictions\/[^/]+$/.test(pathname)
  }
  return pathname === href || (href !== '/dashboard' && pathname.startsWith(`${href}/`))
}
