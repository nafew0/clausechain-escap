import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import RawDataExplorer from '@/views/RawDataExplorer'
export const metadata = { title: 'Raw Data — ClauseChain' }
export default function RawDataPage() { return <ProtectedRoute><Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Raw Data' }]}><PageLoader label="Loading raw data" /></WorkspaceShell>}><ModeRoute><RawDataExplorer /></ModeRoute></Suspense></ProtectedRoute> }
