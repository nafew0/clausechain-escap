'use client'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { getAnalyticsColors } from '@/lib/analytics'

import { ChartTooltip } from './chart-utils'

interface LineSeries {
  dataKey: string
  name?: string
  color?: string
}

interface QLineChartProps {
  data?: Record<string, unknown>[]
  lines?: LineSeries[]
  showDots?: boolean
  curved?: boolean
  showArea?: boolean
  showLabels?: boolean
  colorScheme?: string
  height?: number
}

export default function QLineChart({
  data = [],
  lines = [],
  showDots = false,
  curved = true,
  showArea = false,
  showLabels = false,
  colorScheme = 'default',
  height = 300,
}: QLineChartProps) {
  const palette = getAnalyticsColors(colorScheme)
  const lineSeries: LineSeries[] = lines.length
    ? lines
    : [{ dataKey: 'count', name: 'Count', color: palette[0] }]

  return (
    <div className="h-[300px] w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data}>
          <defs>
            {lineSeries.map((line, index) => (
              <linearGradient id={`line-fill-${index}`} key={line.dataKey} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={line.color || palette[index % palette.length]} stopOpacity={0.3} />
                <stop offset="95%" stopColor={line.color || palette[index % palette.length]} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="rgb(var(--theme-border-rgb) / 0.55)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: 'rgb(var(--theme-muted-foreground-rgb))', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: 'rgb(var(--theme-muted-foreground-rgb))', fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} />
          {lineSeries.map((line, index) => (
            showArea ? (
              <Area
                key={line.dataKey}
                type={curved ? 'monotone' : 'linear'}
                dataKey={line.dataKey}
                name={line.name || line.dataKey}
                stroke={line.color || palette[index % palette.length]}
                fill={`url(#line-fill-${index})`}
                strokeWidth={2}
              >
                {showLabels ? <LabelList dataKey={line.dataKey} position="top" fontSize={11} /> : null}
              </Area>
            ) : (
              <Line
                key={line.dataKey}
                type={curved ? 'monotone' : 'linear'}
                dataKey={line.dataKey}
                name={line.name || line.dataKey}
                stroke={line.color || palette[index % palette.length]}
                strokeWidth={2.5}
                dot={showDots || showLabels}
              >
                {showLabels ? <LabelList dataKey={line.dataKey} position="top" fontSize={11} /> : null}
              </Line>
            )
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
