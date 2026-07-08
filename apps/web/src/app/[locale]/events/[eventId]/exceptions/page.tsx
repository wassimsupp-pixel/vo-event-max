'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertCircle, AlertTriangle, Info, CheckCircle2, UserCheck, ShieldAlert, Sparkles } from 'lucide-react'

// Mocked exceptions
const INITIAL_EXCEPTIONS = [
  {
    id: 'e1',
    type: 'DATA_CONFLICT',
    severity: 'critical',
    message: 'Conflit de données sur la société : "LivaNova" (Client) vs "Livanova Plc" (FCM)',
    participant: 'Thomas Bernard',
    email: 'thomas.bernard@livanoba.com',
    details: {
      field: 'company',
      val_client: 'LivaNova',
      val_fcm: 'Livanova Plc'
    }
  },
  {
    id: 'e2',
    type: 'PARTICIPANT_NO_FLIGHT',
    severity: 'warning',
    message: 'Aucune réservation de vol trouvée pour ce participant',
    participant: 'Marc Leroy',
    email: 'marc.leroy@livanoba.com',
    details: {}
  },
  {
    id: 'e3',
    type: 'DUPLICATE_EMAIL',
    severity: 'critical',
    message: 'Doublon détecté : L\'adresse email "camille.moreau@livanoba.com" est utilisée pour deux inscriptions',
    participant: 'Camille Moreau',
    email: 'camille.moreau@livanoba.com',
    details: {}
  },
  {
    id: 'e4',
    type: 'DATE_INCOHERENCE',
    severity: 'warning',
    message: 'Date de départ après la date d\'arrivée',
    participant: 'Isabelle Dupont',
    email: 'isabelle.dupont@livanoba.com',
    details: {
      field: 'dates',
      arrival: '10/11/2025',
      departure: '08/11/2025'
    }
  }
]

export default function ExceptionsPage() {
  const params = useParams()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')

  const [exceptions, setExceptions] = useState(INITIAL_EXCEPTIONS)
  const [activeResolve, setActiveResolve] = useState<any | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleResolveConflict = (resolution: string) => {
    if (!activeResolve) return

    // Update exception list by removing the resolved exception
    setExceptions(prev => prev.filter(e => e.id !== activeResolve.id))

    // Set success banner
    setSuccessMessage(`Conflit résolu pour ${activeResolve.participant}. Valeur retenue : "${resolution}".`)
    setTimeout(() => setSuccessMessage(null), 3000)
    setActiveResolve(null)
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <AlertCircle className="h-5 w-5 text-[var(--color-danger)]" />
      case 'warning':
        return <AlertTriangle className="h-5 w-5 text-[var(--color-warning)]" />
      default:
        return <Info className="h-5 w-5 text-[var(--color-text-secondary)]" />
    }
  }

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'critical':
        return (
          <Badge className="bg-[var(--color-danger-light)] text-[var(--color-danger)] border-0">
            Critique
          </Badge>
        )
      case 'warning':
        return (
          <Badge className="bg-[var(--color-warning-light)] text-[var(--color-warning)] border-0">
            Attention
          </Badge>
        )
      default:
        return (
          <Badge className="bg-slate-100 text-slate-600 border-0">
            Info
          </Badge>
        )
    }
  }

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle={t('exceptions')}
      pageSubtitle="Passez en revue les anomalies de consolidation détectées et résolvez les conflits"
    >
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">{t('exceptions')}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            {exceptions.length} exceptions en attente de traitement
          </p>
        </div>

        {successMessage && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-success-light)] border border-[var(--color-success)]/20 text-[var(--color-success)] text-sm font-medium animate-fade-in">
            <CheckCircle2 className="h-5 w-5 shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          {/* Main Exceptions List */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {exceptions.length === 0 ? (
              <Card className="p-8 text-center border-[var(--color-border)] shadow-[var(--shadow-card)] flex flex-col items-center justify-center space-y-3 bg-white">
                <div className="h-12 w-12 rounded-full bg-[var(--color-success-light)] flex items-center justify-center">
                  <CheckCircle2 className="h-6 w-6 text-[var(--color-success)]" />
                </div>
                <h3 className="font-semibold text-sm text-[var(--color-text-primary)]">Félicitations !</h3>
                <p className="text-xs text-[var(--color-text-secondary)]">Aucune anomalie ou conflit de données n'est en attente.</p>
              </Card>
            ) : (
              exceptions.map((exc) => (
                <Card
                  key={exc.id}
                  className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] hover:border-slate-300 transition-all bg-white flex items-start gap-4"
                >
                  <div className="mt-0.5">{getSeverityIcon(exc.severity)}</div>
                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-semibold text-[var(--color-text-primary)] truncate">
                        {exc.participant}
                      </h3>
                      <span className="text-xs text-[var(--color-text-secondary)]">({exc.email})</span>
                      {getSeverityBadge(exc.severity)}
                      <Badge variant="outline" className="text-[10px] uppercase border-slate-200">
                        {exc.type}
                      </Badge>
                    </div>

                    <p className="text-xs text-[var(--color-text-secondary)] font-medium leading-relaxed">
                      {exc.message}
                    </p>

                    {exc.type === 'DATA_CONFLICT' && (
                      <div className="pt-2">
                        <Button
                          size="sm"
                          className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white text-xs h-8"
                          onClick={() => setActiveResolve(exc)}
                        >
                          <Sparkles className="h-3.5 w-3.5 mr-1.5" /> Résoudre le conflit
                        </Button>
                      </div>
                    )}
                  </div>
                </Card>
              ))
            )}
          </div>

          {/* Right Panel: Resolution details */}
          <div className="col-span-12 lg:col-span-4 space-y-6">
            {activeResolve ? (
              <Card className="p-5 border-[var(--color-accent)] shadow-[var(--shadow-card)] bg-white space-y-5">
                <div className="border-b pb-3 flex items-start gap-2">
                  <ShieldAlert className="h-5 w-5 text-[var(--color-accent)] mt-0.5 shrink-0" />
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                      Résolution de conflit
                    </h3>
                    <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
                      Sélectionnez la valeur correcte à enregistrer dans la Master List
                    </p>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="text-xs text-[var(--color-text-primary)]">
                    Participant : <strong className="font-semibold">{activeResolve.participant}</strong>
                  </div>

                  <div className="space-y-3">
                    <div className="rounded-md border p-3 bg-slate-50 space-y-2 hover:border-[var(--color-accent)] cursor-pointer" onClick={() => handleResolveConflict(activeResolve.details.val_client)}>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Source Client</span>
                        <Badge className="bg-slate-200 text-slate-700 hover:bg-slate-200/90 text-[9px]">Conserver</Badge>
                      </div>
                      <div className="text-sm font-bold text-[var(--color-text-primary)]">
                        {activeResolve.details.val_client}
                      </div>
                    </div>

                    <div className="rounded-md border p-3 bg-slate-50 space-y-2 hover:border-[var(--color-accent)] cursor-pointer" onClick={() => handleResolveConflict(activeResolve.details.val_fcm)}>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Source FCM Broker</span>
                        <Badge className="bg-slate-200 text-slate-700 hover:bg-slate-200/90 text-[9px]">Conserver</Badge>
                      </div>
                      <div className="text-sm font-bold text-[var(--color-text-primary)]">
                        {activeResolve.details.val_fcm}
                      </div>
                    </div>
                  </div>

                  <div className="text-[10px] text-[var(--color-text-secondary)] leading-relaxed">
                    💡 La valeur choisie écrasera les données actuelles de la Master List et verrouillera le champ pour empêcher toute écriture lors des ré-imports futurs.
                  </div>
                </div>

                <Button variant="outline" size="sm" className="w-full text-xs h-9 border-[var(--color-border)]" onClick={() => setActiveResolve(null)}>
                  Fermer
                </Button>
              </Card>
            ) : (
              <Card className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white space-y-4">
                <h4 className="text-sm font-semibold text-[var(--color-text-primary)]">Instructions</h4>
                <div className="space-y-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
                  <p>
                    Les exceptions proviennent d'incohérences de données détectées lors de la consolidation de vos fichiers importés.
                  </p>
                  <div className="flex gap-2 items-start">
                    <UserCheck className="h-4 w-4 text-[var(--color-accent)] shrink-0" />
                    <span><strong>Consolidation Non Destructive :</strong> Résoudre un conflit verrouille le champ sélectionné afin d'éviter qu'une mise à jour future n'écrase votre correction.</span>
                  </div>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
