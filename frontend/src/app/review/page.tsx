import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import ReviewWorkbench from '@/components/review/ReviewWorkbench'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'

export default function ReviewPage() {
  return (
    <ProtectedRoute>
      <WorkspaceShell breadcrumbs={[{ label: 'Review & approve' }]} contentMode="contained">
        <Suspense fallback={<PageLoader variant="screen" label="Loading the review workspace" />}>
          <ModeRoute><ReviewWorkbench /></ModeRoute>
        </Suspense>
      </WorkspaceShell>
    </ProtectedRoute>
  )
}
