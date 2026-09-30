import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import WorkspaceDashboard from '@/views/WorkspaceDashboard'

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Dashboard' }]}><div className="run-page-state">Loading…</div></WorkspaceShell>}>
        <ModeRoute><WorkspaceDashboard /></ModeRoute>
      </Suspense>
    </ProtectedRoute>
  )
}
