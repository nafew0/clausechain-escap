import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import EvidenceUpdates from '@/views/EvidenceUpdates'

export default function EvidenceUpdatesPage() {
  return <ProtectedRoute><Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Evidence Updates' }]}><PageLoader label="Loading evidence updates" /></WorkspaceShell>}><ModeRoute><EvidenceUpdates /></ModeRoute></Suspense></ProtectedRoute>
}
