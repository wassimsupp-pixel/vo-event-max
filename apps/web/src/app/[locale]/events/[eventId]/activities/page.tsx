'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { Compass, Users, Plus, Calendar, Search } from 'lucide-react'
import { api } from '@/lib/api'

interface Activity {
  id: string
  name: string
  description?: string
  date_time?: string
  location?: string
  capacity?: number
  registrations_count: number
}

interface ParticipantRegistration {
  id: string
  participant_id: string
  activity_id: string
  status: string
  participant_name?: string
  dietary_requirements?: string
}

export default function ActivitiesPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const [activities, setActivities] = useState<Activity[]>([])
  const [selectedActivity, setSelectedActivity] = useState<Activity | null>(null)
  const [roster, setRoster] = useState<ParticipantRegistration[]>([])
  const [participants, setParticipants] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [rosterLoading, setRosterLoading] = useState(false)

  // Form states
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [newCapacity, setNewCapacity] = useState(50)
  const [newDateTime, setNewDateTime] = useState('2025-11-12T14:00')

  const [registerPartId, setRegisterPartId] = useState('')

  const fetchActivities = async () => {
    try {
      setLoading(true)
      const data = await api.activities.list(eventId)
      setActivities(data)
      
      const partRes = await api.participants.list(eventId, { per_page: 200 })
      setParticipants(partRes.data)
    } catch (err) {
      console.error('Failed to fetch activities', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchRoster = async (activityId: string) => {
    try {
      setRosterLoading(true)
      const data = await api.activities.listParticipants(activityId)
      setRoster(data)
    } catch (err) {
      console.error('Failed to fetch activity roster', err)
    } finally {
      setRosterLoading(false)
    }
  }

  useEffect(() => {
    fetchActivities()
  }, [eventId])

  useEffect(() => {
    if (selectedActivity) {
      fetchRoster(selectedActivity.id)
    }
  }, [selectedActivity])

  const handleCreateActivity = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName) return
    try {
      await api.activities.create(eventId, {
        name: newName,
        description: newDesc,
        location: newLocation,
        capacity: newCapacity,
        date_time: newDateTime ? `${newDateTime}:00Z` : undefined,
      })
      setNewName('')
      setNewDesc('')
      setNewLocation('')
      await fetchActivities()
    } catch (err) {
      console.error('Failed to create activity', err)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedActivity || !registerPartId) return
    try {
      await api.activities.register(selectedActivity.id, registerPartId)
      setRegisterPartId('')
      // Refresh
      await fetchActivities()
      // Update selected activity count
      const updated = await api.activities.list(eventId)
      setActivities(updated)
      const found = updated.find(a => a.id === selectedActivity.id)
      if (found) setSelectedActivity(found)
    } catch (err) {
      console.error('Failed to register participant', err)
    }
  }

  const handleUnregister = async (partId: string) => {
    if (!selectedActivity) return
    try {
      await api.activities.unregister(selectedActivity.id, partId)
      await fetchActivities()
      const updated = await api.activities.list(eventId)
      setActivities(updated)
      const found = updated.find(a => a.id === selectedActivity.id)
      if (found) setSelectedActivity(found)
    } catch (err) {
      console.error('Failed to unregister participant', err)
    }
  }

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Compass className="h-6 w-6 text-[var(--color-accent)]" />
              Activités & Dîners
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Gérez les excursions, visites guidées et attributions de tables avec suivi des régimes alimentaires.
            </p>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <KPICard
            label="Activités proposées"
            value={activities.length}
            icon={<Compass className="h-5 w-5" />}
            accentColor="var(--color-accent)"
          />
          <KPICard
            label="Inscriptions enregistrées"
            value={activities.reduce((acc, a) => acc + a.registrations_count, 0)}
            icon={<Users className="h-5 w-5" />}
            accentColor="var(--color-success)"
          />
          <KPICard
            label="Capacité totale"
            value={activities.reduce((acc, a) => acc + (a.capacity || 0), 0)}
            icon={<Calendar className="h-5 w-5" />}
            accentColor="var(--color-cta)"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Create Activity Form */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm h-fit">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              Créer une activité
            </h2>
            <form onSubmit={handleCreateActivity} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Nom de l&apos;activité
                </label>
                <input
                  type="text"
                  placeholder="Ex. Dîner Gala Restaurant Barceloneta"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Description
                </label>
                <textarea
                  placeholder="Ex. Menu 3 services au bord de l'eau"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)] h-20"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  Lieu
                </label>
                <input
                  type="text"
                  placeholder="Ex. Port Vell, Barcelona"
                  value={newLocation}
                  onChange={(e) => setNewLocation(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                    Capacité
                  </label>
                  <input
                    type="number"
                    value={newCapacity}
                    onChange={(e) => setNewCapacity(Number(e.target.value))}
                    className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                    Date & Heure
                  </label>
                  <input
                    type="datetime-local"
                    value={newDateTime}
                    onChange={(e) => setNewDateTime(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                  />
                </div>
              </div>
              <button
                type="submit"
                className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors"
              >
                Ajouter l&apos;activité
              </button>
            </form>
          </div>

          {/* Activities List */}
          <div className="rounded-[var(--radius-card)] border bg-white shadow-sm overflow-hidden lg:col-span-2">
            <div className="p-6 border-b">
              <h2 className="text-lg font-bold text-[var(--color-text-primary)]">Liste des Activités</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                    <th className="p-4">Activité</th>
                    <th className="p-4">Lieu / Date</th>
                    <th className="p-4">Inscrits / Capacité</th>
                    <th className="p-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-[var(--color-text-primary)]">
                  {loading ? (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-[var(--color-text-secondary)]">
                        Chargement des activités...
                      </td>
                    </tr>
                  ) : activities.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-[var(--color-text-secondary)]">
                        Aucune activité configurée.
                      </td>
                    </tr>
                  ) : (
                    activities.map((act) => (
                      <tr
                        key={act.id}
                        className={`hover:bg-slate-50 transition-colors cursor-pointer ${
                          selectedActivity?.id === act.id ? 'bg-[var(--color-accent-light)]/30' : ''
                        }`}
                        onClick={() => setSelectedActivity(act)}
                      >
                        <td className="p-4">
                          <div className="font-bold">{act.name}</div>
                          <div className="text-xs text-[var(--color-text-secondary)]">{act.description}</div>
                        </td>
                        <td className="p-4">
                          <div className="text-xs font-semibold">{act.location || '-'}</div>
                          <div className="text-[10px] text-gray-400">
                            {act.date_time ? new Date(act.date_time).toLocaleString('fr-FR', {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            }) : '-'}
                          </div>
                        </td>
                        <td className="p-4">
                          <span className="font-semibold text-[var(--color-accent)]">
                            {act.registrations_count}
                          </span>{' '}
                          / {act.capacity || '∞'}
                        </td>
                        <td className="p-4 text-right">
                          <button className="text-[var(--color-accent)] font-semibold text-xs transition-colors">
                            Voir le Roster ➔
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

        {/* Selected Activity Roster */}
        {selectedActivity && (
          <div className="rounded-[var(--radius-card)] border bg-white shadow-sm p-6 mt-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center border-b pb-4 mb-4 gap-4">
              <div>
                <h3 className="text-lg font-bold text-[var(--color-text-primary)]">
                  Roster des inscrits : {selectedActivity.name}
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  Gérez la liste de présence pour cette excursion ou ce dîner.
                </p>
              </div>
              <form onSubmit={handleRegister} className="flex gap-2">
                <select
                  value={registerPartId}
                  onChange={(e) => setRegisterPartId(e.target.value)}
                  className="border rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white w-48"
                  required
                >
                  <option value="">Sélectionner un participant...</option>
                  {participants.map(p => (
                    <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>
                  ))}
                </select>
                <button
                  type="submit"
                  className="rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors"
                >
                  Inscrire
                </button>
              </form>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                    <th className="p-3">Participant</th>
                    <th className="p-3">Régime Alimentaire</th>
                    <th className="p-3">Statut</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-[var(--color-text-primary)]">
                  {rosterLoading ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-[var(--color-text-secondary)]">
                        Chargement des inscrits...
                      </td>
                    </tr>
                  ) : roster.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-[var(--color-text-secondary)]">
                        Aucun inscrit pour le moment.
                      </td>
                    </tr>
                  ) : (
                    roster.map((reg) => (
                      <tr key={reg.id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-3 font-semibold">{reg.participant_name}</td>
                        <td className="p-3">
                          {reg.dietary_requirements ? (
                            <span className="inline-flex items-center rounded bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800 border border-amber-200">
                              {reg.dietary_requirements}
                            </span>
                          ) : (
                            <span className="text-gray-400 text-xs">-</span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Inscrit
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <button
                            onClick={() => handleUnregister(reg.participant_id)}
                            className="text-rose-600 hover:text-rose-900 font-semibold text-xs transition-colors"
                          >
                            Désinscrire
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
