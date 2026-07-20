import { Suspense } from 'react'
import ProtectedRoute from '@/components/ProtectedRoute'
import SourceLibrary from '@/views/SourceLibrary'
import AdminLoadingState from '@/components/AdminLoadingState'

export default function JurisdictionsIndexPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<AdminLoadingState message="Loading source configuration…" />}><SourceLibrary /></Suspense>
    </ProtectedRoute>
  )
}
