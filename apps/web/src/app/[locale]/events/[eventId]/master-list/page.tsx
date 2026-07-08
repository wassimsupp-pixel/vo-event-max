'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { ParticipantTable } from '@/components/participants/ParticipantTable'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Download, Search, Filter, CheckCircle2, AlertCircle, HelpCircle } from 'lucide-react'
import type { Participant } from '@/lib/api'

const MOCK_PARTICIPANTS: Participant[] = [
  {
    id: '1', event_id: '1', first_name: 'Sophie', last_name: 'Martin',
    email: 'sophie.martin@livanoba.com', status: 'complete', confidence: 'certain',
    has_flight: true, has_hotel: true, has_transfer: true, has_activity: true,
    locked_fields: [], sources: ['fcm', 'client'], created_at: '', updated_at: '',
  },
  {
    id: '2', event_id: '1', first_name: 'Thomas', last_name: 'Bernard',
    email: 'thomas.bernard@livanoba.com', status: 'complete', confidence: 'probable',
    has_flight: true, has_hotel: true, has_transfer: false, has_activity: true,
    locked_fields: [], sources: ['client'], created_at: '', updated_at: '',
  },
  {
    id: '3', event_id: '1', first_name: 'Isabelle', last_name: 'Dupont',
    email: 'isabelle.dupont@livanoba.com', status: 'incomplete', confidence: 'to_verify',
    has_flight: true, has_hotel: false, has_transfer: false, has_activity: false,
    locked_fields: [], sources: ['fcm'], created_at: '', updated_at: '',
  },
  {
    id: '4', event_id: '1', first_name: 'Marc', last_name: 'Leroy',
    email: 'marc.leroy@livanoba.com', status: 'conflict', confidence: 'probable',
    has_flight: false, has_hotel: true, has_transfer: true, has_activity: false,
    locked_fields: ['email'], sources: ['client', 'hotel'], created_at: '', updated_at: '',
  },
  {
    id: '5', event_id: '1', first_name: 'Camille', last_name: 'Moreau',
    email: 'camille.moreau@livanoba.com', status: 'complete', confidence: 'certain',
    has_flight: true, has_hotel: true, has_transfer: true, has_activity: true,
    locked_fields: [], sources: ['client', 'fcm', 'hotel'], created_at: '', updated_at: '',
  },
]

export default function MasterListPage() {
  const params = useParams()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')
  const tActions = useTranslations('actions')

  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [participants, setParticipants] = useState<Participant[]>(MOCK_PARTICIPANTS)
  const [isExporting, setIsExporting] = useState(false)

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value
    setSearchQuery(query)
    filterData(query, statusFilter)
  }

  const handleFilterStatus = (status: string | null) => {
    setStatusFilter(status)
    filterData(searchQuery, status)
  }

  const filterData = (query: string, status: string | null) => {
    let filtered = MOCK_PARTICIPANTS
    if (query) {
      const q = query.toLowerCase()
      filtered = filtered.filter(
        p => p.first_name.toLowerCase().includes(q) ||
             p.last_name.toLowerCase().includes(q) ||
             p.email?.toLowerCase().includes(q)
      )
    }
    if (status) {
      filtered = filtered.filter(p => p.status === status)
    }
    setParticipants(filtered)
  }

  const handleExport = () => {
    setIsExporting(true)
    setTimeout(() => {
      setIsExporting(false)
      // Trigger a direct mock download of a spreadsheet file
      const link = document.createElement('a')
      link.href = '#'
      link.setAttribute('download', `VO_Event_Max_Masterlist_${eventId}.xlsx`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }, 1500)
  }

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
            <Download className="h-4.5 w-4.5" />
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

        {/* Master Table */}
        <Card className="border-[var(--color-border)] shadow-[var(--shadow-card)] overflow-hidden">
          <ParticipantTable participants={participants} loading={false} />
          
          <div className="p-4 bg-slate-50 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
            <div>
              Affichage de {participants.length} sur {MOCK_PARTICIPANTS.length} participants
            </div>
            <div className="flex gap-1.5">
              <Button variant="outline" size="sm" className="h-7 text-xs border-[var(--color-border)]" disabled>Précédent</Button>
              <Button variant="outline" size="sm" className="h-7 text-xs border-[var(--color-border)]" disabled>Suivant</Button>
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
                Certaines informations de voyage ou d'hébergement manquent à l'appel.
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
