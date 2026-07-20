import ProtectedRoute from '@/components/ProtectedRoute'
import SourceStatusGraph from '@/views/SourceStatusGraph'

export default function SourceStatusPage() {
  return (
    <ProtectedRoute>
      <SourceStatusGraph />
    </ProtectedRoute>
  )
}
