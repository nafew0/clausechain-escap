import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import SourceMatchWorkbench from '@/components/match/SourceMatchWorkbench'

export default async function SourceMatchPage({ params }: PageProps<'/match/[findingKey]'>) {
  const { findingKey } = await params
  return (
    <ProtectedRoute>
      <WorkspaceShell breadcrumbs={[{ label: 'Review', href: '/review' }, { label: 'Source Match' }]}>
        <Suspense fallback={<div className="match-page-state" aria-label="Loading Source Match" />}>
          <SourceMatchWorkbench findingKey={findingKey} />
        </Suspense>
      </WorkspaceShell>
    </ProtectedRoute>
  )
}
