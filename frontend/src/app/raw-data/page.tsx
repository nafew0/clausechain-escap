import ProtectedRoute from '@/components/ProtectedRoute'
import RawDataExplorer from '@/views/RawDataExplorer'
export const metadata = { title: 'Raw Data — ClauseChain' }
export default function RawDataPage() { return <ProtectedRoute><RawDataExplorer /></ProtectedRoute> }
