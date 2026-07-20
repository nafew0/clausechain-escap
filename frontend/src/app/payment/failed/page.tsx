import { Suspense } from 'react'
import PaymentFailed from '@/views/PaymentFailed'

export default function PaymentFailedPage() {
  return (
    <Suspense>
      <PaymentFailed />
    </Suspense>
  )
}
