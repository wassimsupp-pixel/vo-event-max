'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { GitMerge, Loader2, CheckCircle2, Users, ArrowRight, Sparkles, ShieldQuestion, Mail, Phone, Building2, Globe } from 'lucide-react'
import { api, type MatchCandidate, type MatchCandidateParty } from '@/lib/api'

const REC_STYLE: Record<string, { label: string; cls: string; icon: React.ElementType }> = {
  fusionner: { label: 'IA : probablement la même personne', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: Sparkles },
  separer: { label: 'IA : probablement deux personnes', cls: 'bg-rose-50 text-rose-700 border-rose-200', icon: Users },
  incertain: { label: 'IA : incertain — à trancher', cls: 'bg-amber-50 text-amber-700 border-amber-200', icon: ShieldQuestion },
}

function Party({ p, fallbackName }: { p?: MatchCandidateParty | null; fallbackName?: string | null }) {
  const rows: { icon: React.ElementType; value?: string | null }[] = [
    { icon: Mail, value: p?.email },
    { icon: Phone, value: p?.telephone },
    { icon: Building2, value: p?.societe },
    { icon: Globe, value: p?.nationalite },
  ]
  return (
    <div className="flex-1 rounded-lg border border-[var(--color-border)] bg-white p-4">
      <p className="text-sm font-bold text-[var(--color-text-primary)]">{p?.nom || fallbackName || '—'}</p>
      <ul className="mt-2 space-y-1.5">
        {rows.map((r, i) => (
          <li key={i} className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <r.icon className="h-3.5 w-3.5 shrink-0 opacity-70" />
            <span className={r.value ? '' : 'italic opacity-50'}>{r.value || 'non renseigné'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function MatchReviewPage() {
  const { eventId, locale } = useParams() as { eventId: string; locale: string }
  const [candidates, setCandidates] = useState<MatchCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [statusMsg, setStatusMsg] = useState('')

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
      const res = await api.matching.resolve(c.id, decision)
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

                  <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
                    <Party p={c.details_a} fallbackName={c.name_a} />
                    <div className="flex shrink-0 items-center justify-center text-[var(--color-text-secondary)]">
                      <span className="rounded-full border px-2 py-1 text-xs font-bold">= ?</span>
                    </div>
                    <Party p={c.details_b} fallbackName={c.name_b} />
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
