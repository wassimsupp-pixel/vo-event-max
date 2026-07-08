'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { Plane, Upload, AlertCircle, RefreshCw, CheckCircle, Search } from 'lucide-react'
import { api } from '@/lib/api'

interface Flight {
  id: string
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

export default function FlightsPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const t = useTranslations('nav')
  const [flights, setFlights] = useState<Flight[]>([])
  const [loading, setLoading] = useState(true)
  const [extracting, setExtracting] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusMessage, setStatusMessage] = useState('')

  const fetchFlights = async () => {
    try {
      setLoading(true)
      const data = await api.flights.list(eventId)
      setFlights(data)
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
      setStatusMessage(res.message)
      await fetchFlights()
    } catch (err) {
      console.error('Failed to extract flights', err)
      setStatusMessage('Error extracting flights.')
    } finally {
      setExtracting(false)
    }
  }

  const filteredFlights = flights.filter(f => 
    (f.participant_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    f.flight_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (f.pnr_code || '').toLowerCase().includes(searchTerm.toLowerCase())
  )

  const missingFlightsCount = flights.filter(f => f.status === 'cancelled').length

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Plane className="h-6 w-6 text-[var(--color-accent)]" />
              Gestion des Vols
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Visualisation et synchronisation des détails de vols des participants.
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
            Extraire depuis FCM
          </button>
        </div>

        {statusMessage && (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-600" />
            {statusMessage}
          </div>
        )}

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <KPICard
            label="Total passagers avec vol"
            value={flights.length}
            icon={<Plane className="h-5 w-5" />}
            accentColor="var(--color-accent)"
          />
          <KPICard
            label="Aéroports de départ différents"
            value={new Set(flights.map(f => f.departure_airport)).size}
            icon={<Plane className="h-5 w-5 rotate-45" />}
            accentColor="var(--color-success)"
          />
          <KPICard
            label="Vols signalés annulés"
            value={missingFlightsCount}
            icon={<AlertCircle className="h-5 w-5" />}
            accentColor="var(--color-danger)"
          />
        </div>

        {/* Search */}
        <div className="flex items-center gap-2 max-w-md bg-white border rounded-lg px-3 py-2 shadow-sm">
          <Search className="h-4 w-4 text-[var(--color-text-secondary)]" />
          <input
            type="text"
            placeholder="Rechercher par passager, vol, PNR..."
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
                  <th className="p-4">Passager</th>
                  <th className="p-4">N° de Vol</th>
                  <th className="p-4">PNR</th>
                  <th className="p-4">Route</th>
                  <th className="p-4">Départ</th>
                  <th className="p-4">Arrivée</th>
                  <th className="p-4">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y text-[var(--color-text-primary)]">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-[var(--color-text-secondary)]">
                      Chargement des vols en cours...
                    </td>
                  </tr>
                ) : filteredFlights.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-[var(--color-text-secondary)]">
                      Aucun vol trouvé.
                    </td>
                  </tr>
                ) : (
                  filteredFlights.map((flight) => (
                    <tr key={flight.id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-4 font-semibold">{flight.participant_name || 'N/A'}</td>
                      <td className="p-4">
                        <span className="font-mono bg-slate-100 rounded px-1.5 py-0.5 text-xs text-slate-800">
                          {flight.flight_number}
                        </span>
                      </td>
                      <td className="p-4 font-mono text-xs">{flight.pnr_code || '-'}</td>
                      <td className="p-4">
                        {flight.departure_airport} ➔ {flight.arrival_airport}
                      </td>
                      <td className="p-4 text-xs">
                        {new Date(flight.departure_time).toLocaleString('fr-FR', {
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })}
                      </td>
                      <td className="p-4 text-xs">
                        {new Date(flight.arrival_time).toLocaleString('fr-FR', {
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })}
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          flight.status === 'confirmed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}>
                          {flight.status === 'confirmed' ? 'Confirmé' : 'Annulé'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
