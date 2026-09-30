import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import SubmissionExplorer from '@/components/submission/SubmissionExplorer'
import { ModeRoute } from '@/components/workspace/RunModeTabs'

export default function SubmissionPage() {
  return <ProtectedRoute><WorkspaceShell breadcrumbs={[{ label: 'RDTII Dataset' }]}><Suspense fallback={<PageLoader label="Loading the RDTII dataset" />}><ModeRoute><SubmissionExplorer /></ModeRoute></Suspense></WorkspaceShell></ProtectedRoute>
}
