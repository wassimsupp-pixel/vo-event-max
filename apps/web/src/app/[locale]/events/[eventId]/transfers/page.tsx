'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { TableSkeleton } from '@/components/ui/TableSkeleton'
import { Truck, Users, Compass, AlertCircle, RefreshCw, Search } from 'lucide-react'
import { api } from '@/lib/api'

interface Transfer {
  id: string
  transfer_type: string
  pickup_location: string
  dropoff_location: string
  pickup_time: string
  vehicle_type?: string
  status: string
  participant_name?: string
  flight_number?: string
}

export default function TransfersPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const t = useTranslations('transfers')
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [loading, setLoading] = useState(true)
  const [grouping, setGrouping] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')

  // Dispatcher settings
  const [windowMinutes, setWindowMinutes] = useState(60)
  const [pickupLoc, setPickupLoc] = useState('Aéroport de Bruxelles (BRU)')
  const [dropoffLoc, setDropoffLoc] = useState('Hôtel de la Conférence')
  const [vehicle, setVehicle] = useState('Shuttle Bus (50 places)')
  const [statusMsg, setStatusMsg] = useState('')

  const fetchTransfers = async () => {
    try {
      setLoading(true)
      const data = await api.transfers.list(eventId)
      setTransfers(data)
    } catch (err) {
      console.error('Failed to fetch transfers', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTransfers()
  }, [eventId])

  const handleAutoGroup = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      setGrouping(true)
      setStatusMsg('')
      const res = await api.transfers.group(eventId, {
        window_minutes: windowMinutes,
        pickup_location: pickupLoc,
        dropoff_location: dropoffLoc,
        vehicle_type: vehicle,
      })
      setStatusMsg(res.message)
      await fetchTransfers()
    } catch (err) {
      console.error('Failed to group transfers', err)
      setStatusMsg(t('errorMsg'))
    } finally {
      setGrouping(false)
    }
  }

  const filteredTransfers = transfers.filter(t =>
    (t.participant_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.pickup_location.toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.dropoff_location.toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Clicking a KPI scrolls to the detailed list of concerned participants (§12)
  const scrollToDetailList = () => {
    document.getElementById('detail-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Truck className="h-6 w-6 text-[var(--color-accent)]" />
              {t('title')}
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('subtitle')}
            </p>
          </div>
        </div>

        {statusMsg && (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 flex items-center gap-2">
            <Users className="h-4 w-4 text-emerald-600" />
            {statusMsg}
          </div>
        )}

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <KPICard
            label={t('kpiTransfers')}
            value={transfers.length}
            icon={<Truck className="h-5 w-5" />}
            accentColor="var(--color-accent)"
            onClick={scrollToDetailList}
          />
          <KPICard
            label={t('kpiGrouped')}
            value={new Set(transfers.map(t => t.pickup_time)).size}
            icon={<Compass className="h-5 w-5" />}
            accentColor="var(--color-success)"
            onClick={scrollToDetailList}
          />
          <KPICard
            label={t('kpiShuttles')}
            value={transfers.length > 0 ? (transfers.length / new Set(transfers.map(t => t.pickup_time)).size).toFixed(1) : 0}
            icon={<Users className="h-5 w-5" />}
            accentColor="var(--color-cta)"
            onClick={scrollToDetailList}
          />
        </div>

        {/* Group Dispatcher form */}
        <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
            <RefreshCw className="h-5 w-5 text-[var(--color-accent)]" />
            {t('autoGroupTitle')}
          </h2>
          <form onSubmit={handleAutoGroup} className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                {t('slotSizeLabel')}
              </label>
              <select
                value={windowMinutes}
                onChange={(e) => setWindowMinutes(Number(e.target.value))}
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
              >
                <option value={30}>{t('minutesOption', { count: 30 })}</option>
                <option value={60}>{t('hourOption')}</option>
                <option value={90}>{t('hourHalfOption')}</option>
                <option value={120}>{t('hoursOption')}</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                {t('pickupLocationLabel')}
              </label>
              <input
                type="text"
                value={pickupLoc}
                onChange={(e) => setPickupLoc(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                {t('dropoffLocationLabel')}
              </label>
              <input
                type="text"
                value={dropoffLoc}
                onChange={(e) => setDropoffLoc(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                required
              />
            </div>
            <div>
              <button
                type="submit"
                disabled={grouping}
                className="w-full rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {grouping ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {t('calculateGroupsButton')}
              </button>
            </div>
          </form>
        </div>

        {/* Search */}
        <div id="detail-list" className="flex items-center gap-2 max-w-md bg-white border rounded-lg px-3 py-2 shadow-sm scroll-mt-24">
          <Search className="h-4 w-4 text-[var(--color-text-secondary)]" />
          <input
            type="text"
            placeholder={t('searchPlaceholder')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full text-sm outline-none bg-transparent"
          />
        </div>

        {/* Transfers list */}
        <div className="rounded-[var(--radius-card)] border bg-white shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                  <th className="p-4">{t('tablePassenger')}</th>
                  <th className="p-4">{t('tablePickupLocation')}</th>
                  <th className="p-4">{t('tableDropoffLocation')}</th>
                  <th className="p-4">{t('tablePickupTime')}</th>
                  <th className="p-4">{t('tableFlight')}</th>
                  <th className="p-4">{t('tableVehicle')}</th>
                  <th className="p-4">{t('tableStatus')}</th>
                </tr>
              </thead>
              <tbody className="divide-y text-[var(--color-text-primary)]">
                {loading ? (
                  <TableSkeleton cols={7} rows={4} />
                ) : filteredTransfers.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-[var(--color-text-secondary)]">
                      {t('noTransfers')}
                    </td>
                  </tr>
                ) : (
                  filteredTransfers.map((tTrans) => (
                    <tr key={tTrans.id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-4 font-semibold">{tTrans.participant_name || 'N/A'}</td>
                      <td className="p-4">{tTrans.pickup_location}</td>
                      <td className="p-4">{tTrans.dropoff_location}</td>
                      <td className="p-4 text-xs font-semibold text-[var(--color-accent)] bg-[var(--color-accent-light)]/40 rounded">
                        {new Date(tTrans.pickup_time).toLocaleString(locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US', {
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })}
                      </td>
                      <td className="p-4 font-mono text-xs text-slate-800">{tTrans.flight_number || '-'}</td>
                      <td className="p-4 text-xs">{tTrans.vehicle_type || 'Shuttle Standard'}</td>
                      <td className="p-4">
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {t('statusScheduled')}
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
