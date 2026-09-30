import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import ModelComparison from '@/views/ModelComparison'

export default function ComparisonPage() {
  return <ProtectedRoute><Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Model Comparison' }]}><PageLoader label="Loading the model comparison" /></WorkspaceShell>}><ModelComparison /></Suspense></ProtectedRoute>
}
