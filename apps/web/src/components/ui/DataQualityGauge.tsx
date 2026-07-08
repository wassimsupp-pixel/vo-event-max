'use client'

import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { cn } from '@/lib/utils'

interface DataQualityGaugeProps {
  percentage: number
  label?: string
  size?: number
  className?: string
}

export function DataQualityGauge({
  percentage,
  label = 'Qualité globale',
  size = 140,
  className,
}: DataQualityGaugeProps) {
  const clampedPct = Math.min(100, Math.max(0, percentage))

  const color =
    clampedPct >= 80
      ? 'var(--color-success)'
      : clampedPct >= 60
        ? 'var(--color-warning)'
        : 'var(--color-danger)'

  const trackColor = 'var(--color-border)'

  const data = [
    { value: clampedPct },
    { value: 100 - clampedPct },
  ]

  const textColor =
    clampedPct >= 80
      ? '#47AB75'
      : clampedPct >= 60
        ? '#F99A4C'
        : '#D9534F'

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div style={{ width: size, height: size }} className="relative">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={size * 0.32}
              outerRadius={size * 0.46}
              startAngle={90}
              endAngle={-270}
              dataKey="value"
              strokeWidth={0}
            >
              <Cell fill={color} />
              <Cell fill={trackColor} />
            </Pie>
          </PieChart>
        </ResponsiveContainer>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="text-2xl font-bold leading-none tabular-nums"
            style={{ color: textColor }}
          >
            {clampedPct}%
          </span>
        </div>
      </div>

      {label && (
        <p className="mt-2 text-center text-xs font-medium text-[var(--color-text-secondary)]">
          {label}
        </p>
      )}
    </div>
  )
}
