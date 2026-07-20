'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'

const AdminPayments = dynamic(() => import('@/views/admin/AdminPayments'), {
  ssr: false,
  loading: () => <AdminLoadingState />,
})

export default function AdminPaymentsPage() {
  return <AdminPayments />
}
