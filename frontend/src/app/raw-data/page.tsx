import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import RawDataExplorer from '@/views/RawDataExplorer'
export const metadata = { title: 'Raw Data — ClauseChain' }
export default function RawDataPage() { return <ProtectedRoute><Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Raw Data' }]}><div className="run-page-state">Loading…</div></WorkspaceShell>}><ModeRoute><RawDataExplorer /></ModeRoute></Suspense></ProtectedRoute> }
