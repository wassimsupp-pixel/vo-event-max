'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Check, Calendar, Plus, Loader2, Folder, Briefcase } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { useRouter, useParams } from 'next/navigation'

interface Event {
  id: string
  project_id: string
  name: string
  location_city?: string
  location_country?: string
  start_date?: string
}

interface Project {
  id: string
  name: string
  client_name: string
}

interface EventSelectorProps {
  currentEventId: string
}

export function EventSelector({ currentEventId }: EventSelectorProps) {
  const [open, setOpen] = useState(false)
  const [events, setEvents] = useState<Event[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  // Creation state
  const [isCreating, setIsCreating] = useState(false)
  const [creationMode, setCreationMode] = useState<'existing' | 'new'>('existing')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [newEventName, setNewEventName] = useState('')
  const [newProjectName, setNewProjectName] = useState('')
  const [newClientName, setNewClientName] = useState('')
  const [creatingLoading, setCreatingLoading] = useState(false)

  const router = useRouter()
  const params = useParams()
  const locale = (params.locale as string) || 'fr'

  // Load events and projects
  useEffect(() => {
    async function loadData() {
      try {
        const [eventsData, projectsData] = await Promise.all([
          api.events.list(),
          api.projects.list(),
        ])
        setEvents(eventsData)
        setProjects(projectsData)
        if (projectsData.length > 0) {
          setSelectedProjectId(projectsData[0].id)
        }
      } catch (err) {
        console.error('Failed to load events/projects:', err)
        // Fallbacks
        const fallbackProj = { id: '00000000-0000-0000-0000-000000000002', name: 'Barcelona Summit', client_name: 'LivaNova' }
        setProjects([fallbackProj])
        setEvents([
          {
            id: '00000000-0000-0000-0000-000000000003',
            project_id: '00000000-0000-0000-0000-000000000002',
            name: 'LivaNova — Barcelona Summit 2025',
            location_city: 'Barcelone',
            location_country: 'Espagne',
            start_date: '2025-11-10',
          },
        ])
        setSelectedProjectId(fallbackProj.id)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const currentEvent = events.find((e) => e.id === currentEventId) ?? {
    id: currentEventId,
    name: 'Chargement de l\'événement...',
  }

  const handleSwitch = (eventId: string) => {
    router.push(`/${locale}/events/${eventId}/dashboard`)
    setOpen(false)
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newEventName.trim()) return

    setCreatingLoading(true)
    try {
      let targetProjectId = selectedProjectId

      if (creationMode === 'new') {
        if (!newProjectName.trim() || !newClientName.trim()) {
          alert('Veuillez remplir le nom du projet et le nom du client.')
          setCreatingLoading(false)
          return
        }
        // 1. Create the new project first
        const newProj = await api.projects.create({
          name: newProjectName.trim(),
          client_name: newClientName.trim(),
        })
        setProjects((prev) => [...prev, newProj])
        targetProjectId = newProj.id
      }

      // 2. Create the event under that project
      const newEvent = await api.events.create(newEventName.trim(), targetProjectId)
      setEvents((prev) => [...prev, newEvent])
      
      // Reset form
      setIsCreating(false)
      setNewEventName('')
      setNewProjectName('')
      setNewClientName('')
      
      // Switch automatically to the newly created event dashboard
      router.push(`/${locale}/events/${newEvent.id}/dashboard`)
      setOpen(false)
    } catch (err) {
      console.error('Failed to create project/event:', err)
      const msg = err instanceof Error ? err.message : String(err)
      alert(`Erreur lors de la création : ${msg}`)
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
        <span className="max-w-[220px] truncate">{currentEvent.name}</span>
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
            className="absolute left-0 top-full z-20 mt-1.5 w-[320px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-xl"
            style={{ boxShadow: 'var(--shadow-dropdown)' }}
          >
            {!isCreating ? (
              <>
                <div className="border-b border-[var(--color-border)] px-3 py-2 bg-slate-50 flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)]">
                    Projets & Événements
                  </span>
                </div>

                <div className="max-h-[300px] overflow-y-auto p-2 space-y-3">
                  {loading ? (
                    <div className="flex items-center justify-center py-6 text-xs text-[var(--color-text-secondary)]">
                      <Loader2 className="mr-1.5 h-4 w-4 animate-spin text-[var(--color-accent)]" />
                      Chargement...
                    </div>
                  ) : projects.length === 0 ? (
                    <div className="text-center py-4 text-xs text-[var(--color-text-secondary)]">
                      Aucun projet trouvé.
                    </div>
                  ) : (
                    projects.map((project) => {
                      const projectEvents = events.filter((e) => e.project_id === project.id)
                      return (
                        <div key={project.id} className="space-y-1">
                          {/* Project Header */}
                          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-50 border border-slate-100 text-xs font-semibold text-[var(--color-text-primary)]">
                            <Briefcase className="h-3.5 w-3.5 text-[var(--color-accent)]" />
                            <span className="truncate">{project.client_name} — {project.name}</span>
                          </div>

                          {/* Events under this project */}
                          <div className="pl-2 space-y-0.5">
                            {projectEvents.length === 0 ? (
                              <p className="text-[11px] text-[var(--color-text-secondary)] italic px-3 py-1">
                                Aucun événement dans ce projet.
                              </p>
                            ) : (
                              projectEvents.map((event) => (
                                <button
                                  key={event.id}
                                  onClick={() => handleSwitch(event.id)}
                                  className={cn(
                                    'flex w-full items-center justify-between rounded-md px-3 py-1.5 text-left transition-colors',
                                    'hover:bg-[var(--color-bg-subtle)]',
                                    event.id === currentEventId && 'bg-[var(--color-accent-light)] font-semibold text-[var(--color-accent)]'
                                  )}
                                >
                                  <span className="truncate text-xs text-[var(--color-text-primary)]">
                                    {event.name}
                                  </span>
                                  {event.id === currentEventId && (
                                    <Check className="h-3.5 w-3.5 text-[var(--color-accent)] flex-shrink-0" />
                                  )}
                                </button>
                              ))
                            )}
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>

                {/* Create Event Trigger */}
                <div className="border-t border-[var(--color-border)] bg-[var(--color-bg-subtle)] p-2">
                  <button
                    onClick={() => setIsCreating(true)}
                    className="flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-bold text-[var(--color-accent)] hover:bg-[var(--color-accent-light)] transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Créer un nouveau projet / événement
                  </button>
                </div>
              </>
            ) : (
              /* Create Form */
              <div className="p-3 space-y-3">
                <div className="flex items-center justify-between border-b pb-2">
                  <span className="text-xs font-bold text-[var(--color-text-primary)]">
                    Création Projet / Événement
                  </span>
                </div>

                {/* Mode toggle */}
                <div className="grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 text-xs">
                  <button
                    type="button"
                    onClick={() => setCreationMode('existing')}
                    className={cn(
                      'rounded py-1 text-center font-medium transition-colors',
                      creationMode === 'existing' ? 'bg-white shadow-sm text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'
                    )}
                  >
                    Projet existant
                  </button>
                  <button
                    type="button"
                    onClick={() => setCreationMode('new')}
                    className={cn(
                      'rounded py-1 text-center font-medium transition-colors',
                      creationMode === 'new' ? 'bg-white shadow-sm text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'
                    )}
                  >
                    Nouveau projet
                  </button>
                </div>

                <form onSubmit={handleCreate} className="space-y-2.5">
                  {creationMode === 'existing' ? (
                    <div>
                      <label className="block text-[10px] font-semibold text-[var(--color-text-secondary)] mb-1">
                        Sélectionner le projet
                      </label>
                      <select
                        value={selectedProjectId}
                        onChange={(e) => setSelectedProjectId(e.target.value)}
                        className="w-full rounded border border-[var(--color-border)] px-2 py-1 text-xs outline-none bg-white focus:border-[var(--color-accent)] text-[var(--color-text-primary)]"
                        disabled={creatingLoading}
                      >
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.client_name} — {p.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <>
                      <div>
                        <label className="block text-[10px] font-semibold text-[var(--color-text-secondary)] mb-1">
                          Nom du client
                        </label>
                        <input
                          type="text"
                          placeholder="Ex: LivaNova, Medtronic..."
                          value={newClientName}
                          onChange={(e) => setNewClientName(e.target.value)}
                          className="w-full rounded border border-[var(--color-border)] px-2 py-1 text-xs outline-none focus:border-[var(--color-accent)] text-[var(--color-text-primary)]"
                          required
                          disabled={creatingLoading}
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-semibold text-[var(--color-text-secondary)] mb-1">
                          Nom du projet
                        </label>
                        <input
                          type="text"
                          placeholder="Ex: Barcelona Summit 2025..."
                          value={newProjectName}
                          onChange={(e) => setNewProjectName(e.target.value)}
                          className="w-full rounded border border-[var(--color-border)] px-2 py-1 text-xs outline-none focus:border-[var(--color-accent)] text-[var(--color-text-primary)]"
                          required
                          disabled={creatingLoading}
                        />
                      </div>
                    </>
                  )}

                  <div>
                    <label className="block text-[10px] font-semibold text-[var(--color-text-secondary)] mb-1">
                      Nom de l&apos;événement
                    </label>
                    <input
                      type="text"
                      placeholder="Ex: Kick-off meeting, Séminaire..."
                      value={newEventName}
                      onChange={(e) => setNewEventName(e.target.value)}
                      className="w-full rounded border border-[var(--color-border)] px-2 py-1 text-xs outline-none focus:border-[var(--color-accent)] text-[var(--color-text-primary)]"
                      required
                      disabled={creatingLoading}
                    />
                  </div>

                  <div className="flex justify-end gap-1.5 border-t pt-2 mt-2">
                    <button
                      type="button"
                      onClick={() => setIsCreating(false)}
                      className="rounded px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-slate-100 transition-colors"
                      disabled={creatingLoading}
                    >
                      Annuler
                    </button>
                    <button
                      type="submit"
                      className="flex items-center gap-1 rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-semibold text-white hover:bg-[var(--color-accent)]/90 transition-colors"
                      disabled={creatingLoading || !newEventName.trim()}
                    >
                      {creatingLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                      Créer
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
