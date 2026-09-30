'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'

const AdminRoles = dynamic(() => import('@/views/admin/AdminRoles'), {
  ssr: false,
  loading: () => <AdminLoadingState message="Loading roles" />,
})

export default function AdminRolesPage() {
  return <AdminRoles />
}
