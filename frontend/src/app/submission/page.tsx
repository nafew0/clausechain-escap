import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import SubmissionExplorer from '@/components/submission/SubmissionExplorer'
import { SnapshotBanner } from '@/components/workspace/SnapshotBanner'

export default function SubmissionPage() {
  return <ProtectedRoute><WorkspaceShell breadcrumbs={[{ label: 'RDTII Dataset' }]}><SnapshotBanner /><Suspense fallback={<div className="submission-page-state" />}><SubmissionExplorer /></Suspense></WorkspaceShell></ProtectedRoute>
}
