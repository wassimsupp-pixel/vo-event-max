'use client'

import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import type { Participant } from '@/lib/api'

interface ParticipantTableProps {
  participants: Participant[]
  loading?: boolean
  eventId?: string
  locale?: string
  className?: string
}

function ServiceIcon({ active }: { active: boolean }) {
  if (active) {
    return <Check className="mx-auto h-4 w-4 text-[var(--color-success)]" />
  }
  return <X className="mx-auto h-4 w-4 text-[var(--color-border-strong)]" />
}

function SkeletonRow() {
  return (
    <tr className="border-b border-[var(--color-border)] animate-pulse">
      {[...Array(8)].map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 rounded bg-gray-100" style={{ width: `${60 + ((i * 17) % 40)}%` }} />
        </td>
      ))}
    </tr>
  )
}

export function ParticipantTable({
  participants,
  loading = false,
  eventId,
  locale = 'fr',
  className,
}: ParticipantTableProps) {
  const t = useTranslations('participants')
  const router = useRouter()

  const handleRowClick = (participantId: string) => {
    if (eventId) {
      router.push(`/${locale}/events/${eventId}/participants/${participantId}`)
    }
  }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)]',
        'shadow-[var(--shadow-card)]',
        className
      )}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px] border-collapse">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-subtle)]">
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('lastName')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('firstName')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('email')}
              </th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('flight')}
              </th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('hotel')}
              </th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('transfer')}
              </th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('activity')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                {t('status')}
              </th>
            </tr>
          </thead>

          <tbody>
            {loading
              ? [...Array(5)].map((_, i) => <SkeletonRow key={i} />)
              : participants.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => handleRowClick(p.id)}
                    className={cn(
                      'group border-b border-[var(--color-border)] bg-white transition-colors',
                      'cursor-pointer hover:bg-[var(--color-accent-light)]',
                      'last:border-0'
                    )}
                  >
                    <td className="px-4 py-3 text-sm font-medium text-[var(--color-text-primary)]">
                      {p.last_name}
                    </td>
                    <td className="px-4 py-3 text-sm text-[var(--color-text-primary)]">
                      {p.first_name}
                    </td>
                    <td className="px-4 py-3 text-sm text-[var(--color-text-secondary)]">
                      {p.email}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <ServiceIcon active={p.has_flight} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <ServiceIcon active={p.has_hotel} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <ServiceIcon active={p.has_transfer} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <ServiceIcon active={p.has_activities} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={p.completeness_status} />
                    </td>
                  </tr>
                ))}

            {!loading && participants.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="py-12 text-center text-sm text-[var(--color-text-secondary)]"
                >
                  Aucun participant trouvé
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
