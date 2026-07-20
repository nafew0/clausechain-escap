'use client'
import { createContext, useContext, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { resolveApiAssetUrl } from '@/services/api'
import { getPublicBranding, type PublicBrandingResponse } from '@/services/branding'

interface BrandingContextValue {
  logoUrl: string
  faviconUrl: string
  loginBannerUrl: string
  registerBannerUrl: string
}

const DEFAULT_BRANDING = {
  logoUrl: '/branding/logo.svg',
  faviconUrl: '/branding/logo.ico',
  loginBannerUrl: '/branding/loginpage.webp',
  registerBannerUrl: '/branding/registerpage.webp',
}

const BrandingContext = createContext<BrandingContextValue>(DEFAULT_BRANDING)

function resolveBrandingValue(value: string | null | undefined, fallback: string) {
  return resolveApiAssetUrl(value || '') || fallback
}

function applyFavicon(faviconUrl: string) {
  if (typeof document === 'undefined' || !faviconUrl) {
    return
  }

  const head = document.head
  ;[
    { rel: 'icon', key: 'app-favicon-icon' },
    { rel: 'shortcut icon', key: 'app-favicon-shortcut' },
  ].forEach(({ rel, key }) => {
    let link = head.querySelector<HTMLLinkElement>(`link[data-branding-key="${key}"]`)
    if (!link) {
      link = document.createElement('link')
      link.setAttribute('data-branding-key', key)
      head.appendChild(link)
    }
    link.rel = rel
    link.href = faviconUrl
  })
}

function buildBrandingValue(data: PublicBrandingResponse | undefined): BrandingContextValue {
  return {
    logoUrl: resolveBrandingValue(data?.branding_logo_url, DEFAULT_BRANDING.logoUrl),
    faviconUrl: resolveBrandingValue(data?.branding_favicon_url, DEFAULT_BRANDING.faviconUrl),
    loginBannerUrl: resolveBrandingValue(
      data?.branding_login_banner_url,
      DEFAULT_BRANDING.loginBannerUrl
    ),
    registerBannerUrl: resolveBrandingValue(
      data?.branding_register_banner_url,
      DEFAULT_BRANDING.registerBannerUrl
    ),
  }
}

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const { data } = useQuery({
    queryKey: ['public-branding'],
    queryFn: getPublicBranding,
    staleTime: 60_000,
  })

  const value = useMemo(() => buildBrandingValue(data), [data])

  useEffect(() => {
    applyFavicon(value.faviconUrl)
  }, [value.faviconUrl])

  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>
}

export function useBranding() {
  return useContext(BrandingContext)
}
