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
import { useParams, useRouter } from 'next/navigation'
import {
  Users,
  Database,
  CheckSquare,
  AlertTriangle,
  ChevronRight,
  CheckCircle2,
  Loader2,
  Calendar,
  Play,
  Zap,
  XCircle,
} from 'lucide-react'
import { api, type Participant, type UploadedFile, type Exception, type ConsolidationRun } from '@/lib/api'

export default function DashboardPage() {
  const params = useParams()
  const router = useRouter()
  const locale = (params.locale as string) || 'fr'
  const eventId = params.eventId as string

  const t = useTranslations('dashboard')
  const tKpi = useTranslations('dashboard.kpi')
  const tActions = useTranslations('actions')
  const tExceptions = useTranslations('exceptions')
  const tSources = useTranslations('sources')

  const [loading, setLoading] = useState(true)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [totalParticipants, setTotalParticipants] = useState(0)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [exceptions, setExceptions] = useState<Exception[]>([])

  // Consolidation state
  const [consolidating, setConsolidating] = useState(false)
  const [consolidationRun, setConsolidationRun] = useState<ConsolidationRun | null>(null)
  const [consolidationMsg, setConsolidationMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadDashboardData = async () => {
      if (!eventId) return
      setLoading(true)
      try {
        const [participantsData, filesData, exceptionsData] = await Promise.all([
          api.participants.list(eventId, { page_size: 5 }),
          api.files.list(eventId),
          api.exceptions.list(eventId),
        ])
        setParticipants(participantsData.items)
        setTotalParticipants(participantsData.total)
        setFiles(filesData)
        setExceptions(exceptionsData)
      } catch (err) {
        console.error('Failed to load dashboard data:', err)
      } finally {
        setLoading(false)
      }
    }

  useEffect(() => {
    loadDashboardData()
  }, [eventId])

  // Kick off a consolidation run and poll until done
  const handleRunConsolidation = async () => {
    if (consolidating || files.length === 0) return
    setConsolidating(true)
    setConsolidationMsg(null)
    try {
      const run = await api.consolidation.run(eventId)
      setConsolidationRun(run)

      // Poll every 2s until the run finishes
      const poll = async (): Promise<void> => {
        const updated = await api.consolidation.get(eventId, run.id)
        setConsolidationRun(updated)
        if (updated.status === 'running' || updated.status === 'pending') {
          await new Promise(r => setTimeout(r, 2000))
          return poll()
        }
        if (updated.status === 'done') {
          setConsolidationMsg({ type: 'success', text: t('successRun', { matched: updated.stats?.matched ?? 0, conflicts: updated.stats?.conflicts ?? 0 }) })
          await loadDashboardData()
        } else {
          setConsolidationMsg({ type: 'error', text: t('errorRun') })
        }
      }
      await poll()
    } catch (err) {
      console.error('Consolidation failed:', err)
      setConsolidationMsg({ type: 'error', text: t('errorApi') })
    } finally {
      setConsolidating(false)
    }
  }

  // Calculations
  const completeCount = participants.filter((p) => p.completeness_status === 'complete').length
  const completenessRate = totalParticipants > 0 ? Math.round((completeCount / totalParticipants) * 100) : 0

  const activeExceptionsCount = exceptions.filter((e) => !e.resolved).length
  const conflictsCount = exceptions.filter((e) => e.type === 'conflict' && !e.resolved).length
  const duplicatesCount = exceptions.filter((e) => e.type === 'duplicate' && !e.resolved).length
  const notFoundCount = exceptions.filter((e) => e.type === 'not_found' && !e.resolved).length
  const toCheckCount = exceptions.filter((e) => e.type === 'to_verify' && !e.resolved).length

  // Navigation targets for the dashboard's clickable blocks
  const exceptionsBase = `/${locale}/events/${eventId}/exceptions`
  const stepperRoutes = [
    `/${locale}/events/${eventId}/sources`,     // 0 Importation
    `/${locale}/events/${eventId}/sources`,     // 1 Analyse
    `/${locale}/events/${eventId}/master-list`, // 2 Matching
    `/${locale}/events/${eventId}/master-list`, // 3 Consolidation
    exceptionsBase,                             // 4 Validation
  ]

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
  const activitiesPct = totalParticipants > 0 ? Math.round((participants.filter((p) => p.has_activities).length / totalParticipants) * 100) : 0
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
        {/* Page header with Consolidation CTA */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">{t('title')}</h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{t('subtitle')}</p>
          </div>
          <button
            onClick={handleRunConsolidation}
            disabled={consolidating || files.length === 0 || loading}
            className="flex items-center gap-2 rounded-lg bg-[var(--color-cta)] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-cta)]/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
          >
            {consolidating ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Consolidation en cours...</>
            ) : (
              <><Zap className="h-4 w-4" /> Lancer la consolidation</>
            )}
          </button>
        </div>

        {/* Consolidation status banner */}
        {consolidationMsg && (
          <div className={`flex items-center gap-3 rounded-lg border p-4 text-sm font-medium ${
            consolidationMsg.type === 'success'
              ? 'bg-[var(--color-success-light)] border-[var(--color-success)]/20 text-[var(--color-success)]'
              : 'bg-[var(--color-danger-light)] border-[var(--color-danger)]/20 text-[var(--color-danger)]'
          }`}>
            {consolidationMsg.type === 'success'
              ? <CheckCircle2 className="h-5 w-5 shrink-0" />
              : <XCircle className="h-5 w-5 shrink-0" />
            }
            <span>{consolidationMsg.text}</span>
            <button onClick={() => setConsolidationMsg(null)} className="ml-auto text-xs underline opacity-70 hover:opacity-100">Fermer</button>
          </div>
        )}

        {/* KPI Row */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KPICard
            label={tKpi('participants')}
            value={totalParticipants}
            icon={<Users className="h-5 w-5" />}
            accentColor="var(--color-accent)"
            href={`/${locale}/events/${eventId}/master-list`}
          />
          <KPICard
            label={tKpi('sources')}
            value={`${importedCount}/${totalRequiredSources}`}
            delta={importedCount === totalRequiredSources ? "Toutes importées" : "Importation en cours"}
            deltaPositive={importedCount > 0}
            icon={<Database className="h-5 w-5" />}
            accentColor="var(--color-success)"
            href={`/${locale}/events/${eventId}/sources`}
          />
          <KPICard
            label={tKpi('complete')}
            value={totalParticipants > 0 ? `${completenessRate}%` : '-'}
            icon={<CheckSquare className="h-5 w-5" />}
            accentColor="var(--color-cta)"
            href={`/${locale}/events/${eventId}/master-list`}
          />
          <KPICard
            label={tKpi('exceptions')}
            value={activeExceptionsCount}
            delta={activeExceptionsCount === 0 ? "Aucune exception" : undefined}
            deltaPositive={activeExceptionsCount === 0}
            icon={<AlertTriangle className="h-5 w-5" />}
            accentColor="var(--color-danger)"
            href={`/${locale}/events/${eventId}/exceptions`}
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
                <ConsolidationStepper
                  steps={getStepperSteps()}
                  onStepClick={(i) => router.push(stepperRoutes[i])}
                />
              </div>

              {/* Data Quality Gauge */}
              <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('dataQuality')}
                </h3>
                <DataQualityGauge
                  percentage={totalParticipants > 0 ? completenessRate : 0}
                  label="Qualité globale des données"
                  onClick={() => router.push(`/${locale}/events/${eventId}/master-list`)}
                />
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
                    Importez des fichiers dans l&apos;onglet Sources pour commencer.
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
                      lastUpdated={hasFile ? tSources('recently') : undefined}
                      onImport={() => router.push(`/${locale}/events/${eventId}/sources`)}
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
                  onClick={() => router.push(`${exceptionsBase}?type=conflict`)}
                />
                <ExceptionItem
                  type={tExceptions('duplicate')}
                  count={duplicatesCount}
                  severity="warning"
                  onClick={() => router.push(`${exceptionsBase}?type=duplicate`)}
                />
                <ExceptionItem
                  type={tExceptions('notFound')}
                  count={notFoundCount}
                  severity="warning"
                  onClick={() => router.push(`${exceptionsBase}?type=not_found`)}
                />
                <ExceptionItem
                  type={tExceptions('toCheck')}
                  count={toCheckCount}
                  severity="info"
                  onClick={() => router.push(`${exceptionsBase}?type=to_verify`)}
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
