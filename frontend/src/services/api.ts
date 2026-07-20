import axios from 'axios'

declare module 'axios' {
  export interface AxiosRequestConfig {
    skipAuthRefresh?: boolean
    preserveAuthError?: boolean
    _retry?: boolean
  }

  export interface InternalAxiosRequestConfig {
    skipAuthRefresh?: boolean
    preserveAuthError?: boolean
    _retry?: boolean
  }
}

let inMemoryAccessToken = ''
const AUTH_REFRESH_EXCLUDED_PATHS = [
  '/auth/login/',
  '/auth/register/',
  '/auth/social/',
  '/auth/token/refresh/',
  '/auth/password-reset/',
  '/auth/resend-verification-email/',
  '/auth/verify-email/',
]

function resolveApiUrl() {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL?.trim()
  if (!configuredUrl) {
    return '/api'
  }
  if (
    process.env.NODE_ENV === 'development' &&
    /^https?:\/\/(localhost|127\.0\.0\.1):8000\/api\/?$/i.test(configuredUrl)
  ) {
    return '/api'
  }
  return configuredUrl.replace(/\/+$/, '')
}

export const API_URL = resolveApiUrl()

export function getAccessToken() {
  return inMemoryAccessToken
}

export function setAccessToken(token: string | null | undefined) {
  inMemoryAccessToken = token?.trim() || ''
}

export function clearAccessToken() {
  inMemoryAccessToken = ''
}

export async function refreshAccessToken(signal?: AbortSignal) {
  const response = await axios.post(
    `${API_URL}/auth/token/refresh/`,
    {},
    {
      withCredentials: true,
      timeout: 8_000,
      signal,
      headers: {
        'Content-Type': 'application/json',
      },
    }
  )

  const nextAccessToken = response.data?.access || ''
  setAccessToken(nextAccessToken)
  return nextAccessToken
}

export function resolveApiAssetUrl(value: string | null | undefined): string {
  if (!value) {
    return ''
  }

  if (
    /^https?:\/\//i.test(value) ||
    value.startsWith('data:') ||
    value.startsWith('blob:')
  ) {
    return value
  }

  const normalizedPath = value.startsWith('/') ? value : `/${value}`

  try {
    if (/^https?:\/\//i.test(API_URL)) {
      return new URL(normalizedPath, API_URL).toString()
    }
  } catch (error) {
    console.error('Failed to resolve API asset URL:', error)
  }

  return normalizedPath
}

// Create axios instance
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const accessToken = getAccessToken()
    if (accessToken) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    const preserveAuthError = Boolean(originalRequest?.preserveAuthError)
    const skipAuthRefresh =
      Boolean(originalRequest?.skipAuthRefresh) ||
      AUTH_REFRESH_EXCLUDED_PATHS.some((path) => originalRequest?.url?.includes(path))

    // If error is 401 and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry && !skipAuthRefresh) {
      originalRequest._retry = true

      try {
        const accessToken = await refreshAccessToken()
        if (!accessToken) {
          return Promise.reject(error)
        }

        // Update the failed request with new token
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${accessToken}`

        // Retry the original request
        return api(originalRequest)
      } catch (refreshError) {
        clearAccessToken()
        if (!preserveAuthError) {
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

export default api
