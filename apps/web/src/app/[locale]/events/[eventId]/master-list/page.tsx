'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { ParticipantTable } from '@/components/participants/ParticipantTable'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Download, Search, Filter, CheckCircle2, AlertCircle, HelpCircle, Loader2 } from 'lucide-react'
import type { Participant, ParticipantStatus } from '@/lib/api'
import { api } from '@/lib/api'

const PER_PAGE = 20

export default function MasterListPage() {
  const params = useParams()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')
  const tActions = useTranslations('actions')

  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [isExporting, setIsExporting] = useState(false)

  // Debounced search query
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(1) // reset to first page on new search
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Also reset page when filter changes
  useEffect(() => {
    setPage(1)
  }, [statusFilter])

  const fetchParticipants = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.participants.list(eventId, {
        page,
        page_size: PER_PAGE,
        search: debouncedSearch || undefined,
        status: (statusFilter as ParticipantStatus) ?? undefined,
      })
      setParticipants(result.items)
      setTotal(result.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du chargement des participants')
      setParticipants([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [eventId, page, debouncedSearch, statusFilter])

  useEffect(() => {
    fetchParticipants()
  }, [fetchParticipants])

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value)
  }

  const handleFilterStatus = (status: string | null) => {
    setStatusFilter(status)
  }

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

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))
  const startItem = total === 0 ? 0 : (page - 1) * PER_PAGE + 1
  const endItem = Math.min(page * PER_PAGE, total)

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle={t('masterList')}
      pageSubtitle="Consultez et exportez la liste consolidée et validée de tous les participants"
    >
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">{t('masterList')}</h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
              Base de données consolidée en temps réel
            </p>
          </div>
          <Button
            className="bg-[var(--color-cta)] hover:bg-[var(--color-cta)]/90 text-white font-medium self-start md:self-auto flex items-center gap-2 shadow-sm"
            onClick={handleExport}
            disabled={isExporting}
          >
            {isExporting ? (
              <Loader2 className="h-4.5 w-4.5 animate-spin" />
            ) : (
              <Download className="h-4.5 w-4.5" />
            )}
            {isExporting ? 'Génération...' : tActions('export')}
          </Button>
        </div>

        {/* Filters Panel */}
        <Card className="p-4 border-[var(--color-border)] shadow-[var(--shadow-card)] flex flex-col md:flex-row gap-4 items-center justify-between">
          <div className="relative w-full md:w-80">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[var(--color-text-secondary)]" />
            <input
              type="text"
              placeholder="Rechercher par nom, email..."
              className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white pl-9 pr-4 py-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              value={searchQuery}
              onChange={handleSearch}
            />
          </div>

          <div className="flex flex-wrap gap-2 w-full md:w-auto items-center">
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] flex items-center gap-1">
              <Filter className="h-3 w-3" /> Filtrer :
            </span>
            <Button
              variant={statusFilter === null ? 'default' : 'outline'}
              size="sm"
              className={statusFilter === null ? 'bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/95 border-0' : 'text-xs border-[var(--color-border)]'}
              onClick={() => handleFilterStatus(null)}
            >
              Tous
            </Button>
            <Button
              variant={statusFilter === 'complete' ? 'default' : 'outline'}
              size="sm"
              className={statusFilter === 'complete' ? 'bg-[var(--color-success)] text-white hover:bg-[var(--color-success)]/95 border-0' : 'text-xs border-[var(--color-border)]'}
              onClick={() => handleFilterStatus('complete')}
            >
              Complet
            </Button>
            <Button
              variant={statusFilter === 'incomplete' ? 'default' : 'outline'}
              size="sm"
              className={statusFilter === 'incomplete' ? 'bg-[var(--color-warning)] text-[var(--color-text-primary)] hover:bg-[var(--color-warning)]/95 border-0' : 'text-xs border-[var(--color-border)]'}
              onClick={() => handleFilterStatus('incomplete')}
            >
              Incomplet
            </Button>
            <Button
              variant={statusFilter === 'conflict' ? 'default' : 'outline'}
              size="sm"
              className={statusFilter === 'conflict' ? 'bg-[var(--color-danger)] text-white hover:bg-[var(--color-danger)]/95 border-0' : 'text-xs border-[var(--color-border)]'}
              onClick={() => handleFilterStatus('conflict')}
            >
              Conflit
            </Button>
          </div>
        </Card>

        {/* Error State */}
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--color-danger)] bg-red-50 p-4 text-sm text-[var(--color-danger)]">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Master Table */}
        <Card className="border-[var(--color-border)] shadow-[var(--shadow-card)] overflow-hidden">
          <ParticipantTable participants={participants} loading={loading} />

          <div className="p-4 bg-slate-50 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
            <div>
              {loading
                ? 'Chargement...'
                : total === 0
                ? 'Aucun participant trouvé'
                : `Affichage de ${startItem} à ${endItem} sur ${total} participants`}
            </div>
            <div className="flex gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs border-[var(--color-border)]"
                disabled={page <= 1 || loading}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                Précédent
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs border-[var(--color-border)]"
                disabled={page >= totalPages || loading}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              >
                Suivant
              </Button>
            </div>
          </div>
        </Card>

        {/* Info Legend */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-start gap-2.5 p-3.5 bg-slate-50 rounded-lg border border-[var(--color-border)]">
            <CheckCircle2 className="h-5 w-5 text-[var(--color-success)] shrink-0" />
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Complet</h4>
              <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
                Toutes les informations nécessaires (vol, hôtel) sont présentes et concordantes.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2.5 p-3.5 bg-slate-50 rounded-lg border border-[var(--color-border)]">
            <AlertCircle className="h-5 w-5 text-[var(--color-warning)] shrink-0" />
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Incomplet</h4>
              <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
                Certaines informations de voyage ou d&apos;hébergement manquent à l&apos;appel.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2.5 p-3.5 bg-slate-50 rounded-lg border border-[var(--color-border)]">
            <HelpCircle className="h-5 w-5 text-[var(--color-danger)] shrink-0" />
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-primary)]">Conflit</h4>
              <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
                Des incohérences ont été détectées entre les fichiers client, FCM ou hôtel.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
