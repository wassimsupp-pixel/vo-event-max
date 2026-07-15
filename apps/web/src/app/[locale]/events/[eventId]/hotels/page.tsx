'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { TableSkeleton } from '@/components/ui/TableSkeleton'
import { Hotel, Bed, Calendar, Plus, RefreshCw, Search } from 'lucide-react'
import { api, type ParticipantLookupItem } from '@/lib/api'

interface HotelProperty {
  id: string
  name: string
  address?: string
  city?: string
  contact_info?: string
}

interface RoomingNight {
  id: string
  hotel_id: string
  participant_id: string
  night_date: string
  room_type: string
  status: string
  participant_name?: string
  hotel_name?: string
}

export default function HotelsPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const t = useTranslations('hotels')
  const [hotels, setHotels] = useState<HotelProperty[]>([])
  const [roomingList, setRoomingList] = useState<RoomingNight[]>([])
  const [participants, setParticipants] = useState<ParticipantLookupItem[]>([])
  const [loading, setLoading] = useState(true)
  
  // Modals / Form states
  const [newHotelName, setNewHotelName] = useState('')
  const [newHotelCity, setNewHotelCity] = useState('')
  const [assignParticipantId, setAssignParticipantId] = useState('')
  const [assignHotelId, setAssignHotelId] = useState('')
  const [assignDate, setAssignDate] = useState('2025-11-10')
  const [assignRoomType, setAssignRoomType] = useState('single')
  const [searchTerm, setSearchTerm] = useState('')

  const fetchData = async () => {
    try {
      setLoading(true)
      const [hotelData, roomingData, partList] = await Promise.all([
        api.hotels.list(eventId),
        api.hotels.listRooming(eventId),
        api.participants.lookup(eventId)
      ])
      setHotels(hotelData)
      setRoomingList(roomingData)
      setParticipants(partList)
    } catch (err) {
      console.error('Failed to fetch hotels data', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [eventId])

  const handleAddHotel = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newHotelName) return
    try {
      await api.hotels.create(eventId, {
        name: newHotelName,
        city: newHotelCity,
      })
      setNewHotelName('')
      setNewHotelCity('')
      await fetchData()
    } catch (err) {
      console.error('Failed to add hotel', err)
    }
  }

  const handleAssignRoom = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!assignParticipantId || !assignHotelId || !assignDate) return
    try {
      if (assignParticipantId === 'all') {
        await api.hotels.assignRoomingBulk(eventId, {
          hotel_id: assignHotelId,
          night_date: assignDate,
          room_type: assignRoomType,
          status: 'confirmed',
        })
      } else {
        await api.hotels.assignRooming(eventId, {
          participant_id: assignParticipantId,
          hotel_id: assignHotelId,
          night_date: assignDate,
          room_type: assignRoomType,
        })
      }
      await fetchData()
    } catch (err) {
      console.error('Failed to assign rooming night', err)
    }
  }

  const handleDeleteRooming = async (id: string) => {
    try {
      await api.hotels.deleteRooming(id)
      await fetchData()
    } catch (err) {
      console.error('Failed to delete rooming night', err)
    }
  }

  const filteredRooming = roomingList.filter(r =>
    (r.participant_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (r.hotel_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Clicking a KPI scrolls to the detailed list of concerned participants (§11)
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
              <Hotel className="h-6 w-6 text-[var(--color-accent)]" />
              {t('title')}
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('subtitle')}
            </p>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <KPICard
            label={t('kpiProperties')}
            value={hotels.length}
            icon={<Hotel className="h-5 w-5" />}
            accentColor="var(--color-accent)"
            onClick={scrollToDetailList}
          />
          <KPICard
            label={t('kpiNights')}
            value={roomingList.length}
            icon={<Bed className="h-5 w-5" />}
            accentColor="var(--color-success)"
            onClick={scrollToDetailList}
          />
          <KPICard
            label={t('kpiParticipants')}
            value={new Set(roomingList.map(r => r.participant_id)).size}
            icon={<Calendar className="h-5 w-5" />}
            accentColor="var(--color-cta)"
            onClick={scrollToDetailList}
          />
        </div>

        {/* Form area */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Add Hotel Property */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              {t('addHotelTitle')}
            </h2>
            <form onSubmit={handleAddHotel} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('hotelNameLabel')}
                </label>
                <input
                  type="text"
                  placeholder="Ex. W Barcelona"
                  value={newHotelName}
                  onChange={(e) => setNewHotelName(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('cityLabel')}
                </label>
                <input
                  type="text"
                  placeholder="Ex. Barcelona"
                  value={newHotelCity}
                  onChange={(e) => setNewHotelCity(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                />
              </div>
              <button
                type="submit"
                className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors"
              >
                {t('addHotelButton')}
              </button>
            </form>
          </div>

          {/* Assign Night */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              {t('assignNightTitle')}
            </h2>
            <form onSubmit={handleAssignRoom} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('participantLabel')}
                </label>
                <select
                  value={assignParticipantId}
                  onChange={(e) => setAssignParticipantId(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
                  required
                >
                  <option value="">{t('selectPlaceholder')}</option>
                  <option value="all">Tous les participants (en bloc)</option>
                  {participants.map(p => (
                    <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('hotelLabel')}
                </label>
                <select
                  value={assignHotelId}
                  onChange={(e) => setAssignHotelId(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
                  required
                >
                  <option value="">{t('selectPlaceholder')}</option>
                  {hotels.map(h => (
                    <option key={h.id} value={h.id}>{h.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('dateLabel')}
                </label>
                <input
                  type="date"
                  value={assignDate}
                  onChange={(e) => setAssignDate(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('roomTypeLabel')}
                </label>
                <select
                  value={assignRoomType}
                  onChange={(e) => setAssignRoomType(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
                >
                  <option value="single">{t('roomTypeSingle')}</option>
                  <option value="double">{t('roomTypeDouble')}</option>
                  <option value="twin">{t('roomTypeTwin')}</option>
                  <option value="suite">{t('roomTypeSuite')}</option>
                </select>
              </div>
              <div className="col-span-1 md:col-span-2">
                <button
                  type="submit"
                  className="w-full rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors"
                >
                  {t('confirmAssignment')}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Rooming list table */}
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

        <div className="rounded-[var(--radius-card)] border bg-white shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                  <th className="p-4">{t('tableParticipant')}</th>
                  <th className="p-4">{t('tableHotel')}</th>
                  <th className="p-4">{t('tableNightDate')}</th>
                  <th className="p-4">{t('tableRoomType')}</th>
                  <th className="p-4">{t('tableStatus')}</th>
                  <th className="p-4 text-right">{t('tableActions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y text-[var(--color-text-primary)]">
                {loading ? (
                  <TableSkeleton cols={6} rows={4} />
                ) : filteredRooming.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-[var(--color-text-secondary)]">
                      {t('noAssignments')}
                    </td>
                  </tr>
                ) : (
                  filteredRooming.map((room) => (
                    <tr key={room.id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-4 font-semibold">{room.participant_name || 'N/A'}</td>
                      <td className="p-4">{room.hotel_name || 'N/A'}</td>
                      <td className="p-4 font-mono text-xs">{room.night_date}</td>
                      <td className="p-4">
                        {room.room_type === 'single' ? t('roomTypeSingle') :
                         room.room_type === 'double' ? t('roomTypeDouble') :
                         room.room_type === 'twin' ? t('roomTypeTwin') :
                         room.room_type === 'suite' ? t('roomTypeSuite') : room.room_type}
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          room.status === 'confirmed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}>
                          {room.status === 'confirmed' ? t('statusConfirmed') : t('statusRequested')}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <button
                          onClick={() => handleDeleteRooming(room.id)}
                          className="text-rose-600 hover:text-rose-900 font-semibold text-xs transition-colors"
                        >
                          {t('deleteButton')}
                        </button>
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
