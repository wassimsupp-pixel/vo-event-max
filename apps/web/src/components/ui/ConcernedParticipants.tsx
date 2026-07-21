'use client'

import { useRouter } from 'next/navigation'
import { ArrowRight, CheckCircle } from 'lucide-react'

/** One master-list row (subset used to build "concerned participants" cohorts). */
export interface CohortRow {
  id: string
  first_name?: string | null
  last_name?: string | null
  email?: string | null
  company?: string | null
  completeness_status?: string | null
  has_flight?: boolean | null
  has_hotel?: boolean | null
  has_transfer?: boolean | null
  has_activities?: boolean | null
}

function statusBadge(status?: string | null) {
  const map: Record<string, string> = {
    complete: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    incomplete: 'bg-amber-50 text-amber-700 border-amber-200',
    conflict: 'bg-rose-50 text-rose-700 border-rose-200',
    pending: 'bg-slate-50 text-slate-600 border-slate-200',
  }
  const cls = map[status || ''] || 'bg-slate-50 text-slate-600 border-slate-200'
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {status || 'n/d'}
    </span>
  )
}

/**
 * Detailed list of the participants concerned by a clicked KPI (feedback §10-12):
 * name, company, email, completeness status, recommended action + a link to the
 * participant sheet. Rendered full-width below the KPI grid.
 */
export function ConcernedParticipants({
  rows,
  title,
  action,
  locale,
  eventId,
  emptyText,
  quickActionLabel,
  onQuickAction,
}: {
  rows: CohortRow[]
  title: string
  action: string
  locale: string
  eventId: string
  emptyText: string
  /** Optional extra per-row button (e.g. "Ajouter hébergement"), rendered
   * next to "Ouvrir". Omit both props to keep the default behaviour. */
  quickActionLabel?: string
  onQuickAction?: (row: CohortRow) => void
}) {
  const router = useRouter()
  const name = (r: CohortRow) => [r.first_name, r.last_name].filter(Boolean).join(' ') || 'N/A'

  return (
    <div className="rounded-[var(--radius-card)] border bg-white shadow-sm overflow-hidden">
      <div className="flex flex-col gap-0.5 border-b bg-[var(--color-bg-subtle)] p-4">
        <h3 className="text-sm font-bold text-[var(--color-text-primary)]">
          {title} · {rows.length}
        </h3>
        <p className="text-xs text-[var(--color-text-secondary)]">{action}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b bg-[var(--color-bg-subtle)] font-medium text-[var(--color-text-secondary)]">
              <th className="p-3">Participant</th>
              <th className="p-3">Entreprise</th>
              <th className="p-3">Email</th>
              <th className="p-3">Statut</th>
              <th className="p-3 text-right">Fiche</th>
            </tr>
          </thead>
          <tbody className="divide-y text-[var(--color-text-primary)]">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-[var(--color-text-secondary)]">
                  <span className="inline-flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-emerald-600" />
                    {emptyText}
                  </span>
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50 transition-colors">
                  <td className="p-3 font-semibold">{name(r)}</td>
                  <td className="p-3 text-xs text-[var(--color-text-secondary)]">{r.company || '-'}</td>
                  <td className="p-3 text-xs">
                    {r.email || <span className="font-semibold text-rose-600">manquant</span>}
                  </td>
                  <td className="p-3">{statusBadge(r.completeness_status)}</td>
                  <td className="p-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {onQuickAction && quickActionLabel && (
                        <button
                          onClick={() => onQuickAction(r)}
                          className="inline-flex items-center gap-1 rounded-md border border-[var(--color-accent)] px-2 py-1 text-xs font-semibold text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-light)]/30"
                        >
                          {quickActionLabel}
                        </button>
                      )}
                      <button
                        onClick={() => router.push(`/${locale}/events/${eventId}/participants/${r.id}`)}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--color-accent)] transition-colors hover:underline"
                      >
                        Ouvrir <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
