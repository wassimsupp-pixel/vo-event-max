'use client'

import { useState, useEffect, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Download, Search, Filter, CheckCircle2, AlertCircle, HelpCircle, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'

const PER_PAGE = 20

interface MasterRow {
  id: string
  first_name?: string
  last_name?: string
  email?: string
  company?: string
  phone?: string
  completeness_status?: string
  has_flight?: boolean
  has_hotel?: boolean
  has_transfer?: boolean
  has_activities?: boolean
  attendee_category?: string | null
  job_title?: string | null
  region?: string | null
  country?: string | null
  passport_number?: string | null
  dietary_requirements?: string | null
  food_allergy_info?: string | null
  // Enriched travel details (from master_list_service)
  flight_summary?: string | null
  flight_count?: number
  hotel_name?: string | null
  hotel_checkin?: string | null
  hotel_checkout?: string | null
  hotel_nights_count?: number
  hotel_room_type?: string | null
  transfer_summary?: string | null
  activities_summary?: string | null
}

/** Multi-line detail cell: shows the text (pre-wrapped) or a red "manquant" hint. */
function DetailCell({ text, missing = 'manquant' }: { text?: string | null; missing?: string }) {
  if (text && text.trim()) {
    return <span className="block whitespace-pre-line text-[11px] leading-snug text-[var(--color-text-primary)]">{text}</span>
  }
  return <span className="text-[11px] font-semibold text-[var(--color-danger)]">{missing}</span>
}

function StatusPill({ status }: { status?: string }) {
  const cfg =
    status === 'complete' ? { c: 'bg-[var(--color-success-light)] text-[var(--color-success)]', l: 'Complet' }
      : status === 'conflict' ? { c: 'bg-[var(--color-danger-light)] text-[var(--color-danger)]', l: 'Conflit' }
      : { c: 'bg-[var(--color-warning-light)] text-[var(--color-warning)]', l: 'Incomplet' }
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${cfg.c}`}>{cfg.l}</span>
}

export default function MasterListPage() {
  const params = useParams()
  const router = useRouter()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')
  const tActions = useTranslations('actions')

  const [rows, setRows] = useState<MasterRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [missingFilter, setMissingFilter] = useState<'flight' | 'hotel' | 'transfer' | null>(null)
  const [page, setPage] = useState(1)
  const [isExporting, setIsExporting] = useState(false)

  useEffect(() => {
    const m = new URLSearchParams(window.location.search).get('missing')
    if (m === 'flight' || m === 'hotel' || m === 'transfer') setMissingFilter(m)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const res = await api.masterList.get(eventId)
        if (!cancelled) setRows(res.items || [])
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Erreur lors du chargement de la master list')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    if (eventId) load()
    return () => { cancelled = true }
  }, [eventId])

  useEffect(() => { setPage(1) }, [searchQuery, statusFilter, missingFilter])

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return rows.filter((r) => {
      if (statusFilter && r.completeness_status !== statusFilter) return false
      if (missingFilter === 'flight' && r.has_flight) return false
      if (missingFilter === 'hotel' && r.has_hotel) return false
      if (missingFilter === 'transfer' && r.has_transfer) return false
      if (!q) return true
      return [r.first_name, r.last_name, r.email, r.company, r.region, r.attendee_category, r.country, r.job_title, r.phone]
        .some((v) => (v || '').toString().toLowerCase().includes(q))
    })
  }, [rows, searchQuery, statusFilter, missingFilter])

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))
  const pageRows = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE)
  const startItem = total === 0 ? 0 : (page - 1) * PER_PAGE + 1
  const endItem = Math.min(page * PER_PAGE, total)

  const handleExport = async () => {
    setIsExporting(true)
    try {
      const exp = await api.exports.create(eventId, '')
      const { signed_url } = await api.exports.getDownloadUrl(exp.id)
      window.open(signed_url, '_blank')
    } catch {
      console.warn('Export not available - API not configured')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle={t('masterList')}
      pageSubtitle="Liste consolidée et détaillée de tous les participants"
    >
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">{t('masterList')}</h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
              {loading ? 'Chargement…' : `${rows.length} participants — informations fusionnées de tous les fichiers sources`}
            </p>
          </div>
          <Button
            className="bg-[var(--color-cta)] hover:bg-[var(--color-cta)]/90 text-white font-medium self-start md:self-auto flex items-center gap-2 shadow-sm"
            onClick={handleExport}
            disabled={isExporting}
          >
            {isExporting ? <Loader2 className="h-4.5 w-4.5 animate-spin" /> : <Download className="h-4.5 w-4.5" />}
            {isExporting ? 'Génération...' : tActions('export')}
          </Button>
        </div>

        {/* Filters */}
        <Card className="p-4 border-[var(--color-border)] shadow-[var(--shadow-card)] flex flex-col md:flex-row gap-4 items-center justify-between">
          <div className="relative w-full md:w-96">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[var(--color-text-secondary)]" />
            <input
              type="text"
              placeholder="Rechercher par nom, email, société, région, catégorie, pays…"
              className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white pl-9 pr-4 py-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2 w-full md:w-auto items-center">
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] flex items-center gap-1">
              <Filter className="h-3 w-3" /> Filtrer :
            </span>
            {([['Tous', null], ['Complet', 'complete'], ['Incomplet', 'incomplete'], ['Conflit', 'conflict']] as const).map(([label, val]) => (
              <Button
                key={label}
                variant={statusFilter === val ? 'default' : 'outline'}
                size="sm"
                className={statusFilter === val ? 'bg-[var(--color-accent)] text-white border-0' : 'text-xs border-[var(--color-border)]'}
                onClick={() => setStatusFilter(val)}
              >
                {label}
              </Button>
            ))}
          </div>
        </Card>

        {missingFilter && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-4 py-2.5 text-sm">
            <span className="font-medium text-[var(--color-text-primary)]">
              Filtre : participants {missingFilter === 'flight' ? 'sans vol' : missingFilter === 'hotel' ? 'sans hôtel' : 'sans transfert'} ({total})
            </span>
            <button
              onClick={() => { setMissingFilter(null); window.history.replaceState({}, '', window.location.pathname) }}
              className="text-xs font-semibold text-[var(--color-accent)] hover:underline"
            >
              Réinitialiser
            </button>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-danger)] bg-red-50 p-4 text-sm text-[var(--color-danger)]">
            <AlertCircle className="h-4 w-4 shrink-0" /><span>{error}</span>
          </div>
        )}

        {/* Detailed master table */}
        <Card className="border-[var(--color-border)] shadow-[var(--shadow-card)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1500px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-subtle)] text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                  <th className="px-3 py-3">Nom</th>
                  <th className="px-3 py-3">Prénom</th>
                  <th className="px-3 py-3">Email</th>
                  <th className="px-3 py-3">Catégorie</th>
                  <th className="px-3 py-3">Région</th>
                  <th className="px-3 py-3 min-w-[210px]">Vol (compagnie · trajet · horaires)</th>
                  <th className="px-3 py-3 min-w-[150px]">Hôtel (arrivée → départ)</th>
                  <th className="px-3 py-3 min-w-[180px]">Transfert</th>
                  <th className="px-3 py-3 min-w-[160px]">Activités (jour/heure)</th>
                  <th className="px-3 py-3 min-w-[140px]">Régime / Allergies</th>
                  <th className="px-3 py-3">Statut</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [...Array(6)].map((_, i) => (
                    <tr key={i} className="border-b border-[var(--color-border)] animate-pulse">
                      {[...Array(11)].map((__, j) => (
                        <td key={j} className="px-3 py-3"><div className="h-4 rounded bg-gray-100" style={{ width: `${50 + ((j * 13) % 40)}%` }} /></td>
                      ))}
                    </tr>
                  ))
                ) : pageRows.length === 0 ? (
                  <tr><td colSpan={11} className="py-12 text-center text-sm text-[var(--color-text-secondary)]">Aucun participant trouvé</td></tr>
                ) : (
                  pageRows.map((r) => {
                    const hotelText = [
                      r.hotel_name,
                      (r.hotel_checkin || r.hotel_checkout) ? `${r.hotel_checkin || '?'} → ${r.hotel_checkout || '?'}` : '',
                      [r.hotel_room_type, r.hotel_nights_count ? `${r.hotel_nights_count} nuit(s)` : ''].filter(Boolean).join(' · '),
                    ].filter(Boolean).join('\n')
                    const dietText = [r.dietary_requirements, r.food_allergy_info].filter(Boolean).join('\n')
                    return (
                    <tr
                      key={r.id}
                      onClick={() => router.push(`/${locale}/events/${eventId}/participants/${r.id}`)}
                      className="group border-b border-[var(--color-border)] bg-white cursor-pointer align-top transition-colors hover:bg-[var(--color-accent-light)] last:border-0"
                    >
                      <td className="px-3 py-3 font-medium text-[var(--color-text-primary)]">{r.last_name || '—'}</td>
                      <td className="px-3 py-3 text-[var(--color-text-primary)]">{r.first_name || '—'}</td>
                      <td className="px-3 py-3 text-[var(--color-text-secondary)]">{r.email || <span className="font-semibold text-[var(--color-danger)]">manquant</span>}</td>
                      <td className="px-3 py-3 text-[var(--color-text-secondary)]">{r.attendee_category || '—'}</td>
                      <td className="px-3 py-3 text-[var(--color-text-secondary)]">{r.region || '—'}</td>
                      <td className="px-3 py-3"><DetailCell text={r.flight_summary} missing="pas de vol" /></td>
                      <td className="px-3 py-3"><DetailCell text={hotelText} missing="pas d'hôtel" /></td>
                      <td className="px-3 py-3"><DetailCell text={r.transfer_summary} missing="pas de transfert" /></td>
                      <td className="px-3 py-3"><DetailCell text={r.activities_summary} missing="aucune activité" /></td>
                      <td className="px-3 py-3"><DetailCell text={dietText} missing="non renseigné" /></td>
                      <td className="px-3 py-3"><StatusPill status={r.completeness_status} /></td>
                    </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="p-4 bg-slate-50 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
            <div>{loading ? 'Chargement...' : total === 0 ? 'Aucun participant trouvé' : `Affichage de ${startItem} à ${endItem} sur ${total} participants`}</div>
            <div className="flex gap-1.5">
              <Button variant="outline" size="sm" className="h-7 text-xs border-[var(--color-border)]" disabled={page <= 1 || loading} onClick={() => setPage(p => Math.max(1, p - 1))}>Précédent</Button>
              <Button variant="outline" size="sm" className="h-7 text-xs border-[var(--color-border)]" disabled={page >= totalPages || loading} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Suivant</Button>
            </div>
          </div>
        </Card>

        {/* Legend */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-start gap-2.5 p-3.5 bg-slate-50 rounded-lg border border-[var(--color-border)]">
            <CheckCircle2 className="h-5 w-5 text-[var(--color-success)] shrink-0" />
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Complet</h4>
              <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">Nom, email et vol présents et concordants.</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5 p-3.5 bg-slate-50 rounded-lg border border-[var(--color-border)]">
            <AlertCircle className="h-5 w-5 text-[var(--color-warning)] shrink-0" />
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Incomplet</h4>
              <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">Des informations de voyage ou d&apos;hébergement manquent.</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5 p-3.5 bg-slate-50 rounded-lg border border-[var(--color-border)]">
            <HelpCircle className="h-5 w-5 text-[var(--color-danger)] shrink-0" />
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Conflit</h4>
              <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">Des incohérences ont été détectées entre les fichiers sources.</p>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
