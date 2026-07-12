'use client'

import { useTranslations } from 'next-intl'
import { Clock, Upload, AlertCircle, CheckCircle2, Loader2, Edit3 } from 'lucide-react'
import { cn } from '@/lib/utils'

type SourceStatus = 'imported' | 'pending' | 'error'

interface DataSourceCardProps {
  name: string
  subtitle: string
  icon: string
  lastUpdated?: string
  status: SourceStatus
  onImport?: () => void
  loading?: boolean
  className?: string
}

export function DataSourceCard({
  name,
  subtitle,
  icon,
  lastUpdated,
  status,
  onImport,
  loading = false,
  className,
}: DataSourceCardProps) {
  const tActions = useTranslations('actions')
  const tSources = useTranslations('sources')

  const statusLabels: Record<SourceStatus, string> = {
    imported: tSources('status.imported'),
    pending: tSources('status.pending'),
    error: tSources('status.error'),
  }

  const statusColors: Record<SourceStatus, { color: string; bg: string; Icon: React.ElementType }> = {
    imported: {
      color: 'text-[var(--color-success)]',
      bg: 'bg-[var(--color-success-light)]',
      Icon: CheckCircle2,
    },
    pending: {
      color: 'text-[var(--color-warning)]',
      bg: 'bg-[var(--color-warning-light)]',
      Icon: Clock,
    },
    error: {
      color: 'text-[var(--color-danger)]',
      bg: 'bg-[var(--color-danger-light)]',
      Icon: AlertCircle,
    },
  }

  const cfg = statusColors[status]
  const label = statusLabels[status]

  return (
    <div
      className={cn(
        'flex flex-col justify-between gap-4 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4.5',
        'shadow-[var(--shadow-card)] transition-shadow hover:shadow-md h-full',
        className
      )}
    >
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent-light)] text-xl">
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-xs sm:text-sm font-semibold text-[var(--color-text-primary)] leading-tight">
              {name}
            </h3>
            <p className="mt-1 text-[10px] sm:text-xs text-[var(--color-text-secondary)] leading-normal">
              {subtitle}
            </p>
          </div>
        </div>

        {/* Status + Last updated */}
        <div className="flex flex-col gap-1.5 items-start">
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold w-fit',
              cfg.bg,
              cfg.color
            )}
          >
            <cfg.Icon className="h-3.5 w-3.5" />
            {label}
          </span>

          {lastUpdated && (
            <span className="flex items-center gap-1 text-xs text-[var(--color-text-secondary)] font-medium">
              <Clock className="h-3.5 w-3.5 text-slate-400" />
              {lastUpdated}
            </span>
          )}
        </div>
      </div>

      {/* Import button */}
      <button
        onClick={onImport}
        disabled={loading}
        className={cn(
          'flex w-full items-center justify-center gap-1.5 rounded-lg py-2.5 text-xs sm:text-sm font-semibold transition-all',
          status === 'imported'
            ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 active:scale-[0.99]'
            : 'bg-[var(--color-accent)] text-white hover:bg-[#6B5A93] active:scale-[0.99]',
          'disabled:cursor-not-allowed disabled:opacity-60'
        )}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : status === 'imported' ? (
          <Edit3 className="h-4 w-4" />
        ) : (
          <Upload className="h-4 w-4" />
        )}
        {loading ? tActions('loading') : status === 'imported' ? tActions('edit') : tActions('import')}
      </button>
    </div>
  )
}
