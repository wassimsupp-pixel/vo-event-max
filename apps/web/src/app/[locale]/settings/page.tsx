'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Settings, User, Shield, Globe, Save, CheckCircle2, Loader2 } from 'lucide-react'
import { createClient } from '@/lib/supabase'

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
      </div>
    </AppLayout>
  )
}
