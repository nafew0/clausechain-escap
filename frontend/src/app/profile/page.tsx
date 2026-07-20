import ProtectedRoute from '@/components/ProtectedRoute'
import Profile from '@/views/Profile'

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      <Profile />
    </ProtectedRoute>
  )
}
