import api from './api'

export interface PublicBrandingResponse {
  branding_logo_url?: string
  branding_favicon_url?: string
  branding_login_banner_url?: string
  branding_register_banner_url?: string
}

export async function getPublicBranding() {
  const response = await api.get<PublicBrandingResponse>('/auth/branding/', {
    skipAuthRefresh: true,
    preserveAuthError: true,
    headers: {
      'Cache-Control': 'no-store',
    },
  })
  return response.data
}
