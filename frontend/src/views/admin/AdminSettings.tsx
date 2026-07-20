'use client'
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useToast } from '@/hooks/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CustomSelect } from '@/components/ui/custom-select'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { getAdminSettings, testAdminAI, updateAdminSettings } from '@/services/admin'

type SocialKey =
  | 'social_login_google_enabled'
  | 'social_login_facebook_enabled'
  | 'social_login_github_enabled'
type BrandingField =
  | 'branding_logo'
  | 'branding_favicon'
  | 'branding_login_banner'
  | 'branding_register_banner'
type BrandingUrlKey =
  | 'branding_logo_url'
  | 'branding_favicon_url'
  | 'branding_login_banner_url'
  | 'branding_register_banner_url'
type BrandingCustomizedKey =
  | 'branding_logo_customized'
  | 'branding_favicon_customized'
  | 'branding_login_banner_customized'
  | 'branding_register_banner_customized'

interface FormState {
  require_email_verification: boolean
  logged_in_users_only_default: boolean
  signup_captcha_enabled: boolean
  signup_disposable_email_blocking_enabled: boolean
  signup_burst_limit: number
  signup_short_window_limit: number
  signup_sustained_limit: number
  social_login_google_enabled: boolean
  social_login_facebook_enabled: boolean
  social_login_github_enabled: boolean
  ai_provider: string
  ai_model_openai: string
  ai_model_anthropic: string
}

interface BrandingAssetLimit {
  label: string
  max_width: number
  max_height: number
  max_size_bytes: number
  allowed_formats: string[]
}

type BrandingFileState = Record<BrandingField, File | null>
type BrandingClearState = Record<BrandingField, boolean>

const BRANDING_ASSET_CONFIG: Array<{
  field: BrandingField
  urlKey: BrandingUrlKey
  customizedKey: BrandingCustomizedKey
  title: string
  description: string
  accept: string
  previewShellClassName: string
  previewImageClassName: string
}> = [
  {
    field: 'branding_logo',
    urlKey: 'branding_logo_url',
    customizedKey: 'branding_logo_customized',
    title: 'Logo',
    description: 'Used in the navbar, auth screens, and outbound auth emails.',
    accept: 'image/png,image/jpeg,image/webp',
    previewShellClassName:
      'flex h-28 items-center justify-center rounded-[1.15rem] border border-[rgb(var(--theme-border-rgb)/0.72)] bg-[rgb(var(--theme-neutral-rgb)/0.42)] p-4',
    previewImageClassName: 'max-h-full w-full object-contain',
  },
  {
    field: 'branding_favicon',
    urlKey: 'branding_favicon_url',
    customizedKey: 'branding_favicon_customized',
    title: 'Favicon',
    description: 'Applied to the browser tab after the public branding settings load.',
    accept: 'image/png,image/webp',
    previewShellClassName:
      'flex h-28 items-center justify-center rounded-[1.15rem] border border-[rgb(var(--theme-border-rgb)/0.72)] bg-[rgb(var(--theme-neutral-rgb)/0.42)] p-4',
    previewImageClassName: 'h-16 w-16 rounded-2xl object-contain',
  },
  {
    field: 'branding_login_banner',
    urlKey: 'branding_login_banner_url',
    customizedKey: 'branding_login_banner_customized',
    title: 'Login banner',
    description: 'Shown on the left side of the login screen on large layouts.',
    accept: 'image/png,image/jpeg,image/webp',
    previewShellClassName:
      'overflow-hidden rounded-[1.15rem] border border-[rgb(var(--theme-border-rgb)/0.72)] bg-[rgb(var(--theme-neutral-rgb)/0.42)]',
    previewImageClassName: 'h-40 w-full object-cover',
  },
  {
    field: 'branding_register_banner',
    urlKey: 'branding_register_banner_url',
    customizedKey: 'branding_register_banner_customized',
    title: 'Registration banner',
    description: 'Shown on the left side of the registration screen on large layouts.',
    accept: 'image/png,image/jpeg,image/webp',
    previewShellClassName:
      'overflow-hidden rounded-[1.15rem] border border-[rgb(var(--theme-border-rgb)/0.72)] bg-[rgb(var(--theme-neutral-rgb)/0.42)]',
    previewImageClassName: 'h-40 w-full object-cover',
  },
]

const DEFAULT_BRANDING_PREVIEW_URLS: Record<BrandingField, string> = {
  branding_logo: '/branding/logo.svg',
  branding_favicon: '/branding/logo.ico',
  branding_login_banner: '/branding/loginpage.webp',
  branding_register_banner: '/branding/registerpage.webp',
}

function createEmptyBrandingFiles(): BrandingFileState {
  return {
    branding_logo: null,
    branding_favicon: null,
    branding_login_banner: null,
    branding_register_banner: null,
  }
}

function createEmptyBrandingClears(): BrandingClearState {
  return {
    branding_logo: false,
    branding_favicon: false,
    branding_login_banner: false,
    branding_register_banner: false,
  }
}

function readNumberSetting(
  settings: Record<string, unknown> | null | undefined,
  key: string,
  fallback: number
) {
  const value = Number(settings?.[key] ?? fallback)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

function buildInitialState(settings: Record<string, unknown> | null | undefined): FormState {
  return {
    require_email_verification: Boolean(settings?.require_email_verification ?? false),
    logged_in_users_only_default: Boolean(settings?.logged_in_users_only_default ?? false),
    signup_captcha_enabled: Boolean(settings?.signup_captcha_enabled ?? false),
    signup_disposable_email_blocking_enabled: Boolean(
      settings?.signup_disposable_email_blocking_enabled ?? false
    ),
    signup_burst_limit: readNumberSetting(settings, 'signup_burst_limit', 1),
    signup_short_window_limit: readNumberSetting(settings, 'signup_short_window_limit', 3),
    signup_sustained_limit: readNumberSetting(settings, 'signup_sustained_limit', 10),
    social_login_google_enabled: Boolean(settings?.social_login_google_enabled ?? false),
    social_login_facebook_enabled: Boolean(settings?.social_login_facebook_enabled ?? false),
    social_login_github_enabled: Boolean(settings?.social_login_github_enabled ?? false),
    ai_provider: String(settings?.ai_provider || 'openai'),
    ai_model_openai: String(settings?.ai_model_openai || ''),
    ai_model_anthropic: String(settings?.ai_model_anthropic || ''),
  }
}

function extractErrorMessage(error: unknown, fallback: string) {
  const payload = (error as { response?: { data?: unknown } })?.response?.data

  if (typeof (payload as Record<string, unknown>)?.detail === 'string') {
    return String((payload as Record<string, unknown>).detail)
  }
  if (typeof payload === 'string') {
    return payload
  }
  if (payload && typeof payload === 'object') {
    const firstValue = Object.values(payload as object)[0]
    if (Array.isArray(firstValue) && firstValue.length > 0) {
      return String(firstValue[0])
    }
    if (typeof firstValue === 'string') {
      return firstValue
    }
  }
  return fallback
}

function getBrandingPreviewUrl(
  settings: Record<string, unknown> | undefined,
  field: BrandingField,
  urlKey: BrandingUrlKey,
  willClear: boolean
) {
  if (willClear) {
    return DEFAULT_BRANDING_PREVIEW_URLS[field]
  }

  const configuredUrl = settings?.[urlKey]
  if (typeof configuredUrl === 'string' && configuredUrl) {
    return configuredUrl
  }
  return DEFAULT_BRANDING_PREVIEW_URLS[field]
}

export default function AdminSettings() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [formState, setFormState] = useState(buildInitialState(null))
  const [brandingFiles, setBrandingFiles] = useState<BrandingFileState>(
    createEmptyBrandingFiles()
  )
  const [brandingClears, setBrandingClears] = useState<BrandingClearState>(
    createEmptyBrandingClears()
  )
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: getAdminSettings,
  })

  useEffect(() => {
    // Sync fetched settings into the editable admin form after each successful refetch.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFormState(buildInitialState(data))
    setBrandingFiles(createEmptyBrandingFiles())
    setBrandingClears(createEmptyBrandingClears())
  }, [data])

  const handleChange = (key: keyof FormState, value: FormState[keyof FormState]) => {
    setFormState((current) => ({
      ...current,
      [key]: value,
    }))
  }

  const handleIntegerChange = (key: keyof FormState, rawValue: string) => {
    const parsed = Number.parseInt(rawValue, 10)
    if (Number.isNaN(parsed)) {
      return
    }
    handleChange(key, Math.max(1, parsed))
  }

  const handleBrandingFileChange = (field: BrandingField, file: File | null) => {
    setBrandingFiles((current) => ({
      ...current,
      [field]: file,
    }))
    setBrandingClears((current) => ({
      ...current,
      [field]: false,
    }))
  }

  const toggleBrandingClear = (field: BrandingField) => {
    setBrandingFiles((current) => ({
      ...current,
      [field]: null,
    }))
    setBrandingClears((current) => ({
      ...current,
      [field]: !current[field],
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const hasBrandingChanges = BRANDING_ASSET_CONFIG.some(
        ({ field }) => Boolean(brandingFiles[field]) || brandingClears[field]
      )

      let payload: FormData | Record<string, unknown>
      if (hasBrandingChanges) {
        const multipart = new FormData()
        Object.entries(formState).forEach(([key, value]) => {
          multipart.append(key, String(value))
        })

        BRANDING_ASSET_CONFIG.forEach(({ field }) => {
          const pendingFile = brandingFiles[field]
          if (pendingFile) {
            multipart.append(field, pendingFile)
          }
          if (brandingClears[field]) {
            multipart.append(`clear_${field}`, 'true')
          }
        })

        payload = multipart
      } else {
        payload = { ...formState }
      }

      const updatedSettings = await updateAdminSettings(payload)
      queryClient.setQueryData(['admin-settings'], updatedSettings)
      await queryClient.invalidateQueries({ queryKey: ['public-branding'] })
      toast({
        title: 'Settings saved',
        description: 'reactdjango updated the platform settings successfully.',
        variant: 'success',
      })
    } catch (requestError) {
      toast({
        title: 'Save failed',
        description: extractErrorMessage(
          requestError,
          'reactdjango could not save settings right now.'
        ),
        variant: 'error',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    const provider = formState.ai_provider
    const model =
      provider === 'openai' ? formState.ai_model_openai : formState.ai_model_anthropic

    setTesting(true)
    try {
      const response = await testAdminAI({
        provider,
        model,
      })
      toast({
        title: 'Connection successful',
        description: response.message,
        variant: 'success',
      })
    } catch (requestError) {
      toast({
        title: 'Connection failed',
        description: extractErrorMessage(
          requestError,
          'reactdjango could not validate the AI provider.'
        ),
        variant: 'error',
      })
    } finally {
      setTesting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-muted-foreground">
        Loading settings...
      </div>
    )
  }

  if (error) {
    return (
      <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-rose-600">
        reactdjango could not load settings right now.
      </div>
    )
  }

  const brandingLimits = (data?.branding_asset_limits || {}) as Record<
    BrandingField,
    BrandingAssetLimit
  >

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card className="theme-panel rounded-[1.8rem] border-0">
        <CardHeader>
          <CardTitle>Authentication defaults</CardTitle>
          <CardDescription>
            Global auth, branding, and collector defaults for new workspaces.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center justify-between gap-4 rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3">
            <div>
              <p className="font-medium text-foreground">Require email verification</p>
              <p className="text-sm text-muted-foreground">
                New accounts must verify email before sign-in.
              </p>
            </div>
            <Switch
              checked={formState.require_email_verification}
              onCheckedChange={(value) => handleChange('require_email_verification', value)}
            />
          </div>

          <div className="flex items-center justify-between gap-4 rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3">
            <div>
              <p className="font-medium text-foreground">
                Logged-in respondents only by default
              </p>
              <p className="text-sm text-muted-foreground">
                New content defaults to authenticated users only.
              </p>
            </div>
            <Switch
              checked={formState.logged_in_users_only_default}
              onCheckedChange={(value) => handleChange('logged_in_users_only_default', value)}
            />
          </div>

          <div className="flex items-center justify-between gap-4 rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3">
            <div>
              <p className="font-medium text-foreground">Signup CAPTCHA</p>
              <p className="text-sm text-muted-foreground">
                Require a simple arithmetic CAPTCHA before new accounts can register.
              </p>
            </div>
            <Switch
              checked={formState.signup_captcha_enabled}
              onCheckedChange={(value) => handleChange('signup_captcha_enabled', value)}
            />
          </div>

          <div className="flex items-center justify-between gap-4 rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3">
            <div>
              <p className="font-medium text-foreground">Block disposable email domains</p>
              <p className="text-sm text-muted-foreground">
                Reject registrations that use known temporary inbox providers.
              </p>
            </div>
            <Switch
              checked={formState.signup_disposable_email_blocking_enabled}
              onCheckedChange={(value) =>
                handleChange('signup_disposable_email_blocking_enabled', value)
              }
            />
          </div>

          <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
            <div className="space-y-1">
              <p className="font-medium text-foreground">Signup rate limits</p>
              <p className="text-sm text-muted-foreground">
                The time windows stay fixed. Change only the number of registrations
                allowed per IP in each window.
              </p>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  15 seconds
                </p>
                <Input
                  type="number"
                  min={1}
                  inputMode="numeric"
                  value={formState.signup_burst_limit}
                  onChange={(event) =>
                    handleIntegerChange('signup_burst_limit', event.target.value)
                  }
                />
                <p className="text-sm text-muted-foreground">Requests allowed per IP.</p>
              </div>
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  10 minutes
                </p>
                <Input
                  type="number"
                  min={1}
                  inputMode="numeric"
                  value={formState.signup_short_window_limit}
                  onChange={(event) =>
                    handleIntegerChange('signup_short_window_limit', event.target.value)
                  }
                />
                <p className="text-sm text-muted-foreground">Requests allowed per IP.</p>
              </div>
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  1 hour
                </p>
                <Input
                  type="number"
                  min={1}
                  inputMode="numeric"
                  value={formState.signup_sustained_limit}
                  onChange={(event) =>
                    handleIntegerChange('signup_sustained_limit', event.target.value)
                  }
                />
                <p className="text-sm text-muted-foreground">Requests allowed per IP.</p>
              </div>
            </div>
          </div>

          <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
            <div className="space-y-1">
              <p className="font-medium text-foreground">Branding assets</p>
              <p className="text-sm text-muted-foreground">
                Upload runtime branding without rebuilding the frontend. Removing a custom
                image falls back to the bundled asset in `frontend/public/branding`.
              </p>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              {BRANDING_ASSET_CONFIG.map((asset) => {
                const limit = brandingLimits[asset.field]
                const pendingFile = brandingFiles[asset.field]
                const willClear = brandingClears[asset.field]
                const isCustomized = Boolean(data?.[asset.customizedKey])
                const previewUrl = getBrandingPreviewUrl(data, asset.field, asset.urlKey, willClear)

                return (
                  <div
                    key={asset.field}
                    className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-[rgb(var(--theme-neutral-rgb)/0.28)] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-foreground">{asset.title}</p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          {asset.description}
                        </p>
                      </div>
                      <Badge
                        variant={
                          pendingFile ? 'warning' : willClear ? 'warning' : isCustomized ? 'success' : 'secondary'
                        }
                      >
                        {pendingFile
                          ? 'Pending upload'
                          : willClear
                            ? 'Will use default'
                            : isCustomized
                              ? 'Custom'
                              : 'Bundled default'}
                      </Badge>
                    </div>

                    <div className="mt-4">
                      <div className={asset.previewShellClassName}>
                        <img
                          src={previewUrl}
                          alt={`${asset.title} preview`}
                          className={asset.previewImageClassName}
                        />
                      </div>
                    </div>

                    <div className="mt-4 space-y-3">
                      <input
                        type="file"
                        accept={asset.accept}
                        onChange={(event) =>
                          handleBrandingFileChange(asset.field, event.target.files?.[0] || null)
                        }
                        className="block w-full text-sm text-muted-foreground file:mr-4 file:rounded-full file:border-0 file:bg-[rgb(var(--theme-primary-soft-rgb)/0.9)] file:px-4 file:py-2 file:text-sm file:font-semibold file:text-[rgb(var(--theme-primary-ink-rgb))]"
                      />

                      {pendingFile ? (
                        <p className="text-sm text-foreground">
                          Selected file: <span className="font-medium">{pendingFile.name}</span>
                        </p>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No new file selected.
                        </p>
                      )}

                      {limit ? (
                        <p className="text-sm text-muted-foreground">
                          Max size: {limit.max_width}x{limit.max_height} px,{' '}
                          {Math.round(limit.max_size_bytes / (1024 * 1024))} MB, formats:{' '}
                          {limit.allowed_formats.join(', ')}.
                        </p>
                      ) : null}

                      <Button
                        type="button"
                        variant="outline"
                        className="rounded-xl"
                        onClick={() => toggleBrandingClear(asset.field)}
                      >
                        {willClear ? 'Keep current asset' : 'Use bundled default'}
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium text-foreground">Rate-limit storage</p>
              <Badge
                variant={data.rate_limit_storage_meta?.is_shared_backend ? 'success' : 'warning'}
              >
                {data.rate_limit_storage_meta?.is_shared_backend
                  ? 'Shared backend'
                  : 'Single-node cache'}
              </Badge>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Backend: <code>{String(data.rate_limit_storage_meta?.cache_backend || 'unknown')}</code>
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Production rate limiting should run on a shared Redis cache with{' '}
              <code>USE_REDIS=true</code>. Configure <code>TRUSTED_PROXY_IPS</code> so
              signup limits use the real client IP.
            </p>
            {data.rate_limit_storage_meta?.warning ? (
              <p className="mt-3 text-sm text-amber-700">
                {data.rate_limit_storage_meta.warning}
              </p>
            ) : null}
          </div>

          {(
            [
              {
                key: 'social_login_google_enabled' as SocialKey,
                title: 'Google social login',
                description: data.social_login_google_meta?.configured
                  ? 'Allow users to sign in or sign up with Google.'
                  : 'Add Google client credentials to the backend environment before enabling this provider.',
                configured: Boolean(data.social_login_google_meta?.configured),
              },
              {
                key: 'social_login_facebook_enabled' as SocialKey,
                title: 'Facebook social login',
                description: data.social_login_facebook_meta?.configured
                  ? 'Allow Facebook login. First-time Facebook users must verify email before access is granted.'
                  : 'Add Facebook client credentials to the backend environment before enabling this provider.',
                configured: Boolean(data.social_login_facebook_meta?.configured),
              },
              {
                key: 'social_login_github_enabled' as SocialKey,
                title: 'GitHub social login',
                description: data.social_login_github_meta?.configured
                  ? 'Allow users to sign in or sign up with GitHub using a verified GitHub email.'
                  : 'Add GitHub client credentials to the backend environment before enabling this provider.',
                configured: Boolean(data.social_login_github_meta?.configured),
              },
            ] as Array<{
              key: SocialKey
              title: string
              description: string
              configured: boolean
            }>
          ).map((provider) => (
            <div
              key={provider.key}
              className="flex items-center justify-between gap-4 rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium text-foreground">{provider.title}</p>
                  <Badge variant={provider.configured ? 'success' : 'warning'}>
                    {provider.configured ? 'Configured' : 'Missing credentials'}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{provider.description}</p>
              </div>
              <Switch
                checked={formState[provider.key]}
                onCheckedChange={(value) => handleChange(provider.key, value)}
                disabled={!provider.configured}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="theme-panel rounded-[1.8rem] border-0">
        <CardHeader>
          <CardTitle>AI provider configuration</CardTitle>
          <CardDescription>
            Provider selection and environment-managed AI secret status.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Provider
              </p>
              <CustomSelect
                value={formState.ai_provider}
                onChange={(value) => handleChange('ai_provider', value)}
                options={[
                  { label: 'OpenAI', value: 'openai' },
                  { label: 'Anthropic', value: 'anthropic' },
                ]}
              />
            </div>
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Default model
              </p>
              <Input
                value={
                  formState.ai_provider === 'openai'
                    ? formState.ai_model_openai
                    : formState.ai_model_anthropic
                }
                onChange={(event) =>
                  handleChange(
                    formState.ai_provider === 'openai'
                      ? 'ai_model_openai'
                      : 'ai_model_anthropic',
                    event.target.value
                  )
                }
                placeholder={
                  formState.ai_provider === 'openai'
                    ? 'gpt-5-mini'
                    : 'claude-3-7-sonnet-latest'
                }
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="font-medium text-foreground">OpenAI key</p>
                <Badge variant={data.ai_api_key_openai_meta.configured ? 'success' : 'warning'}>
                  {data.ai_api_key_openai_meta.configured ? 'Configured' : 'Missing'}
                </Badge>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {data.ai_api_key_openai_meta.configured
                  ? 'Configured in the server environment. reactdjango does not expose provider secrets in the admin panel.'
                  : 'Configure `OPENAI_API_KEY` on the server to enable OpenAI requests and connection testing.'}
              </p>
            </div>

            <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="font-medium text-foreground">Anthropic key</p>
                <Badge
                  variant={data.ai_api_key_anthropic_meta.configured ? 'success' : 'warning'}
                >
                  {data.ai_api_key_anthropic_meta.configured ? 'Configured' : 'Missing'}
                </Badge>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {data.ai_api_key_anthropic_meta.configured
                  ? 'Configured in the server environment. reactdjango does not expose provider secrets in the admin panel.'
                  : 'Configure `ANTHROPIC_API_KEY` on the server to enable Anthropic requests and connection testing.'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button className="rounded-xl" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save settings'}
            </Button>
            <Button
              variant="outline"
              className="rounded-xl"
              onClick={handleTest}
              disabled={testing}
            >
              {testing ? 'Testing...' : 'Test connection'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
