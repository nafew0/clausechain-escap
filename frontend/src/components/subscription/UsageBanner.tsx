'use client'
import Link from 'next/link'
import { AlertTriangle, ArrowRight, Sparkles } from 'lucide-react'

import PlanBadge from '@/components/subscription/PlanBadge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

interface ItemUsage {
  used: number
  limit: number
  unlimited: boolean
}

interface Usage {
  items?: ItemUsage
  plan?: Record<string, unknown>
}

function UsageBanner({ usage, className }: { usage?: Usage; className?: string }) {
  const itemUsage = usage?.items

  if (!itemUsage || itemUsage.unlimited || !itemUsage.limit) {
    return null
  }

  const percentage = Math.max(
    0,
    Math.min(100, Math.round((itemUsage.used / itemUsage.limit) * 100))
  )
  const atLimit = itemUsage.used >= itemUsage.limit

  return (
    <div
      className={cn(
        'rounded-[2rem] border px-5 py-5 shadow-[0_18px_40px_rgb(var(--theme-shadow-rgb)/0.08)]',
        atLimit
          ? 'border-rose-200 bg-rose-50/95'
          : 'border-amber-200 bg-amber-50/95',
        className
      )}
    >
      <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                'inline-flex h-10 w-10 items-center justify-center rounded-2xl',
                atLimit ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'
              )}
            >
              {atLimit ? (
                <AlertTriangle className="h-5 w-5" />
              ) : (
                <Sparkles className="h-5 w-5" />
              )}
            </span>
            <PlanBadge plan={usage?.plan} />
          </div>

          <div>
            <h2 className="text-xl font-semibold tracking-tight text-foreground">
              {atLimit
                ? 'Item limit reached'
                : `You've used ${itemUsage.used} of ${itemUsage.limit} items`}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {atLimit
                ? `You've reached the item cap on the ${usage?.plan?.name as string || 'Free'} plan. Upgrade to create more.`
                : `You're approaching the item cap on the ${usage?.plan?.name as string || 'Free'} plan. Upgrade before you run out of slots.`}
            </p>
          </div>

          <div className="max-w-xl space-y-2">
            <Progress value={percentage} className="h-3 bg-white/80" />
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {percentage}% of item capacity used
            </p>
          </div>
        </div>

        <Button asChild className="min-w-40 rounded-full">
          <Link href="/pricing">
            Upgrade plan
            <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </div>
    </div>
  )
}

export default UsageBanner
