import ProtectedRoute from '@/components/ProtectedRoute'
import PipelineLedger from '@/views/PipelineLedger'

export default function LedgerPage() {
  return (
    <ProtectedRoute>
      <PipelineLedger />
    </ProtectedRoute>
  )
}
