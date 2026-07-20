'use client'
import { cn } from '@/lib/utils'
import { useBranding } from '@/contexts/BrandingContext'

interface BrandLogoProps {
  className?: string
  imageClassName?: string
  compact?: boolean
}

export default function BrandLogo({ className, imageClassName, compact = false }: BrandLogoProps) {
  const { logoUrl } = useBranding()

  return (
    <div className={cn('flex items-center', className)}>
      <img
        src={logoUrl}
        alt="ClauseChain logo"
        loading="eager"
        decoding="async"
        className={cn(
          'block shrink-0 object-contain [filter:drop-shadow(0_1px_1px_rgba(255,255,255,0.8))_drop-shadow(0_2px_8px_rgba(91,45,98,0.08))]',
          compact
            ? 'h-[1.45rem] w-[7.8rem] sm:h-[1.6rem] sm:w-[8.6rem]'
            : 'h-[2.1rem] w-[11.4rem] sm:h-[2.35rem] sm:w-[12.8rem] lg:h-[2.55rem] lg:w-[13.9rem]',
          imageClassName
        )}
      />
    </div>
  )
}
