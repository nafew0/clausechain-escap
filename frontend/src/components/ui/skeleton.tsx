'use client'
import { cn } from '@/lib/utils'

export function Skeleton({ className = '' }) {
  return <div className={cn('animate-pulse rounded-2xl bg-[rgb(var(--theme-neutral-strong-rgb))]', className)} />
}
