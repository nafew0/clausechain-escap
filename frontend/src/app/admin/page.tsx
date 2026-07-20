'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'

const AdminDashboard = dynamic(() => import('@/views/admin/AdminDashboard'), {
  ssr: false,
  loading: () => <AdminLoadingState />,
})

export default function AdminPage() {
  return <AdminDashboard />
}
