'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { BarChart3, Plane, Hotel, Truck, Users, Activity, FileText } from 'lucide-react'
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
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [hotelNights, setHotelNights] = useState<HotelNightItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      setLoading(true)
      const sumData = await api.reports.getSummary(eventId)
      setSummary(sumData)
      
      const nightData = await api.reports.getHotelNights(eventId)
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

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <BarChart3 className="h-6 w-6 text-[var(--color-accent)]" />
              Rapports & Statistiques
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Analyse de complétude, suivi d&apos;attribution des ressources et bilans de l&apos;événement.
            </p>
          </div>
        </div>

        {/* KPIs */}
        {summary && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <KPICard
              label="Total participants"
              value={summary.total_registered}
              icon={<Users className="h-5 w-5" />}
              accentColor="var(--color-accent)"
            />
            <KPICard
              label="Sans vol renseigné"
              value={summary.missing_flight}
              icon={<Plane className="h-5 w-5" />}
              accentColor="var(--color-danger)"
            />
            <KPICard
              label="Sans hébergement"
              value={summary.missing_hotel}
              icon={<Hotel className="h-5 w-5" />}
              accentColor="var(--color-warning)"
            />
            <KPICard
              label="Sans transfert planifié"
              value={summary.missing_transfer}
              icon={<Truck className="h-5 w-5" />}
              accentColor="var(--color-cta)"
            />
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Hotel Occupancy stats */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Hotel className="h-5 w-5 text-[var(--color-accent)]" />
              Nuitées d&apos;hôtel confirmées par date
            </h2>
            {loading ? (
              <p className="text-sm text-[var(--color-text-secondary)]">Chargement des données...</p>
            ) : hotelNights.length === 0 ? (
              <p className="text-sm text-[var(--color-text-secondary)]">Aucune nuitée confirmée.</p>
            ) : (
              <div className="space-y-4">
                {hotelNights.map((item) => (
                  <div key={item.night_date} className="flex items-center gap-4">
                    <span className="w-24 text-sm font-semibold text-[var(--color-text-secondary)]">
                      {new Date(item.night_date).toLocaleDateString('fr-FR', {
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
                        {item.count} chambres occupées
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
              Taux de complétude global
            </h2>
            {summary && (
              <div className="flex flex-col gap-6">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-semibold text-[var(--color-text-secondary)]">Vols bookés</span>
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
                    <span className="font-semibold text-[var(--color-text-secondary)]">Hôtels alloués</span>
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
                    <span className="font-semibold text-[var(--color-text-secondary)]">Transferts programmés</span>
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
            <h3 className="font-bold text-[var(--color-text-primary)]">Générer le rapport final</h3>
            <p className="text-xs text-[var(--color-text-secondary)]">Télécharger un bilan complet de l&apos;événement contenant la Rooming List et le planning de transfert.</p>
          </div>
          <button className="flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors">
            <FileText className="h-4 w-4" />
            Exporter le Bilan complet
          </button>
        </div>
      </div>
    </AppLayout>
  )
}
