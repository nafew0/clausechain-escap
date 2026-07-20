'use client'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { getAnalyticsColors } from '@/lib/analytics'

import { ChartTooltip } from './chart-utils'

interface BarSeries {
  dataKey: string
  name?: string
  fill?: string
}

interface QBarChartProps {
  data?: Record<string, unknown>[]
  dataKey?: string
  nameKey?: string
  colors?: string[]
  colorScheme?: string
  showLabels?: boolean
  orientation?: 'vertical' | 'horizontal'
  stacked?: boolean
  series?: BarSeries[]
  height?: number
}

export default function QBarChart({
  data = [],
  dataKey = 'count',
  nameKey = 'label',
  colors,
  colorScheme = 'default',
  showLabels = false,
  orientation = 'vertical',
  stacked = false,
  series,
  height = 300,
}: QBarChartProps) {
  const palette = colors || getAnalyticsColors(colorScheme)
  const barSeries: BarSeries[] = series?.length
    ? series
    : [{ dataKey, name: dataKey, fill: palette[0] }]
  const useDistributedCells = barSeries.length === 1 && !stacked

  return (
    <div className="h-[300px] w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout={orientation === 'horizontal' ? 'vertical' : 'horizontal'}>
          <CartesianGrid stroke="rgb(var(--theme-border-rgb) / 0.55)" vertical={false} />
          <XAxis
            type={orientation === 'horizontal' ? 'number' : 'category'}
            dataKey={orientation === 'horizontal' ? undefined : nameKey}
            tick={{ fill: 'rgb(var(--theme-muted-foreground-rgb))', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type={orientation === 'horizontal' ? 'category' : 'number'}
            dataKey={orientation === 'horizontal' ? nameKey : undefined}
            tick={{ fill: 'rgb(var(--theme-muted-foreground-rgb))', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={orientation === 'horizontal' ? 100 : 40}
          />
          <Tooltip content={<ChartTooltip />} />
          {barSeries.map((item, index) => (
            <Bar
              key={item.dataKey}
              dataKey={item.dataKey}
              name={item.name || item.dataKey}
              fill={item.fill || palette[index % palette.length]}
              radius={orientation === 'horizontal' ? [0, 10, 10, 0] : [10, 10, 0, 0]}
              stackId={stacked ? 'stack' : undefined}
            >
              {useDistributedCells
                ? data.map((entry, i) => (
                    <Cell
                      key={`${item.dataKey}-${String(entry[nameKey] ?? i)}`}
                      fill={palette[i % palette.length]}
                    />
                  ))
                : null}
              {showLabels ? (
                <LabelList
                  dataKey={item.dataKey}
                  position={orientation === 'horizontal' ? 'right' : 'top'}
                  fontSize={11}
                />
              ) : null}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
