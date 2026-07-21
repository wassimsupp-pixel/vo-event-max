'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Lock, Unlock, ArrowLeft, Save, User, Clock, FileText, CheckCircle2, Loader2, Plane, Hotel, Bus, Sparkles, Database, Mail, Send, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import type { Participant } from '@/lib/api'

interface ConsolidatedView {
  flights: any[]
  transfers: any[]
  hotel_nights: any[]
  activities: any[]
  source_records: any[]
}

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
  const [consolidated, setConsolidated] = useState<ConsolidatedView | null>(null)

  // Individual confirmation (§13 + Lettre individuelle)
  const [confirmation, setConfirmation] = useState<{
    subject: string; body: string; missing: string[]; source: string; commId: string | null; persisted: boolean
  } | null>(null)
  const [genConfirm, setGenConfirm] = useState(false)
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null)
  // In-flight guards: without these, double-clicking "Marquer comme envoyé"
  // fires api.communications.send() twice concurrently -- sending the
  // confirmation email to the participant twice.
  const [savingConfirm, setSavingConfirm] = useState(false)
  const [sendingConfirm, setSendingConfirm] = useState(false)

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
      // Consolidated view is best-effort — don't block the profile if it fails
      try {
        setConsolidated(await api.participants.getConsolidated(participantId))
      } catch {
        /* ignore */
      }
    }
    if (participantId) load()
  }, [participantId])

  // Deep-link from the "Champs manquants" exceptions: ?field=email focuses and
  // highlights that input so the user lands right on the field to fill.
  useEffect(() => {
    if (!participant) return
    const field = new URLSearchParams(window.location.search).get('field')
    if (!field) return
    const timer = setTimeout(() => {
      const el = document.querySelector(`input[name="${field}"]`) as HTMLInputElement | null
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el.focus()
        el.classList.add('ring-2', 'ring-[var(--color-accent)]')
        setTimeout(() => el.classList.remove('ring-2', 'ring-[var(--color-accent)]'), 2500)
      }
    }, 150)
    return () => clearTimeout(timer)
  }, [participant])

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

  const handleGenerateConfirmation = async () => {
    setGenConfirm(true)
    setConfirmMsg(null)
    try {
      const r = await api.communications.generateConfirmation(eventId, participantId)
      setConfirmation({
        subject: r.subject,
        body: r.body,
        missing: r.missing,
        source: r.source,
        commId: r.communication?.id ?? null,
        persisted: r.persisted,
      })
      if (!r.persisted) setConfirmMsg('Aperçu généré. Exécutez la migration communications pour activer le suivi et l’envoi.')
    } catch {
      setConfirmMsg('Erreur lors de la génération de la confirmation.')
    } finally {
      setGenConfirm(false)
    }
  }

  const handleSaveConfirmation = async () => {
    if (!confirmation?.commId || savingConfirm) return
    setSavingConfirm(true)
    try {
      await api.communications.update(confirmation.commId, { subject: confirmation.subject, body: confirmation.body, status: 'ready' })
      setConfirmMsg('Confirmation enregistrée (prête à envoyer).')
    } catch {
      setConfirmMsg('Erreur lors de l’enregistrement.')
    } finally {
      setSavingConfirm(false)
    }
  }

  const handleSendConfirmation = async () => {
    if (!confirmation?.commId || sendingConfirm) return
    setSendingConfirm(true)
    try {
      await api.communications.update(confirmation.commId, { subject: confirmation.subject, body: confirmation.body })
      await api.communications.send(confirmation.commId)
      setConfirmMsg('Confirmation marquée comme envoyée.')
    } catch {
      setConfirmMsg('Erreur lors de l’envoi.')
    } finally {
      setSendingConfirm(false)
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

        {/* Consolidated operational master-list view (§6) */}
        {consolidated && (
          <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white space-y-6">
            <div className="flex items-center gap-2 border-b pb-4">
              <Database className="h-5 w-5 text-[var(--color-accent)]" />
              <h3 className="font-semibold text-sm text-[var(--color-text-primary)]">Vue consolidée (master list)</h3>
            </div>

            {/* Summary tiles */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { icon: <Plane className="h-4 w-4" />, label: 'Vols', count: consolidated.flights.length },
                { icon: <Hotel className="h-4 w-4" />, label: 'Nuitées', count: consolidated.hotel_nights.length },
                { icon: <Bus className="h-4 w-4" />, label: 'Transferts', count: consolidated.transfers.length },
                { icon: <Sparkles className="h-4 w-4" />, label: 'Activités', count: consolidated.activities.length },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-[var(--color-border)] bg-slate-50 p-3">
                  <div className="flex items-center gap-1.5 text-[var(--color-text-secondary)]">
                    {s.icon}
                    <span className="text-xs font-medium">{s.label}</span>
                  </div>
                  <div className="mt-1 text-2xl font-bold text-[var(--color-text-primary)]">{s.count}</div>
                </div>
              ))}
            </div>

            {/* Flights */}
            {consolidated.flights.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Vols</h4>
                {consolidated.flights.map((f) => (
                  <div key={f.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                    <span className="font-mono font-semibold">{f.flight_number || '—'}</span>
                    <span>{f.departure_airport} → {f.arrival_airport}</span>
                    {f.departure_time && <span className="text-[var(--color-text-secondary)]">{new Date(f.departure_time).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })}</span>}
                    {f.status && <span className="text-[var(--color-text-secondary)]">{f.status}</span>}
                  </div>
                ))}
              </div>
            )}

            {/* Hotel nights */}
            {consolidated.hotel_nights.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Hôtels &amp; nuitées</h4>
                {consolidated.hotel_nights.map((h) => (
                  <div key={h.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                    <span className="font-semibold">{h.hotels?.name || 'Hôtel'}</span>
                    {h.night_date && <span>{new Date(h.night_date).toLocaleDateString('fr-FR', { dateStyle: 'medium' })}</span>}
                    {h.room_type && <span className="text-[var(--color-text-secondary)]">{h.room_type}</span>}
                    {h.status && <span className="text-[var(--color-text-secondary)]">{h.status}</span>}
                  </div>
                ))}
              </div>
            )}

            {/* Transfers */}
            {consolidated.transfers.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Transferts</h4>
                {consolidated.transfers.map((tr) => (
                  <div key={tr.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                    <span className="font-semibold">{tr.pickup_location || '—'} → {tr.dropoff_location || '—'}</span>
                    {tr.pickup_time && <span className="text-[var(--color-text-secondary)]">{new Date(tr.pickup_time).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })}</span>}
                    {tr.transfer_type && <span className="text-[var(--color-text-secondary)]">{tr.transfer_type}</span>}
                  </div>
                ))}
              </div>
            )}

            {/* Activities */}
            {consolidated.activities.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Activités</h4>
                <div className="flex flex-wrap gap-2">
                  {consolidated.activities.map((a) => (
                    <Badge key={a.id} className="bg-[var(--color-accent-light)] text-[var(--color-accent)] border-0">
                      {a.activities?.name || 'Activité'}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Raw source rows (admin/pm only, provided by the API) */}
            {consolidated.source_records.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
                  Données sources complètes ({consolidated.source_records.length})
                </h4>
                {consolidated.source_records.map((sr) => {
                  const data: Record<string, any> = sr.normalized_data || sr.raw_data || {}
                  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== '' && v !== undefined)
                  return (
                    <div key={sr.id} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                      <div className="mb-2 text-[11px] font-semibold text-[var(--color-accent)]">
                        {sr.uploaded_files?.source_type || 'source'}
                        {sr.uploaded_files?.original_filename ? ` — ${sr.uploaded_files.original_filename}` : ''}
                      </div>
                      <div className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                        {entries.map(([k, v]) => (
                          <div key={k} className="flex flex-col">
                            <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">{k.replace(/_/g, ' ')}</span>
                            <span className="text-xs text-[var(--color-text-primary)] break-words">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        )}

        {/* Individual confirmation (§13 + Lettre individuelle) */}
        <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white space-y-5">
          <div className="flex items-center justify-between border-b pb-4">
            <div className="flex items-center gap-2">
              <Mail className="h-5 w-5 text-[var(--color-accent)]" />
              <h3 className="font-semibold text-sm text-[var(--color-text-primary)]">Confirmation individuelle du participant</h3>
            </div>
            {confirmation && (
              <Badge variant="outline" className="text-[10px] border-[var(--color-border)] text-[var(--color-text-secondary)]">
                {confirmation.source === 'gemini' ? 'Généré par IA' : 'Modèle'}
              </Badge>
            )}
          </div>

          {confirmMsg && (
            <div className="flex items-center gap-2 rounded-lg bg-[var(--color-accent-light)] px-3 py-2 text-xs font-medium text-[var(--color-text-primary)]">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-[var(--color-accent)]" />
              <span>{confirmMsg}</span>
            </div>
          )}

          {!confirmation ? (
            <div className="flex flex-col items-start gap-3">
              <p className="text-xs text-[var(--color-text-secondary)]">
                Génère un e-mail de confirmation personnalisé à partir des données consolidées du participant.
                Le contenu n’utilise que les informations disponibles et validées — rien n’est inventé.
              </p>
              <Button
                onClick={handleGenerateConfirmation}
                disabled={genConfirm}
                className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white flex items-center gap-2"
              >
                {genConfirm ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Générer la confirmation
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {confirmation.missing.length > 0 && (
                <div className="flex items-start gap-2 rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-3 py-2 text-xs">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--color-warning)]" />
                  <span className="text-[var(--color-text-primary)]">
                    Informations manquantes (non inventées) :{' '}
                    {confirmation.missing.map((m) => (m === 'flights' ? 'vols' : m === 'hotel_nights' ? 'hôtel' : m === 'transfers' ? 'transferts' : m)).join(', ')}.
                  </span>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[var(--color-text-secondary)]">Objet</label>
                <input
                  type="text"
                  value={confirmation.subject}
                  onChange={(e) => setConfirmation((c) => c && { ...c, subject: e.target.value })}
                  className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white px-3 py-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[var(--color-text-secondary)]">Message</label>
                <textarea
                  value={confirmation.body}
                  onChange={(e) => setConfirmation((c) => c && { ...c, body: e.target.value })}
                  rows={14}
                  className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white px-3 py-2 font-mono text-[var(--color-text-primary)] whitespace-pre-wrap focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                />
              </div>

              <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
                <Button variant="outline" onClick={handleGenerateConfirmation} disabled={genConfirm} className="flex items-center gap-2">
                  {genConfirm ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Régénérer
                </Button>
                <Button
                  variant="outline"
                  onClick={handleSaveConfirmation}
                  disabled={!confirmation.commId || savingConfirm}
                  className="flex items-center gap-2"
                  title={confirmation.commId ? '' : 'Migration communications requise'}
                >
                  {savingConfirm ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Enregistrer
                </Button>
                <Button
                  onClick={handleSendConfirmation}
                  disabled={!confirmation.commId || sendingConfirm}
                  className="bg-[var(--color-success)] hover:bg-emerald-600 text-white flex items-center gap-2"
                  title={confirmation.commId ? '' : 'Migration communications requise'}
                >
                  {sendingConfirm ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Marquer comme envoyé
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </AppLayout>
  )
}

