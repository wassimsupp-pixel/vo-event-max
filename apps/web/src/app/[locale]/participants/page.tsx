'use client'

import React, { useState } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Search, User, Calendar, CheckSquare, Eye } from 'lucide-react'
import { api } from '@/lib/api'

interface HistoryItem {
  event_name: string
  event_date?: string
  dietary_requirements?: string
}

interface ParticipantHistory {
  email: string
  full_name: string
  history: HistoryItem[]
}

export default function GlobalParticipantsPage() {
  const { locale } = useParams() as { locale: string }
  const [emailQuery, setEmailQuery] = useState('')
  const [results, setResults] = useState<ParticipantHistory[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!emailQuery.trim()) return
    try {
      setLoading(true)
      setSearched(true)
      const data = await api.globalParticipants.getHistory(emailQuery)
      setResults(data)
    } catch (err) {
      console.error('Failed to query global participant history', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppLayout eventId="global" locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <User className="h-6 w-6 text-[var(--color-accent)]" />
              Recherche Transversale de Participants
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Retrouvez l&apos;historique de présence et les préférences alimentaires d&apos;un invité sur l&apos;ensemble de ses participations.
            </p>
          </div>
        </div>

        {/* Search Form */}
        <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm max-w-xl">
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 border rounded-lg px-3 py-2 bg-slate-50">
              <Search className="h-4 w-4 text-[var(--color-text-secondary)]" />
              <input
                type="email"
                placeholder="Entrez l'adresse email du participant..."
                value={emailQuery}
                onChange={(e) => setEmailQuery(e.target.value)}
                className="w-full text-sm outline-none bg-transparent"
                required
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-colors disabled:opacity-50"
            >
              Rechercher
            </button>
          </form>
        </div>

        {/* Results */}
        {loading ? (
          <p className="text-sm text-[var(--color-text-secondary)]">Recherche de l&apos;historique en cours...</p>
        ) : searched && results.length === 0 ? (
          <div className="rounded-[var(--radius-card)] border border-dashed p-8 text-center text-[var(--color-text-secondary)] bg-white max-w-xl">
            Aucun historique trouvé pour cet email dans l&apos;organisation.
          </div>
        ) : (
          results.map((profile) => (
            <div key={profile.email} className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Profile Card */}
              <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm h-fit">
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-12 w-12 rounded-full bg-[var(--color-accent-light)] text-[var(--color-accent)] flex items-center justify-center font-bold text-lg">
                    {profile.full_name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div>
                    <h3 className="font-bold text-[var(--color-text-primary)] text-lg">{profile.full_name}</h3>
                    <p className="text-xs text-[var(--color-text-secondary)]">{profile.email}</p>
                  </div>
                </div>
              </div>

              {/* Event Timeline History */}
              <div className="lg:col-span-2 rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
                <h3 className="font-bold text-[var(--color-text-primary)] mb-6 flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-[var(--color-accent)]" />
                  Historique de présence aux événements
                </h3>
                <div className="relative border-l border-slate-200 ml-3 pl-6 space-y-8">
                  {profile.history.map((event, idx) => (
                    <div key={idx} className="relative">
                      {/* Marker */}
                      <span className="absolute -left-[31px] top-1.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-[var(--color-accent)] bg-white">
                        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
                      </span>
                      
                      <div>
                        <h4 className="font-bold text-[var(--color-text-primary)]">{event.event_name}</h4>
                        {event.event_date && (
                          <p className="text-[10px] text-gray-400 font-mono mt-0.5">
                            Début de l&apos;événement :{' '}
                            {new Date(event.event_date).toLocaleDateString('fr-FR', {
                              dateStyle: 'medium',
                            })}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-2">
                          <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-800 border border-emerald-200">
                            Présence confirmée
                          </span>
                          {event.dietary_requirements ? (
                            <span className="inline-flex items-center rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-800 border border-amber-200">
                              Préférence : {event.dietary_requirements}
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-500 border border-slate-200">
                              Aucune restriction
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </AppLayout>
  )
}
