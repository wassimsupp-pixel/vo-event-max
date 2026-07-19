'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Settings, User, Shield, Globe, Save, CheckCircle2, Loader2, GitMerge, MapPin, Users, Star, AlertTriangle } from 'lucide-react'
import { createClient } from '@/lib/supabase'
import { api, type EventMergeSuggestion } from '@/lib/api'

export default function SettingsPage() {
  const { locale } = useParams() as { locale: string }
  const router = useRouter()

  const [language, setLanguage] = useState(locale)
  const [userName, setUserName] = useState('Marie Dubois')
  const [userRole, setUserRole] = useState('Event Manager')
  const [email, setEmail] = useState('marie.dubois@vo-event.be')
  const [notifEmails, setNotifEmails] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)

  // Similar-event merge suggestions (org-level, non-destructive until confirmed)
  const [suggestions, setSuggestions] = useState<EventMergeSuggestion[]>([])
  const [loadingSug, setLoadingSug] = useState(true)
  const [mergingId, setMergingId] = useState<string | null>(null)
  const [mergeMsg, setMergeMsg] = useState<string | null>(null)

  const loadSuggestions = async () => {
    setLoadingSug(true)
    try {
      setSuggestions(await api.eventGrouping.suggestions())
    } catch {
      /* endpoint may be unavailable — show nothing */
    } finally {
      setLoadingSug(false)
    }
  }

  useEffect(() => {
    loadSuggestions()
  }, [])

  const handleMerge = async (s: EventMergeSuggestion) => {
    const mergeIds = s.events.map((e) => e.id).filter((id) => id !== s.canonical_event_id)
    const canonicalName = s.events.find((e) => e.id === s.canonical_event_id)?.name || 'cet événement'
    if (!confirm(`Fusionner ${mergeIds.length} événement(s) dans « ${canonicalName} » ? Cette action est irréversible.`)) return
    setMergingId(s.canonical_event_id)
    setMergeMsg(null)
    try {
      const res = await api.eventGrouping.merge(s.canonical_event_id, mergeIds)
      setMergeMsg(res.message)
      await loadSuggestions()
    } catch (err) {
      setMergeMsg(err instanceof Error ? err.message : 'Erreur lors de la fusion.')
    } finally {
      setMergingId(null)
    }
  }

  useEffect(() => {
    async function loadUser() {
      try {
        const supabase = createClient()
        const { data: { user } } = await supabase.auth.getUser()
        if (user) {
          const name = user.user_metadata?.full_name || user.email?.split('@')[0] || 'Utilisateur VO'
          setUserName(name)
          setEmail(user.email || '')

          try {
            const { data: profile } = await supabase.from('users').select('role').eq('id', user.id).single()
            if (profile) {
              setUserRole(profile.role === 'admin' ? 'Administrateur' : profile.role === 'pm' ? 'Chef de projet' : 'Utilisateur')
            }
          } catch {
            // ignore
          }
        }
      } catch (err) {
        console.error('Failed to load settings:', err)
      } finally {
        setLoading(false)
      }
    }
    loadUser()
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSuccess(false)
    setSaving(true)
    try {
      const supabase = createClient()
      const { data: { user } } = await supabase.auth.getUser()
      if (user) {
        // 1. Update Supabase Auth metadata
        await supabase.auth.updateUser({
          data: { full_name: userName }
        })
        // 2. Update public.users database row
        await supabase.from('users').update({
          full_name: userName,
        }).eq('id', user.id)
      }
      setSuccess(true)
      setTimeout(() => {
        setSuccess(false)
        if (language !== locale) {
          router.push(`/${language}/settings`)
        }
      }, 1500)
    } catch (err) {
      console.error('Failed to save settings:', err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppLayout eventId="global" locale={locale}>
      <div className="flex flex-col gap-6 p-6 max-w-4xl">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Settings className="h-6 w-6 text-[var(--color-accent)]" />
              Paramètres
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Gérez vos préférences utilisateur, la langue de la plateforme et les options de notification.
            </p>
          </div>
        </div>

        {success && (
          <div className="flex items-center gap-2 rounded-lg bg-[var(--color-success-light)] p-3 text-sm text-[var(--color-success)] font-semibold animate-fade-in">
            <CheckCircle2 className="h-5 w-5" />
            Paramètres enregistrés avec succès.
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent)]" />
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6">
            {/* Profile Section */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <User className="h-4 w-4 text-[var(--color-accent)]" />
                Mon Profil
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-1">Nom complet</label>
                  <input
                    type="text"
                    value={userName}
                    onChange={(e) => setUserName(e.target.value)}
                    className="w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm outline-none text-[var(--color-text-primary)] focus:border-[var(--color-accent)]"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-1">Rôle</label>
                  <input
                    type="text"
                    value={userRole}
                    disabled
                    className="w-full rounded-lg border border-[var(--color-border)] bg-gray-50 px-3 py-2 text-sm outline-none text-[var(--color-text-secondary)]"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-1">Adresse email</label>
                  <input
                    type="email"
                    value={email}
                    disabled
                    className="w-full rounded-lg border border-[var(--color-border)] bg-gray-50 px-3 py-2 text-sm outline-none text-[var(--color-text-secondary)]"
                  />
                </div>
              </div>
            </div>

            {/* Platform Settings */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Globe className="h-4 w-4 text-[var(--color-accent)]" />
                Langue de l&apos;interface
              </h3>
              <div className="max-w-xs">
                <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-1">Langue par défaut</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm outline-none text-[var(--color-text-primary)] bg-white focus:border-[var(--color-accent)]"
                >
                  <option value="fr">Français (FR)</option>
                  <option value="nl">Nederlands (NL)</option>
                  <option value="en">English (EN)</option>
                </select>
              </div>
            </div>

            {/* Notifications */}
            <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Shield className="h-4 w-4 text-[var(--color-accent)]" />
                Notifications & Sécurité
              </h3>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={notifEmails}
                  onChange={(e) => setNotifEmails(e.target.checked)}
                  className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                />
                <span className="text-sm text-[var(--color-text-primary)]">
                  Recevoir des rapports d&apos;exception hebdomadaires par email
                </span>
              </label>
            </div>

            {/* Action button */}
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--color-accent)]/90 transition-all active:scale-[0.98] disabled:opacity-60"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Enregistrer
              </button>
            </div>
          </form>
        )}

        {/* Similar-event merge — org-level, non-destructive until confirmed */}
        <div className="rounded-[var(--radius-card)] border bg-white p-6 shadow-sm">
          <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
            <GitMerge className="h-4 w-4 text-[var(--color-accent)]" />
            Événements similaires à regrouper
          </h3>
          <p className="mb-4 text-xs text-[var(--color-text-secondary)]">
            L&apos;IA détecte les événements au nom proche (ex. « Innovation Summit » / « 2026 Global Innovation Summit »).
            Vérifiez, puis fusionnez-les en un seul — toutes les données sont déplacées vers l&apos;événement conservé.
          </p>

          {mergeMsg && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-[var(--color-accent-light)] px-3 py-2 text-xs font-medium text-[var(--color-text-primary)]">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-[var(--color-accent)]" />
              {mergeMsg}
            </div>
          )}

          {loadingSug ? (
            <div className="flex items-center justify-center py-8 text-sm text-[var(--color-text-secondary)]">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Analyse des événements…
            </div>
          ) : suggestions.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-4 text-center text-xs text-[var(--color-text-secondary)]">
              Aucun groupe d&apos;événements similaires détecté.
            </p>
          ) : (
            <div className="space-y-4">
              {suggestions.map((s) => (
                <div key={s.canonical_event_id} className="rounded-lg border border-amber-200 bg-amber-50/40 p-4">
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 font-semibold text-amber-700 border border-amber-200">
                      <AlertTriangle className="h-3 w-3" /> {s.events.length} événements proches
                    </span>
                    <span className="text-[var(--color-text-secondary)]">Similarité min. {Math.round(s.min_similarity)}%</span>
                    {s.ai_confirmed === true && (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-700">IA : même événement</span>
                    )}
                  </div>

                  <div className="space-y-1.5">
                    {s.events.map((ev) => {
                      const isCanonical = ev.id === s.canonical_event_id
                      return (
                        <div
                          key={ev.id}
                          className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-3 py-2 text-xs ${
                            isCanonical ? 'border-[var(--color-accent)] bg-white' : 'border-slate-200 bg-white/60'
                          }`}
                        >
                          {isCanonical ? (
                            <span className="inline-flex items-center gap-1 font-semibold text-[var(--color-accent)]">
                              <Star className="h-3.5 w-3.5" /> À conserver
                            </span>
                          ) : (
                            <span className="text-[10px] font-semibold text-rose-600">sera fusionné →</span>
                          )}
                          <span className="font-semibold text-[var(--color-text-primary)]">{ev.name}</span>
                          <span className="inline-flex items-center gap-1 text-[var(--color-text-secondary)]">
                            <Users className="h-3 w-3" /> {ev.participant_count}
                          </span>
                          {ev.location_city && (
                            <span className="inline-flex items-center gap-1 text-[var(--color-text-secondary)]">
                              <MapPin className="h-3 w-3" /> {ev.location_city}
                            </span>
                          )}
                          {ev.start_date && <span className="text-[var(--color-text-secondary)]">{ev.start_date}</span>}
                        </div>
                      )
                    })}
                  </div>

                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={() => handleMerge(s)}
                      disabled={mergingId === s.canonical_event_id}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[var(--color-accent)]/90 disabled:opacity-50"
                    >
                      {mergingId === s.canonical_event_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitMerge className="h-3.5 w-3.5" />}
                      Fusionner ces événements
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  )
}
