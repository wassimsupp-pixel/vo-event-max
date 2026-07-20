'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { GitMerge, Loader2, CheckCircle2, Users, ArrowRight, Sparkles, ShieldQuestion, Mail, Phone, Building2, Globe, Check } from 'lucide-react'
import { api, type MatchCandidate, type MatchCandidateParty } from '@/lib/api'

const REC_STYLE: Record<string, { label: string; cls: string; icon: React.ElementType }> = {
  fusionner: { label: 'IA : probablement la même personne', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: Sparkles },
  separer: { label: 'IA : probablement deux personnes', cls: 'bg-rose-50 text-rose-700 border-rose-200', icon: Users },
  incertain: { label: 'IA : incertain — à trancher', cls: 'bg-amber-50 text-amber-700 border-amber-200', icon: ShieldQuestion },
}

// Fields the user can pick a side for. `api` is the participant column name.
const CHOOSABLE = [
  { key: 'email', api: 'email', label: 'Email', icon: Mail },
  { key: 'telephone', api: 'phone', label: 'Téléphone', icon: Phone },
  { key: 'societe', api: 'company', label: 'Société', icon: Building2 },
  { key: 'nationalite', api: 'nationality', label: 'Nationalité', icon: Globe },
] as const

const partyVal = (p: MatchCandidateParty | null | undefined, key: string): string =>
  ((p as Record<string, unknown> | null | undefined)?.[key] as string | null | undefined)?.trim() || ''

export default function MatchReviewPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const [candidates, setCandidates] = useState<MatchCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [statusMsg, setStatusMsg] = useState('')
  // Per-candidate, per-field side choice: { [candidateId]: { email: 'a' | 'b' } }
  const [choices, setChoices] = useState<Record<string, Record<string, 'a' | 'b'>>>({})

  // Default side for a field: the surviving fiche (b) when it has a value,
  // otherwise the other one — i.e. exactly what a plain merge would keep.
  const sideFor = (c: MatchCandidate, key: string): 'a' | 'b' => {
    const explicit = choices[c.id]?.[key]
    if (explicit) return explicit
    return partyVal(c.details_b, key) ? 'b' : 'a'
  }
  const pick = (candId: string, key: string, side: 'a' | 'b') =>
    setChoices((prev) => ({ ...prev, [candId]: { ...(prev[candId] || {}), [key]: side } }))

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.matching.candidates(eventId)
      setCandidates(data)
    } catch (err) {
      console.error('Failed to load match candidates', err)
    } finally {
      setLoading(false)
    }
  }, [eventId])

  useEffect(() => { load() }, [load])

  const resolve = async (c: MatchCandidate, decision: 'fusionner' | 'separer') => {
    setBusyId(c.id)
    setStatusMsg('')
    try {
      // Send the chosen value for every field the user could pick a side for.
      let keep: Record<string, string> | undefined
      if (decision === 'fusionner') {
        keep = {}
        for (const f of CHOOSABLE) {
          const side = sideFor(c, f.key)
          const val = partyVal(side === 'a' ? c.details_a : c.details_b, f.key)
          if (val) keep[f.api] = val
        }
        if (Object.keys(keep).length === 0) keep = undefined
      }
      const res = await api.matching.resolve(c.id, decision, keep)
      setCandidates(prev => prev.filter(x => x.id !== c.id))
      setStatusMsg(res.message || (decision === 'fusionner' ? 'Fiches fusionnées.' : 'Fiches conservées séparées.'))
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : 'Erreur lors de la décision.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <AppLayout eventId={eventId} locale={locale} pageTitle="Fusions à vérifier">
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="border-b pb-5">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-[var(--color-text-primary)]">
            <GitMerge className="h-6 w-6 text-[var(--color-accent)]" />
            Fusions à vérifier
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Paires de participants que le moteur n&apos;a pas pu trancher seul. L&apos;IA a donné un avis ; à vous de confirmer la fusion ou de garder les fiches séparées.
            Quand les deux fiches diffèrent sur un champ, <strong>cliquez la valeur à conserver</strong> avant de fusionner.
          </p>
        </div>

        {statusMsg && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            {statusMsg}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16 text-sm text-[var(--color-text-secondary)]">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Chargement…
          </div>
        ) : candidates.length === 0 ? (
          <Card className="flex flex-col items-center gap-2 p-12 text-center">
            <CheckCircle2 className="h-10 w-10 text-[var(--color-success)]" />
            <p className="text-base font-semibold text-[var(--color-text-primary)]">Aucune fusion à vérifier</p>
            <p className="max-w-md text-sm text-[var(--color-text-secondary)]">
              Le moteur a tout tranché automatiquement. Les cas réellement ambigus apparaîtront ici après une consolidation.
            </p>
          </Card>
        ) : (
          <div className="space-y-5">
            {candidates.map((c) => {
              const rec = REC_STYLE[c.ai_recommendation || 'incertain'] || REC_STYLE.incertain
              const RecIcon = rec.icon
              return (
                <Card key={c.id} className="p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${rec.cls}`}>
                      <RecIcon className="h-3.5 w-3.5" /> {rec.label}
                      {typeof c.ai_confidence === 'number' && c.ai_confidence > 0 ? ` (${Math.round(c.ai_confidence)}%)` : ''}
                    </span>
                    {typeof c.deterministic_score === 'number' && (
                      <span className="text-xs font-medium text-[var(--color-text-secondary)]">
                        Similarité du nom : {Math.round(c.deterministic_score)}%
                      </span>
                    )}
                  </div>

                  {c.ai_justification && (
                    <p className="rounded-md bg-slate-50 px-3 py-2 text-sm italic text-[var(--color-text-secondary)]">
                      « {c.ai_justification} »
                    </p>
                  )}

                  <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
                    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-px bg-[var(--color-border)]">
                      <div className="truncate bg-slate-100 px-3 py-2 text-sm font-bold text-[var(--color-text-primary)]">
                        {c.details_a?.nom || c.name_a || '—'}
                      </div>
                      <div className="truncate bg-slate-100 px-3 py-2 text-sm font-bold text-[var(--color-text-primary)]">
                        {c.details_b?.nom || c.name_b || '—'}
                      </div>
                    </div>

                    {CHOOSABLE.map((f) => {
                      const va = partyVal(c.details_a, f.key)
                      const vb = partyVal(c.details_b, f.key)
                      if (!va && !vb) return null
                      const side = sideFor(c, f.key)
                      const bothDiffer = !!va && !!vb && va !== vb
                      const Icon = f.icon
                      const cell = (val: string, mine: 'a' | 'b') => {
                        const selected = side === mine && !!val
                        const selectable = !!val && bothDiffer
                        return (
                          <button
                            type="button"
                            disabled={!selectable}
                            onClick={() => selectable && pick(c.id, f.key, mine)}
                            className={`flex items-start gap-2 px-3 py-2 text-left text-xs transition-colors ${
                              !val
                                ? 'bg-white italic text-slate-400'
                                : selected
                                ? 'bg-[var(--color-accent-light)] font-semibold text-[var(--color-text-primary)] ring-1 ring-inset ring-[var(--color-accent)]'
                                : 'bg-white text-[var(--color-text-secondary)] hover:bg-slate-50'
                            } ${selectable ? 'cursor-pointer' : 'cursor-default'}`}
                          >
                            {selected ? (
                              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-accent)]" />
                            ) : (
                              <span className="w-3.5 shrink-0" />
                            )}
                            <span className="break-all">{val || 'non renseigné'}</span>
                          </button>
                        )
                      }
                      return (
                        <div key={f.key}>
                          <div className="flex items-center gap-1.5 bg-slate-50/70 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
                            <Icon className="h-3 w-3" /> {f.label}
                            {bothDiffer && (
                              <span className="ml-1 rounded bg-amber-100 px-1 py-0.5 text-[9px] font-bold text-amber-700">
                                à choisir
                              </span>
                            )}
                          </div>
                          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-px bg-[var(--color-border)]">
                            {cell(va, 'a')}
                            {cell(vb, 'b')}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-4">
                    <Button
                      variant="outline"
                      onClick={() => resolve(c, 'separer')}
                      disabled={busyId === c.id}
                    >
                      Garder séparé
                    </Button>
                    <Button
                      className="flex items-center gap-2 bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90"
                      onClick={() => resolve(c, 'fusionner')}
                      disabled={busyId === c.id}
                    >
                      {busyId === c.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitMerge className="h-4 w-4" />}
                      Fusionner en une fiche <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
