'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/contexts/AuthContext'
import { PageLoader } from '@/components/clausechain/PageLoader'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [user, loading, router])

  if (loading) return <PageLoader variant="screen" />

  if (!user) return null

  return <>{children}</>
}
