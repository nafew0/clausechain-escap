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

export async function getAdminDashboard() {
  const response = await api.get('/admin/dashboard/')
  return response.data
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

export async function getAdminPayments(params: Record<string, string> = {}) {
  const response = await api.get(`/admin/payments/?${buildParams(params).toString()}`)
  return response.data
}

export async function exportAdminPayments(params: Record<string, string> = {}) {
  const response = await api.get(`/admin/payments/export/?${buildParams(params).toString()}`, {
    responseType: 'blob',
  })
  return response.data
}

export async function searchAdminBkashTransaction(trxId: string) {
  const response = await api.get(
    `/admin/payments/bkash/search/?${buildParams({ trx_id: trxId }).toString()}`
  )
  return response.data
}

export async function refundAdminBkashPayment(paymentId: string, payload: Record<string, unknown>) {
  const response = await api.post(`/admin/payments/bkash/${paymentId}/refund/`, payload)
  return response.data
}

export async function getAdminSettings() {
  const response = await api.get('/admin/settings/')
  return response.data
}

export async function updateAdminSettings(payload: Record<string, unknown> | FormData) {
  const isFormData = payload instanceof FormData
  const response = await api.patch('/admin/settings/', payload, {
    headers: isFormData ? { 'Content-Type': 'multipart/form-data' } : undefined,
  })
  return response.data
}

export async function testAdminAI(payload: Record<string, unknown>) {
  const response = await api.post('/admin/settings/test-ai/', payload)
  return response.data
}
