'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { TableSkeleton } from '@/components/ui/TableSkeleton'
import { Plane, Upload, AlertCircle, RefreshCw, CheckCircle, Search, UserX } from 'lucide-react'
import { api } from '@/lib/api'
import { ConcernedParticipants, type CohortRow } from '@/components/ui/ConcernedParticipants'

interface Flight {
  id: string
  participant_id?: string
  pnr_code?: string
  airline?: string
  flight_number: string
  departure_airport: string
  arrival_airport: string
  departure_time: string
  arrival_time: string
  baggage_info?: string
  status: string
  participant_name?: string
}

interface PassengerFlights {
  key: string
  participant_id?: string
  participant_name: string
  segments: Flight[]
}

export default function FlightsPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const t = useTranslations('flights')
  const [flights, setFlights] = useState<Flight[]>([])
  const [loading, setLoading] = useState(true)
  const [extracting, setExtracting] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'confirmed' | 'cancelled'>('all')
  const [masterRows, setMasterRows] = useState<CohortRow[]>([])
  const [showMissing, setShowMissing] = useState(false)

  const fetchFlights = async () => {
    try {
      setLoading(true)
      const [data, master] = await Promise.all([
        api.flights.list(eventId),
        api.masterList.get(eventId).catch(() => ({ items: [] as CohortRow[] })),
      ])
      setFlights(data)
      setMasterRows((master.items as CohortRow[]) || [])
    } catch (err) {
      console.error('Failed to fetch flights', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFlights()
  }, [eventId])

  const handleExtract = async () => {
    try {
      setExtracting(true)
      setStatusMessage('')
      const res = await api.flights.extract(eventId)
      setStatusMessage(t('extractSuccess') + ': ' + res.message)
      await fetchFlights()
    } catch (err) {
      console.error('Failed to extract flights', err)
      setStatusMessage(t('extractError'))
    } finally {
      setExtracting(false)
    }
  }

  const filteredFlights = flights.filter(f => {
    const q = searchTerm.toLowerCase()
    const matchesSearch =
      (f.participant_name || '').toLowerCase().includes(q) ||
      f.flight_number.toLowerCase().includes(q) ||
      (f.pnr_code || '').toLowerCase().includes(q)
    const matchesStatus = statusFilter === 'all' ? true : f.status === statusFilter
    return matchesSearch && matchesStatus
  })

  // Group segments by passenger: a round trip = outbound + return = ONE row,
  // not two. Keeps every segment but shows one line per participant.
  const groupedPassengers: PassengerFlights[] = (() => {
    const map = new Map<string, PassengerFlights>()
    for (const f of filteredFlights) {
      const key = f.participant_id || f.participant_name || f.id
      let g = map.get(key)
      if (!g) {
        g = { key, participant_id: f.participant_id, participant_name: f.participant_name || 'N/A', segments: [] }
        map.set(key, g)
      }
      g.segments.push(f)
    }
    const arr = Array.from(map.values())
    arr.forEach(g => g.segments.sort((a, b) => String(a.departure_time || '').localeCompare(String(b.departure_time || ''))))
    arr.sort((a, b) => a.participant_name.localeCompare(b.participant_name))
    return arr
  })()

  const segmentLabel = (count: number, idx: number) => {
    if (count < 2) return null
    if (idx === 0) return 'Aller'
    if (idx === count - 1) return 'Retour'
    return `Vol ${idx + 1}`
  }

  const missingFlightsCount = flights.filter(f => f.status === 'cancelled').length
  const withoutFlight = masterRows.filter(r => !r.has_flight)

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Plane className="h-6 w-6 text-[var(--color-accent)]" />
              {t('title')}
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('subtitle')}
            </p>
          </div>
          <button
            onClick={handleExtract}
            disabled={extracting}
            className="flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors disabled:opacity-50"
          >
            {extracting ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            {t('extractButton')}
          </button>
        </div>

        {statusMessage && (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-600" />
            {statusMessage}
          </div>
        )}

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <KPICard
            label={t('kpiTotal')}
            value={flights.length}
            icon={<Plane className="h-5 w-5" />}
            accentColor="var(--color-accent)"
            onClick={() => { setStatusFilter('all'); setShowMissing(false) }}
            active={statusFilter === 'all' && !showMissing}
          />
          <KPICard
            label={t('kpiAirports')}
            value={new Set(flights.map(f => f.departure_airport)).size}
            icon={<Plane className="h-5 w-5 rotate-45" />}
            accentColor="var(--color-success)"
          />
          <KPICard
            label={t('kpiCancelled')}
            value={missingFlightsCount}
            icon={<AlertCircle className="h-5 w-5" />}
            accentColor="var(--color-danger)"
            onClick={() => { setStatusFilter('cancelled'); setShowMissing(false) }}
            active={statusFilter === 'cancelled' && !showMissing}
          />
          <KPICard
            label="Sans vol"
            value={withoutFlight.length}
            icon={<UserX className="h-5 w-5" />}
            accentColor="var(--color-danger)"
            onClick={() => setShowMissing(v => !v)}
            active={showMissing}
          />
        </div>

        {/* Concerned participants: those without any flight (§10) */}
        {showMissing && (
          <ConcernedParticipants
            rows={withoutFlight}
            title="Participants sans vol"
            action="Action recommandée : relancer FCM / le participant pour obtenir les informations de vol."
            emptyText="Tous les participants ont un vol renseigné."
            locale={locale}
            eventId={eventId}
          />
        )}

        {/* Search */}
        <div className="flex items-center gap-2 max-w-md bg-white border rounded-lg px-3 py-2 shadow-sm">
          <Search className="h-4 w-4 text-[var(--color-text-secondary)]" />
          <input
            type="text"
            placeholder={t('searchPlaceholder')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full text-sm outline-none bg-transparent"
          />
        </div>

        {/* Flights list */}
        <div className="rounded-[var(--radius-card)] border bg-white shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                  <th className="p-4">{t('tablePassenger')}</th>
                  <th className="p-4">Vols (aller / retour)</th>
                  <th className="p-4">{t('tablePnr')}</th>
                  <th className="p-4">{t('tableStatus')}</th>
                </tr>
              </thead>
              <tbody className="divide-y text-[var(--color-text-primary)]">
                {loading ? (
                  <TableSkeleton cols={4} rows={4} />
                ) : groupedPassengers.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-8 text-center text-[var(--color-text-secondary)]">
                      {t('noFlights')}
                    </td>
                  </tr>
                ) : (
                  groupedPassengers.map((pax) => {
                    const anyCancelled = pax.segments.some(s => s.status === 'cancelled')
                    const pnrs = Array.from(new Set(pax.segments.map(s => s.pnr_code).filter(Boolean)))
                    return (
                      <tr key={pax.key} className="hover:bg-slate-50 transition-colors align-top">
                        <td className="p-4 font-semibold whitespace-nowrap">
                          {pax.participant_name}
                          {pax.segments.length > 1 && (
                            <span className="ml-2 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                              {pax.segments.length} vols
                            </span>
                          )}
                        </td>
                        <td className="p-4">
                          <div className="flex flex-col gap-1.5">
                            {pax.segments.map((s, idx) => {
                              const label = segmentLabel(pax.segments.length, idx)
                              const localeTag = locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US'
                              return (
                                <div key={s.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                                  {label && (
                                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${idx === 0 ? 'bg-sky-100 text-sky-700' : 'bg-violet-100 text-violet-700'}`}>
                                      {label}
                                    </span>
                                  )}
                                  <span className="font-mono bg-slate-100 rounded px-1.5 py-0.5 text-slate-800">{s.flight_number}</span>
                                  {s.airline && <span className="font-medium">{s.airline}</span>}
                                  <span className="font-medium">{s.departure_airport} ➔ {s.arrival_airport}</span>
                                  <span className="text-[var(--color-text-secondary)]">
                                    {new Date(s.departure_time).toLocaleString(localeTag, { dateStyle: 'short', timeStyle: 'short' })}
                                    {s.arrival_time && ` → ${new Date(s.arrival_time).toLocaleString(localeTag, { dateStyle: 'short', timeStyle: 'short' })}`}
                                  </span>
                                  {s.baggage_info && (
                                    <span className="text-[var(--color-text-secondary)]">· Bagages : {s.baggage_info}</span>
                                  )}
                                  {s.status === 'cancelled' && (
                                    <span className="text-[10px] font-semibold text-rose-600">(annulé)</span>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        </td>
                        <td className="p-4 font-mono text-xs whitespace-nowrap">{pnrs.length > 0 ? pnrs.join(', ') : '-'}</td>
                        <td className="p-4">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                            !anyCancelled
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}>
                            {!anyCancelled ? t('statusConfirmed') : t('statusCancelled')}
                          </span>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
