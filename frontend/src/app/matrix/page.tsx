import ProtectedRoute from '@/components/ProtectedRoute'
import RDTIIMatrix from '@/views/RDTIIMatrix'

export default function MatrixPage() {
  return (
    <ProtectedRoute>
      <RDTIIMatrix />
    </ProtectedRoute>
  )
}
