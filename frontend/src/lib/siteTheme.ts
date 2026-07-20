interface Rgb { r: number; g: number; b: number }
interface Hsl { h: number; s: number; l: number }

export interface ThemeColors {
  primary: string
  secondary: string
  accent: string
}

interface ThemeState {
  mode?: string
  presetId?: string
  customColors?: Partial<ThemeColors>
}

const WHITE_RGB: Rgb = { r: 255, g: 255, b: 255 }
const FOREGROUND_RGB: Rgb = { r: 15, g: 23, b: 42 }
const DEFAULT_SITE_COLORS: ThemeColors = {
  primary: '#1d6fb8',
  secondary: '#bc5eb3',
  accent: '#5b2d62',
}

export const SITE_THEME_STORAGE_KEY = 'reactdjango-site-theme'

export const DEFAULT_SITE_THEME_ID = 'quest-default'

export const SITE_THEME_PRESETS = [
  {
    id: 'quest-default',
    name: 'ClauseChain ESCAP',
    description: 'ESCAP authority blue with orchid and deep plum accents.',
    colors: DEFAULT_SITE_COLORS,
  },
  {
    id: 'citrus-studio',
    name: 'Citrus Studio',
    description: 'Orange, teal, and sky.',
    colors: {
      primary: '#ea580c',
      secondary: '#0f766e',
      accent: '#0284c7',
    },
  },
  {
    id: 'harbor-signal',
    name: 'Harbor Signal',
    description: 'Teal, cobalt, and coral.',
    colors: {
      primary: '#0f766e',
      secondary: '#1d4ed8',
      accent: '#fb7185',
    },
  },
  {
    id: 'ember-field',
    name: 'Ember Field',
    description: 'Crimson, spruce, and gold.',
    colors: {
      primary: '#dc2626',
      secondary: '#166534',
      accent: '#f59e0b',
    },
  },
  {
    id: 'grove-board',
    name: 'Grove Board',
    description: 'Forest, cyan, and amber.',
    colors: {
      primary: '#15803d',
      secondary: '#0f766e',
      accent: '#d97706',
    },
  },
]

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function round(value: number, digits = 1): number {
  return Number(value.toFixed(digits))
}

export function normalizeHex(value: string | null | undefined, fallback = DEFAULT_SITE_COLORS.primary): string {
  if (!value) {
    return fallback
  }

  const trimmed = value.trim()
  const withHash = trimmed.startsWith('#') ? trimmed : `#${trimmed}`

  if (/^#[0-9a-f]{3}$/i.test(withHash)) {
    return `#${withHash
      .slice(1)
      .split('')
      .map((part: string) => `${part}${part}`)
      .join('')
      .toLowerCase()}`
  }

  if (/^#[0-9a-f]{6}$/i.test(withHash)) {
    return withHash.toLowerCase()
  }

  return fallback
}

function hexToRgb(value: string): Rgb {
  const hex = normalizeHex(value)

  return {
    r: Number.parseInt(hex.slice(1, 3), 16),
    g: Number.parseInt(hex.slice(3, 5), 16),
    b: Number.parseInt(hex.slice(5, 7), 16),
  }
}

function rgbToCssValue({ r, g, b }: Rgb): string {
  return `${r} ${g} ${b}`
}

function mixRgb(base: Rgb, mixWith: Rgb, mixWeight: number): Rgb {
  return {
    r: Math.round(base.r * (1 - mixWeight) + mixWith.r * mixWeight),
    g: Math.round(base.g * (1 - mixWeight) + mixWith.g * mixWeight),
    b: Math.round(base.b * (1 - mixWeight) + mixWith.b * mixWeight),
  }
}

function rgbToHsl({ r, g, b }: Rgb): Hsl {
  const red = r / 255
  const green = g / 255
  const blue = b / 255
  const max = Math.max(red, green, blue)
  const min = Math.min(red, green, blue)
  const delta = max - min

  let hue = 0

  if (delta !== 0) {
    if (max === red) {
      hue = ((green - blue) / delta) % 6
    } else if (max === green) {
      hue = (blue - red) / delta + 2
    } else {
      hue = (red - green) / delta + 4
    }
  }

  hue = Math.round(hue * 60)
  if (hue < 0) {
    hue += 360
  }

  const lightness = (max + min) / 2
  const saturation =
    delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1))

  return {
    h: clamp(hue, 0, 360),
    s: clamp(round(saturation * 100), 0, 100),
    l: clamp(round(lightness * 100), 0, 100),
  }
}

function hslToCssValue(rgb: Rgb): string {
  const { h, s, l } = rgbToHsl(rgb)
  return `${h} ${s}% ${l}%`
}

function getRelativeLuminance({ r, g, b }: Rgb): number {
  const channel = [r, g, b].map((value: number) => {
    const normalized = value / 255
    return normalized <= 0.03928
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4
  })

  return channel[0] * 0.2126 + channel[1] * 0.7152 + channel[2] * 0.0722
}

function getReadableForeground(background: Rgb): Rgb {
  return getRelativeLuminance(background) > 0.43 ? FOREGROUND_RGB : WHITE_RGB
}

function getPresetById(presetId: string): typeof SITE_THEME_PRESETS[number] {
  return (
    SITE_THEME_PRESETS.find((preset) => preset.id === presetId) ??
    SITE_THEME_PRESETS[0]
  )
}

export function resolveThemeColors(themeState: ThemeState = {}): ThemeColors {
  const preset = getPresetById(themeState.presetId ?? DEFAULT_SITE_THEME_ID)
  const baseColors: ThemeColors =
    themeState.mode === 'custom'
      ? {
          primary: normalizeHex(
            themeState.customColors?.primary,
            preset.colors.primary
          ),
          secondary: normalizeHex(
            themeState.customColors?.secondary,
            preset.colors.secondary
          ),
          accent: normalizeHex(
            themeState.customColors?.accent,
            preset.colors.accent
          ),
        }
      : preset.colors

  return {
    primary: normalizeHex(baseColors.primary, SITE_THEME_PRESETS[0].colors.primary),
    secondary: normalizeHex(
      baseColors.secondary,
      SITE_THEME_PRESETS[0].colors.secondary
    ),
    accent: normalizeHex(baseColors.accent, SITE_THEME_PRESETS[0].colors.accent),
  }
}

export function buildSiteThemeVariables(colors: ThemeColors): Record<string, string> {
  const primary = hexToRgb(colors.primary)
  const secondary = hexToRgb(colors.secondary)
  const accent = hexToRgb(colors.accent)

  const primarySoft = mixRgb(primary, WHITE_RGB, 0.88)
  const primaryStrong = mixRgb(primary, WHITE_RGB, 0.72)
  const primaryInk = mixRgb(FOREGROUND_RGB, primary, 0.22)

  const secondarySoft = mixRgb(secondary, WHITE_RGB, 0.89)
  const secondaryStrong = mixRgb(secondary, WHITE_RGB, 0.74)
  const secondaryInk = mixRgb(FOREGROUND_RGB, secondary, 0.18)

  const accentSoft = mixRgb(accent, WHITE_RGB, 0.9)
  const accentStrong = mixRgb(accent, WHITE_RGB, 0.72)
  const accentInk = mixRgb(FOREGROUND_RGB, accent, 0.2)

  const mixedBase = mixRgb(primary, secondary, 0.5)
  const mixedAccent = mixRgb(mixedBase, accent, 0.35)
  const mixedSoft = mixRgb(mixedAccent, WHITE_RGB, 0.92)
  const mixedStrong = mixRgb(mixedAccent, WHITE_RGB, 0.78)
  const neutral = mixRgb(mixedBase, WHITE_RGB, 0.95)
  const neutralStrong = mixRgb(mixedBase, WHITE_RGB, 0.9)

  const border = mixRgb(mixedBase, WHITE_RGB, 0.8)
  const input = mixRgb(secondary, WHITE_RGB, 0.84)
  const muted = mixRgb(primary, WHITE_RGB, 0.94)
  const mutedForeground = mixRgb(FOREGROUND_RGB, mixedBase, 0.35)
  const shadow = mixRgb(FOREGROUND_RGB, primary, 0.12)
  const heroSpot = mixRgb(accent, WHITE_RGB, 0.82)

  return {
    '--background': hslToCssValue(WHITE_RGB),
    '--foreground': hslToCssValue(FOREGROUND_RGB),
    '--card': hslToCssValue(WHITE_RGB),
    '--card-foreground': hslToCssValue(FOREGROUND_RGB),
    '--popover': hslToCssValue(WHITE_RGB),
    '--popover-foreground': hslToCssValue(FOREGROUND_RGB),
    '--primary': hslToCssValue(primary),
    '--primary-foreground': hslToCssValue(getReadableForeground(primary)),
    '--secondary': hslToCssValue(secondarySoft),
    '--secondary-foreground': hslToCssValue(secondaryInk),
    '--muted': hslToCssValue(muted),
    '--muted-foreground': hslToCssValue(mutedForeground),
    '--accent': hslToCssValue(accentSoft),
    '--accent-foreground': hslToCssValue(accentInk),
    '--destructive': '0 84.2% 60.2%',
    '--destructive-foreground': '210 40% 98%',
    '--border': hslToCssValue(border),
    '--input': hslToCssValue(input),
    '--ring': hslToCssValue(primary),
    '--theme-foreground-rgb': rgbToCssValue(FOREGROUND_RGB),
    '--theme-primary-rgb': rgbToCssValue(primary),
    '--theme-secondary-rgb': rgbToCssValue(secondary),
    '--theme-accent-rgb': rgbToCssValue(accent),
    '--theme-primary-soft-rgb': rgbToCssValue(primarySoft),
    '--theme-primary-strong-rgb': rgbToCssValue(primaryStrong),
    '--theme-primary-ink-rgb': rgbToCssValue(primaryInk),
    '--theme-secondary-soft-rgb': rgbToCssValue(secondarySoft),
    '--theme-secondary-strong-rgb': rgbToCssValue(secondaryStrong),
    '--theme-secondary-ink-rgb': rgbToCssValue(secondaryInk),
    '--theme-accent-soft-rgb': rgbToCssValue(accentSoft),
    '--theme-accent-strong-rgb': rgbToCssValue(accentStrong),
    '--theme-accent-ink-rgb': rgbToCssValue(accentInk),
    '--theme-mix-soft-rgb': rgbToCssValue(mixedSoft),
    '--theme-mix-strong-rgb': rgbToCssValue(mixedStrong),
    '--theme-neutral-rgb': rgbToCssValue(neutral),
    '--theme-neutral-strong-rgb': rgbToCssValue(neutralStrong),
    '--theme-border-rgb': rgbToCssValue(border),
    '--theme-input-rgb': rgbToCssValue(input),
    '--theme-muted-rgb': rgbToCssValue(muted),
    '--theme-muted-foreground-rgb': rgbToCssValue(mutedForeground),
    '--theme-shadow-rgb': rgbToCssValue(shadow),
    '--theme-hero-start-rgb': rgbToCssValue(primarySoft),
    '--theme-hero-end-rgb': rgbToCssValue(mixedSoft),
    '--theme-hero-spot-rgb': rgbToCssValue(heroSpot),
  }
}
