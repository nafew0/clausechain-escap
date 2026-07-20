import ProtectedRoute from '@/components/ProtectedRoute'
import DocumentWorkspace from '@/views/DocumentWorkspace'

interface Props {
  params: Promise<{ country: string; docId: string }>
}

export default async function DocumentPage({ params }: Props) {
  const { country, docId } = await params
  return (
    <ProtectedRoute>
      <DocumentWorkspace country={country} docId={docId} />
    </ProtectedRoute>
  )
}
