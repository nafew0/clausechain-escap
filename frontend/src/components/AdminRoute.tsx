'use client'
import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'

import { useAuth } from '@/contexts/AuthContext'
import useAdminAccess from '@/hooks/useAdminAccess'
import AdminLoadingState from '@/components/AdminLoadingState'

export default function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const { canAccessAdmin, loading: adminAccessLoading } = useAdminAccess()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?redirect=${encodeURIComponent(pathname ?? '')}`)
    } else if (!loading && !adminAccessLoading && user && !canAccessAdmin) {
      router.replace('/dashboard')
    }
  }, [user, loading, adminAccessLoading, canAccessAdmin, router, pathname])

  if (loading || (Boolean(user) && adminAccessLoading)) {
    return <AdminLoadingState />
  }

  if (!user || !canAccessAdmin) return null

  return <>{children}</>
}
