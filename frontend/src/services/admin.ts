import api from './api'

const adminGateCache = new Map<string, boolean>()
const adminGateRequests = new Map<string, Promise<boolean>>()
let adminGateCacheVersion = 0

function buildParams(params: Record<string, string | number | boolean | undefined | null> = {}) {
  const searchParams = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    searchParams.set(key, String(value))
  })

  return searchParams
}

function getResponseStatus(error: unknown) {
  return (error as { response?: { status?: number } })?.response?.status
}

export function resetAdminGateCache(userId?: string) {
  adminGateCacheVersion += 1

  if (!userId) {
    adminGateCache.clear()
    adminGateRequests.clear()
    return
  }

  adminGateCache.delete(userId)
  adminGateRequests.delete(userId)
}

export function getCachedAdminGateAccess(userId: string) {
  return adminGateCache.get(userId)
}

export function getAdminGateCacheVersion() {
  return adminGateCacheVersion
}

export async function checkAdminGate() {
  await api.get('/admin/_gate/', {
    headers: {
      'Cache-Control': 'no-store',
    },
  })
}

export async function resolveAdminGateAccess(userId: string) {
  const cachedAccess = adminGateCache.get(userId)
  if (cachedAccess !== undefined) {
    return cachedAccess
  }

  const pendingRequest = adminGateRequests.get(userId)
  if (pendingRequest) {
    return pendingRequest
  }

  const request = checkAdminGate()
    .then(() => {
      adminGateCache.set(userId, true)
      return true
    })
    .catch((error) => {
      const responseStatus = getResponseStatus(error)
      if (responseStatus === 401 || responseStatus === 403) {
        adminGateCache.set(userId, false)
        return false
      }
      throw error
    })
    .finally(() => {
      adminGateRequests.delete(userId)
    })

  adminGateRequests.set(userId, request)
  return request
}

export async function getAdminUsers(params: Record<string, string> = {}) {
  const response = await api.get(`/admin/users/?${buildParams(params).toString()}`)
  return response.data
}

export async function getAdminUserDetail(userId: string) {
  const response = await api.get(`/admin/users/${userId}/`)
  return response.data
}

export async function updateAdminUser(userId: string, payload: Record<string, unknown>) {
  const response = await api.patch(`/admin/users/${userId}/`, payload)
  return response.data
}

export async function deleteAdminUser(userId: string) {
  const response = await api.delete(`/admin/users/${userId}/`)
  return response.data
}

export async function sendAdminPasswordReset(userId: string) {
  const response = await api.post(`/admin/users/${userId}/send-password-reset/`)
  return response.data
}

export interface AdminRoleMember {
  id: string
  username: string
  full_name: string
  email: string
  is_active: boolean
}

export interface AdminRole {
  key: 'admin' | 'reviewer' | 'viewer'
  label: string
  description: string
  permissions: string[]
  user_count: number
  default_for_new_users: boolean
  members: AdminRoleMember[]
}

/** The three account roles, what each can do, and who holds them. */
export async function getAdminRoles(): Promise<{ roles: AdminRole[] }> {
  const response = await api.get('/admin/roles/')
  return response.data
}
