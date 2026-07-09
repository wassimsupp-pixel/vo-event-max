'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Check, Calendar, Plus, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { useRouter, useParams } from 'next/navigation'

interface Event {
  id: string
  name: string
  location_city?: string
  location_country?: string
  start_date?: string
}

interface EventSelectorProps {
  currentEventId: string
}

export function EventSelector({ currentEventId }: EventSelectorProps) {
  const [open, setOpen] = useState(false)
  const [events, setEvents] = useState<Event[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [newEventName, setNewEventName] = useState('')
  const [creatingLoading, setCreatingLoading] = useState(false)
  const [loading, setLoading] = useState(true)

  const router = useRouter()
  const params = useParams()
  const locale = (params.locale as string) || 'fr'

  // Load events
  useEffect(() => {
    async function loadEvents() {
      try {
        const data = await api.events.list()
        setEvents(data)
      } catch (err) {
        console.error('Failed to load events:', err)
        // Fallback to seeded event if database/network has issues
        setEvents([
          {
            id: '00000000-0000-0000-0000-000000000003',
            name: 'LivaNova — Barcelona Summit 2025',
            location_city: 'Barcelone',
            location_country: 'Espagne',
            start_date: '2025-11-10',
          },
        ])
      } finally {
        setLoading(false)
      }
    }
    loadEvents()
  }, [])

  const currentEvent = events.find((e) => e.id === currentEventId) ?? {
    id: currentEventId,
    name: 'LivaNova — Barcelona Summit 2025',
  }

  const handleSwitch = (eventId: string) => {
    router.push(`/${locale}/events/${eventId}/dashboard`)
    setOpen(false)
  }

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newEventName.trim()) return

    setCreatingLoading(true)
    try {
      const newEvent = await api.events.create(newEventName.trim())
      setEvents((prev) => [...prev, newEvent])
      setIsCreating(false)
      setNewEventName('')
      
      // Switch automatically to the newly created event dashboard
      router.push(`/${locale}/events/${newEvent.id}/dashboard`)
      setOpen(false)
    } catch (err) {
      console.error('Failed to create event:', err)
      alert('Erreur lors de la création de l\'événement. Veuillez réessayer.')
    } finally {
      setCreatingLoading(false)
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-3 py-2',
          'text-sm font-medium text-[var(--color-text-primary)] transition-all',
          'hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-light)]',
          open && 'border-[var(--color-accent)] bg-[var(--color-accent-light)]'
        )}
      >
        <Calendar className="h-4 w-4 text-[var(--color-accent)]" />
        <span className="max-w-[200px] truncate">{currentEvent.name}</span>
        <ChevronDown
          className={cn(
            'h-4 w-4 text-[var(--color-text-secondary)] transition-transform',
            open && 'rotate-180'
          )}
        />
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />

          {/* Dropdown */}
          <div
            className="absolute left-0 top-full z-20 mt-1.5 w-[280px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white"
            style={{ boxShadow: 'var(--shadow-dropdown)' }}
          >
            <div className="border-b border-[var(--color-border)] px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                Événements
              </p>
            </div>
            
            <ul className="max-h-[240px] overflow-y-auto p-1">
              {loading ? (
                <li className="flex items-center justify-center py-4 text-xs text-[var(--color-text-secondary)]">
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  Chargement...
                </li>
              ) : (
                events.map((event) => (
                  <li key={event.id}>
                    <button
                      onClick={() => handleSwitch(event.id)}
                      className={cn(
                        'flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors',
                        'hover:bg-[var(--color-bg-subtle)]',
                        event.id === currentEventId && 'bg-[var(--color-accent-light)]'
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                          {event.name}
                        </p>
                        {(event.location_city || event.start_date) && (
                          <p className="text-xs text-[var(--color-text-secondary)]">
                            {event.location_city || ''}
                            {event.location_city && event.start_date ? ' — ' : ''}
                            {event.start_date || ''}
                          </p>
                        )}
                      </div>
                      {event.id === currentEventId && (
                        <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-accent)]" />
                      )}
                    </button>
                  </li>
                ))
              )}
            </ul>

            {/* Create Event Form */}
            <div className="border-t border-[var(--color-border)] bg-[var(--color-bg-subtle)] p-2">
              {!isCreating ? (
                <button
                  onClick={() => setIsCreating(true)}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold text-[var(--color-accent)] hover:bg-[var(--color-accent-light)] transition-colors"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Créer un événement vierge
                </button>
              ) : (
                <form onSubmit={handleCreateEvent} className="space-y-1.5">
                  <input
                    type="text"
                    placeholder="Nom du nouvel événement..."
                    value={newEventName}
                    onChange={(e) => setNewEventName(e.target.value)}
                    className="w-full rounded border border-[var(--color-border)] bg-white px-2 py-1 text-xs outline-none focus:border-[var(--color-accent)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)]"
                    autoFocus
                    disabled={creatingLoading}
                  />
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => setIsCreating(false)}
                      className="rounded px-2 py-1 text-[10px] font-medium text-[var(--color-text-secondary)] hover:bg-gray-200 transition-colors"
                      disabled={creatingLoading}
                    >
                      Annuler
                    </button>
                    <button
                      type="submit"
                      className="flex items-center gap-1 rounded bg-[var(--color-accent)] px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-[#6B5A93] transition-colors"
                      disabled={creatingLoading || !newEventName.trim()}
                    >
                      {creatingLoading && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
                      Créer
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
