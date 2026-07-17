'use client'

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { X, UserPlus, Trash2, Loader2, Users, Eye, Pencil, ChevronDown } from 'lucide-react'
import { api, ProjectMember } from '@/lib/api'
import { cn } from '@/lib/utils'

interface EventOption {
  id: string
  name: string
}

interface ShareProjectModalProps {
  projectId: string
  projectName: string
  events: EventOption[]
  onClose: () => void
}

/**
 * Share a project with existing platform users: list members, add by email
 * with an access level (viewer/editor), optionally restrict to specific
 * events, change level, revoke. (Invitation links/emails come later.)
 */
export function ShareProjectModal({ projectId, projectName, events, onClose }: ShareProjectModalProps) {
  const t = useTranslations('sharing')

  const [members, setMembers] = useState<ProjectMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Add form
  const [email, setEmail] = useState('')
  const [level, setLevel] = useState<'viewer' | 'editor'>('viewer')
  const [scopeAll, setScopeAll] = useState(true)
  const [scopeEvents, setScopeEvents] = useState<Set<string>>(new Set())
  const [showScope, setShowScope] = useState(false)
  const [adding, setAdding] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setMembers(await api.sharing.listMembers(projectId))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'))
    } finally {
      setLoading(false)
    }
  }, [projectId, t])

  useEffect(() => { load() }, [load])

  const handleAdd = async () => {
    if (!email.trim()) return
    setAdding(true)
    setError(null)
    try {
      await api.sharing.addMember(projectId, {
        email: email.trim(),
        access_level: level,
        event_ids: scopeAll ? null : Array.from(scopeEvents),
      })
      setEmail('')
      setScopeAll(true)
      setScopeEvents(new Set())
      setShowScope(false)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('addError'))
    } finally {
      setAdding(false)
    }
  }

  const handleLevelChange = async (m: ProjectMember, newLevel: 'viewer' | 'editor') => {
    if (m.access_level === newLevel) return
    setBusyId(m.id)
    try {
      await api.sharing.updateMember(projectId, m.id, { access_level: newLevel })
      setMembers((prev) => prev.map((x) => (x.id === m.id ? { ...x, access_level: newLevel } : x)))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('updateError'))
    } finally {
      setBusyId(null)
    }
  }

  const handleRemove = async (m: ProjectMember) => {
    setBusyId(m.id)
    try {
      await api.sharing.removeMember(projectId, m.id)
      setMembers((prev) => prev.filter((x) => x.id !== m.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('removeError'))
    } finally {
      setBusyId(null)
    }
  }

  const toggleScopeEvent = (id: string) => {
    setScopeEvents((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const scopeLabel = (m: ProjectMember) => {
    if (!m.event_ids || m.event_ids.length === 0) return t('wholeProject')
    const names = m.event_ids
      .map((id) => events.find((e) => e.id === id)?.name)
      .filter(Boolean)
    return names.length > 0 ? names.join(', ') : t('someEvents', { count: m.event_ids.length })
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t('title', { name: projectName })}
    >
      <div
        className="w-full max-w-lg rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <Users className="h-4 w-4 flex-shrink-0 text-[var(--color-accent)]" />
            <span className="truncate text-sm font-bold text-[var(--color-text-primary)]">
              {t('title', { name: projectName })}
            </span>
          </div>
          <button
            onClick={onClose}
            aria-label={t('close')}
            className="rounded-md p-1.5 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto p-4 space-y-4">
          {error && (
            <p className="rounded-lg bg-[var(--color-danger-light)] px-3 py-2 text-xs font-medium text-[var(--color-danger)]">
              {error}
            </p>
          )}

          {/* Add member */}
          <div className="space-y-2 rounded-lg border border-[var(--color-border)] p-3">
            <p className="text-xs font-semibold text-[var(--color-text-primary)]">{t('addTitle')}</p>
            <p className="text-[11px] text-[var(--color-text-secondary)]">{t('existingOnly')}</p>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
                placeholder={t('emailPlaceholder')}
                className="min-w-0 flex-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs focus:border-[var(--color-accent)] focus:outline-none"
              />
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value as 'viewer' | 'editor')}
                className="rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-xs focus:border-[var(--color-accent)] focus:outline-none"
                aria-label={t('accessLevel')}
              >
                <option value="viewer">{t('viewer')}</option>
                <option value="editor">{t('editor')}</option>
              </select>
              <button
                onClick={handleAdd}
                disabled={adding || !email.trim()}
                className="flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
                {t('add')}
              </button>
            </div>

            {/* Event scope */}
            <button
              type="button"
              onClick={() => setShowScope((v) => !v)}
              className="flex items-center gap-1 text-[11px] font-medium text-[var(--color-accent)] hover:underline"
            >
              <ChevronDown className={cn('h-3 w-3 transition-transform', showScope && 'rotate-180')} />
              {scopeAll ? t('scopeWhole') : t('scopeRestricted', { count: scopeEvents.size })}
            </button>
            {showScope && (
              <div className="space-y-1 rounded-lg bg-[var(--color-bg-subtle)] p-2">
                <label className="flex items-center gap-2 text-xs text-[var(--color-text-primary)]">
                  <input
                    type="checkbox"
                    checked={scopeAll}
                    onChange={(e) => setScopeAll(e.target.checked)}
                  />
                  {t('wholeProject')}
                </label>
                {!scopeAll && events.map((ev) => (
                  <label key={ev.id} className="flex items-center gap-2 pl-4 text-xs text-[var(--color-text-primary)]">
                    <input
                      type="checkbox"
                      checked={scopeEvents.has(ev.id)}
                      onChange={() => toggleScopeEvent(ev.id)}
                    />
                    <span className="truncate">{ev.name}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Member list */}
          <div className="space-y-1.5">
            <p className="text-xs font-semibold text-[var(--color-text-primary)]">{t('membersTitle')}</p>
            {loading ? (
              <div className="flex items-center justify-center py-4 text-xs text-[var(--color-text-secondary)]">
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin text-[var(--color-accent)]" />
                {t('loading')}
              </div>
            ) : members.length === 0 ? (
              <p className="py-2 text-center text-xs italic text-[var(--color-text-secondary)]">
                {t('noMembers')}
              </p>
            ) : (
              members.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-[var(--color-text-primary)]">
                      {m.full_name || m.email}
                    </p>
                    <p className="truncate text-[11px] text-[var(--color-text-secondary)]">
                      {m.full_name ? `${m.email} · ` : ''}{scopeLabel(m)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => handleLevelChange(m, 'viewer')}
                      disabled={busyId === m.id}
                      title={t('viewer')}
                      className={cn(
                        'rounded-md p-1.5 transition-colors',
                        m.access_level === 'viewer'
                          ? 'bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)]'
                      )}
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleLevelChange(m, 'editor')}
                      disabled={busyId === m.id}
                      title={t('editor')}
                      className={cn(
                        'rounded-md p-1.5 transition-colors',
                        m.access_level === 'editor'
                          ? 'bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)]'
                      )}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemove(m)}
                      disabled={busyId === m.id}
                      title={t('remove')}
                      aria-label={t('remove')}
                      className="rounded-md p-1.5 text-[var(--color-text-secondary)] hover:bg-[var(--color-danger-light)] hover:text-[var(--color-danger)] transition-colors"
                    >
                      {busyId === m.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
