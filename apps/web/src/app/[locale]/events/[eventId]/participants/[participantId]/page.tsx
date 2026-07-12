'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Lock, Unlock, ArrowLeft, Save, User, Clock, FileText, CheckCircle2, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import type { Participant } from '@/lib/api'

const EDITABLE_FIELDS = ['first_name', 'last_name', 'email', 'company', 'phone', 'nationality', 'dietary_requirements']

export default function ParticipantDetailPage() {
  const params = useParams()
  const router = useRouter()
  const locale = params.locale as string
  const eventId = params.eventId as string
  const participantId = params.participantId as string

  const t = useTranslations('nav')

  const [participant, setParticipant] = useState<Participant | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lockedFields, setLockedFields] = useState<Record<string, boolean>>({})
  const [isSaved, setIsSaved] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const data = await api.participants.get(participantId)
        setParticipant(data)
        const locks: Record<string, boolean> = {}
        EDITABLE_FIELDS.forEach(f => { locks[f] = data.locked_fields.includes(f) })
        setLockedFields(locks)
      } catch {
        setError('Impossible de charger le participant.')
      } finally {
        setLoading(false)
      }
    }
    if (participantId) load()
  }, [participantId])

  const handleToggleLock = async (field: string) => {
    if (!participant) return
    const isLocked = lockedFields[field]
    setLockedFields(prev => ({ ...prev, [field]: !prev[field] }))
    try {
      if (isLocked) {
        await api.participants.unlockField(participantId, field)
      } else {
        await api.participants.lockField(participantId, field)
      }
    } catch {
      // Revert on failure
      setLockedFields(prev => ({ ...prev, [field]: isLocked }))
    }
  }

  const handleSave = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!participant) return
    setSaving(true)
    try {
      const formData = new FormData(e.currentTarget)
      const update: Record<string, string> = {}
      EDITABLE_FIELDS.forEach(f => {
        const val = formData.get(f)
        if (val !== null) update[f] = val as string
      })
      const updated = await api.participants.update(participantId, update)
      setParticipant(updated)
      setIsSaved(true)
      setTimeout(() => setIsSaved(false), 2000)
    } catch {
      setError('Erreur lors de la sauvegarde.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <AppLayout
        eventId={eventId}
        locale={locale}
        pageTitle="Détails du Participant"
        pageSubtitle="Consultez les informations consolidées, gérez les verrous de champs et l'audit trail"
      >
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-10 w-10 animate-spin text-[var(--color-accent)]" />
        </div>
      </AppLayout>
    )
  }

  if (error && !participant) {
    return (
      <AppLayout
        eventId={eventId}
        locale={locale}
        pageTitle="Détails du Participant"
        pageSubtitle="Consultez les informations consolidées, gérez les verrous de champs et l'audit trail"
      >
        <div className="flex flex-col items-center justify-center py-24 gap-4">
          <p className="text-sm text-[var(--color-danger)]">{error}</p>
          <Button variant="outline" onClick={() => router.back()}>Retour</Button>
        </div>
      </AppLayout>
    )
  }

  if (!participant) return null

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle="Détails du Participant"
      pageSubtitle="Consultez les informations consolidées, gérez les verrous de champs et l'audit trail"
    >
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" onClick={() => router.back()} className="h-9 w-9 border-[var(--color-border)]">
            <ArrowLeft className="h-4.5 w-4.5 text-[var(--color-text-secondary)]" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
              {participant.first_name} {participant.last_name}
            </h1>
            <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">ID: {participantId}</p>
          </div>
        </div>

        {isSaved && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-success-light)] border border-[var(--color-success)]/20 text-[var(--color-success)] text-sm font-medium animate-fade-in">
            <CheckCircle2 className="h-5 w-5 shrink-0" />
            <span>Modifications enregistrées avec succès. Audit Trail mis à jour.</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-sm font-medium">
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          {/* Main Edit Form */}
          <div className="col-span-12 lg:col-span-8 space-y-6">
            <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white">
              <form onSubmit={handleSave} className="space-y-6">
                <div className="flex items-center justify-between border-b pb-4">
                  <div className="flex items-center gap-2">
                    <User className="h-5 w-5 text-[var(--color-accent)]" />
                    <h3 className="font-semibold text-sm text-[var(--color-text-primary)]">Profil du Participant</h3>
                  </div>
                  <Badge variant="outline" className="border-[var(--color-success)] text-[var(--color-success)] bg-[var(--color-success-light)]">
                    Consolidé ({participant.confidence})
                  </Badge>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {[
                    { field: 'first_name', label: 'Prénom', val: participant.first_name },
                    { field: 'last_name', label: 'Nom', val: participant.last_name },
                    { field: 'email', label: 'Email', val: participant.email },
                    { field: 'company', label: 'Société', val: participant.company || '' },
                    { field: 'phone', label: 'Téléphone', val: participant.phone || '' },
                    { field: 'nationality', label: 'Nationalité', val: participant.nationality || '' },
                    { field: 'dietary_requirements', label: 'Régime Alimentaire', val: participant.dietary_requirements || '', sensitive: true }
                  ].map((item) => (
                    <div key={item.field} className="space-y-1.5">
                      <label className="text-xs font-semibold text-[var(--color-text-secondary)] flex items-center justify-between">
                        <span>{item.label} {item.sensitive && <span className="text-[var(--color-danger)] font-medium">(Sensible)</span>}</span>
                        {lockedFields[item.field] !== undefined && (
                          <button
                            type="button"
                            className={`flex items-center gap-1 text-[10px] hover:underline font-semibold ${
                              lockedFields[item.field] ? 'text-[var(--color-accent)]' : 'text-slate-400'
                            }`}
                            onClick={() => handleToggleLock(item.field)}
                          >
                            {lockedFields[item.field] ? (
                              <>
                                <Lock className="h-3 w-3" /> Verrouillé
                              </>
                            ) : (
                              <>
                                <Unlock className="h-3 w-3" /> Déverrouillé
                              </>
                            )}
                          </button>
                        )}
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          name={item.field}
                          defaultValue={item.val}
                          disabled={lockedFields[item.field]}
                          className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white px-3 py-2 text-[var(--color-text-primary)] disabled:bg-slate-50 disabled:text-slate-500 focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                        />
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex justify-end pt-4 border-t gap-3">
                  <Button variant="outline" type="button" onClick={() => router.back()}>
                    Retour
                  </Button>
                  <Button
                    type="submit"
                    disabled={saving}
                    className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white flex items-center gap-2"
                  >
                    {saving ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    Enregistrer les modifications
                  </Button>
                </div>
              </form>
            </Card>
          </div>

          {/* Right Panel: Audit Trail & Sources */}
          <div className="col-span-12 lg:col-span-4 space-y-6">
            {/* Sources tracking */}
            <Card className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white space-y-4">
              <h4 className="text-sm font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                <FileText className="h-4.5 w-4.5 text-[var(--color-accent)]" /> Sources associées
              </h4>
              <div className="space-y-3">
                {participant.sources.length === 0 ? (
                  <p className="text-xs text-[var(--color-text-secondary)]">Aucune source associée.</p>
                ) : (
                  participant.sources.map((source) => (
                    <div key={source} className="flex items-center justify-between p-2.5 rounded border border-slate-100 bg-slate-50">
                      <span className="text-xs font-medium text-[var(--color-text-primary)] capitalize">{source}</span>
                      <Badge className="bg-[var(--color-success-light)] text-[var(--color-success)] border-0 text-[10px]">Présent</Badge>
                    </div>
                  ))
                )}
              </div>
            </Card>

            {/* Audit Trail */}
            <Card className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white space-y-4">
              <h4 className="text-sm font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                <Clock className="h-4.5 w-4.5 text-[var(--color-accent)]" /> Journal d&apos;audit (Audit Trail)
              </h4>
              <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                L&apos;audit trail sera disponible après configuration de la base de données.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}

