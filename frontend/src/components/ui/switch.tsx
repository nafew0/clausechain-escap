'use client'
import { cn } from '@/lib/utils'

interface SwitchProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
}

function Switch({ checked, onCheckedChange, className, disabled = false, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => {
        if (!disabled) {
          onCheckedChange?.(!checked)
        }
      }}
      className={cn(
        'relative inline-flex h-7 w-12 shrink-0 items-center rounded-[0.8rem] border border-transparent transition disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'bg-primary' : 'bg-[rgb(var(--theme-neutral-strong-rgb))]',
        className
      )}
      {...props}
    >
      <span
        className={cn(
          'pointer-events-none inline-block h-5 w-5 transform rounded-[0.6rem] bg-white shadow-sm transition',
          checked ? 'translate-x-6' : 'translate-x-1'
        )}
      />
    </button>
  )
}

export { Switch }
