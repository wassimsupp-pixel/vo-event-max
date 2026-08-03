'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Link2, Copy, Check, Loader2, ExternalLink, Users, Info, AlertTriangle } from 'lucide-react'
import { api, errorMessage } from '@/lib/api'

// Virtual uploaded_files row the API creates for public submissions
// (routers/public_registration.py). Its row count is how many people have
// filled the form, so the page can report intake without a new endpoint.
const FORM_FILENAME = "Formulaire d'inscription en ligne"

export default function RegistrationFormPage() {
  const params = useParams()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const [link, setLink] = useState<{ url: string; is_open: boolean } | null>(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)
  const [copied, setCopied] = useState(false)
  const [submissions, setSubmissions] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadLink = useCallback(async () => {
    try {
      const info = await api.events.getRegistrationLink(eventId)
      // Built from the browser's own origin + the organizer's current locale,
      // so the shared link matches the domain in use and opens in their
      // language (the API's own url hardcodes /fr/).
      setLink({ url: `${window.location.origin}/${locale}/register/${info.token}`, is_open: info.is_open })
      setUnavailable(null)
    } catch (err) {
      setUnavailable(errorMessage(err, "Le lien d'inscription n'est pas disponible pour cet événement."))
      setLink(null)
    } finally {
      setLoading(false)
    }
  }, [eventId, locale])

  const loadSubmissions = useCallback(async () => {
    try {
      const files = await api.files.list(eventId)
      const form = files.find((f) => f.filename === FORM_FILENAME)
      setSubmissions(form ? form.row_count : 0)
    } catch {
      setSubmissions(null)   // best-effort — never block the link on this
    }
  }, [eventId])

  useEffect(() => {
    loadLink()
    loadSubmissions()
  }, [loadLink, loadSubmissions])

  const handleCopy = async () => {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setActionError('Copie impossible depuis ce navigateur — sélectionnez le lien manuellement.')
    }
  }

  const handleToggle = async () => {
    if (!link || toggling) return
    setToggling(true)
    setActionError(null)
    try {
      const res = await api.events.setRegistrationOpen(eventId, !link.is_open)
      setLink((prev) => (prev ? { ...prev, is_open: res.is_open } : prev))
    } catch (err) {
      setActionError(errorMessage(err, 'Impossible de modifier le statut des inscriptions.'))
    } finally {
      setToggling(false)
    }
  }

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle="Formulaire d'inscription"
      pageSubtitle="Partagez un lien public : les réponses alimentent directement la master list"
    >
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
            Formulaire d&apos;inscription
          </h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            Envoyez ce lien à vos participants pour qu&apos;ils remplissent eux-mêmes leurs
            informations.
          </p>
        </div>

        {actionError && (
          <div className="rounded-lg border border-[var(--color-danger)] bg-[var(--color-danger-light)] px-4 py-3 text-sm text-[var(--color-danger)]">
            {actionError}
          </div>
        )}

        {loading ? (
          <Card className="flex items-center gap-2 p-6 text-sm text-[var(--color-text-secondary)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Chargement du lien…
          </Card>
        ) : unavailable ? (
          <Card className="p-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-warning)]" />
              <div>
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Lien indisponible
                </p>
                <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{unavailable}</p>
              </div>
            </div>
          </Card>
        ) : link ? (
          <>
            <Card className="p-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <Link2 className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-accent)]" />
                  <div>
                    <p className="text-sm font-semibold text-[var(--color-text-primary)]">
                      Lien public de cet événement
                    </p>
                    <p className="text-xs text-[var(--color-text-secondary)]">
                      Aucun compte n&apos;est nécessaire pour le remplir.
                    </p>
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={
                    link.is_open
                      ? 'border-[var(--color-success)] bg-[var(--color-success-light)] text-[var(--color-success)]'
                      : 'border-[var(--color-text-secondary)] bg-slate-50 text-[var(--color-text-secondary)]'
                  }
                >
                  {link.is_open ? 'Inscriptions ouvertes' : 'Inscriptions fermées'}
                </Badge>
              </div>

              <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
                <input
                  readOnly
                  value={link.url}
                  onFocus={(e) => e.currentTarget.select()}
                  className="w-full flex-1 truncate rounded-md border border-[var(--color-border)] bg-slate-50 px-3 py-2 text-xs text-[var(--color-text-secondary)] outline-none"
                />
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" type="button" onClick={handleCopy} className="flex items-center gap-1.5 whitespace-nowrap">
                    {copied ? <Check className="h-3.5 w-3.5 text-[var(--color-success)]" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? 'Copié' : 'Copier'}
                  </Button>
                  <a href={link.url} target="_blank" rel="noopener noreferrer">
                    <Button variant="outline" type="button" className="flex items-center gap-1.5 whitespace-nowrap">
                      <ExternalLink className="h-3.5 w-3.5" />
                      Aperçu
                    </Button>
                  </a>
                  <Button
                    variant="outline"
                    type="button"
                    onClick={handleToggle}
                    disabled={toggling}
                    className="whitespace-nowrap"
                  >
                    {toggling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : link.is_open ? 'Fermer les inscriptions' : 'Rouvrir les inscriptions'}
                  </Button>
                </div>
              </div>

              {!link.is_open && (
                <p className="mt-3 text-xs text-[var(--color-text-secondary)]">
                  Le lien reste valide mais refuse toute nouvelle réponse tant qu&apos;il est fermé.
                </p>
              )}
            </Card>

            <div className="grid gap-4 sm:grid-cols-2">
              <Card className="p-5">
                <div className="flex items-center gap-3">
                  <Users className="h-5 w-5 text-[var(--color-accent)]" />
                  <div>
                    <p className="text-2xl font-bold text-[var(--color-text-primary)]">
                      {submissions === null ? '—' : submissions}
                    </p>
                    <p className="text-xs text-[var(--color-text-secondary)]">
                      {submissions === null
                        ? 'Nombre de réponses indisponible'
                        : 'réponse(s) reçue(s) via ce lien'}
                    </p>
                  </div>
                </div>
              </Card>

              <Card className="p-5">
                <div className="flex items-start gap-3">
                  <Info className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-text-secondary)]" />
                  <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                    Chaque réponse déclenche une consolidation automatique : le participant
                    apparaît dans la master list en quelques secondes, fusionné avec vos autres
                    sources s&apos;il y figure déjà.
                  </p>
                </div>
              </Card>
            </div>
          </>
        ) : null}
      </div>
    </AppLayout>
  )
}
