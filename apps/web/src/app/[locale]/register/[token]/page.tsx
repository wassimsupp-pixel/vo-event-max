'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { Loader2, AlertCircle, CheckCircle2, Lock } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { EventMaxLogo } from '@/components/ui/EventMaxLogo'

type LoadState =
  | { status: 'loading' }
  | { status: 'invalid' }
  | { status: 'closed'; eventName: string }
  | { status: 'ready'; eventName: string }
  | { status: 'submitted' }

const fieldClass = cn(
  'w-full rounded-lg border border-[var(--color-border)] px-3 py-2.5 text-sm',
  'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)]',
  'outline-none transition-all bg-white',
  'focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-light)]',
  'disabled:opacity-60'
)

function Field({
  id, label, required, children,
}: { id: string; label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-[var(--color-text-primary)]">
        {label} {required && <span className="text-[var(--color-danger)]">*</span>}
      </label>
      {children}
    </div>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[var(--color-accent-light)] via-white to-[var(--color-cta-light)] px-4 py-10">
      <div className="w-full max-w-[560px]">
        <div
          className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white"
          style={{ boxShadow: 'var(--shadow-modal)' }}
        >
          <div className="px-8 pb-4 pt-8 text-center">
            <div className="mb-4 flex flex-col items-center justify-center select-none">
              <EventMaxLogo className="h-12 w-auto text-[var(--color-text-primary)]" />
              <span className="mt-2 text-[10px] font-medium text-[var(--color-text-secondary)]">Powered by VO Communication Group</span>
            </div>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}

export default function PublicRegistrationPage() {
  const params = useParams()
  const token = params.token as string

  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState({
    first_name: '', last_name: '', email: '', company: '', phone: '', nationality: '',
    dietary_requirements: '', food_allergy_info: '', special_requests: '', room_preference: '',
    pmr_needs: '', remarks: '', consent: false,
    website: '', // honeypot — left empty by real visitors, never shown
  })

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const info = await api.publicRegistration.getInfo(token)
        if (cancelled) return
        setState(info.is_open ? { status: 'ready', eventName: info.event_name } : { status: 'closed', eventName: info.event_name })
      } catch {
        if (!cancelled) setState({ status: 'invalid' })
      }
    }
    if (token) load()
    return () => { cancelled = true }
  }, [token])

  const setField = (field: keyof typeof form) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const value = e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value
    setForm((f) => ({ ...f, [field]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!form.consent) {
      setError('Merci de cocher la case de consentement pour continuer.')
      return
    }
    setSubmitting(true)
    try {
      await api.publicRegistration.submit(token, form)
      setState({ status: 'submitted' })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue. Merci de réessayer.")
    } finally {
      setSubmitting(false)
    }
  }

  if (state.status === 'loading') {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-3 px-8 pb-10">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
          <p className="text-sm text-[var(--color-text-secondary)]">Chargement du formulaire...</p>
        </div>
      </Shell>
    )
  }

  if (state.status === 'invalid') {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-3 px-8 pb-10 text-center">
          <AlertCircle className="h-8 w-8 text-[var(--color-danger)]" />
          <h1 className="text-lg font-bold text-[var(--color-text-primary)]">Formulaire introuvable</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Ce lien d&apos;inscription n&apos;est plus valide. Contactez l&apos;organisateur de l&apos;événement pour obtenir le bon lien.
          </p>
        </div>
      </Shell>
    )
  }

  if (state.status === 'closed') {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-3 px-8 pb-10 text-center">
          <Lock className="h-8 w-8 text-[var(--color-text-secondary)]" />
          <h1 className="text-lg font-bold text-[var(--color-text-primary)]">Inscriptions fermées</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Les inscriptions pour <strong>{state.eventName}</strong> ne sont plus ouvertes. Contactez l&apos;organisateur si vous pensez qu&apos;il s&apos;agit d&apos;une erreur.
          </p>
        </div>
      </Shell>
    )
  }

  if (state.status === 'submitted') {
    return (
      <Shell>
        <div className="flex flex-col items-center gap-3 px-8 pb-10 text-center">
          <CheckCircle2 className="h-8 w-8 text-[var(--color-success)]" />
          <h1 className="text-lg font-bold text-[var(--color-text-primary)]">Inscription bien reçue !</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Merci, vos informations ont été transmises à l&apos;organisateur. Vous pouvez fermer cette page.
          </p>
        </div>
      </Shell>
    )
  }

  return (
    <Shell>
      <form onSubmit={handleSubmit} className="px-8 pb-8">
        <h1 className="mb-1 text-center text-lg font-bold text-[var(--color-text-primary)]">{state.eventName}</h1>
        <p className="mb-6 text-center text-sm text-[var(--color-text-secondary)]">
          Merci de compléter vos informations pour cet événement.
        </p>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-[var(--color-danger-light)] p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-danger)]" />
            <p className="text-sm text-[var(--color-danger)]">{error}</p>
          </div>
        )}

        {/* Honeypot — hidden from real visitors, bots fill every field they find */}
        <div className="hidden" aria-hidden="true">
          <label htmlFor="website">Ne pas remplir ce champ</label>
          <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" value={form.website} onChange={setField('website')} />
        </div>

        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <Field id="first_name" label="Prénom" required>
            <input id="first_name" type="text" required value={form.first_name} onChange={setField('first_name')} className={fieldClass} disabled={submitting} />
          </Field>
          <Field id="last_name" label="Nom" required>
            <input id="last_name" type="text" required value={form.last_name} onChange={setField('last_name')} className={fieldClass} disabled={submitting} />
          </Field>
        </div>

        <Field id="email" label="Adresse email" required>
          <input id="email" type="email" required value={form.email} onChange={setField('email')} className={fieldClass} disabled={submitting} />
        </Field>

        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <Field id="company" label="Société">
            <input id="company" type="text" value={form.company} onChange={setField('company')} className={fieldClass} disabled={submitting} />
          </Field>
          <Field id="phone" label="Téléphone">
            <input id="phone" type="tel" value={form.phone} onChange={setField('phone')} className={fieldClass} disabled={submitting} />
          </Field>
        </div>

        <Field id="nationality" label="Nationalité">
          <input id="nationality" type="text" value={form.nationality} onChange={setField('nationality')} className={fieldClass} disabled={submitting} />
        </Field>

        <div className="my-5 border-t border-[var(--color-border)] pt-5">
          <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-primary)]">Informations complémentaires</h2>
        </div>

        <Field id="dietary_requirements" label="Régime alimentaire">
          <input id="dietary_requirements" type="text" placeholder="Ex. Végétarien, halal, sans gluten..." value={form.dietary_requirements} onChange={setField('dietary_requirements')} className={fieldClass} disabled={submitting} />
        </Field>

        <Field id="food_allergy_info" label="Allergies">
          <input id="food_allergy_info" type="text" placeholder="Ex. Arachides, fruits de mer..." value={form.food_allergy_info} onChange={setField('food_allergy_info')} className={fieldClass} disabled={submitting} />
        </Field>

        <Field id="room_preference" label="Préférences de chambre">
          <input id="room_preference" type="text" placeholder="Ex. Lit double, chambre non-fumeur..." value={form.room_preference} onChange={setField('room_preference')} className={fieldClass} disabled={submitting} />
        </Field>

        <Field id="pmr_needs" label="Besoins d'accessibilité (PMR)">
          <input id="pmr_needs" type="text" placeholder="Ex. Accès fauteuil roulant, chambre accessible..." value={form.pmr_needs} onChange={setField('pmr_needs')} className={fieldClass} disabled={submitting} />
        </Field>

        <Field id="special_requests" label="Demandes spéciales">
          <textarea id="special_requests" rows={2} value={form.special_requests} onChange={setField('special_requests')} className={fieldClass} disabled={submitting} />
        </Field>

        <Field id="remarks" label="Remarques">
          <textarea id="remarks" rows={2} value={form.remarks} onChange={setField('remarks')} className={fieldClass} disabled={submitting} />
        </Field>

        <label className="mb-6 mt-2 flex items-start gap-2.5 text-xs text-[var(--color-text-secondary)]">
          <input
            type="checkbox"
            checked={form.consent}
            onChange={setField('consent')}
            disabled={submitting}
            className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-[var(--color-border)]"
          />
          <span>
            J&apos;accepte que les informations transmises ci-dessus, y compris mes préférences alimentaires et mes besoins
            d&apos;accessibilité le cas échéant, soient utilisées par l&apos;organisateur dans le seul cadre de la préparation
            de cet événement. <span className="text-[var(--color-danger)]">*</span>
          </span>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[var(--color-accent)]/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {submitting ? 'Envoi en cours...' : "Envoyer mon inscription"}
        </button>
      </form>
    </Shell>
  )
}
