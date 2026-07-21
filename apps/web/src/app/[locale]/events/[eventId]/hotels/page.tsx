'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { TableSkeleton } from '@/components/ui/TableSkeleton'
import { Hotel, Bed, Calendar, Plus, Search, UserX, AlertTriangle } from 'lucide-react'
import { api, type ParticipantLookupItem } from '@/lib/api'
import { ConcernedParticipants, type CohortRow } from '@/components/ui/ConcernedParticipants'

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
  const [masterRows, setMasterRows] = useState<CohortRow[]>([])
  const [showMissing, setShowMissing] = useState(false)
  const [loading, setLoading] = useState(true)
  
  // Modals / Form states
  const [newHotelName, setNewHotelName] = useState('')
  const [newHotelCity, setNewHotelCity] = useState('')
  const [assignParticipantId, setAssignParticipantId] = useState('')
  const [participantSearch, setParticipantSearch] = useState('')
  const [showParticipantDropdown, setShowParticipantDropdown] = useState(false)
  const [assignHotelId, setAssignHotelId] = useState('')
  const [assignCheckIn, setAssignCheckIn] = useState('2025-11-10')
  const [assignCheckOut, setAssignCheckOut] = useState('2025-11-11')
  const [assignRoomType, setAssignRoomType] = useState('single')
  const [searchTerm, setSearchTerm] = useState('')

  // In-flight guards + user-visible errors: these actions used to fail
  // silently (console.error only) and had no disabled state, so a double
  // click (e.g. on "Confirmer l'attribution" with "Tous les participants
  // en bloc" selected) could fire the same mutation twice concurrently.
  const [addingHotel, setAddingHotel] = useState(false)
  const [assigningRoom, setAssigningRoom] = useState(false)
  const [deletingStayKey, setDeletingStayKey] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const fetchData = async () => {
    try {
      setLoading(true)
      const [hotelData, roomingData, partList, master] = await Promise.all([
        api.hotels.list(eventId),
        api.hotels.listRooming(eventId),
        api.participants.lookup(eventId),
        api.masterList.get(eventId).catch(() => ({ items: [] as CohortRow[] })),
      ])
      setHotels(hotelData)
      setRoomingList(roomingData)
      setParticipants(partList)
      setMasterRows((master.items as CohortRow[]) || [])
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
    if (!newHotelName || addingHotel) return
    setAddingHotel(true)
    setActionError(null)
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
      setActionError(err instanceof Error ? `Échec de l'ajout de l'hôtel : ${err.message}` : "Échec de l'ajout de l'hôtel. Réessayez.")
    } finally {
      setAddingHotel(false)
    }
  }

  // A stay is a check-in/check-out RANGE, but the backend still models one
  // row per NIGHT (HotelNightCreate only takes a single night_date) -- so a
  // 3-night stay needs 3 calls. Standard hotel semantics: nights run from
  // check-in (inclusive) to the day before check-out (the guest leaves that
  // morning), so 21/07 -> 23/07 is 2 nights (21/07, 22/07).
  const nightsInRange = (checkIn: string, checkOut: string): string[] => {
    const nights: string[] = []
    const start = new Date(checkIn + 'T00:00:00')
    const end = new Date(checkOut + 'T00:00:00')
    for (let d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
      nights.push(d.toISOString().slice(0, 10))
    }
    return nights
  }

  const handleAssignRoom = async (e: React.FormEvent) => {
    e.preventDefault()
    if (assigningRoom) return
    if (!assignParticipantId) {
      setActionError('Sélectionnez un participant dans la liste (ou "Tous les participants").')
      return
    }
    if (!assignHotelId || !assignCheckIn || !assignCheckOut) return
    const nights = nightsInRange(assignCheckIn, assignCheckOut)
    if (nights.length === 0) {
      setActionError('La date de départ doit être après la date d\'arrivée.')
      return
    }
    setAssigningRoom(true)
    setActionError(null)
    try {
      for (const night_date of nights) {
        if (assignParticipantId === 'all') {
          await api.hotels.assignRoomingBulk(eventId, {
            hotel_id: assignHotelId,
            night_date,
            room_type: assignRoomType,
            status: 'confirmed',
          })
        } else {
          await api.hotels.assignRooming(eventId, {
            participant_id: assignParticipantId,
            hotel_id: assignHotelId,
            night_date,
            room_type: assignRoomType,
          })
        }
      }
      await fetchData()
    } catch (err) {
      console.error('Failed to assign rooming night', err)
      setActionError(err instanceof Error ? `Échec de l'attribution : ${err.message}` : "Échec de l'attribution de la chambre. Réessayez.")
    } finally {
      setAssigningRoom(false)
    }
  }

  // Pre-fills the assign form with a participant clicked from the "Sans
  // hébergement" list and scrolls to it, so the user only needs to pick the
  // hotel + dates and confirm.
  const handleQuickAddHotel = (row: CohortRow) => {
    setAssignParticipantId(row.id)
    setParticipantSearch([row.first_name, row.last_name].filter(Boolean).join(' '))
    document.getElementById('assign-night-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }


  const filteredRooming = roomingList.filter(r =>
    (r.participant_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (r.hotel_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Group nights per (participant · hotel · room type) into one stay: instead of
  // one row per night, show the client with the date range and the night count
  // (e.g. 21/07/2026 - 22/07/2026 => 2).
  const fmtDate = (iso: string) => {
    const d = new Date(iso)
    return isNaN(d.getTime())
      ? iso
      : `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
  }
  interface Stay {
    key: string
    participant_name?: string
    hotel_name?: string
    room_type: string
    status: string
    nightIds: string[]
    firstNight: string
    lastNight: string
    nights: number
  }
  const stays: Stay[] = Object.values(
    filteredRooming.reduce((acc: Record<string, Stay>, r) => {
      const key = `${r.participant_id}|${r.hotel_id}|${r.room_type}`
      const s = acc[key] || (acc[key] = {
        key,
        participant_name: r.participant_name,
        hotel_name: r.hotel_name,
        room_type: r.room_type,
        status: r.status,
        nightIds: [],
        firstNight: r.night_date,
        lastNight: r.night_date,
        nights: 0,
      })
      s.nightIds.push(r.id)
      if (r.night_date < s.firstNight) s.firstNight = r.night_date
      if (r.night_date > s.lastNight) s.lastNight = r.night_date
      s.nights += 1
      return acc
    }, {})
  ).sort((a, b) => (a.participant_name || '').localeCompare(b.participant_name || ''))

  const handleDeleteStay = async (stay: Stay) => {
    if (deletingStayKey) return
    setDeletingStayKey(stay.key)
    setActionError(null)
    try {
      await Promise.all(stay.nightIds.map((id) => api.hotels.deleteRooming(id)))
      await fetchData()
    } catch (err) {
      console.error('Failed to delete stay', err)
      setActionError(err instanceof Error ? `Échec de la suppression : ${err.message}` : "Échec de la suppression du séjour. Réessayez.")
    } finally {
      setDeletingStayKey(null)
    }
  }

  const withoutHotel = masterRows.filter(r => !r.has_hotel)

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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
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
          <KPICard
            label="Sans hébergement"
            value={withoutHotel.length}
            icon={<UserX className="h-5 w-5" />}
            accentColor="var(--color-danger)"
            onClick={() => setShowMissing(v => !v)}
            active={showMissing}
          />
        </div>

        {/* Concerned participants: those without any hotel night (§11) */}
        {showMissing && (
          <ConcernedParticipants
            rows={withoutHotel}
            title="Participants sans hébergement"
            action="Action recommandée : vérifier la rooming list et attribuer une chambre."
            emptyText="Tous les participants ont un hébergement."
            locale={locale}
            eventId={eventId}
            quickActionLabel="Ajouter hébergement"
            onQuickAction={handleQuickAddHotel}
          />
        )}

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
                disabled={addingHotel}
                className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {addingHotel ? '…' : t('addHotelButton')}
              </button>
            </form>
          </div>

          {/* Assign Night */}
          <div id="assign-night-form" className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm scroll-mt-24">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              {t('assignNightTitle')}
            </h2>
            <form onSubmit={handleAssignRoom} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="relative md:col-span-2">
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('participantLabel')}
                </label>
                <input
                  type="text"
                  value={participantSearch}
                  onChange={(e) => {
                    setParticipantSearch(e.target.value)
                    setAssignParticipantId('')
                    setShowParticipantDropdown(true)
                  }}
                  onFocus={() => setShowParticipantDropdown(true)}
                  onBlur={() => setTimeout(() => setShowParticipantDropdown(false), 150)}
                  placeholder={t('participantSearchPlaceholder')}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                />
                {showParticipantDropdown && (
                  <div className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border bg-white shadow-lg">
                    <button
                      type="button"
                      onMouseDown={() => {
                        setAssignParticipantId('all')
                        setParticipantSearch('Tous les participants (en bloc)')
                        setShowParticipantDropdown(false)
                      }}
                      className="block w-full px-3 py-2 text-left text-sm font-semibold hover:bg-slate-50 border-b"
                    >
                      Tous les participants (en bloc)
                    </button>
                    {(() => {
                      const q = participantSearch.trim().toLowerCase()
                      const matches = participants.filter(p =>
                        `${p.first_name} ${p.last_name}`.toLowerCase().includes(q)
                      ).slice(0, 50)
                      if (matches.length === 0) {
                        return (
                          <div className="px-3 py-2 text-sm text-[var(--color-text-secondary)]">
                            Aucun participant trouvé.
                          </div>
                        )
                      }
                      return matches.map(p => (
                        <button
                          key={p.id}
                          type="button"
                          onMouseDown={() => {
                            setAssignParticipantId(p.id)
                            setParticipantSearch(`${p.first_name} ${p.last_name}`)
                            setShowParticipantDropdown(false)
                          }}
                          className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                        >
                          {p.first_name} {p.last_name}
                        </button>
                      ))
                    })()}
                  </div>
                )}
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
                  {t('checkInLabel')}
                </label>
                <input
                  type="date"
                  value={assignCheckIn}
                  onChange={(e) => setAssignCheckIn(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('checkOutLabel')}
                </label>
                <input
                  type="date"
                  value={assignCheckOut}
                  min={assignCheckIn}
                  onChange={(e) => setAssignCheckOut(e.target.value)}
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
                  disabled={assigningRoom}
                  className="w-full rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {assigningRoom ? '…' : t('confirmAssignment')}
                </button>
              </div>
            </form>
          </div>
        </div>

        {actionError && (
          <div className="flex items-center gap-2 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-4 py-2.5 text-sm text-[var(--color-danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

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
                  <th className="p-4">{t('tableStay')}</th>
                  <th className="p-4 text-center">{t('tableNights')}</th>
                  <th className="p-4">{t('tableRoomType')}</th>
                  <th className="p-4">{t('tableStatus')}</th>
                  <th className="p-4 text-right">{t('tableActions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y text-[var(--color-text-primary)]">
                {loading ? (
                  <TableSkeleton cols={7} rows={4} />
                ) : stays.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-[var(--color-text-secondary)]">
                      {t('noAssignments')}
                    </td>
                  </tr>
                ) : (
                  stays.map((stay) => (
                    <tr key={stay.key} className="hover:bg-slate-50 transition-colors">
                      <td className="p-4 font-semibold">{stay.participant_name || 'N/A'}</td>
                      <td className="p-4">{stay.hotel_name || 'N/A'}</td>
                      <td className="p-4 whitespace-nowrap">
                        {stay.nights > 1
                          ? `${fmtDate(stay.firstNight)} - ${fmtDate(stay.lastNight)}`
                          : fmtDate(stay.firstNight)}
                      </td>
                      <td className="p-4 text-center">
                        <span className="inline-flex items-center justify-center min-w-[1.75rem] rounded-full bg-[var(--color-accent-light)] px-2 py-0.5 text-xs font-bold text-[var(--color-accent)]">
                          {stay.nights}
                        </span>
                      </td>
                      <td className="p-4">
                        {stay.room_type === 'single' ? t('roomTypeSingle') :
                         stay.room_type === 'double' ? t('roomTypeDouble') :
                         stay.room_type === 'twin' ? t('roomTypeTwin') :
                         stay.room_type === 'suite' ? t('roomTypeSuite') : stay.room_type}
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          stay.status === 'confirmed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}>
                          {stay.status === 'confirmed' ? t('statusConfirmed') : t('statusRequested')}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <button
                          onClick={() => handleDeleteStay(stay)}
                          disabled={deletingStayKey !== null}
                          className="text-rose-600 hover:text-rose-900 font-semibold text-xs transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {deletingStayKey === stay.key ? '…' : t('deleteButton')}
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
