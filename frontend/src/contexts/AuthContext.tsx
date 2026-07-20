'use client'
import { createContext, useState, useEffect, useContext, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import api, {
  clearAccessToken,
  refreshAccessToken,
  setAccessToken,
} from '../services/api'
import { resetAdminGateCache } from '../services/admin'

export interface CurrentPlan {
  id?: string
  slug: string
  name: string
  tier: number
}

export interface User {
  id: string
  username: string
  email: string
  first_name: string
  last_name: string
  full_name?: string
  avatar?: string
  bio?: string
  organization?: string
  designation?: string
  phone?: string
  is_superuser?: boolean
  email_verified?: boolean
  is_active?: boolean
  last_login?: string
  created_at?: string
  current_plan?: CurrentPlan
}

interface AuthResult {
  success: boolean
  user?: User
  error?: string
}

interface RegisterResult extends AuthResult {
  message?: string
  emailVerificationRequired?: boolean
  emailHint?: string
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  error: string | null
  isAuthenticated: boolean
  signingOut: boolean
  login: (username: string, password: string) => Promise<AuthResult>
  register: (userData: Record<string, unknown>) => Promise<RegisterResult>
  resendVerificationEmail: (identifier: string) => Promise<{ success: boolean; message?: string; error?: string }>
  logout: () => Promise<void>
  updateUser: (userData: Record<string, unknown> | FormData) => Promise<AuthResult>
  refreshUser: () => Promise<void>
  completeCookieLogin: () => Promise<AuthResult>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const clearAuthState = useCallback(() => {
    clearAccessToken()
    localStorage.removeItem('accessToken')
    localStorage.removeItem('refreshToken')
    resetAdminGateCache()
    setUser(null)
  }, [])

  const completeCookieLogin = useCallback(async (signal?: AbortSignal): Promise<AuthResult> => {
    try {
      const accessToken = await refreshAccessToken(signal)
      if (!accessToken) {
        clearAuthState()
        return { success: false, error: 'Login session is unavailable.' }
      }
      const response = await api.get('/auth/user/')
      resetAdminGateCache()
      setUser(response.data)
      sessionStorage.removeItem('clausechain_explicit_logout')
      return { success: true, user: response.data }
    } catch {
      clearAuthState()
      return { success: false, error: 'Login session is unavailable.' }
    }
  }, [clearAuthState])

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 8_000)
    const initializeAuth = async () => {
      localStorage.removeItem('accessToken')
      localStorage.removeItem('refreshToken')
      if (sessionStorage.getItem('clausechain_explicit_logout') === '1') {
        clearAuthState()
        setLoading(false)
        return
      }
      try {
        await completeCookieLogin(controller.signal)
      } finally {
        window.clearTimeout(timeout)
        setLoading(false)
      }
    }
    initializeAuth()
    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [clearAuthState, completeCookieLogin])

  const extractErrorMessage = (err: unknown, fallbackMessage: string): string => {
    const e = err as { response?: { data?: unknown } }
    const payload = e.response?.data

    if (typeof (payload as Record<string, unknown>)?.detail === 'string') {
      return (payload as Record<string, string>).detail
    }
    if (typeof (payload as Record<string, unknown>)?.error === 'string') {
      return (payload as Record<string, string>).error
    }
    if (typeof payload === 'string') return payload

    if (payload && typeof payload === 'object') {
      const firstValue = Object.values(payload as object)[0]
      if (Array.isArray(firstValue) && firstValue.length > 0) return String(firstValue[0])
      if (typeof firstValue === 'string') return firstValue
    }

    return fallbackMessage
  }

  const login = async (username: string, password: string): Promise<AuthResult> => {
    try {
      setError(null)
      const response = await api.post('/auth/login/', { username, password })
      const { user: userData, access_token: accessToken } = response.data
      setAccessToken(accessToken)
      sessionStorage.removeItem('clausechain_explicit_logout')
      resetAdminGateCache()
      setUser(userData)
      return { success: true, user: userData }
    } catch (err) {
      const errorMessage = extractErrorMessage(err, 'Login failed')
      setError(errorMessage)
      return { success: false, error: errorMessage }
    }
  }

  const register = async (userData: Record<string, unknown>): Promise<RegisterResult> => {
    try {
      setError(null)
      const response = await api.post('/auth/register/', userData)
      const {
        user: registeredUser,
        access_token: accessToken,
        email_verification_required: emailVerificationRequired,
        email_hint: emailHint,
        message,
      } = response.data

      if (accessToken) {
        sessionStorage.removeItem('clausechain_explicit_logout')
        setAccessToken(accessToken)
        resetAdminGateCache()
        setUser(registeredUser)
      } else {
        clearAuthState()
      }

      return {
        success: true,
        user: registeredUser,
        message,
        emailVerificationRequired: Boolean(emailVerificationRequired),
        emailHint: emailHint || '',
      }
    } catch (err) {
      const errorMessage = extractErrorMessage(err, 'Registration failed')
      setError(errorMessage)
      return { success: false, error: errorMessage }
    }
  }

  const resendVerificationEmail = async (identifier: string) => {
    try {
      setError(null)
      const response = await api.post('/auth/resend-verification-email/', { identifier })
      return {
        success: true,
        message: response.data?.detail || 'If an eligible account exists, a verification email will arrive shortly.',
      }
    } catch (err) {
      const errorMessage = extractErrorMessage(err, 'Could not resend verification email')
      setError(errorMessage)
      return { success: false, error: errorMessage }
    }
  }

  const logout = async () => {
    if (signingOut) return
    setSigningOut(true)
    sessionStorage.setItem('clausechain_explicit_logout', '1')
    clearAuthState()
    queryClient.clear()
    let confirmed = true
    try {
      await api.post('/auth/logout/', {}, { skipAuthRefresh: true, preserveAuthError: true, timeout: 8_000 })
    } catch (err) {
      confirmed = false
      console.error('Logout error:', err)
    } finally {
      router.replace(confirmed ? '/login?signed_out=1' : '/login?signed_out=1&logout_unconfirmed=1')
      router.refresh()
      setSigningOut(false)
    }
  }

  const updateUser = async (userData: Record<string, unknown> | FormData): Promise<AuthResult> => {
    try {
      setError(null)
      const isFormData = userData instanceof FormData
      const response = await api.patch('/auth/user/update/', userData, {
        headers: isFormData ? { 'Content-Type': 'multipart/form-data' } : undefined,
      })
      resetAdminGateCache()
      setUser(response.data)
      return { success: true, user: response.data }
    } catch (err) {
      const errorMessage = extractErrorMessage(err, 'Update failed')
      setError(errorMessage)
      return { success: false, error: errorMessage }
    }
  }

  const refreshUser = async () => {
    try {
      const response = await api.get('/auth/user/')
      resetAdminGateCache()
      setUser(response.data)
    } catch (err) {
      console.error('Failed to refresh user:', err)
    }
  }

  const value: AuthContextValue = {
    user,
    loading,
    error,
    login,
    register,
    resendVerificationEmail,
    logout,
    updateUser,
    refreshUser,
    completeCookieLogin,
    isAuthenticated: !!user,
    signingOut,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export default AuthContext
