'use client'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'

import {
  buildSiteThemeVariables,
  DEFAULT_SITE_THEME_ID,
  normalizeHex,
  resolveThemeColors,
  SITE_THEME_PRESETS,
  SITE_THEME_STORAGE_KEY,
  type ThemeColors,
} from '@/lib/siteTheme'

type SiteThemePreset = typeof SITE_THEME_PRESETS[number]

interface ThemeState {
  mode: 'preset' | 'custom'
  presetId: string
  customColors: ThemeColors
}

interface SiteThemeContextValue {
  presets: SiteThemePreset[]
  mode: string
  activePreset: SiteThemePreset
  activeColors: ThemeColors
  setPresetTheme: (presetId: string) => void
  setCustomColor: (role: string, value: string) => void
  resetTheme: () => void
}

const SiteThemeContext = createContext<SiteThemeContextValue | null>(null)

function readInitialThemeState(): ThemeState {
  const fallback: ThemeState = {
    mode: 'preset',
    presetId: DEFAULT_SITE_THEME_ID,
    customColors: SITE_THEME_PRESETS[0].colors,
  }

  if (typeof window === 'undefined') {
    return fallback
  }

  const stored = window.localStorage.getItem(SITE_THEME_STORAGE_KEY)
  if (!stored) {
    return fallback
  }

  try {
    const parsed = JSON.parse(stored)
    const colors = resolveThemeColors(parsed)

    return {
      mode: parsed.mode === 'custom' ? 'custom' : 'preset',
      presetId: parsed.presetId || DEFAULT_SITE_THEME_ID,
      customColors: colors,
    }
  } catch (error) {
    console.error('Unable to read site theme:', error)
    return fallback
  }
}

export function useSiteTheme(): SiteThemeContextValue {
  const context = useContext(SiteThemeContext)
  if (!context) {
    throw new Error('useSiteTheme must be used within a SiteThemeProvider')
  }

  return context
}

export function SiteThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeState, setThemeState] = useState<ThemeState>(readInitialThemeState)

  const activeColors = useMemo(() => resolveThemeColors(themeState), [themeState])
  const activePreset =
    SITE_THEME_PRESETS.find((preset) => preset.id === themeState.presetId) ??
    SITE_THEME_PRESETS[0]
  const themeVariables = useMemo(
    () => buildSiteThemeVariables(activeColors),
    [activeColors]
  )

  useEffect(() => {
    Object.entries(themeVariables).forEach(([property, value]) => {
      document.documentElement.style.setProperty(property, value)
    })
  }, [themeVariables])

  useEffect(() => {
    window.localStorage.setItem(
      SITE_THEME_STORAGE_KEY,
      JSON.stringify({
        mode: themeState.mode,
        presetId: themeState.presetId,
        customColors: activeColors,
      })
    )
  }, [activeColors, themeState.mode, themeState.presetId])

  const setPresetTheme = (presetId: string) => {
    setThemeState((current) => ({
      mode: 'preset',
      presetId,
      customColors: current.customColors,
    }))
  }

  const setCustomColor = (role: string, value: string) => {
    setThemeState((current) => {
      const nextBase = resolveThemeColors(current)
      const roleKey = role as keyof ThemeColors

      return {
        mode: 'custom',
        presetId: current.presetId,
        customColors: {
          ...nextBase,
          ...(current.customColors ?? {}),
          [roleKey]: normalizeHex(value, nextBase[roleKey]),
        },
      }
    })
  }

  const resetTheme = () => {
    setThemeState({
      mode: 'preset',
      presetId: DEFAULT_SITE_THEME_ID,
      customColors: SITE_THEME_PRESETS[0].colors,
    })
  }

  const value: SiteThemeContextValue = {
    presets: SITE_THEME_PRESETS,
    mode: themeState.mode,
    activePreset,
    activeColors,
    setPresetTheme,
    setCustomColor,
    resetTheme,
  }

  return (
    <SiteThemeContext.Provider value={value}>
      {children}
    </SiteThemeContext.Provider>
  )
}
