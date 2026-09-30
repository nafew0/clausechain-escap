'use client'
import dynamic from 'next/dynamic'

import AdminLoadingState from '@/components/AdminLoadingState'

const AdminSettings = dynamic(() => import('@/views/admin/AdminSettings'), {
  ssr: false,
  loading: () => <AdminLoadingState />,
})

export default function AdminSettingsPage() {
  return <AdminSettings />
}
