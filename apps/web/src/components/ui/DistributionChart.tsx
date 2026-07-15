'use client'

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const defaultData = [
  { name: 'Vols', value: 72, color: '#806CAF' },
  { name: 'Hôtels', value: 68, color: '#47AB75' },
  { name: 'Transferts', value: 81, color: '#F99A4C' },
  { name: 'Activités', value: 45, color: '#3B82F6' },
  { name: 'Comms', value: 90, color: '#8B5CF6' },
]

interface DistributionChartProps {
  data?: Array<{ name: string; value: number; color: string }>
  /** When provided, each legend row becomes clickable and calls this with the item name. */
  onItemClick?: (name: string) => void
}

export function DistributionChart({ data: customData, onItemClick }: DistributionChartProps) {
  const activeData = customData || defaultData

  return (
    <div className="flex flex-col">
      <div className="h-[140px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={activeData}
              cx="50%"
              cy="50%"
              innerRadius={35}
              outerRadius={60}
              dataKey="value"
              strokeWidth={2}
              stroke="#fff"
            >
              {activeData.map((entry, index) => (
                <Cell key={index} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: any) => [`${value}%`, '']}
              contentStyle={{
                borderRadius: '8px',
                border: '1px solid #ECECEC',
                fontSize: '12px',
                boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <ul className="mt-2 grid grid-cols-1 gap-1">
        {activeData.map((item) => (
          <li key={item.name}>
            <button
              type="button"
              onClick={onItemClick ? () => onItemClick(item.name) : undefined}
              className={
                'flex w-full items-center justify-between rounded px-1.5 py-0.5 text-xs transition-colors ' +
                (onItemClick ? 'cursor-pointer hover:bg-[var(--color-bg-subtle)]' : 'cursor-default')
              }
            >
              <span className="flex items-center gap-1.5">
                <span
                  className="h-2 w-2 flex-shrink-0 rounded-full"
                  style={{ background: item.color }}
                />
                <span className="text-[var(--color-text-secondary)]">{item.name}</span>
              </span>
              <span className="font-semibold tabular-nums text-[var(--color-text-primary)]">
                {item.value}%
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
