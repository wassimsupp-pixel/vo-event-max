'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { BarChart3, Plane, Hotel, Truck, Users, Activity, FileText, Loader2 } from 'lucide-react'
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

export default function ReportsPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const t = useTranslations('reports')
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [hotelNights, setHotelNights] = useState<HotelNightItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      setLoading(true)
      const [sumData, nightData] = await Promise.all([
        api.reports.getSummary(eventId),
        api.reports.getHotelNights(eventId)
      ])
      setSummary(sumData)
      setHotelNights(nightData)
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
