'use client'

interface TooltipEntry {
  dataKey: string
  name?: string
  value: number | string
}

interface ChartTooltipProps {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string
  formatter?: (value: number | string, entry: TooltipEntry) => React.ReactNode
}

export function ChartTooltip({ active, payload, label, formatter }: ChartTooltipProps) {
  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="theme-panel rounded-2xl px-3 py-2 text-xs shadow-lg">
      {label ? <p className="font-semibold text-foreground">{label}</p> : null}
      <div className="mt-1 space-y-1">
        {payload.map((entry) => (
          <div key={entry.dataKey} className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">{entry.name || entry.dataKey}</span>
            <span className="font-semibold text-foreground">
              {formatter ? formatter(entry.value, entry) : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
