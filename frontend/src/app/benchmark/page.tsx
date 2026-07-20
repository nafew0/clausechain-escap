import ProtectedRoute from '@/components/ProtectedRoute'
import BenchmarkDashboard from '@/views/BenchmarkDashboard'

export default function BenchmarkPage() {
  return (
    <ProtectedRoute>
      <BenchmarkDashboard />
    </ProtectedRoute>
  )
}
