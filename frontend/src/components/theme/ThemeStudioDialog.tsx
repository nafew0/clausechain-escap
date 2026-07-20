'use client'
import { useMemo, useState } from 'react'
import { Palette, RotateCcw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { HelpPopover } from '@/components/ui/help-popover'
import { Input } from '@/components/ui/input'
import { useSiteTheme } from '@/contexts/SiteThemeContext'
import { normalizeHex, SITE_THEME_PRESETS, type ThemeColors } from '@/lib/siteTheme'

const COLOR_FIELDS: Array<{ key: keyof ThemeColors; label: string; helper: string }> = [
  {
    key: 'primary',
    label: 'Primary',
    helper: 'Main actions, links, and dominant highlights.',
  },
  {
    key: 'secondary',
    label: 'Secondary',
    helper: 'Support surfaces, cards, and softer chips.',
  },
  {
    key: 'accent',
    label: 'Accent',
    helper: 'Callouts, decorative chips, and contrast moments.',
  },
]

function ActiveChip() {
  return (
    <span className="rounded-full border border-[rgb(var(--theme-primary-strong-rgb)/0.88)] bg-[rgb(var(--theme-primary-soft-rgb)/0.88)] px-2 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.22em] text-[rgb(var(--theme-primary-ink-rgb))]">
      Active
    </span>
  )
}

export default function ThemeStudioDialog() {
  const {
    presets,
    mode,
    activePreset,
    activeColors,
    setPresetTheme,
    setCustomColor,
    resetTheme,
  } = useSiteTheme()
  const [open, setOpen] = useState(false)
  const [draftColors, setDraftColors] = useState(activeColors)

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      setDraftColors(activeColors)
    }
    setOpen(nextOpen)
  }

  const handleReset = () => {
    setDraftColors(SITE_THEME_PRESETS[0].colors)
    resetTheme()
  }

  const subtitle = useMemo(() => {
    if (mode === 'custom') {
      return 'Custom'
    }

    return activePreset?.name || 'Preset'
  }, [activePreset?.name, mode])

  const commitDraftColor = (key: keyof ThemeColors) => {
    const normalized = normalizeHex(draftColors[key], activeColors[key])
    setDraftColors((current) => ({
      ...current,
      [key]: normalized,
    }))
    setCustomColor(key, normalized)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          className="gap-2 rounded-full border-[rgb(var(--theme-border-rgb)/0.85)] bg-white/85 shadow-sm"
        >
          <Palette className="h-4 w-4 text-primary" />
          Theme
        </Button>
      </DialogTrigger>
      <DialogContent
        overlayClassName="bg-transparent backdrop-blur-0"
        className="left-auto right-2 top-[4.65rem] w-[min(50rem,calc(100vw-1rem))] max-h-[calc(100vh-5.5rem)] max-w-none translate-x-0 translate-y-0 gap-5 overflow-y-auto rounded-[1.5rem] border border-[rgb(var(--theme-border-rgb)/0.88)] bg-white p-4 pr-12 shadow-[0_24px_52px_rgb(var(--theme-shadow-rgb)/0.18)] sm:right-4 sm:w-[min(50rem,calc(100vw-2rem))] sm:p-5 sm:pr-14"
      >
        <DialogHeader className="space-y-0">
          <div className="flex items-center justify-between gap-3 pr-2">
            <div className="flex flex-wrap items-center gap-2">
              <DialogTitle className="text-lg font-semibold tracking-tight">
                Theme Studio
              </DialogTitle>
              <Badge variant="outline" className="rounded-full">
                {subtitle}
              </Badge>
            </div>
            <HelpPopover title="Site theme" align="end">
              Pick one preset or set your own primary, secondary, and accent colors. Softer chips, cards, and surfaces are derived mathematically from those three colors.
            </HelpPopover>
          </div>
          <DialogDescription className="sr-only">
            Configure the site-wide three-color palette.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground">Presets</p>
                <HelpPopover title="Presets">
                  Choose a ready-made palette. You can still adjust any color below.
                </HelpPopover>
              </div>
              <Button variant="ghost" size="sm" className="gap-2" onClick={handleReset}>
                <RotateCcw className="h-4 w-4" />
                Reset
              </Button>
            </div>

            <div className="-mx-1 overflow-x-auto px-1 pb-1">
              <div className="grid min-w-[44rem] grid-cols-5 gap-2">
                {presets.map((preset) => {
                  const isActive = mode === 'preset' && activePreset?.id === preset.id

                  return (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => {
                        setDraftColors(preset.colors)
                        setPresetTheme(preset.id)
                      }}
                      className={`relative overflow-hidden rounded-[1.1rem] border p-2.5 text-left transition ${
                        isActive
                          ? 'border-[rgb(var(--theme-primary-rgb)/0.55)] bg-[rgb(var(--theme-primary-soft-rgb)/0.46)] shadow-sm'
                          : 'border-[rgb(var(--theme-border-rgb)/0.8)] bg-white hover:border-[rgb(var(--theme-primary-rgb)/0.35)]'
                      }`}
                    >
                      <div className="flex min-h-10 items-start justify-between gap-2">
                        <p className="text-sm font-semibold leading-5 text-foreground">
                          {preset.name}
                        </p>
                        {isActive ? <ActiveChip /> : null}
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        {Object.values(preset.colors).map((color) => (
                          <span
                            key={`${preset.id}-${color}`}
                            className="h-6 w-6 rounded-full border border-white/80 shadow-sm"
                            style={{ backgroundColor: color }}
                          />
                        ))}
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          </section>

          <section className="rounded-[1.25rem] border border-[rgb(var(--theme-border-rgb)/0.8)] bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <p className="text-sm font-semibold text-foreground">Custom colors</p>
              <HelpPopover title="Custom palette">
                Primary usually drives buttons and focus states, secondary softens panels, and accent lifts chips and highlights.
              </HelpPopover>
            </div>

            <div className="-mx-1 overflow-x-auto px-1 pb-1">
              <div className="grid min-w-[34rem] grid-cols-3 gap-3">
                {COLOR_FIELDS.map((field) => (
                  <div
                    key={field.key}
                    className="rounded-[1.1rem] border border-[rgb(var(--theme-border-rgb)/0.75)] bg-white p-3"
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground">{field.label}</p>
                      <HelpPopover title={field.label} contentClassName="w-64">
                        {field.helper}
                      </HelpPopover>
                    </div>
                    <div className="grid grid-cols-[56px_minmax(0,1fr)] items-center gap-3">
                      <div className="theme-color-shell h-11">
                        <input
                          type="color"
                          value={activeColors[field.key]}
                          onChange={(event) => {
                            setDraftColors((current) => ({
                              ...current,
                              [field.key]: event.target.value,
                            }))
                            setCustomColor(field.key, event.target.value)
                          }}
                          className="theme-color-input"
                        />
                      </div>
                      <Input
                        value={draftColors[field.key]}
                        onChange={(event) =>
                          setDraftColors((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }))
                        }
                        onBlur={() => commitDraftColor(field.key)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault()
                            commitDraftColor(field.key)
                          }
                        }}
                        className="h-11 rounded-2xl uppercase"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}
