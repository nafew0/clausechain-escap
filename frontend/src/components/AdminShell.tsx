'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'
import AdminRoute from '@/components/AdminRoute'

const AdminLayout = dynamic(() => import('@/views/admin/AdminLayout'), {
  ssr: false,
  loading: () => <AdminLoadingState />,
})

export default function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <AdminRoute>
      <AdminLayout>{children}</AdminLayout>
    </AdminRoute>
  )
}
