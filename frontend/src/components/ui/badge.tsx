'use client'
import { cn } from '@/lib/utils'

const BADGE_VARIANTS = {
  default:
    'border-primary/20 bg-primary/10 text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]',
  secondary:
    'border-[rgb(var(--theme-secondary-strong-rgb)/0.92)] bg-[rgb(var(--theme-secondary-soft-rgb)/0.82)] text-[rgb(var(--theme-secondary-ink-rgb))]',
  success: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  warning: 'bg-amber-100 text-amber-700 border-amber-200',
  danger: 'bg-rose-100 text-rose-700 border-rose-200',
  outline:
    'border-[rgb(var(--theme-accent-strong-rgb)/0.88)] bg-[rgb(var(--theme-accent-soft-rgb)/0.68)] text-[rgb(var(--theme-accent-ink-rgb))]',
}

type BadgeVariant = keyof typeof BADGE_VARIANTS

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em] !rounded-[0.78rem]',
        BADGE_VARIANTS[variant] ?? BADGE_VARIANTS.default,
        className
      )}
      {...props}
    />
  )
}

export { Badge }
