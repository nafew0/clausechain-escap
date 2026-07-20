'use client'
import { useState } from 'react'
import { ArrowRight, CheckCircle2, Sparkles } from 'lucide-react'

import BrandLogo from '@/components/branding/BrandLogo'
import { Badge } from '@/components/ui/badge'

interface Metric {
  value: string
  label: string
}

interface AuthShellProps {
  eyebrow?: string
  title?: string
  description?: string
  imageSrc?: string
  imageAlt?: string
  showcaseTitle?: string
  showcaseDescription?: string
  metrics?: Metric[]
  highlights?: string[]
  children: React.ReactNode
  footer?: React.ReactNode
}

function MediaFallback() {
  return (
    <div className="relative overflow-hidden rounded-[1.55rem_2.25rem_1.55rem_1.55rem] border border-white/50 bg-white/70 p-5 shadow-[0_24px_60px_rgb(var(--theme-shadow-rgb)/0.14)] backdrop-blur">
      <div className="absolute inset-x-8 top-0 h-20 rounded-b-[2rem] bg-[rgb(var(--theme-primary-rgb)/0.12)]" />

      <div className="relative space-y-4">
        <div className="flex items-center justify-between rounded-[1.4rem] border border-[rgb(var(--theme-border-rgb)/0.78)] bg-white px-4 py-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Workspace
            </p>
            <p className="mt-1 text-base font-semibold text-foreground">Question flow locked</p>
          </div>
          <div className="theme-icon-primary flex h-10 w-10 items-center justify-center rounded-2xl">
            <Sparkles className="h-4 w-4" />
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-[1.6rem] border border-[rgb(var(--theme-border-rgb)/0.78)] bg-[rgb(var(--theme-primary-soft-rgb)/0.66)] p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[rgb(var(--theme-primary-ink-rgb))]">
              Project board
            </p>
            <div className="mt-4 space-y-3">
              {[
                ['Onboarding', 'Active'],
                ['Checkout', 'Configured'],
                ['Dashboard', 'Analytics ready'],
              ].map(([label, meta]) => (
                <div
                  key={label}
                  className="flex items-center justify-between rounded-[1.25rem] border border-white/70 bg-white/80 px-3 py-2"
                >
                  <p className="text-sm font-medium text-foreground">{label}</p>
                  <span className="theme-chip-secondary px-2 py-1 text-[10px]">{meta}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded-[1.6rem] border border-[rgb(var(--theme-border-rgb)/0.78)] bg-white/85 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Activity pulse
              </p>
              <div className="mt-4 flex items-end gap-2">
                {[36, 58, 44, 72, 64].map((height, index) => (
                  <span
                    key={index}
                    className={index % 2 === 0
                      ? 'flex-1 rounded-t-full bg-[rgb(var(--theme-primary-rgb)/0.85)]'
                      : 'flex-1 rounded-t-full bg-[rgb(var(--theme-secondary-rgb)/0.82)]'}
                    style={{ height: `${height}px` }}
                  />
                ))}
              </div>
            </div>
            <div className="rounded-[1.6rem] border border-[rgb(var(--theme-border-rgb)/0.78)] bg-[rgb(var(--theme-accent-soft-rgb)/0.82)] p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-[rgb(var(--theme-accent-ink-rgb))]">
                <ArrowRight className="h-4 w-4" />
                Share links, email invites, and report exports in one flow.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function AuthShell({
  eyebrow = '',
  title = '',
  description = '',
  imageSrc,
  imageAlt,
  showcaseTitle = '',
  showcaseDescription = '',
  metrics = [],
  highlights = [],
  children,
  footer,
}: AuthShellProps) {
  const [failedImageSrc, setFailedImageSrc] = useState<string | undefined>()
  const showImage = Boolean(imageSrc && failedImageSrc !== imageSrc)

  return (
    <div className="theme-app-gradient min-h-[calc(100vh-4rem)] px-4 py-8 sm:px-6 sm:py-10">
      <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="relative overflow-hidden rounded-[2rem_2rem_3rem_1.65rem] border border-[rgb(var(--theme-border-rgb)/0.82)] bg-[rgb(var(--theme-neutral-rgb)/0.9)] p-6 shadow-[0_28px_80px_rgb(var(--theme-shadow-rgb)/0.12)] sm:p-8">
          <div className="relative">
            <BrandLogo />
            <Badge variant="secondary" className="mt-8 rounded-full px-3 py-1 text-[11px] uppercase tracking-[0.22em]">
              {eyebrow}
            </Badge>
            <h1
              className="mt-5 max-w-xl text-4xl font-semibold tracking-tight text-[rgb(var(--theme-primary-ink-rgb))] sm:text-5xl"
              style={{ fontFamily: '"Merriweather", serif' }}
            >
              {showcaseTitle}
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-8 text-[rgb(var(--theme-secondary-ink-rgb))] sm:text-lg">
              {showcaseDescription}
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {metrics.map((metric, index) => (
                <div
                  key={metric.label}
                  className={`border border-white/70 bg-white/82 px-4 py-4 shadow-[0_18px_40px_rgb(var(--theme-shadow-rgb)/0.08)] ${
                    index === 0
                      ? 'rounded-[1.3rem_1.3rem_2rem_1.3rem]'
                      : index === 1
                        ? 'rounded-[1.8rem_1.1rem_1.8rem_1.1rem]'
                        : 'rounded-[1.05rem_1.8rem_1.05rem_1.8rem]'
                  }`}
                >
                  <p className="text-2xl font-semibold tracking-tight text-foreground">{metric.value}</p>
                  <p className="mt-1 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    {metric.label}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-8">
              {showImage ? (
                <div className="overflow-hidden rounded-[1.55rem_2.25rem_1.55rem_1.55rem] border border-white/60 bg-white/75 shadow-[0_24px_60px_rgb(var(--theme-shadow-rgb)/0.14)] backdrop-blur">
                  <img
                    src={imageSrc}
                    alt={imageAlt}
                    className="h-[22rem] w-full object-cover"
                    onError={() => setFailedImageSrc(imageSrc)}
                  />
                </div>
              ) : (
                <MediaFallback />
              )}
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {highlights.map((highlight, index) => (
                <div
                  key={highlight}
                  className={`flex items-start gap-3 border border-white/70 bg-white/80 px-4 py-3 ${
                    index % 2 === 0
                      ? 'rounded-[1.3rem_1.3rem_1.95rem_1.3rem]'
                      : 'rounded-[1rem_1.7rem_1rem_1.7rem]'
                  }`}
                >
                  <div className="theme-icon-secondary mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <p className="text-sm leading-6 text-[rgb(var(--theme-secondary-ink-rgb))]">
                    {highlight}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="theme-panel rounded-[1.9rem_2.55rem_1.9rem_1.55rem] p-6 sm:p-8">
          <Badge variant="outline" className="rounded-full px-3 py-1 text-[11px] uppercase tracking-[0.22em]">
            {eyebrow}
          </Badge>
          <h2 className="mt-5 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            {title}
          </h2>
          <p className="mt-3 max-w-xl text-base leading-8 text-muted-foreground">
            {description}
          </p>

          <div className="mt-8">{children}</div>

          {footer ? <div className="mt-8 border-t border-[rgb(var(--theme-border-rgb)/0.8)] pt-6">{footer}</div> : null}
        </section>
      </div>
    </div>
  )
}
