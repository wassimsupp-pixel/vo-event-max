'use client'

import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

type Severity = 'critical' | 'warning' | 'info'

interface ExceptionItemProps {
  type: string
  count: number
  severity: Severity
  onClick?: () => void
  className?: string
}

const severityConfig: Record<Severity, { dot: string; badge: string; badgeText: string }> = {
  critical: {
    dot: 'bg-[var(--color-text-primary)]',
    badge: 'bg-[var(--color-text-primary)] text-white',
    badgeText: '',
  },
  warning: {
    dot: 'bg-gray-500',
    badge: 'bg-gray-200 text-[var(--color-text-primary)]',
    badgeText: '',
  },
  info: {
    dot: 'bg-gray-300',
    badge: 'bg-gray-100 text-gray-500',
    badgeText: '',
  },
}

export function ExceptionItem({ type, count, severity, onClick, className }: ExceptionItemProps) {
  const cfg = severityConfig[severity]

  return (
    <button
      onClick={onClick}
      className={cn(
        'group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left',
        'transition-colors hover:bg-[var(--color-bg-subtle)]',
        'border border-transparent hover:border-[var(--color-border)]',
        className
      )}
    >
      {/* Colored dot */}
      <span className={cn('h-2 w-2 flex-shrink-0 rounded-full', cfg.dot)} />

      {/* Label */}
      <span className="flex-1 text-sm font-medium text-[var(--color-text-primary)]">
        {type}
      </span>

      {/* Count badge */}
      <span
        className={cn(
          'flex-shrink-0 rounded-full px-2 py-0.5 text-xs font-bold tabular-nums',
          cfg.badge
        )}
      >
        {count}
      </span>

      {/* Arrow */}
      <ChevronRight className="h-4 w-4 flex-shrink-0 text-[var(--color-text-secondary)] transition-transform group-hover:translate-x-0.5" />
    </button>
  )
}
