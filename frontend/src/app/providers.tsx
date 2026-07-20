'use client'
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AuthProvider } from '@/contexts/AuthContext'
import { BrandingProvider } from '@/contexts/BrandingContext'
import { SiteThemeProvider } from '@/contexts/SiteThemeContext'
import { ToastProvider } from '@/hooks/useToast'

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      <BrandingProvider>
        <AuthProvider>
          <SiteThemeProvider>
            <ToastProvider>{children}</ToastProvider>
          </SiteThemeProvider>
        </AuthProvider>
      </BrandingProvider>
    </QueryClientProvider>
  )
}
