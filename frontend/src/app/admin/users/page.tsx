'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'

const AdminUsers = dynamic(() => import('@/views/admin/AdminUsers'), {
  ssr: false,
  loading: () => <AdminLoadingState />,
})

export default function AdminUsersPage() {
  return <AdminUsers />
}
