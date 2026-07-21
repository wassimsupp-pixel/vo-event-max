'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { ConsolidationStepper } from '@/components/ui/ConsolidationStepper'
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
  ShieldCheck,
  Sparkles,
  Lightbulb,
  Plane,
  Hotel,
  Bus,
  PartyPopper,
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
  const [analysis, setAnalysis] = useState<any>(null)

  // Consolidation state
  const [consolidating, setConsolidating] = useState(false)
  const [consolidationRun, setConsolidationRun] = useState<ConsolidationRun | null>(null)
  const [consolidationMsg, setConsolidationMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadDashboardData = async () => {
      if (!eventId) return
      setLoading(true)
      try {
        const [participantsData, filesData, exceptionsData, analysisData] = await Promise.all([
          api.participants.list(eventId, { page_size: 5 }),
          api.files.list(eventId),
          api.exceptions.list(eventId),
          api.reports.getAnalysis(eventId).catch(() => null),
        ])
        setParticipants(participantsData.items)
        setTotalParticipants(participantsData.total)
        setFiles(filesData)
        setExceptions(exceptionsData)
        setAnalysis(analysisData)
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

      // Poll until the run finishes. A large consolidation keeps the API worker
      // busy, so individual status polls can transiently fail/timeout — we
      // tolerate that and keep waiting instead of falsely reporting an error.
      const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
      const MAX_MINUTES = 20
      const start = Date.now()
      const poll = async (consecutiveFailures = 0): Promise<void> => {
        if (Date.now() - start > MAX_MINUTES * 60_000) {
          setConsolidationMsg({ type: 'error', text: t('errorRun') })
          return
        }
        let updated
        try {
          updated = await api.consolidation.get(eventId, run.id)
        } catch {
          // API busy during the heavy run — wait longer and retry, don't error out.
          if (consecutiveFailures >= 40) {
            setConsolidationMsg({ type: 'error', text: t('errorApi') })
            return
          }
          await sleep(5000)
          return poll(consecutiveFailures + 1)
        }
        setConsolidationRun(updated)
        if (updated.status === 'running' || updated.status === 'pending') {
          await sleep(3000)
          return poll(0)
        }
        if (updated.status === 'done') {
          setConsolidationMsg({ type: 'success', text: t('successRun', { matched: updated.stats?.matched ?? 0, conflicts: updated.stats?.conflicts ?? 0 }) })
          await loadDashboardData()   // auto-refresh — no manual reload needed
        } else {
          setConsolidationMsg({ type: 'error', text: t('errorRun') })
          await loadDashboardData()
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
  // Full-event-accurate, like withoutFlightCount etc. below: `participants` is
  // capped at page_size: 5, so computing this from it silently showed the
  // completion rate of an arbitrary 5-person sample instead of the event.
  const completeCount = analysis?.complete_count ?? (totalParticipants > 0 ? participants.filter((p) => p.completeness_status === 'complete').length : 0)
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

  // Raw "sans X" counts (MVP feedback §14) come from `analysis`
  // (api.reports.getAnalysis → build_analysis), which scans EVERY participant
  // of the event. The `participants` array above is capped at 5 rows
  // (page_size: 5, it only feeds the "recent participants" preview table) —
  // computing coverage from it would silently show counts for 5 people out of
  // however many are actually in the event. Each tile links straight to the
  // master list pre-filtered to exactly those participants (master-list/
  // page.tsx already reads ?missing= from the URL), not just to the general
  // page for that category.
  const withoutFlightCount = analysis?.without_flight ?? (totalParticipants > 0 ? participants.filter((p) => !p.has_flight).length : 0)
  const withoutHotelCount = analysis?.without_hotel ?? (totalParticipants > 0 ? participants.filter((p) => !p.has_hotel).length : 0)
  const withoutTransferCount = analysis?.without_transfer ?? (totalParticipants > 0 ? participants.filter((p) => !p.has_transfer).length : 0)
  const withoutActivitiesCount = analysis?.without_activities ?? (totalParticipants > 0 ? participants.filter((p) => !p.has_activities).length : 0)
  const masterListBase = `/${locale}/events/${eventId}/master-list`

  // Distribution chart percentages — same full-event source as above.
  const flightsPct = totalParticipants > 0 ? Math.round(((totalParticipants - withoutFlightCount) / totalParticipants) * 100) : 0
  const hotelsPct = totalParticipants > 0 ? Math.round(((totalParticipants - withoutHotelCount) / totalParticipants) * 100) : 0
  const transfersPct = totalParticipants > 0 ? Math.round(((totalParticipants - withoutTransferCount) / totalParticipants) * 100) : 0
  const activitiesPct = totalParticipants > 0 ? Math.round(((totalParticipants - withoutActivitiesCount) / totalParticipants) * 100) : 0
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

        {/* Couverture — raw counts, click-through to the exact concerned
            participants on the master list (MVP feedback §14). */}
        {totalParticipants > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              label="Sans vol"
              value={withoutFlightCount}
              delta={withoutFlightCount === 0 ? 'Tous couverts' : undefined}
              deltaPositive={withoutFlightCount === 0}
              icon={<Plane className="h-5 w-5" />}
              accentColor="var(--color-warning)"
              href={`${masterListBase}?missing=flight`}
            />
            <KPICard
              label="Sans hébergement"
              value={withoutHotelCount}
              delta={withoutHotelCount === 0 ? 'Tous couverts' : undefined}
              deltaPositive={withoutHotelCount === 0}
              icon={<Hotel className="h-5 w-5" />}
              accentColor="var(--color-warning)"
              href={`${masterListBase}?missing=hotel`}
            />
            <KPICard
              label="Sans transfert"
              value={withoutTransferCount}
              delta={withoutTransferCount === 0 ? 'Tous couverts' : undefined}
              deltaPositive={withoutTransferCount === 0}
              icon={<Bus className="h-5 w-5" />}
              accentColor="var(--color-warning)"
              href={`${masterListBase}?missing=transfer`}
            />
            <KPICard
              label="Sans activité"
              value={withoutActivitiesCount}
              delta={withoutActivitiesCount === 0 ? 'Tous couverts' : undefined}
              deltaPositive={withoutActivitiesCount === 0}
              icon={<PartyPopper className="h-5 w-5" />}
              accentColor="var(--color-warning)"
              href={`${masterListBase}?missing=activities`}
            />
          </div>
        )}

        {/* Intelligent data-quality analysis (same engine as Rapports §15) */}
        {analysis && analysis.total > 0 && (
          <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
                <ShieldCheck className="h-4 w-4 text-[var(--color-accent)]" />
                Analyse de la qualité des données
              </h3>
              <Link
                href={`/${locale}/events/${eventId}/reports`}
                className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
              >
                Rapport complet <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              {/* Score + dimensions */}
              <div className="flex items-center gap-4 lg:col-span-1">
                <div
                  className="flex h-20 w-20 flex-shrink-0 flex-col items-center justify-center rounded-full border-4"
                  style={{ borderColor: analysis.quality_score >= 80 ? 'var(--color-success)' : analysis.quality_score >= 60 ? 'var(--color-warning)' : 'var(--color-danger)' }}
                >
                  <span className="text-2xl font-bold text-[var(--color-text-primary)]">{analysis.quality_score}</span>
                  <span className="text-[9px] text-[var(--color-text-secondary)]">/ 100</span>
                </div>
                <div className="flex-1 space-y-1.5">
                  {Object.entries(analysis.dimensions || {}).map(([dim, val]) => {
                    const labels: Record<string, string> = { identite: 'Identité', contact: 'Contact', voyage: 'Voyage', hebergement: 'Hébergement', regime: 'Régime', passeport: 'Passeport' }
                    const v = val as number
                    return (
                      <div key={dim}>
                        <div className="mb-0.5 flex justify-between text-[10px]">
                          <span className="text-[var(--color-text-secondary)]">{labels[dim] || dim}</span>
                          <span className="font-semibold text-[var(--color-text-primary)]">{v}%</span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full rounded-full" style={{ width: `${v}%`, background: v >= 80 ? 'var(--color-success)' : v >= 60 ? 'var(--color-warning)' : 'var(--color-danger)' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Recommendations */}
              <div className="lg:col-span-2">
                <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-cta)]">
                  <Lightbulb className="h-3.5 w-3.5" /> Conseils prioritaires
                </div>
                {(!analysis.recommendations || analysis.recommendations.length === 0) ? (
                  <p className="text-xs text-[var(--color-text-secondary)]">Aucune action requise — données complètes.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {analysis.recommendations.slice(0, 4).map((r: any, i: number) => (
                      <li key={i} className="flex items-start gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5">
                        <AlertTriangle className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${r.severity === 'critical' ? 'text-[var(--color-danger)]' : r.severity === 'warning' ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-secondary)]'}`} />
                        <span className="text-xs text-[var(--color-text-primary)]"><strong className="font-semibold">{r.count}</strong> {r.text}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {analysis.ai_summary && (
                  <div className="mt-3 rounded-lg border border-[var(--color-accent)]/20 bg-[var(--color-accent-light)]/40 p-2.5">
                    <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-[var(--color-accent)]">
                      <Sparkles className="h-3 w-3" /> Synthèse IA
                    </div>
                    <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-[var(--color-text-primary)]">{analysis.ai_summary}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Main content + right panel */}
        <div className="grid grid-cols-12 gap-6">
          {/* Left/main column — col-span-8 */}
          <div className="col-span-12 space-y-6 lg:col-span-8">
            {/* Visual blocks row */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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

              {/* Distribution Donut */}
              <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('breakdown')}
                </h3>
                <DistributionChart
                  data={distributionData}
                  onItemClick={(name) => {
                    const routes: Record<string, string> = {
                      'Vols': 'flights',
                      'Hôtels': 'hotels',
                      'Transferts': 'transfers',
                      'Activités': 'activities',
                      'Comms': 'communications',
                    }
                    const seg = routes[name]
                    if (seg) router.push(`/${locale}/events/${eventId}/${seg}`)
                  }} />
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
