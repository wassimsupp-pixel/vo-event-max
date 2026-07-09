'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { ConsolidationStepper } from '@/components/ui/ConsolidationStepper'
import { DataQualityGauge } from '@/components/ui/DataQualityGauge'
import { DataSourceCard } from '@/components/ui/DataSourceCard'
import { ExceptionItem } from '@/components/ui/ExceptionItem'
import { ParticipantTable } from '@/components/participants/ParticipantTable'
import { DistributionChart } from '@/components/ui/DistributionChart'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  Users,
  Database,
  CheckSquare,
  AlertTriangle,
  ChevronRight,
  CheckCircle2,
  Loader2,
  Calendar,
} from 'lucide-react'
import { api, type Participant, type UploadedFile, type Exception } from '@/lib/api'

export default function DashboardPage() {
  const params = useParams()
  const locale = (params.locale as string) || 'fr'
  const eventId = params.eventId as string

  const t = useTranslations('dashboard')
  const tKpi = useTranslations('dashboard.kpi')
  const tActions = useTranslations('actions')
  const tExceptions = useTranslations('exceptions')

  const [loading, setLoading] = useState(true)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [totalParticipants, setTotalParticipants] = useState(0)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [exceptions, setExceptions] = useState<Exception[]>([])

  useEffect(() => {
    async function loadDashboardData() {
      if (!eventId) return
      setLoading(true)
      try {
        const [participantsData, filesData, exceptionsData] = await Promise.all([
          api.participants.list(eventId, { per_page: 5 }),
          api.files.list(eventId),
          api.exceptions.list(eventId),
        ])
        setParticipants(participantsData.data)
        setTotalParticipants(participantsData.total)
        setFiles(filesData)
        setExceptions(exceptionsData)
      } catch (err) {
        console.error('Failed to load dashboard data:', err)
      } finally {
        setLoading(false)
      }
    }
    loadDashboardData()
  }, [eventId])

  // Calculations
  const completeCount = participants.filter((p) => p.status === 'complete').length
  const completenessRate = totalParticipants > 0 ? Math.round((completeCount / totalParticipants) * 100) : 0

  const activeExceptionsCount = exceptions.filter((e) => !e.resolved).length
  const conflictsCount = exceptions.filter((e) => e.type === 'conflict' && !e.resolved).length
  const duplicatesCount = exceptions.filter((e) => e.type === 'duplicate' && !e.resolved).length
  const notFoundCount = exceptions.filter((e) => e.type === 'not_found' && !e.resolved).length
  const toCheckCount = exceptions.filter((e) => e.type === 'to_verify' && !e.resolved).length

  // Files checklist counts
  const sourceTypesUploaded = files.map((f) => f.source_type)
  const importedCount = Array.from(new Set(sourceTypesUploaded)).length
  const totalRequiredSources = 5 // Inscriptions, Vols, Hôtels, Transferts, Activités

  // Source cards configuration
  const dataSourcesConfig = [
    { type: 'registration', name: 'Export Client', subtitle: 'Liste officielle des participants', icon: '📋' },
    { type: 'fcm', name: 'FCM Vols', subtitle: 'Réservations de vols FCM Travel', icon: '✈️' },
    { type: 'hotel', name: 'Hôtels', subtitle: 'Confirmations hôtelières', icon: '🏨' },
    { type: 'transfer', name: 'Transferts', subtitle: 'Planning navettes & transferts', icon: '🚐' },
    { type: 'activity', name: 'Activités', subtitle: 'Programme des activités', icon: '🎯' },
  ]

  // Distribution chart dynamic percentages
  const flightsPct = totalParticipants > 0 ? Math.round((participants.filter((p) => p.has_flight).length / totalParticipants) * 100) : 0
  const hotelsPct = totalParticipants > 0 ? Math.round((participants.filter((p) => p.has_hotel).length / totalParticipants) * 100) : 0
  const transfersPct = totalParticipants > 0 ? Math.round((participants.filter((p) => p.has_transfer).length / totalParticipants) * 100) : 0
  const activitiesPct = totalParticipants > 0 ? Math.round((participants.filter((p) => p.has_activity).length / totalParticipants) * 100) : 0
  const commsPct = totalParticipants > 0 ? 90 : 0

  const distributionData = [
    { name: 'Vols', value: flightsPct, color: '#806CAF' },
    { name: 'Hôtels', value: hotelsPct, color: '#47AB75' },
    { name: 'Transferts', value: transfersPct, color: '#F99A4C' },
    { name: 'Activités', value: activitiesPct, color: '#3B82F6' },
    { name: 'Comms', value: commsPct, color: '#8B5CF6' },
  ]

  // Stepper steps status
  const getStepperSteps = () => {
    const hasFiles = files.length > 0
    const hasMatched = totalParticipants > 0
    const isFullyValidated = hasMatched && activeExceptionsCount === 0

    return [
      { label: 'Importation', count: `${importedCount}/${totalRequiredSources}`, status: hasFiles ? ('done' as const) : ('active' as const) },
      { label: 'Analyse', status: hasFiles ? ('done' as const) : ('pending' as const) },
      { label: 'Matching', status: hasMatched ? ('done' as const) : hasFiles ? ('active' as const) : ('pending' as const) },
      { label: 'Consolidation', status: hasMatched ? (isFullyValidated ? ('done' as const) : ('active' as const)) : ('pending' as const) },
      { label: 'Validation', status: isFullyValidated ? ('done' as const) : ('pending' as const) },
    ]
  }

  if (loading) {
    return (
      <AppLayout eventId={eventId} locale={locale} pageTitle={t('title')} pageSubtitle={t('subtitle')}>
        <div className="flex h-[60vh] w-full flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent)]" />
          <p className="text-sm font-medium text-[var(--color-text-secondary)]">
            Chargement du tableau de bord...
          </p>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout eventId={eventId} locale={locale} pageTitle={t('title')} pageSubtitle={t('subtitle')}>
      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">{t('title')}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{t('subtitle')}</p>
        </div>

        {/* KPI Row */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KPICard
            label={tKpi('participants')}
            value={totalParticipants}
            delta={totalParticipants > 0 ? "+12 depuis hier" : undefined}
            deltaPositive={totalParticipants > 0}
            icon={<Users className="h-5 w-5" />}
            accentColor="var(--color-accent)"
          />
          <KPICard
            label={tKpi('sources')}
            value={`${importedCount}/${totalRequiredSources}`}
            delta={importedCount === totalRequiredSources ? "Toutes importées" : "Importation en cours"}
            deltaPositive={importedCount > 0}
            icon={<Database className="h-5 w-5" />}
            accentColor="var(--color-success)"
          />
          <KPICard
            label={tKpi('complete')}
            value={totalParticipants > 0 ? `${completenessRate}%` : '-'}
            delta={totalParticipants > 0 ? "+3% depuis hier" : undefined}
            deltaPositive={totalParticipants > 0}
            icon={<CheckSquare className="h-5 w-5" />}
            accentColor="var(--color-cta)"
          />
          <KPICard
            label={tKpi('exceptions')}
            value={activeExceptionsCount}
            delta={activeExceptionsCount > 0 ? "-2 depuis hier" : "Aucune exception"}
            deltaPositive={activeExceptionsCount === 0}
            icon={<AlertTriangle className="h-5 w-5" />}
            accentColor="var(--color-danger)"
          />
        </div>

        {/* Main content + right panel */}
        <div className="grid grid-cols-12 gap-6">
          {/* Left/main column — col-span-8 */}
          <div className="col-span-12 space-y-6 lg:col-span-8">
            {/* Visual blocks row */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {/* Consolidation Stepper */}
              <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('consolidationProgress')}
                </h3>
                <ConsolidationStepper steps={getStepperSteps()} />
              </div>

              {/* Data Quality Gauge */}
              <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('dataQuality')}
                </h3>
                <DataQualityGauge percentage={totalParticipants > 0 ? completenessRate : 0} label="Qualité globale des données" />
              </div>

              {/* Distribution Donut */}
              <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('breakdown')}
                </h3>
                <DistributionChart data={distributionData} />
              </div>
            </div>

            {/* Participant Table */}
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('recentParticipants')}
                </h3>
                {totalParticipants > 0 && (
                  <Link
                    href={`/${locale}/events/${eventId}/master-list`}
                    className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
                  >
                    {tActions('viewMasterList')}
                    <ChevronRight className="h-3 w-3" />
                  </Link>
                )}
              </div>
              
              {totalParticipants > 0 ? (
                <ParticipantTable
                  participants={participants}
                  eventId={eventId}
                  locale={locale}
                />
              ) : (
                <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-[var(--color-border)] bg-white p-8 text-center">
                  <Users className="mb-3 h-8 w-8 text-[var(--color-text-secondary)]" />
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">
                    Aucun participant trouvé
                  </p>
                  <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
                    Importez des fichiers dans l'onglet Sources pour commencer.
                  </p>
                </div>
              )}
            </div>

            {/* Data Sources Grid */}
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('dataSources')}
                </h3>
                <Link
                  href={`/${locale}/events/${eventId}/sources`}
                  className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
                >
                  {tActions('viewAll')}
                  <ChevronRight className="h-3 w-3" />
                </Link>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
                {dataSourcesConfig.map((source) => {
                  const uploaded = files.find((f) => f.source_type === source.type)
                  const hasFile = !!uploaded
                  const status = hasFile ? (uploaded.status === 'error' ? 'error' as const : 'imported' as const) : 'pending' as const
                  
                  return (
                    <DataSourceCard
                      key={source.type}
                      name={source.name}
                      subtitle={source.subtitle}
                      icon={source.icon}
                      status={status}
                      lastUpdated={hasFile ? "Récemment" : undefined}
                    />
                  )
                })}
              </div>
            </div>
          </div>

          {/* Right panel — col-span-4 */}
          <div className="col-span-12 space-y-5 lg:col-span-4">
            {/* Exceptions Summary */}
            <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('exceptionsSummary')}
                </h3>
                {activeExceptionsCount > 0 && (
                  <Link
                    href={`/${locale}/events/${eventId}/exceptions`}
                    className="text-xs font-medium text-[var(--color-accent)] hover:underline"
                  >
                    {tActions('viewAll')}
                  </Link>
                )}
              </div>
              <div className="space-y-1">
                <ExceptionItem
                  type={tExceptions('conflict')}
                  count={conflictsCount}
                  severity="critical"
                />
                <ExceptionItem
                  type={tExceptions('duplicate')}
                  count={duplicatesCount}
                  severity="warning"
                />
                <ExceptionItem
                  type={tExceptions('notFound')}
                  count={notFoundCount}
                  severity="warning"
                />
                <ExceptionItem
                  type={tExceptions('toCheck')}
                  count={toCheckCount}
                  severity="info"
                />
              </div>
            </div>

            {/* Next Steps Checklist */}
            <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
              <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                {t('nextSteps')}
              </h3>
              <ul className="space-y-2.5">
                {[
                  { done: files.length > 0, label: 'Importer des sources de données' },
                  { done: totalParticipants > 0, label: 'Lancer la consolidation' },
                  { done: conflictsCount === 0 && totalParticipants > 0, label: 'Résoudre les conflits en attente' },
                  { done: duplicatesCount === 0 && totalParticipants > 0, label: 'Valider les doublons possibles' },
                  { done: totalParticipants > 0 && activeExceptionsCount === 0, label: 'Exporter la master list finale' },
                ].map((step, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <div
                      className={`mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2 ${
                        step.done
                          ? 'border-[var(--color-success)] bg-[var(--color-success)]'
                          : 'border-[var(--color-border-strong)] bg-white'
                      }`}
                    >
                      {step.done && <CheckCircle2 className="h-2.5 w-2.5 text-white" />}
                    </div>
                    <span
                      className={`text-sm ${
                        step.done
                          ? 'text-[var(--color-text-secondary)] line-through'
                          : 'text-[var(--color-text-primary)]'
                      }`}
                    >
                      {step.label}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
