'use client'

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Check, Calendar, Plus, Loader2, Folder, Briefcase, AlertTriangle, RotateCw, Trash2 } from 'lucide-react'
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
  const [loadError, setLoadError] = useState(false)

  // Deletion (inline confirmation) state
  const [pendingDelete, setPendingDelete] = useState<{ kind: 'event' | 'project'; id: string; name: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

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
  const t = useTranslations('eventSelector')

  // Load events and projects. Extracted so the "retry" action can re-invoke it.
  const loadData = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
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
      // No silent fake-data fallback: surface the failure so the real error is visible
      // and the user isn't misled into thinking the wrong event is loaded.
      console.error('Failed to load events/projects:', err)
      setEvents([])
      setProjects([])
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Validate the URL-provided currentEventId against the real event list.
  // Undefined while loading, when the load failed, or when the id is unknown.
  const currentEvent = events.find((e) => e.id === currentEventId)

  const handleSwitch = (eventId: string) => {
    router.push(`/${locale}/events/${eventId}/dashboard`)
    setOpen(false)
  }

  // After deleting the current event/project, move the user to a remaining
  // event (or refresh so the "event not found" state resolves).
  const navigateAfterDeletion = (remaining: Event[]) => {
    setOpen(false)
    if (remaining.length > 0) {
      router.push(`/${locale}/events/${remaining[0].id}/dashboard`)
    } else {
      router.refresh()
    }
  }

  // Inline confirmation flow (no native window.confirm, real error surfaced).
  const performDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    setActionError(null)
    try {
      if (pendingDelete.kind === 'event') {
        await api.events.delete(pendingDelete.id)
        const remaining = events.filter((x) => x.id !== pendingDelete.id)
        setEvents(remaining)
        if (pendingDelete.id === currentEventId) navigateAfterDeletion(remaining)
      } else {
        await api.projects.delete(pendingDelete.id)
        const deletedIds = new Set(
          events.filter((ev) => ev.project_id === pendingDelete.id).map((ev) => ev.id)
        )
        const remaining = events.filter((ev) => ev.project_id !== pendingDelete.id)
        setProjects((prev) => prev.filter((p) => p.id !== pendingDelete.id))
        setEvents(remaining)
        if (deletedIds.has(currentEventId)) navigateAfterDeletion(remaining)
      }
      setPendingDelete(null)
    } catch (err) {
      console.error('Delete failed:', err)
      setActionError(err instanceof Error ? err.message : t('deleteError'))
    } finally {
      setDeleting(false)
    }
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
          'flex items-center gap-2 rounded-lg border bg-white px-3 py-2',
          'text-sm font-medium text-[var(--color-text-primary)] transition-all',
          loadError
            ? 'border-[var(--color-danger)] hover:bg-[var(--color-danger-light)]'
            : 'border-[var(--color-border)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-light)]',
          open && !loadError && 'border-[var(--color-accent)] bg-[var(--color-accent-light)]',
          open && loadError && 'bg-[var(--color-danger-light)]'
        )}
      >
        {loading ? (
          // Skeleton while the current event is being resolved
          <>
            <Calendar className="h-4 w-4 text-[var(--color-text-secondary)]" />
            <span className="h-4 w-[160px] animate-pulse rounded bg-[var(--color-border)]" aria-hidden />
            <span className="sr-only">{t('loadingEvent')}</span>
          </>
        ) : loadError ? (
          <>
            <AlertTriangle className="h-4 w-4 text-[var(--color-danger)]" />
            <span className="max-w-[220px] truncate text-[var(--color-danger)]">{t('loadError')}</span>
          </>
        ) : currentEvent ? (
          <>
            <Calendar className="h-4 w-4 text-[var(--color-accent)]" />
            <span className="max-w-[220px] truncate">{currentEvent.name}</span>
          </>
        ) : (
          <>
            <AlertTriangle className="h-4 w-4 text-[var(--color-warning)]" />
            <span className="max-w-[220px] truncate text-[var(--color-warning)]">{t('eventNotFound')}</span>
          </>
        )}
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
                {pendingDelete && (
                  <div className="border-b border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] p-3 space-y-2">
                    <p className="text-xs font-medium text-[var(--color-text-primary)]">
                      {pendingDelete.kind === 'event'
                        ? t('confirmDeleteEvent', { name: pendingDelete.name })
                        : t('confirmDeleteProject', { name: pendingDelete.name })}
                    </p>
                    {actionError && (
                      <p className="text-xs font-semibold text-[var(--color-danger)] break-words">{actionError}</p>
                    )}
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => { setPendingDelete(null); setActionError(null) }}
                        disabled={deleting}
                        className="rounded px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-white/70 transition-colors disabled:opacity-50"
                      >
                        Annuler
                      </button>
                      <button
                        type="button"
                        onClick={performDelete}
                        disabled={deleting}
                        className="flex items-center gap-1 rounded bg-[var(--color-danger)] px-3 py-1 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60"
                      >
                        {deleting && <Loader2 className="h-3 w-3 animate-spin" />}
                        Supprimer
                      </button>
                    </div>
                  </div>
                )}
                <div className="border-b border-[var(--color-border)] px-3 py-2 bg-slate-50 flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)]">
                    {t('projectsAndEvents')}
                  </span>
                </div>

                <div className="max-h-[300px] overflow-y-auto p-2 space-y-3">
                  {loading ? (
                    <div className="flex items-center justify-center py-6 text-xs text-[var(--color-text-secondary)]">
                      <Loader2 className="mr-1.5 h-4 w-4 animate-spin text-[var(--color-accent)]" />
                      {t('loading')}
                    </div>
                  ) : loadError ? (
                    <div className="flex flex-col items-center gap-2.5 py-5 px-3 text-center">
                      <AlertTriangle className="h-6 w-6 text-[var(--color-danger)]" />
                      <p className="text-xs font-medium text-[var(--color-danger)]">{t('loadErrorDetail')}</p>
                      <button
                        onClick={() => loadData()}
                        className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-primary)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-light)] transition-colors"
                      >
                        <RotateCw className="h-3.5 w-3.5" />
                        {t('retry')}
                      </button>
                    </div>
                  ) : projects.length === 0 ? (
                    <div className="text-center py-4 text-xs text-[var(--color-text-secondary)]">
                      {t('noProjects')}
                    </div>
                  ) : (
                    projects.map((project) => {
                      const projectEvents = events.filter((e) => e.project_id === project.id)
                      return (
                        <div key={project.id} className="space-y-1">
                          {/* Project Header */}
                          <div className="group/proj flex items-center gap-1.5 px-2 py-1 rounded bg-slate-50 border border-slate-100 text-xs font-semibold text-[var(--color-text-primary)]">
                            <Briefcase className="h-3.5 w-3.5 text-[var(--color-accent)] flex-shrink-0" />
                            <span className="truncate flex-1">{project.client_name} — {project.name}</span>
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); setActionError(null); setPendingDelete({ kind: 'project', id: project.id, name: project.name }) }}
                              title={t('deleteProject')}
                              aria-label={t('deleteProject')}
                              className="flex-shrink-0 rounded p-1 text-[var(--color-text-secondary)] hover:bg-[var(--color-danger-light)] hover:text-[var(--color-danger)] transition-colors"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>

                          {/* Events under this project */}
                          <div className="pl-2 space-y-0.5">
                            {projectEvents.length === 0 ? (
                              <p className="text-[11px] text-[var(--color-text-secondary)] italic px-3 py-1">
                                {t('noEventsInProject')}
                              </p>
                            ) : (
                              projectEvents.map((event) => (
                                <div key={event.id} className="group/evt flex items-center gap-0.5">
                                  <button
                                    onClick={() => handleSwitch(event.id)}
                                    className={cn(
                                      'flex min-w-0 flex-1 items-center justify-between rounded-md px-3 py-1.5 text-left transition-colors',
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
                                  <button
                                    type="button"
                                    onClick={(e) => { e.stopPropagation(); setActionError(null); setPendingDelete({ kind: 'event', id: event.id, name: event.name }) }}
                                    title={t('deleteEvent')}
                                    aria-label={t('deleteEvent')}
                                    className="flex-shrink-0 rounded-md p-1.5 text-[var(--color-text-secondary)] hover:bg-[var(--color-danger-light)] hover:text-[var(--color-danger)] transition-colors"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
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
                    {t('createNew')}
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
