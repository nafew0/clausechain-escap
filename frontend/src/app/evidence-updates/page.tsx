import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import EvidenceUpdates from '@/views/EvidenceUpdates'

export default function EvidenceUpdatesPage() {
  return <ProtectedRoute><Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Evidence Updates' }]}><div className="run-page-state">Loading…</div></WorkspaceShell>}><ModeRoute><EvidenceUpdates /></ModeRoute></Suspense></ProtectedRoute>
}
