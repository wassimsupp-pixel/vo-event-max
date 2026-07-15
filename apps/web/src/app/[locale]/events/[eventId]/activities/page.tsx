'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { KPICard } from '@/components/ui/KPICard'
import { TableSkeleton } from '@/components/ui/TableSkeleton'
import { Compass, Users, Plus, Calendar, Search, Sparkles, Loader2, ImagePlus } from 'lucide-react'
import { api, type ParticipantLookupItem } from '@/lib/api'

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
  const t = useTranslations('activities')
  const [activities, setActivities] = useState<Activity[]>([])
  const [selectedActivity, setSelectedActivity] = useState<Activity | null>(null)
  const [roster, setRoster] = useState<ParticipantRegistration[]>([])
  const [participants, setParticipants] = useState<ParticipantLookupItem[]>([])
  const [loading, setLoading] = useState(true)
  const [rosterLoading, setRosterLoading] = useState(false)

  // Form states
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [newCapacity, setNewCapacity] = useState(50)
  const [newDateTime, setNewDateTime] = useState('2025-11-12T14:00')

  // Poster/flyer AI detection
  const [posterAnalyzing, setPosterAnalyzing] = useState(false)
  const [posterMsg, setPosterMsg] = useState<string | null>(null)

  const [registerPartId, setRegisterPartId] = useState('')

  const handlePosterUpload = async (file: File) => {
    setPosterAnalyzing(true)
    setPosterMsg(null)
    try {
      const res = await api.posters.analyze(eventId, file)
      if (res.error) { setPosterMsg(res.error); return }
      const f = res.fields || {}
      if (f.title) setNewName(String(f.title))
      if (f.location) setNewLocation(String(f.location))
      const cap = parseInt(String(f.capacity ?? '').replace(/\D/g, ''), 10)
      if (!Number.isNaN(cap) && cap > 0) setNewCapacity(cap)
      const parts = [f.description, f.date ? `Date : ${f.date}` : '', f.time ? `Horaire : ${f.time}` : '', f.other ? `Infos : ${f.other}` : ''].filter(Boolean)
      if (parts.length) setNewDesc(parts.join('\n'))
      setPosterMsg('Informations détectées et pré-remplies. Vérifie/ajuste avant de créer.')
    } catch {
      setPosterMsg('Échec de l’analyse de l’affiche.')
    } finally {
      setPosterAnalyzing(false)
    }
  }

  const fetchActivities = async () => {
    try {
      setLoading(true)
      const [activitiesData, partList] = await Promise.all([
        api.activities.list(eventId),
        api.participants.lookup(eventId)
      ])
      setActivities(activitiesData)
      setParticipants(partList)
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
            label={t('kpiProposed')}
            value={activities.length}
            icon={<Compass className="h-5 w-5" />}
            accentColor="var(--color-accent)"
            onClick={() => document.getElementById('detail-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          />
          <KPICard
            label={t('kpiRegistered')}
            value={activities.reduce((acc, a) => acc + a.registrations_count, 0)}
            icon={<Users className="h-5 w-5" />}
            accentColor="var(--color-success)"
            onClick={() => document.getElementById('detail-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          />
          <KPICard
            label={t('kpiCapacity')}
            value={activities.reduce((acc, a) => acc + (a.capacity || 0), 0)}
            icon={<Calendar className="h-5 w-5" />}
            accentColor="var(--color-cta)"
            onClick={() => document.getElementById('detail-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Create Activity Form */}
          <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm h-fit">
            <h2 className="text-lg font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-[var(--color-accent)]" />
              {t('createTitle')}
            </h2>
            <form onSubmit={handleCreateActivity} className="flex flex-col gap-4">
              {/* AI poster/flyer detection */}
              <div className="rounded-lg border border-dashed border-[var(--color-accent)]/40 bg-[var(--color-accent-light)]/30 p-3">
                <label className={`flex items-center gap-2 text-xs font-semibold text-[var(--color-accent)] ${posterAnalyzing ? 'opacity-60' : 'cursor-pointer'}`}>
                  {posterAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                  Détecter depuis une affiche / poster (IA)
                  <input
                    type="file"
                    accept="image/*,application/pdf"
                    className="hidden"
                    disabled={posterAnalyzing}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePosterUpload(f); e.target.value = '' }}
                  />
                </label>
                <p className="mt-1 flex items-center gap-1 text-[10px] text-[var(--color-text-secondary)]">
                  <Sparkles className="h-3 w-3" /> {posterMsg || 'Dépose une affiche : l’IA détecte titre, lieu, horaires, capacité…'}
                </p>
              </div>

              <div>
                <label className="block text-sm font-semibold mb-1 text-[var(--color-text-secondary)]">
                  {t('activityName')}
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
                  {t('description')}
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
                  {t('location')}
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
                    {t('capacity')}
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
                    {t('dateTime')}
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
                {t('addActivityButton')}
              </button>
            </form>
          </div>

          {/* Activities List */}
          <div id="detail-list" className="rounded-[var(--radius-card)] border bg-white shadow-sm overflow-hidden lg:col-span-2 scroll-mt-24">
            <div className="p-6 border-b">
              <h2 className="text-lg font-bold text-[var(--color-text-primary)]">{t('activitiesListTitle')}</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                    <th className="p-4">{t('tableActivity')}</th>
                    <th className="p-4">{t('tableLocationDate')}</th>
                    <th className="p-4">{t('tableRegistrationsCapacity')}</th>
                    <th className="p-4 text-right">{t('tableAction')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-[var(--color-text-primary)]">
                  {loading ? (
                    <TableSkeleton cols={4} rows={3} />
                  ) : activities.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-[var(--color-text-secondary)]">
                        {t('noActivities')}
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
                            {act.date_time ? new Date(act.date_time).toLocaleString(locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US', {
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
                            {t('viewRoster')}
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
                  {t('rosterTitle', { name: selectedActivity.name })}
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('rosterSubtitle')}
                </p>
              </div>
              <form onSubmit={handleRegister} className="flex gap-2">
                <select
                  value={registerPartId}
                  onChange={(e) => setRegisterPartId(e.target.value)}
                  className="border rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-1 focus:ring-[var(--color-accent)] bg-white w-48"
                  required
                >
                  <option value="">{t('selectParticipantPlaceholder')}</option>
                  {participants.map(p => (
                    <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>
                  ))}
                </select>
                <button
                  type="submit"
                  className="rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors"
                >
                  {t('registerButton')}
                </button>
              </form>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] font-medium">
                    <th className="p-3">{t('tableParticipant')}</th>
                    <th className="p-3">{t('tableDietary')}</th>
                    <th className="p-3">{t('tableStatus')}</th>
                    <th className="p-3 text-right">{t('tableActions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-[var(--color-text-primary)]">
                  {rosterLoading ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-[var(--color-text-secondary)]">
                        {t('loadingRoster')}
                      </td>
                    </tr>
                  ) : roster.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-[var(--color-text-secondary)]">
                        {t('noRegistered')}
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
                            {t('statusRegistered')}
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <button
                            onClick={() => handleUnregister(reg.participant_id)}
                            className="text-rose-600 hover:text-rose-900 font-semibold text-xs transition-colors"
                          >
                            {t('unregisterButton')}
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
