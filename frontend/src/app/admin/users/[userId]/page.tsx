'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'

const AdminUserDetail = dynamic(() => import('@/views/admin/AdminUserDetail'), {
  ssr: false,
  loading: () => <AdminLoadingState />,
})

export default function AdminUserDetailPage() {
  return <AdminUserDetail />
}
