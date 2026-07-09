'use client'

import { useTranslations } from 'next-intl'
import { Clock, Upload, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
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

const statusConfig: Record<SourceStatus, { label: string; color: string; bg: string; Icon: React.ElementType }> = {
  imported: {
    label: 'Importé',
    color: 'text-[var(--color-success)]',
    bg: 'bg-[var(--color-success-light)]',
    Icon: CheckCircle2,
  },
  pending: {
    label: 'En attente',
    color: 'text-[var(--color-warning)]',
    bg: 'bg-[var(--color-warning-light)]',
    Icon: Clock,
  },
  error: {
    label: 'Erreur',
    color: 'text-[var(--color-danger)]',
    bg: 'bg-[var(--color-danger-light)]',
    Icon: AlertCircle,
  },
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
  const t = useTranslations('actions')
  const cfg = statusConfig[status]

  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4',
        'shadow-[var(--shadow-card)] transition-shadow hover:shadow-md',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent-light)] text-xl">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {name}
          </h3>
          <p className="mt-0.5 truncate text-xs text-[var(--color-text-secondary)]">
            {subtitle}
          </p>
        </div>
      </div>

      {/* Status + Last updated */}
      <div className="flex items-center justify-between">
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
            cfg.bg,
            cfg.color
          )}
        >
          <cfg.Icon className="h-3 w-3" />
          {cfg.label}
        </span>

        {lastUpdated && (
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">
            <Clock className="h-3 w-3" />
            {lastUpdated}
          </span>
        )}
      </div>

      {/* Import button */}
      <button
        onClick={onImport}
        disabled={loading}
        className={cn(
          'flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition-all',
          'bg-[var(--color-accent)] text-white hover:bg-[#6B5A93] active:scale-[0.99]',
          'disabled:cursor-not-allowed disabled:opacity-60'
        )}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Upload className="h-4 w-4" />
        )}
        {loading ? t('loading') : t('import')}
      </button>
    </div>
  )
}
