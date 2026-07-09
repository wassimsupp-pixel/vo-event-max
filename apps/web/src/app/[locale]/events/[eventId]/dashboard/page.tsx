import { getTranslations } from 'next-intl/server'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { ConsolidationStepper } from '@/components/ui/ConsolidationStepper'
import { DataQualityGauge } from '@/components/ui/DataQualityGauge'
import { DataSourceCard } from '@/components/ui/DataSourceCard'
import { ExceptionItem } from '@/components/ui/ExceptionItem'
import { ParticipantTable } from '@/components/participants/ParticipantTable'
import { DistributionChart } from '@/components/ui/DistributionChart'
import Link from 'next/link'
import {
  Users,
  Database,
  CheckSquare,
  AlertTriangle,
  ChevronRight,
  CheckCircle2,
} from 'lucide-react'
import type { Participant } from '@/lib/api'

// ─── Mock Data ─────────────────────────────────────────────────────────────────

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

const DATA_SOURCES = [
  { id: '1', name: 'Export Client', subtitle: 'Liste officielle des participants', icon: '📋', status: 'imported' as const, lastUpdated: 'Il y a 2h' },
  { id: '2', name: 'FCM Vols', subtitle: 'Réservations de vols FCM Travel', icon: '✈️', status: 'imported' as const, lastUpdated: 'Il y a 4h' },
  { id: '3', name: 'Hôtels', subtitle: 'Confirmations hôtelières', icon: '🏨', status: 'imported' as const, lastUpdated: 'Il y a 1j' },
  { id: '4', name: 'Transferts', subtitle: 'Planning navettes & transferts', icon: '🚐', status: 'imported' as const, lastUpdated: 'Il y a 1j' },
  { id: '5', name: 'Activités', subtitle: 'Programme des activités', icon: '🎯', status: 'pending' as const, lastUpdated: undefined },
  { id: '6', name: 'Templates Comms', subtitle: 'Modèles de communications', icon: '✉️', status: 'pending' as const, lastUpdated: undefined },
  { id: '7', name: 'Master List Réf', subtitle: 'Liste de référence organisateur', icon: '📊', status: 'imported' as const, lastUpdated: 'Il y a 3h' },
]

// ─── Page ──────────────────────────────────────────────────────────────────────

interface DashboardPageProps {
  params: Promise<{ locale: string; eventId: string }>
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { locale, eventId } = await params
  const t = await getTranslations('dashboard')
  const tKpi = await getTranslations('dashboard.kpi')
  const tActions = await getTranslations('actions')
  const tExceptions = await getTranslations('exceptions')

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle={t('title')}
      pageSubtitle={t('subtitle')}
    >
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
            value="324"
            delta="+12 depuis hier"
            deltaPositive={true}
            icon={<Users className="h-5 w-5" />}
            accentColor="var(--color-accent)"
          />
          <KPICard
            label={tKpi('sources')}
            value="7/7"
            delta="Toutes importées"
            deltaPositive={true}
            icon={<Database className="h-5 w-5" />}
            accentColor="var(--color-success)"
          />
          <KPICard
            label={tKpi('complete')}
            value="87%"
            delta="+3% depuis hier"
            deltaPositive={true}
            icon={<CheckSquare className="h-5 w-5" />}
            accentColor="var(--color-cta)"
          />
          <KPICard
            label={tKpi('exceptions')}
            value="18"
            delta="-2 depuis hier"
            deltaPositive={true}
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
                <ConsolidationStepper />
              </div>

              {/* Data Quality Gauge */}
              <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('dataQuality')}
                </h3>
                <DataQualityGauge percentage={87} label="Qualité globale des données" />
              </div>

              {/* Distribution Donut */}
              <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-card)]">
                <h3 className="mb-4 text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('breakdown')}
                </h3>
                <DistributionChart />
              </div>
            </div>

            {/* Participant Table */}
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  {t('recentParticipants')}
                </h3>
                <Link
                  href={`/${locale}/events/${eventId}/master-list`}
                  className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
                >
                  {tActions('viewMasterList')}
                  <ChevronRight className="h-3 w-3" />
                </Link>
              </div>
              <ParticipantTable
                participants={MOCK_PARTICIPANTS}
                eventId={eventId}
                locale={locale}
              />
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
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
                {DATA_SOURCES.map((source) => (
                  <DataSourceCard
                    key={source.id}
                    name={source.name}
                    subtitle={source.subtitle}
                    icon={source.icon}
                    status={source.status}
                    lastUpdated={source.lastUpdated}
                    onImport={() => {}}
                  />
                ))}
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
                <Link
                  href={`/${locale}/events/${eventId}/exceptions`}
                  className="text-xs font-medium text-[var(--color-accent)] hover:underline"
                >
                  {tActions('viewAll')}
                </Link>
              </div>
              <div className="space-y-1">
                <ExceptionItem
                  type={tExceptions('conflict')}
                  count={5}
                  severity="critical"
                  onClick={() => {}}
                />
                <ExceptionItem
                  type={tExceptions('duplicate')}
                  count={3}
                  severity="warning"
                  onClick={() => {}}
                />
                <ExceptionItem
                  type={tExceptions('notFound')}
                  count={7}
                  severity="warning"
                  onClick={() => {}}
                />
                <ExceptionItem
                  type={tExceptions('toCheck')}
                  count={3}
                  severity="info"
                  onClick={() => {}}
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
                  { done: true, label: 'Importer toutes les sources' },
                  { done: true, label: 'Lancer la consolidation' },
                  { done: false, label: 'Résoudre les 5 conflits' },
                  { done: false, label: 'Valider les doublons (3)' },
                  { done: false, label: 'Exporter la master list finale' },
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
