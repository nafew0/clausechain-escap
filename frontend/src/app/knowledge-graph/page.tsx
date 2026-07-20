import ProtectedRoute from '@/components/ProtectedRoute'
import KnowledgeGraph from '@/views/KnowledgeGraph'
export const metadata = { title: 'Knowledge Graph — ClauseChain' }
export default function KnowledgeGraphPage() { return <ProtectedRoute><KnowledgeGraph /></ProtectedRoute> }
