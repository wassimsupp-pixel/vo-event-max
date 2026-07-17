'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { BarChart3, Plane, Hotel, Truck, Users, Activity, FileText, Loader2, Sparkles, Lightbulb, AlertTriangle, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'

interface ReportSummary {
  total_registered: number
  missing_flight: number
  missing_hotel: number
  missing_transfer: number
}

interface HotelNightItem {
  night_date: string
  count: number
}

function DistributionList({ data, total }: { data?: Record<string, number>; total?: number }) {
  const entries = Object.entries(data || {}).slice(0, 8)
  if (entries.length === 0) return <p className="text-xs text-[var(--color-text-secondary)]">Aucune donnée disponible.</p>
  const max = Math.max(...entries.map(([, v]) => v), 1)
  return (
    <div className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center gap-3">
          <span className="w-28 truncate text-xs text-[var(--color-text-secondary)]" title={k}>{k}</span>
          <div className="relative h-5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-[var(--color-accent)]" style={{ width: `${(v / max) * 100}%` }} />
            <span className="absolute inset-0 flex items-center px-2 text-[10px] font-bold text-slate-700">
              {v}{total ? ` (${Math.round((v / total) * 100)}%)` : ''}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ReportsPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const t = useTranslations('reports')
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [hotelNights, setHotelNights] = useState<HotelNightItem[]>([])
  const [analysis, setAnalysis] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      setLoading(true)
      // Fast path: analysis WITHOUT the AI narrative (never blocks the page).
      const [sumData, nightData, analysisData] = await Promise.all([
        api.reports.getSummary(eventId),
        api.reports.getHotelNights(eventId),
        api.reports.getAnalysis(eventId).catch(() => null),
      ])
      setSummary(sumData)
      setHotelNights(nightData)
      setAnalysis(analysisData)
      // Then fetch the AI narrative in the background and merge it in when ready.
      api.reports.getAnalysis(eventId, true)
        .then((full) => {
          if (full?.ai_summary) setAnalysis((prev: typeof analysisData) => prev ? { ...prev, ai_summary: full.ai_summary } : full)
        })
        .catch(() => { /* narrative optional */ })
    } catch (err) {
      console.error('Failed to fetch report statistics', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [eventId])

  const [isExporting, setIsExporting] = useState(false)

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
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <BarChart3 className="h-6 w-6 text-[var(--color-accent)]" />
              {t('title')}
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('subtitle')}
            </p>
          </div>
        </div>

        {/* KPIs */}
        {summary && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <KPICard
              label={t('kpiTotal')}
              value={summary.total_registered}
              icon={<Users className="h-5 w-5" />}
              accentColor="var(--color-accent)"
              href={`/${locale}/events/${eventId}/master-list`}
            />
            <KPICard
              label={t('kpiNoFlight')}
              value={summary.missing_flight}
              icon={<Plane className="h-5 w-5" />}
              accentColor="var(--color-danger)"
              href={`/${locale}/events/${eventId}/master-list?missing=flight`}
            />
            <KPICard
              label={t('kpiNoHotel')}
              value={summary.missing_hotel}
              icon={<Hotel className="h-5 w-5" />}
              accentColor="var(--color-warning)"
              href={`/${locale}/events/${eventId}/master-list?missing=hotel`}
            />
            <KPICard
              label={t('kpiNoTransfer')}
              value={summary.missing_transfer}
              icon={<Truck className="h-5 w-5" />}
              accentColor="var(--color-cta)"
              href={`/${locale}/events/${eventId}/master-list?missing=transfer`}
            />
          </div>
        )}

        {/* Intelligent data-quality analysis + recommendations (§15) */}
        {analysis && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Quality analysis */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-[var(--color-accent)]" />
                Analyse de la qualité des données
              </h2>
              <div className="flex items-center gap-4 mb-5">
                <div className="flex h-20 w-20 flex-shrink-0 flex-col items-center justify-center rounded-full border-4"
                  style={{ borderColor: analysis.quality_score >= 80 ? 'var(--color-success)' : analysis.quality_score >= 60 ? 'var(--color-warning)' : 'var(--color-danger)' }}>
                  <span className="text-2xl font-bold text-[var(--color-text-primary)]">{analysis.quality_score}</span>
                  <span className="text-[9px] text-[var(--color-text-secondary)]">/ 100</span>
                </div>
                <div className="flex-1 space-y-2">
                  {Object.entries(analysis.dimensions || {}).map(([dim, val]) => {
                    const labels: Record<string, string> = { identite: 'Identité', contact: 'Contact', voyage: 'Voyage', hebergement: 'Hébergement', regime: 'Régime', passeport: 'Passeport' }
                    const v = val as number
                    return (
                      <div key={dim}>
                        <div className="flex justify-between text-[11px] mb-0.5">
                          <span className="text-[var(--color-text-secondary)]">{labels[dim] || dim}</span>
                          <span className="font-semibold text-[var(--color-text-primary)]">{v}%</span>
                        </div>
                        <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${v}%`, background: v >= 80 ? 'var(--color-success)' : v >= 60 ? 'var(--color-warning)' : 'var(--color-danger)' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
              {analysis.ai_summary && (
                <div className="rounded-lg border border-[var(--color-accent)]/20 bg-[var(--color-accent-light)]/40 p-3">
                  <div className="flex items-center gap-1.5 mb-1 text-[11px] font-semibold text-[var(--color-accent)]">
                    <Sparkles className="h-3.5 w-3.5" /> Synthèse IA
                  </div>
                  <p className="text-xs text-[var(--color-text-primary)] leading-relaxed whitespace-pre-wrap">{analysis.ai_summary}</p>
                </div>
              )}
            </div>

            {/* Recommendations */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Lightbulb className="h-5 w-5 text-[var(--color-cta)]" />
                Analyse &amp; conseils
              </h2>
              {(!analysis.recommendations || analysis.recommendations.length === 0) ? (
                <div className="flex flex-col items-center justify-center py-8 text-center gap-2">
                  <ShieldCheck className="h-8 w-8 text-[var(--color-success)]" />
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">Aucune action requise — données complètes.</p>
                </div>
              ) : (
                <ul className="space-y-2.5">
                  {analysis.recommendations.map((r: any, i: number) => (
                    <li key={i} className="flex items-start gap-2.5 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                      <AlertTriangle className={`h-4 w-4 shrink-0 mt-0.5 ${r.severity === 'critical' ? 'text-[var(--color-danger)]' : r.severity === 'warning' ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-secondary)]'}`} />
                      <span className="text-xs text-[var(--color-text-primary)]">
                        <strong className="font-semibold">{r.count}</strong> {r.text}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Distribution by region */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h2 className="text-sm font-bold text-[var(--color-text-primary)] mb-4">Répartition par région</h2>
              <DistributionList data={analysis.by_region} total={analysis.total} />
            </div>

            {/* Distribution by category */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h2 className="text-sm font-bold text-[var(--color-text-primary)] mb-4">Répartition par catégorie</h2>
              <DistributionList data={analysis.by_category} total={analysis.total} />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Hotel Occupancy stats */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Hotel className="h-5 w-5 text-[var(--color-accent)]" />
              {t('hotelOccupancyTitle')}
            </h2>
            {loading ? (
              <p className="text-sm text-[var(--color-text-secondary)]">{t('loading')}</p>
            ) : hotelNights.length === 0 ? (
              <p className="text-sm text-[var(--color-text-secondary)]">{t('noNights')}</p>
            ) : (
              <div className="space-y-4">
                {hotelNights.map((item) => (
                  <div key={item.night_date} className="flex items-center gap-4">
                    <span className="w-24 text-sm font-semibold text-[var(--color-text-secondary)]">
                      {new Date(item.night_date).toLocaleDateString(locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US', {
                        weekday: 'short',
                        day: 'numeric',
                        month: 'short',
                      })}
                    </span>
                    <div className="flex-1 bg-slate-100 h-6 rounded-full overflow-hidden relative">
                      <div
                        className="bg-[var(--color-accent)] h-full transition-all duration-500 rounded-full"
                        style={{ width: `${Math.min(100, (item.count / (summary?.total_registered || 1)) * 100)}%` }}
                      />
                      <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-800">
                        {t('roomsOccupied', { count: item.count })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Completeness breakdown */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Activity className="h-5 w-5 text-[var(--color-accent)]" />
              {t('completenessTitle')}
            </h2>
            {summary && (
              <div className="flex flex-col gap-6">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-semibold text-[var(--color-text-secondary)]">{t('flightsBooked')}</span>
                    <span className="font-bold text-[var(--color-text-primary)]">
                      {(((summary.total_registered - summary.missing_flight) / (summary.total_registered || 1)) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden">
                    <div
                      className="bg-emerald-500 h-full rounded-full"
                      style={{ width: `${((summary.total_registered - summary.missing_flight) / (summary.total_registered || 1)) * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-semibold text-[var(--color-text-secondary)]">{t('hotelsAllocated')}</span>
                    <span className="font-bold text-[var(--color-text-primary)]">
                      {(((summary.total_registered - summary.missing_hotel) / (summary.total_registered || 1)) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden">
                    <div
                      className="bg-sky-500 h-full rounded-full"
                      style={{ width: `${((summary.total_registered - summary.missing_hotel) / (summary.total_registered || 1)) * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-semibold text-[var(--color-text-secondary)]">{t('transfersScheduled')}</span>
                    <span className="font-bold text-[var(--color-text-primary)]">
                      {(((summary.total_registered - summary.missing_transfer) / (summary.total_registered || 1)) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden">
                    <div
                      className="bg-amber-500 h-full rounded-full"
                      style={{ width: `${((summary.total_registered - summary.missing_transfer) / (summary.total_registered || 1)) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Action Button for reporting export */}
        <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm flex items-center justify-between">
          <div>
            <h3 className="font-bold text-[var(--color-text-primary)]">{t('finalReportTitle')}</h3>
            <p className="text-xs text-[var(--color-text-secondary)]">{t('finalReportDesc')}</p>
          </div>
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors disabled:opacity-50"
          >
            {isExporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            {isExporting ? t('generating') : t('exportButton')}
          </button>
        </div>
      </div>
    </AppLayout>
  )
}
