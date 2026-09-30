import { PageLoader } from '@/components/clausechain/PageLoader'

export default function AdminLoadingState({
  message = 'Loading admin workspace...',
}: {
  message?: string
}) {
  return <PageLoader variant="screen" label={message} />
}
