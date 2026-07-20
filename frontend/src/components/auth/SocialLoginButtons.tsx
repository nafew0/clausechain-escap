'use client'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, LoaderCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { getSocialProviders, startSocialLogin } from '@/services/auth'

function GoogleIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
      <path fill="#EA4335" d="M12 10.2v3.96h5.5c-.24 1.28-.97 2.36-2.06 3.1l3.32 2.58c1.94-1.78 3.04-4.4 3.04-7.53 0-.68-.06-1.34-.18-1.98H12z" />
      <path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.63-2.43l-3.32-2.58c-.92.62-2.1.99-3.31.99-2.54 0-4.7-1.72-5.48-4.03l-3.43 2.64A10 10 0 0 0 12 22z" />
      <path fill="#4A90E2" d="M6.52 13.95A6.02 6.02 0 0 1 6.2 12c0-.68.12-1.34.32-1.95L3.1 7.4A10 10 0 0 0 2 12c0 1.62.39 3.16 1.1 4.6l3.42-2.65z" />
      <path fill="#FBBC05" d="M12 5.98c1.47 0 2.8.5 3.84 1.48l2.88-2.88C16.96 2.96 14.7 2 12 2A10 10 0 0 0 3.1 7.4l3.42 2.65C7.3 7.7 9.46 5.98 12 5.98z" />
    </svg>
  )
}

function FacebookIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor" {...props}>
      <path d="M13.5 22v-8.2h2.8l.42-3.2H13.5V8.56c0-.93.26-1.56 1.6-1.56h1.7V4.15c-.3-.04-1.33-.15-2.54-.15-2.5 0-4.2 1.53-4.2 4.35v2.42H7.2v3.2h2.86V22h3.44z" />
    </svg>
  )
}

function GitHubIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor" {...props}>
      <path d="M12 .5a12 12 0 0 0-3.8 23.39c.6.11.82-.26.82-.58v-2.22c-3.34.73-4.04-1.42-4.04-1.42-.55-1.38-1.33-1.75-1.33-1.75-1.09-.74.09-.73.09-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.82 2.81 1.3 3.5.99.11-.77.42-1.3.76-1.6-2.67-.3-5.47-1.34-5.47-5.96 0-1.32.47-2.4 1.24-3.25-.12-.3-.54-1.53.12-3.18 0 0 1.01-.32 3.3 1.24a11.5 11.5 0 0 1 6 0c2.28-1.56 3.29-1.24 3.29-1.24.67 1.65.25 2.88.12 3.18.77.85 1.24 1.93 1.24 3.25 0 4.63-2.81 5.66-5.48 5.96.43.37.82 1.1.82 2.23v3.3c0 .32.22.7.83.58A12 12 0 0 0 12 .5z" />
    </svg>
  )
}

const PROVIDER_ICONS: Record<string, (props: React.SVGProps<SVGSVGElement>) => React.ReactElement> = {
  google: GoogleIcon,
  facebook: FacebookIcon,
  github: GitHubIcon,
}

interface SocialProvider {
  id: string
  name: string
  enabled: boolean
  available: boolean
  configured: boolean
}

export default function SocialLoginButtons({ nextPath = '/dashboard' }: { nextPath?: string }) {
  const [pendingProvider, setPendingProvider] = useState('')
  const [actionError, setActionError] = useState('')

  const { data, error, isError, isLoading } = useQuery({
    queryKey: ['social-providers'],
    queryFn: getSocialProviders,
    refetchOnMount: 'always',
    staleTime: 0,
  })

  const providers = ((data?.providers || []) as SocialProvider[]).filter((provider) => provider.enabled)
  const axiosError = error as { response?: { data?: { detail?: string } }; message?: string } | null
  const providerError =
    axiosError?.response?.data?.detail ||
    axiosError?.message ||
    'Social login options could not be loaded right now.'

  const handleSocialLogin = async (providerId: string) => {
    setPendingProvider(providerId)
    setActionError('')
    try {
      const response = await startSocialLogin(providerId, { next: nextPath })
      if (!(response as { authorization_url?: string })?.authorization_url) {
        throw new Error('Authorization URL missing from the server response.')
      }
      window.location.assign((response as { authorization_url: string }).authorization_url)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      const detail = e.response?.data?.detail || e.message || 'Could not start social login.'
      setActionError(detail)
      setPendingProvider('')
    }
  }

  if (isLoading) {
    return (
      <div className="rounded-xl border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/70 px-4 py-3 text-sm text-muted-foreground">
        Checking social login availability...
      </div>
    )
  }

  if (!providers.length && !actionError && !isError) {
    return null
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-[rgb(var(--theme-border-rgb)/0.76)]" />
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Or continue with
        </p>
        <div className="h-px flex-1 bg-[rgb(var(--theme-border-rgb)/0.76)]" />
      </div>

      {isError ? (
        <div className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {providerError}
        </div>
      ) : null}

      {actionError ? (
        <div className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {actionError}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        {providers.map((provider) => {
          const Icon = PROVIDER_ICONS[provider.id]
          const isPending = pendingProvider === provider.id
          const isConfigured = provider.configured
          return (
            <Button
              key={provider.id}
              type="button"
              variant="outline"
              className="h-auto min-h-11 justify-center gap-2 border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-3 py-2"
              onClick={() => handleSocialLogin(provider.id)}
              disabled={Boolean(pendingProvider) || !provider.available}
              title={isConfigured ? `Continue with ${provider.name}` : `${provider.name} credentials are not configured.`}
            >
              {isPending ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : Icon ? (
                <Icon className="h-4 w-4 shrink-0" />
              ) : null}
              <span className="flex min-w-0 flex-col leading-tight">
                <span>{provider.name}</span>
                {!isConfigured ? (
                  <span className="text-[0.68rem] font-medium text-muted-foreground">
                    Setup needed
                  </span>
                ) : null}
              </span>
            </Button>
          )
        })}
      </div>
    </div>
  )
}
