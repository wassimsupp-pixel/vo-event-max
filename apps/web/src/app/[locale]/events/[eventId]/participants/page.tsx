'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Search, Users, Plane, Hotel, Bus, Sparkles, CheckCircle2, AlertCircle, HelpCircle, Loader2, Mail, Building2, Phone } from 'lucide-react'
import { api, type Participant } from '@/lib/api'

const PER_PAGE = 25

const STATUS_META: Record<string, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  complete: { label: 'Complet', className: 'bg-emerald-50 text-emerald-700 border-emerald-200', Icon: CheckCircle2 },
  incomplete: { label: 'Incomplet', className: 'bg-amber-50 text-amber-700 border-amber-200', Icon: AlertCircle },
  conflict: { label: 'Conflit', className: 'bg-rose-50 text-rose-700 border-rose-200', Icon: HelpCircle },
}

export default function EventParticipantsPage() {
  const { locale, eventId } = useParams() as { locale: string; eventId: string }
  const router = useRouter()
  const t = useTranslations('nav')

  const [rows, setRows] = useState<Participant[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [statusFilter, setStatusFilter] = useState<'complete' | 'incomplete' | 'conflict' | null>(null)
  const [page, setPage] = useState(1)

  // Debounce the search box so we don't fire a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(search.trim()), 300)
    return () => clearTimeout(id)
  }, [search])

  useEffect(() => { setPage(1) }, [debounced, statusFilter])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.participants.list(eventId, {
        page,
        page_size: PER_PAGE,
        search: debounced || undefined,
        status: statusFilter || undefined,
      })
      setRows(res.items)
      setTotal(res.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du chargement des participants')
    } finally {
      setLoading(false)
    }
  }, [eventId, page, debounced, statusFilter])

  useEffect(() => { if (eventId) load() }, [eventId, load])

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  const ServiceIcon = ({ on, Icon, label }: { on: boolean; Icon: typeof Plane; label: string }) => (
    <span
      title={label}
      className={`inline-flex h-6 w-6 items-center justify-center rounded-md border ${
        on
          ? 'bg-[var(--color-accent-light)] text-[var(--color-accent)] border-[var(--color-accent)]/30'
          : 'bg-slate-50 text-slate-300 border-slate-200'
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
    </span>
  )

  return (
    <AppLayout eventId={eventId} locale={locale} pageTitle={t('participants')}>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)] flex items-center gap-2">
              <Users className="h-6 w-6 text-[var(--color-accent)]" />
              {t('participants')}
            </h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
              {loading ? 'Chargement…' : `${total} participant(s) consolidé(s)`}
            </p>
          </div>
        </div>

        {/* Filters */}
        <Card className="p-4 border-[var(--color-border)] shadow-[var(--shadow-card)] flex flex-col md:flex-row gap-4 items-center justify-between">
          <div className="relative w-full md:w-96">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[var(--color-text-secondary)]" />
            <input
              type="text"
              placeholder="Rechercher par nom, email, société…"
              className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white pl-9 pr-4 py-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2 w-full md:w-auto items-center">
            {([['Tous', null], ['Complet', 'complete'], ['Incomplet', 'incomplete'], ['Conflit', 'conflict']] as const).map(([label, val]) => (
              <button
                key={label}
                onClick={() => setStatusFilter(val)}
                className={
                  'rounded-full px-3 py-1 text-xs font-semibold transition-colors ' +
                  (statusFilter === val
                    ? 'bg-[var(--color-accent)] text-white'
                    : 'border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)]')
                }
              >
                {label}
              </button>
            ))}
          </div>
        </Card>

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-danger)] bg-red-50 p-4 text-sm text-[var(--color-danger)]">
            <AlertCircle className="h-4 w-4 shrink-0" /><span>{error}</span>
          </div>
        )}

        <Card className="border-[var(--color-border)] shadow-[var(--shadow-card)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-subtle)] text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                  <th className="px-4 py-3">Participant</th>
                  <th className="px-4 py-3"><Mail className="inline h-3.5 w-3.5 mr-1" />Email</th>
                  <th className="px-4 py-3"><Building2 className="inline h-3.5 w-3.5 mr-1" />Société</th>
                  <th className="px-4 py-3"><Phone className="inline h-3.5 w-3.5 mr-1" />Téléphone</th>
                  <th className="px-4 py-3 text-center">Services</th>
                  <th className="px-4 py-3">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {loading ? (
                  <tr><td colSpan={6} className="px-4 py-12 text-center">
                    <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)] mx-auto" />
                  </td></tr>
                ) : rows.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-12 text-center text-[var(--color-text-secondary)]">
                    Aucun participant trouvé.
                  </td></tr>
                ) : (
                  rows.map((p) => {
                    const meta = STATUS_META[p.completeness_status] || STATUS_META.incomplete
                    return (
                      <tr
                        key={p.id}
                        onClick={() => router.push(`/${locale}/events/${eventId}/participants/${p.id}`)}
                        className="cursor-pointer hover:bg-[var(--color-bg-subtle)] transition-colors"
                      >
                        <td className="px-4 py-3 font-semibold text-[var(--color-text-primary)] whitespace-nowrap">
                          {`${p.first_name || ''} ${p.last_name || ''}`.trim() || '—'}
                        </td>
                        <td className="px-4 py-3 text-[var(--color-text-secondary)]">{p.email || '—'}</td>
                        <td className="px-4 py-3 text-[var(--color-text-secondary)]">{p.company || '—'}</td>
                        <td className="px-4 py-3 text-[var(--color-text-secondary)]">{p.phone || '—'}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-center gap-1.5">
                            <ServiceIcon on={p.has_flight} Icon={Plane} label="Vol" />
                            <ServiceIcon on={p.has_hotel} Icon={Hotel} label="Hôtel" />
                            <ServiceIcon on={p.has_transfer} Icon={Bus} label="Transfert" />
                            <ServiceIcon on={p.has_activities} Icon={Sparkles} label="Activités" />
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${meta.className}`}>
                            <meta.Icon className="h-3 w-3" />{meta.label}
                          </span>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--color-text-secondary)]">
              Page {page} / {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((v) => Math.max(1, v - 1))}
                disabled={page <= 1}
                className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold disabled:opacity-40 hover:bg-[var(--color-bg-subtle)]"
              >
                Précédent
              </button>
              <button
                onClick={() => setPage((v) => Math.min(totalPages, v + 1))}
                disabled={page >= totalPages}
                className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold disabled:opacity-40 hover:bg-[var(--color-bg-subtle)]"
              >
                Suivant
              </button>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
