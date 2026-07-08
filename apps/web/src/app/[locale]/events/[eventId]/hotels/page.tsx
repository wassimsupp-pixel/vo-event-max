'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { Hotel, Bed, Calendar, Plus, RefreshCw, Search } from 'lucide-react'
import { api } from '@/lib/api'

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
  const [hotels, setHotels] = useState<HotelProperty[]>([])
  const [roomingList, setRoomingList] = useState<RoomingNight[]>([])
  const [participants, setParticipants] = useState<any[]>([])
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
      const hotelData = await api.hotels.list(eventId)
      setHotels(hotelData)
      
      const roomingData = await api.hotels.listRooming(eventId)
      setRoomingList(roomingData)

      const partRes = await api.participants.list(eventId, { per_page: 200 })
      setParticipants(partRes.data)
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
      await api.hotels.assignRooming(eventId, {
        participant_id: assignParticipantId,
        hotel_id: assignHotelId,
        night_date: assignDate,
        room_type: assignRoomType,
      })
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

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Hotel className="h-6 w-6 text-[var(--color-accent)]" />
              Gestion des Hôtels & Rooming List
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Gérez les hôtels officiels, l&apos;affectation des chambres et le calendrier des nuitées.
            </p>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <KPICard
            label="Hôtels configurés"
            value={hotels.length}
            icon={<Hotel className="h-5 w-5" />}
            accentColor="var(--color-accent)"
          />
          <KPICard
            label="Total nuitées allouées"
            value={roomingList.length}
            icon={<Bed className="h-5 w-5" />}
            accentColor="var(--color-success)"
          />
          <KPICard
            label="Participants avec hôtel"
            value={new Set(roomingList.map(r => r.participant_id)).size}
            icon={<Calendar className="h-5 w-5" />}
            accentColor="var(--color-cta)"
          />
        </div>

        {/* Form area */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Add Hotel Property */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              Ajouter un hôtel partenaire
            </h2>
            <form onSubmit={handleAddHotel} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Nom de l&apos;hôtel
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
                  Ville
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
                Ajouter l&apos;hôtel
              </button>
            </form>
          </div>

          {/* Assign Night */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              Allouer une nuitée
            </h2>
            <form onSubmit={handleAssignRoom} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Participant
                </label>
                <select
                  value={assignParticipantId}
                  onChange={(e) => setAssignParticipantId(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
                  required
                >
                  <option value="">Sélectionner...</option>
                  {participants.map(p => (
                    <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Hôtel
                </label>
                <select
                  value={assignHotelId}
                  onChange={(e) => setAssignHotelId(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
                  required
                >
                  <option value="">Sélectionner...</option>
                  {hotels.map(h => (
                    <option key={h.id} value={h.id}>{h.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Date
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
                  Type de Chambre
                </label>
                <select
                  value={assignRoomType}
                  onChange={(e) => setAssignRoomType(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white"
                >
                  <option value="single">Chambre Simple</option>
                  <option value="double">Chambre Double</option>
                  <option value="twin">Lits Jumeaux (Twin)</option>
                  <option value="suite">Suite</option>
                </select>
              </div>
              <div className="col-span-1 md:col-span-2">
                <button
                  type="submit"
                  className="w-full rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors"
                >
                  Confirmer l&apos;affectation
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Rooming list table */}
        <div className="flex items-center gap-2 max-w-md bg-white border rounded-lg px-3 py-2 shadow-sm">
          <Search className="h-4 w-4 text-[var(--color-text-secondary)]" />
          <input
            type="text"
            placeholder="Rechercher par passager ou hôtel..."
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
                  <th className="p-4">Participant</th>
                  <th className="p-4">Hôtel</th>
                  <th className="p-4">Date de Nuitée</th>
                  <th className="p-4">Type de Chambre</th>
                  <th className="p-4">Statut</th>
                  <th className="p-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y text-[var(--color-text-primary)]">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-[var(--color-text-secondary)]">
                      Chargement de la Rooming List...
                    </td>
                  </tr>
                ) : filteredRooming.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-[var(--color-text-secondary)]">
                      Aucune affectation de chambre enregistrée.
                    </td>
                  </tr>
                ) : (
                  filteredRooming.map((room) => (
                    <tr key={room.id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-4 font-semibold">{room.participant_name || 'N/A'}</td>
                      <td className="p-4">{room.hotel_name || 'N/A'}</td>
                      <td className="p-4 font-mono text-xs">{room.night_date}</td>
                      <td className="p-4 capitalize">{room.room_type}</td>
                      <td className="p-4">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          room.status === 'confirmed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}>
                          {room.status === 'confirmed' ? 'Confirmé' : 'Demandé'}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <button
                          onClick={() => handleDeleteRooming(room.id)}
                          className="text-rose-600 hover:text-rose-900 font-semibold text-xs transition-colors"
                        >
                          Supprimer
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
