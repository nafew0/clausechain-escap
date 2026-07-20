'use client'
import { cn } from '@/lib/utils'

interface ProgressProps {
  value?: number
  className?: string
}

function Progress({ value = 0, className }: ProgressProps) {
  return (
    <div className={cn('h-2.5 w-full overflow-hidden rounded-full bg-slate-200', className)}>
      <div
        className="h-full rounded-full bg-primary transition-all"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  )
}

export { Progress }
