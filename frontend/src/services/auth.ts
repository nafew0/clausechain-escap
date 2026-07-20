import api from './api'

export async function getSignupChallenge() {
  const response = await api.get('/auth/register/captcha/', {
    params: { _: Date.now() },
    skipAuthRefresh: true,
    preserveAuthError: true,
  })
  return response.data
}

export async function getSocialProviders() {
  const response = await api.get('/auth/social/providers/', {
    params: { _: Date.now() },
    skipAuthRefresh: true,
    preserveAuthError: true,
  })
  return response.data
}

export async function startSocialLogin(provider: string, payload: Record<string, unknown> = {}) {
  const response = await api.post(`/auth/social/${provider}/start/`, payload, { skipAuthRefresh: true, preserveAuthError: true })
  return response.data
}

export async function requestPasswordReset(identifier: string) {
  const response = await api.post('/auth/password-reset/request/', { identifier })
  return response.data
}

export async function validatePasswordReset(uid: string, token: string) {
  const response = await api.get('/auth/password-reset/validate/', {
    params: { uid, token },
  })
  return response.data
}

export async function confirmPasswordReset(payload: Record<string, unknown>) {
  const response = await api.post('/auth/password-reset/confirm/', payload)
  return response.data
}
