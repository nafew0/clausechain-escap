import ProtectedRoute from '@/components/ProtectedRoute'
import WorkspaceDashboard from '@/views/WorkspaceDashboard'

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <WorkspaceDashboard />
    </ProtectedRoute>
  )
}
