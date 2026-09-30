import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import ModelComparison from '@/views/ModelComparison'

export default function ComparisonPage() {
  return <ProtectedRoute><Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Model Comparison' }]}><div className="run-page-state">Loading…</div></WorkspaceShell>}><ModelComparison /></Suspense></ProtectedRoute>
}
