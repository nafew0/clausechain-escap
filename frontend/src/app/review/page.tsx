import ProtectedRoute from '@/components/ProtectedRoute'
import ReviewWorkbench from '@/components/review/ReviewWorkbench'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { SnapshotBanner } from '@/components/workspace/SnapshotBanner'

export default function ReviewPage() {
  return (
    <ProtectedRoute>
      <WorkspaceShell breadcrumbs={[{ label: 'Review & approve' }]} contentMode="contained">
        <SnapshotBanner />
        <Suspense fallback={<div className="review-canvas-loading" aria-label="Loading review workspace" />}>
          <ReviewWorkbench />
        </Suspense>
      </WorkspaceShell>
    </ProtectedRoute>
  )
}
import { Suspense } from 'react'
