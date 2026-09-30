import { Suspense } from 'react'

import ProtectedRoute from '@/components/ProtectedRoute'
import RDTIIMatrix from '@/views/RDTIIMatrix'

export default function MatrixPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<div className="run-page-state">Loading matrix…</div>}>
        <RDTIIMatrix />
      </Suspense>
    </ProtectedRoute>
  )
}
