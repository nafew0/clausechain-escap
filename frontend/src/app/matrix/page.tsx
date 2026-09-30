import { Suspense } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'

import ProtectedRoute from '@/components/ProtectedRoute'
import RDTIIMatrix from '@/views/RDTIIMatrix'

export default function MatrixPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<PageLoader variant="screen" label="Loading the RDTII matrix" />}>
        <RDTIIMatrix />
      </Suspense>
    </ProtectedRoute>
  )
}
