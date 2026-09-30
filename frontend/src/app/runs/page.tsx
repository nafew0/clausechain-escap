import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import RunsWorkbench from '@/components/runs/RunsWorkbench'

export default function RunsPage() {
  return <ProtectedRoute><WorkspaceShell breadcrumbs={[{ label: 'Runs' }]}><Suspense fallback={<div className="run-page-state">Loading runs…</div>}><RunsWorkbench /></Suspense></WorkspaceShell></ProtectedRoute>
}
