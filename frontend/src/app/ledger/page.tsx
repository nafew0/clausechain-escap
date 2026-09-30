import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceShell from '@/components/clausechain/WorkspaceShell'
import { ModeRoute } from '@/components/workspace/RunModeTabs'
import PipelineLedger from '@/views/PipelineLedger'

export default function LedgerPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<WorkspaceShell breadcrumbs={[{ label: 'Audit Ledger' }]}><PageLoader label="Loading the audit ledger" /></WorkspaceShell>}>
        <ModeRoute><PipelineLedger /></ModeRoute>
      </Suspense>
    </ProtectedRoute>
  )
}
