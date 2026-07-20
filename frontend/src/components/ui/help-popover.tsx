'use client'
import * as React from 'react'
import { CircleHelp } from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from './dropdown-menu'

interface HelpPopoverProps {
  title?: string
  children?: React.ReactNode
  align?: 'start' | 'center' | 'end'
  contentClassName?: string
  triggerClassName?: string
}

export function HelpPopover({
  title = 'Help',
  children,
  align = 'start',
  contentClassName = '',
  triggerClassName = '',
}: HelpPopoverProps) {
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          onClick={(event) => event.stopPropagation()}
          className={cn(
            'inline-flex h-8 w-8 items-center justify-center rounded-full border border-[rgb(var(--theme-border-rgb)/0.82)] bg-white text-muted-foreground transition hover:border-[rgb(var(--theme-primary-rgb)/0.32)] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20',
            triggerClassName
          )}
        >
          <CircleHelp className="h-4 w-4" />
          <span className="sr-only">{title}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align={align}
        sideOffset={8}
        className={cn(
          'theme-panel w-80 rounded-[1.5rem] p-4',
          contentClassName
        )}
      >
        <div className="space-y-2">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <div className="text-sm leading-6 text-muted-foreground">{children}</div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
