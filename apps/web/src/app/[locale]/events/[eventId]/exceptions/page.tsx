'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertCircle, AlertTriangle, Info, CheckCircle2, UserCheck, ShieldAlert, Sparkles, Loader2, Mail, Phone, Globe, Utensils, Plus, ChevronDown, ChevronRight, ClipboardList } from 'lucide-react'
import { api, type Exception } from '@/lib/api'

// Sub-categories of "Champs manquants" — the actionable editable fiche fields.
const MISSING_FIELD_META: Record<string, { label: string; icon: React.ElementType }> = {
  first_name: { label: 'Prénom', icon: UserCheck },
  email: { label: 'Email', icon: Mail },
  phone: { label: 'Téléphone', icon: Phone },
  nationality: { label: 'Nationalité', icon: Globe },
  dietary_requirements: { label: 'Régime alimentaire', icon: Utensils },
}
const MISSING_FIELD_ORDER = ['first_name', 'email', 'phone', 'nationality', 'dietary_requirements']

const EXC_TYPE_LABELS: Record<string, string> = {
  conflict: 'Conflit de données',
  DATA_CONFLICT: 'Conflit de données',
  duplicate: 'Doublon possible',
  POSSIBLE_DUPLICATE: 'Doublon possible',
  DUPLICATE_EMAIL: 'Email en double',
  not_found: 'Participant non retrouvé',
  to_verify: 'À vérifier',
  PARTICIPANT_NO_FLIGHT: 'Pas de vol',
  PARTICIPANT_NO_HOTEL: 'Pas d’hôtel',
  PARTICIPANT_NO_TRANSFER: 'Pas de transfert',
  PARTICIPANT_NO_DIETARY: 'Pas d’info régime',
  MISSING_CONTACT: 'Aucun contact (email/tél.)',
  MISSING_REQUIRED_FIELD: 'Champ requis manquant',
  INVALID_FORMAT: 'Format invalide',
  DATE_INCOHERENCE: 'Incohérence de dates',
  FLIGHT_NO_PARTICIPANT: 'Vol sans participant',
  NAME_DIVERGENCE: 'Noms divergents entre sources',
  PROBABLE_MATCH: 'Correspondance à confirmer',
  coverage: 'Couverture',
}
const excTypeLabel = (t: string) => EXC_TYPE_LABELS[t] || t

export default function ExceptionsPage() {
  const params = useParams()
  const router = useRouter()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')
  const tExc = useTranslations('exceptions')

  // Optional deep-link filter, e.g. /exceptions?type=conflict from the dashboard.
  // Read from window on mount to avoid a static-prerender bail-out on useSearchParams.
  type ExceptionType = 'conflict' | 'duplicate' | 'not_found' | 'to_verify' | 'coverage' | 'missing_field'
  const validTypes: ExceptionType[] = ['conflict', 'duplicate', 'not_found', 'to_verify', 'coverage', 'missing_field']
  const [typeFilter, setTypeFilter] = useState<ExceptionType | null>(null)
  const [openSubs, setOpenSubs] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const rawType = new URLSearchParams(window.location.search).get('type')
    if (validTypes.includes(rawType as ExceptionType)) {
      // Reading a URL query param once on mount is a legitimate one-off sync.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTypeFilter(rawType as ExceptionType)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const typeLabels: Record<ExceptionType, string> = {
    conflict: tExc('conflict'),
    duplicate: tExc('duplicate'),
    not_found: tExc('notFound'),
    to_verify: tExc('toCheck'),
    coverage: tExc('coverage'),
    missing_field: 'Champs manquants',
  }

  const [exceptions, setExceptions] = useState<Exception[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [resolving, setResolving] = useState<string | null>(null)
  const [activeResolve, setActiveResolve] = useState<Exception | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const loadExceptions = async () => {
    try {
      setLoading(true)
      const data = await api.exceptions.list(eventId)
      setExceptions(data.filter(e => !e.resolved))
    } catch {
      setError('Impossible de charger les exceptions.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadExceptions()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId])

  const handleResolveConflict = async (resolution: string) => {
    if (!activeResolve) return

    setResolving(activeResolve.id)
    try {
      await api.exceptions.resolve(activeResolve.id, resolution)
      setSuccessMessage(`Conflit résolu pour ${activeResolve.participant_name ?? activeResolve.id}. Valeur retenue : "${resolution}".`)
      setTimeout(() => setSuccessMessage(null), 3000)
      setActiveResolve(null)
      await loadExceptions()
    } catch {
      setError('Erreur lors de la résolution du conflit.')
    } finally {
      setResolving(null)
    }
  }

  const handleResolveSimple = async (exc: Exception) => {
    setResolving(exc.id)
    try {
      await api.exceptions.resolve(exc.id, 'resolved')
      setSuccessMessage(`Exception marquée comme résolue.`)
      setTimeout(() => setSuccessMessage(null), 3000)
      await loadExceptions()
    } catch {
      setError('Erreur lors de la résolution.')
    } finally {
      setResolving(null)
    }
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

  const filteredExceptions = typeFilter
    ? exceptions.filter((e) => e.type === typeFilter)
    : exceptions

  // "Champs manquants" get a dedicated grouped-by-field rendering (one row per
  // participant with an "Ajouter" button). Everything else stays a flat list.
  const missingFieldExcs = filteredExceptions.filter((e) => e.type === 'missing_field')
  const flatExcs = filteredExceptions.filter((e) => e.type !== 'missing_field')
  const missingBySub: Record<string, Exception[]> = {}
  for (const f of MISSING_FIELD_ORDER) missingBySub[f] = []
  for (const e of missingFieldExcs) {
    const mf = (e.context_data?.missing_fields as string[] | undefined) || []
    for (const f of mf) if (missingBySub[f]) missingBySub[f].push(e)
  }
  const goToParticipant = (pid?: string, field?: string) => {
    if (!pid) return
    router.push(`/${locale}/events/${eventId}/participants/${pid}${field ? `?field=${field}` : ''}`)
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
            {loading ? '\u2026' : `${filteredExceptions.length} exceptions en attente de traitement`}
          </p>
        </div>

        {/* Type filter (deep-linkable from the dashboard) */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setTypeFilter(null)}
            className={
              'rounded-full px-3 py-1 text-xs font-semibold transition-colors ' +
              (typeFilter === null
                ? 'bg-[var(--color-accent)] text-white'
                : 'border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)]')
            }
          >
            {tExc('filterAll')}
          </button>
          {validTypes.map((vt) => (
            <button
              key={vt}
              onClick={() => setTypeFilter(vt)}
              className={
                'rounded-full px-3 py-1 text-xs font-semibold transition-colors ' +
                (typeFilter === vt
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)]')
              }
            >
              {typeLabels[vt]}
            </button>
          ))}
        </div>

        {successMessage && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-success-light)] border border-[var(--color-success)]/20 text-[var(--color-success)] text-sm font-medium animate-fade-in">
            <CheckCircle2 className="h-5 w-5 shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-sm font-medium">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          {/* Main Exceptions List */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {loading ? (
              <Card className="p-8 border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent)]" />
              </Card>
            ) : filteredExceptions.length === 0 ? (
              <Card className="p-8 text-center border-[var(--color-border)] shadow-[var(--shadow-card)] flex flex-col items-center justify-center space-y-3 bg-white">
                <div className="h-12 w-12 rounded-full bg-[var(--color-success-light)] flex items-center justify-center">
                  <CheckCircle2 className="h-6 w-6 text-[var(--color-success)]" />
                </div>
                <h3 className="font-semibold text-sm text-[var(--color-text-primary)]">Félicitations !</h3>
                <p className="text-xs text-[var(--color-text-secondary)]">Aucune anomalie ou conflit de données n&apos;est en attente.</p>
              </Card>
            ) : (
              <>
              {/* Champs manquants — grouped by field, each with an "Ajouter" button */}
              {missingFieldExcs.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <ClipboardList className="h-5 w-5 text-[var(--color-accent)]" />
                    <h2 className="text-sm font-bold text-[var(--color-text-primary)]">Champs manquants</h2>
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      — cliquez « Ajouter » pour compléter la fiche du participant
                    </span>
                  </div>
                  {MISSING_FIELD_ORDER.filter((f) => missingBySub[f].length > 0).map((f) => {
                    const meta = MISSING_FIELD_META[f]
                    const Icon = meta.icon
                    const items = missingBySub[f]
                    const open = openSubs[f] ?? true
                    return (
                      <Card key={f} className="overflow-hidden border-[var(--color-border)] shadow-[var(--shadow-card)] bg-white p-0">
                        <button
                          onClick={() => setOpenSubs((s) => ({ ...s, [f]: !(s[f] ?? true) }))}
                          className="flex w-full items-center justify-between px-5 py-3 hover:bg-slate-50"
                        >
                          <span className="flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
                            <Icon className="h-4 w-4 text-[var(--color-accent)]" />
                            {meta.label}
                            <Badge className="bg-[var(--color-accent-light)] text-[var(--color-accent)] border-0">{items.length}</Badge>
                          </span>
                          {open ? <ChevronDown className="h-4 w-4 text-[var(--color-text-secondary)]" /> : <ChevronRight className="h-4 w-4 text-[var(--color-text-secondary)]" />}
                        </button>
                        {open && (
                          <div className="divide-y border-t">
                            {items.map((e) => (
                              <div key={e.id} className="flex items-center justify-between gap-3 px-5 py-2.5">
                                <span className="text-sm text-[var(--color-text-primary)] truncate">
                                  {e.participant_name || (e.context_data?.participant_name as string) || '—'}
                                </span>
                                <Button
                                  size="sm"
                                  className="h-8 shrink-0 bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90 text-xs"
                                  onClick={() => goToParticipant(e.participant_id, f)}
                                >
                                  <Plus className="mr-1 h-3.5 w-3.5" /> Ajouter
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}
                      </Card>
                    )
                  })}
                </div>
              )}

              {/* Flat list for all other exception types */}
              {flatExcs.map((exc) => (
                <Card
                  key={exc.id}
                  className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] hover:border-slate-300 transition-all bg-white flex items-start gap-4"
                >
                  <div className="mt-0.5">{getSeverityIcon(exc.severity)}</div>
                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-semibold text-[var(--color-text-primary)] truncate">
                        {exc.participant_name ?? excTypeLabel(exc.exception_type ?? exc.type)}
                      </h3>
                      {getSeverityBadge(exc.severity)}
                      <Badge variant="outline" className="text-[10px] border-slate-200">
                        {excTypeLabel(exc.exception_type ?? exc.type)}
                      </Badge>
                    </div>

                    <p className="text-xs text-[var(--color-text-secondary)] font-medium leading-relaxed">
                      {exc.message}
                    </p>

                    <div className="pt-2 flex items-center gap-2">
                      {exc.type === 'conflict' && exc.value_a !== undefined && exc.value_b !== undefined ? (
                        <Button
                          size="sm"
                          className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white text-xs h-8"
                          onClick={() => setActiveResolve(exc)}
                          disabled={resolving === exc.id}
                        >
                          {resolving === exc.id ? (
                            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                          ) : (
                            <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                          )}
                          Résoudre le conflit
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs h-8 border-[var(--color-border)]"
                          onClick={() => handleResolveSimple(exc)}
                          disabled={resolving === exc.id}
                        >
                          {resolving === exc.id ? (
                            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
                          )}
                          Marquer comme résolu
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
              </>
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
                    Participant : <strong className="font-semibold">{activeResolve.participant_name ?? '\u2014'}</strong>
                  </div>

                  <div className="space-y-3">
                    <div
                      className="rounded-md border p-3 bg-slate-50 space-y-2 hover:border-[var(--color-accent)] cursor-pointer"
                      onClick={() => handleResolveConflict(activeResolve.value_a || '')}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                          {activeResolve.source_a ?? 'Source A'}
                        </span>
                        <Badge className="bg-slate-200 text-slate-700 hover:bg-slate-200/90 text-[9px]">Conserver</Badge>
                      </div>
                      <div className="text-sm font-bold text-[var(--color-text-primary)]">
                        {activeResolve.value_a}
                      </div>
                    </div>

                    <div
                      className="rounded-md border p-3 bg-slate-50 space-y-2 hover:border-[var(--color-accent)] cursor-pointer"
                      onClick={() => handleResolveConflict(activeResolve.value_b || '')}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                          {activeResolve.source_b ?? 'Source B'}
                        </span>
                        <Badge className="bg-slate-200 text-slate-700 hover:bg-slate-200/90 text-[9px]">Conserver</Badge>
                      </div>
                      <div className="text-sm font-bold text-[var(--color-text-primary)]">
                        {activeResolve.value_b}
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
                    Les exceptions proviennent d&apos;incohérences de données détectées lors de la consolidation de vos fichiers importés.
                  </p>
                  <div className="flex gap-2 items-start">
                    <UserCheck className="h-4 w-4 text-[var(--color-accent)] shrink-0" />
                    <span><strong>Consolidation Non Destructive :</strong> Résoudre un conflit verrouille le champ sélectionné afin d&apos;éviter qu&apos;une mise à jour future n&apos;écrase votre correction.</span>
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
