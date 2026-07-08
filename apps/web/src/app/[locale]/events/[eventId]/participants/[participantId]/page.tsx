'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Lock, Unlock, ArrowLeft, Save, User, Clock, FileText, CheckCircle2 } from 'lucide-react'
import type { Participant } from '@/lib/api'

const MOCK_PARTICIPANT: Participant = {
  id: '1',
  event_id: '1',
  first_name: 'Sophie',
  last_name: 'Martin',
  email: 'sophie.martin@livanoba.com',
  company: 'LivaNova',
  phone: '+32 490 12 34 56',
  nationality: 'Belge',
  dietary_requirements: 'Sans gluten',
  status: 'complete',
  confidence: 'certain',
  has_flight: true,
  has_hotel: true,
  has_transfer: true,
  has_activity: true,
  locked_fields: ['email'],
  sources: ['fcm', 'client'],
  created_at: '2026-07-08T10:00:00Z',
  updated_at: '2026-07-08T14:30:00Z',
}

const MOCK_AUDIT_LOG = [
  { id: 'l1', user: 'Marie Dupont', action: 'Lock email', field: 'email', old: 'sophie.martin@livanoba.com', new: 'sophie.martin@livanoba.com', date: '2026-07-08T14:30:00Z' },
  { id: 'l2', user: 'Système (Auto-merge)', action: 'Consolidation', field: 'company', old: '', new: 'LivaNova', date: '2026-07-08T12:00:00Z' },
  { id: 'l3', user: 'Marie Dupont', action: 'Création participant', field: 'all', old: '', new: '', date: '2026-07-08T10:00:00Z' }
]

export default function ParticipantDetailPage() {
  const params = useParams()
  const router = useRouter()
  const locale = params.locale as string
  const eventId = params.eventId as string
  const participantId = params.participantId as string

  const t = useTranslations('nav')

  const [participant, setParticipant] = useState<Participant>(MOCK_PARTICIPANT)
  const [lockedFields, setLockedFields] = useState<Record<string, boolean>>({
    email: true,
    first_name: false,
    last_name: false,
    company: false,
    phone: false,
    dietary_requirements: false,
  })
  const [isSaved, setIsSaved] = useState(false)

  const handleToggleLock = (field: string) => {
    setLockedFields(prev => ({ ...prev, [field]: !prev[field] }))
  }

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaved(true)
    setTimeout(() => setIsSaved(false), 2000)
  }

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
                    Consolidé (Certain)
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
                  <Button type="submit" className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white flex items-center gap-2">
                    <Save className="h-4 w-4" /> Enregistrer les modifications
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
                <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 bg-slate-50">
                  <span className="text-xs font-medium text-[var(--color-text-primary)]">Fichier Inscriptions Client</span>
                  <Badge className="bg-[var(--color-success-light)] text-[var(--color-success)] border-0 text-[10px]">Présent</Badge>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 bg-slate-50">
                  <span className="text-xs font-medium text-[var(--color-text-primary)]">Fichier Broker FCM Travel</span>
                  <Badge className="bg-[var(--color-success-light)] text-[var(--color-success)] border-0 text-[10px]">Présent</Badge>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded border border-slate-100 bg-slate-50">
                  <span className="text-xs font-medium text-[var(--color-text-primary)]">Confirmations Hôtels</span>
                  <Badge className="bg-slate-100 text-slate-500 border-0 text-[10px]">Absent</Badge>
                </div>
              </div>
            </Card>

            {/* Audit Trail */}
            <Card className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white space-y-4">
              <h4 className="text-sm font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                <Clock className="h-4.5 w-4.5 text-[var(--color-accent)]" /> Journal d'audit (Audit Trail)
              </h4>
              <div className="relative border-l border-slate-200 pl-4 ml-2 space-y-4">
                {MOCK_AUDIT_LOG.map((log) => (
                  <div key={log.id} className="relative text-xs">
                    {/* Circle dot on timeline */}
                    <div className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full border border-white bg-[var(--color-accent)]" />
                    <div className="font-semibold text-[var(--color-text-primary)]">
                      {log.action} ({log.field !== 'all' ? log.field : 'Profil'})
                    </div>
                    <div className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
                      Par {log.user} • {new Date(log.date).toLocaleString('fr-FR')}
                    </div>
                    {log.old !== log.new && (
                      <div className="text-[9px] bg-slate-50 p-1 border rounded mt-1 text-[var(--color-text-secondary)] font-mono">
                        "{log.old}" → "{log.new}"
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
