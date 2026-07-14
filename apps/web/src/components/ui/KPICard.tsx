import { ReactNode } from 'react'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface KPICardProps {
  label: string
  value: string | number
  delta?: string
  deltaPositive?: boolean
  icon?: ReactNode
  accentColor?: string
  className?: string
  /** When provided, the whole card becomes a link to this route. */
  href?: string
}

export function KPICard({
  label,
  value,
  delta,
  deltaPositive,
  icon,
  accentColor = 'var(--color-accent)',
  className,
  href,
}: KPICardProps) {
  const DeltaIcon =
    deltaPositive === true
      ? TrendingUp
      : deltaPositive === false
        ? TrendingDown
        : Minus

  const deltaColor =
    deltaPositive === true
      ? 'text-[var(--color-success)]'
      : deltaPositive === false
        ? 'text-[var(--color-danger)]'
        : 'text-[var(--color-text-secondary)]'

  const content = (
    <div
      className={cn(
        'relative h-full overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5',
        'shadow-[var(--shadow-card)] transition-all hover:shadow-md',
        href && 'cursor-pointer hover:border-[var(--color-accent)]',
        className
      )}
      style={{ borderLeft: `3px solid ${accentColor}` }}
    >
      {/* Icon */}
      {icon && (
        <div
          className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-lg opacity-80"
          style={{ background: `${accentColor}18` }}
        >
          <span style={{ color: accentColor }}>{icon}</span>
        </div>
      )}

      {/* Value */}
      <div className="text-[40px] font-bold leading-none tracking-tight text-[var(--color-text-primary)]">
        {value}
      </div>

      {/* Label */}
      <div className="mt-1.5 text-sm font-medium text-[var(--color-text-secondary)]">
        {label}
      </div>

      {/* Delta */}
      {delta && (
        <div className={cn('mt-2 flex items-center gap-1 text-xs font-medium', deltaColor)}>
          <DeltaIcon className="h-3 w-3" />
          {delta}
        </div>
      )}
    </div>
  )

  if (href) {
    return (
      <Link href={href} className="block h-full">
        {content}
      </Link>
    )
  }

  return content
}
