'use client'
import { useEffect, useState } from 'react'

import { useAuth } from '@/contexts/AuthContext'
import {
  getAdminGateCacheVersion,
  getCachedAdminGateAccess,
  resolveAdminGateAccess,
} from '@/services/admin'

export default function useAdminAccess() {
  const { user, loading: authLoading } = useAuth()
  const [resolvedUserId, setResolvedUserId] = useState<string | null>(null)
  const [resolvedAccess, setResolvedAccess] = useState<boolean | null>(null)
  const [resolvedVersion, setResolvedVersion] = useState<number | null>(null)
  const userId = user?.id ?? null
  const cachedAccess = userId ? getCachedAdminGateAccess(userId) : undefined
  const cacheVersion = getAdminGateCacheVersion()

  useEffect(() => {
    if (authLoading || !userId || cachedAccess !== undefined) {
      return
    }

    let cancelled = false

    resolveAdminGateAccess(userId)
      .then((hasAdminAccess) => {
        if (cancelled) return
        setResolvedUserId(userId)
        setResolvedAccess(hasAdminAccess)
        setResolvedVersion(getAdminGateCacheVersion())
      })
      .catch(() => {
        if (cancelled) return
        setResolvedUserId(userId)
        setResolvedAccess(false)
        setResolvedVersion(getAdminGateCacheVersion())
      })

    return () => {
      cancelled = true
    }
  }, [authLoading, userId, cachedAccess])

  const hasResolvedAccess =
    resolvedUserId === userId && resolvedVersion === cacheVersion
  const canAccessAdmin = cachedAccess ?? (hasResolvedAccess ? resolvedAccess : null) ?? false
  const loading =
    authLoading || (Boolean(userId) && cachedAccess === undefined && !hasResolvedAccess)

  return {
    canAccessAdmin,
    loading,
  }
}
