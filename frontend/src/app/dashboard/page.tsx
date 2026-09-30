import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import WorkspaceDashboard from '@/views/WorkspaceDashboard'

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Dashboard' }]}><PageLoader label="Loading the dashboard" /></WorkspaceShell>}>
        <ModeRoute><WorkspaceDashboard /></ModeRoute>
      </Suspense>
    </ProtectedRoute>
  )
}
