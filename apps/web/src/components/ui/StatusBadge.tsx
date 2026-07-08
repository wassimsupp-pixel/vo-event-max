'use client'

import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

type StatusType =
  | 'complete'
  | 'incomplete'
  | 'conflict'
  | 'certain'
  | 'probable'
  | 'to_verify'
  | 'not_found'

interface StatusBadgeProps {
  status: StatusType
  className?: string
}

const statusConfig: Record<
  StatusType,
  { bg: string; text: string; dot: string; labelKey: string }
> = {
  complete: {
    bg: 'bg-[var(--color-success-light)]',
    text: 'text-[var(--color-success)]',
    dot: 'bg-[var(--color-success)]',
    labelKey: 'complete',
  },
  incomplete: {
    bg: 'bg-[var(--color-warning-light)]',
    text: 'text-[var(--color-warning)]',
    dot: 'bg-[var(--color-warning)]',
    labelKey: 'incomplete',
  },
  conflict: {
    bg: 'bg-[var(--color-danger-light)]',
    text: 'text-[var(--color-danger)]',
    dot: 'bg-[var(--color-danger)]',
    labelKey: 'conflict',
  },
  certain: {
    bg: 'bg-[var(--color-success-light)]',
    text: 'text-[var(--color-success)]',
    dot: 'bg-[var(--color-success)]',
    labelKey: 'certain',
  },
  probable: {
    bg: 'bg-[var(--color-accent-light)]',
    text: 'text-[var(--color-accent)]',
    dot: 'bg-[var(--color-accent)]',
    labelKey: 'probable',
  },
  to_verify: {
    bg: 'bg-[var(--color-warning-light)]',
    text: 'text-[var(--color-warning)]',
    dot: 'bg-[var(--color-warning)]',
    labelKey: 'toVerify',
  },
  not_found: {
    bg: 'bg-gray-100',
    text: 'text-gray-500',
    dot: 'bg-gray-400',
    labelKey: 'notFound',
  },
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const t = useTranslations('status')
  const config = statusConfig[status]

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        config.bg,
        config.text,
        className
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full flex-shrink-0', config.dot)} />
      {t(config.labelKey as any)}
    </span>
  )
}
