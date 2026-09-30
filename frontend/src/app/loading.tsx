import { PageLoader } from '@/components/clausechain/PageLoader'

/** Shown by Next while any route segment loads (every page). */
export default function Loading() {
  return <PageLoader variant="screen" />
}
