import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import RunsWorkbench from '@/components/runs/RunsWorkbench'

export default function RunsPage() {
  return <ProtectedRoute><WorkspaceShell breadcrumbs={[{ label: 'Runs' }]}><Suspense fallback={<PageLoader label="Loading runs" />}><RunsWorkbench /></Suspense></WorkspaceShell></ProtectedRoute>
}
