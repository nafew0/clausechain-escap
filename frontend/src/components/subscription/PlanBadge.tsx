'use client'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const PLAN_STYLES = {
  free: 'border-slate-200 bg-slate-100 text-slate-700',
  pro: 'border-sky-200 bg-sky-100 text-sky-700',
  enterprise: 'border-emerald-200 bg-emerald-100 text-emerald-700',
}

type PlanSlug = keyof typeof PLAN_STYLES

interface PlanBadgeProps {
  plan?: { slug?: string; name?: string }
  className?: string
}

function PlanBadge({ plan, className }: PlanBadgeProps) {
  const slug = ((plan?.slug || 'free').toLowerCase()) as PlanSlug
  const label = plan?.name ? `${plan.name} Plan` : 'Free Plan'

  return (
    <Badge
      variant="secondary"
      className={cn(PLAN_STYLES[slug] ?? PLAN_STYLES.free, className)}
    >
      {label}
    </Badge>
  )
}

export default PlanBadge
