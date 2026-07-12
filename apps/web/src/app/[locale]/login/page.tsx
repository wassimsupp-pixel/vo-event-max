'use client'

import { useState, useTransition } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { Zap, Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { createClient } from '@/lib/supabase'
import { cn } from '@/lib/utils'

export default function LoginPage() {
  const router = useRouter()
  const params = useParams()
  const locale = (params?.locale as string) || 'fr'
  const [isPending, startTransition] = useTransition()
  const [isSignUp, setIsSignUp] = useState(false)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [language, setLanguage] = useState(locale)
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)

    startTransition(async () => {
      try {
        const supabase = createClient()
        if (isSignUp) {
          const { data, error } = await supabase.auth.signUp({
            email,
            password,
            options: {
              data: {
                full_name: fullName,
                preferred_language: language,
              },
            },
          })
          if (error) {
            setError(error.message)
            return
          }
          
          // Optionally attempt public.users table update
          if (data?.user) {
            try {
              await supabase.from('users').update({
                preferred_language: language,
              }).eq('id', data.user.id)
            } catch (dbErr) {
              console.warn('Could not update users table directly:', dbErr)
            }
          }
          
          setSuccess('Compte créé avec succès ! Connectez-vous avec vos identifiants.')
          setIsSignUp(false)
          setPassword('')
        } else {
          const { data, error } = await supabase.auth.signInWithPassword({ email, password })
          if (error) {
            setError(error.message === 'Invalid login credentials'
              ? 'Email ou mot de passe incorrect.'
              : error.message
            )
            return
          }
          
          let userLang = locale || 'fr'
          if (data?.user) {
            try {
              const { data: profile } = await supabase
                .from('users')
                .select('preferred_language')
                .eq('id', data.user.id)
                .single()
              if (profile?.preferred_language) {
                userLang = profile.preferred_language
              }
            } catch (pErr) {
              console.warn('Failed to load user language preference on login:', pErr)
            }
          }
          
          router.push(`/${userLang}/events/00000000-0000-0000-0000-000000000003/dashboard`)
          router.refresh()
        }
      } catch {
        setError('Une erreur inattendue est survenue. Veuillez réessayer.')
      }
    })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[var(--color-accent-light)] via-white to-[var(--color-cta-light)] px-4">
      <div className="w-full max-w-[400px]">
        {/* Card */}
        <div
          className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white"
          style={{ boxShadow: 'var(--shadow-modal)' }}
        >
          {/* Header */}
          <div className="px-8 pb-4 pt-8 text-center">
            <div className="mb-4 flex flex-col items-center justify-center select-none text-[var(--color-text-primary)]">
              <div className="w-[145px] h-[100px]">
                <svg className="w-full h-full" viewBox="0 0 160 110">
                  <text x="0" y="42" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="900" font-size="48" letter-spacing="-2px" fill="currentColor">VO</text>
                  <line x1="0" y1="54" x2="70" y2="54" stroke="currentColor" stroke-width="7" />
                  <text x="0" y="80" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="800" font-size="18" letter-spacing="-0.5px" fill="currentColor">communication</text>
                  <text x="0" y="100" font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="800" font-size="18" letter-spacing="-0.5px" fill="currentColor">group</text>
                </svg>
              </div>
              <span className="mt-1 text-[10px] font-bold uppercase tracking-[4px] text-[var(--color-accent)]">Event Max</span>
            </div>
            <h1 className="text-xl font-bold text-[var(--color-text-primary)]">
              {isSignUp ? 'Créer un compte' : 'Connexion'}
            </h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
              Plateforme de gestion événementielle
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="px-8 pb-6">
            {/* Error message */}
            {error && (
              <div className="mb-4 flex items-start gap-2 rounded-lg bg-[var(--color-danger-light)] p-3">
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-danger)]" />
                <p className="text-sm text-[var(--color-danger)]">{error}</p>
              </div>
            )}

            {/* Success message */}
            {success && (
              <div className="mb-4 flex items-start gap-2 rounded-lg bg-[var(--color-success-light)] p-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-success)]" />
                <p className="text-sm text-[var(--color-success)]">{success}</p>
              </div>
            )}

            {/* Full name (Sign Up only) */}
            {isSignUp && (
              <>
                <div className="mb-4">
                  <label
                    htmlFor="fullName"
                    className="mb-1.5 block text-sm font-medium text-[var(--color-text-primary)]"
                  >
                    Nom complet
                  </label>
                  <input
                    id="fullName"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Marie Dupont"
                    required={isSignUp}
                    className={cn(
                      'w-full rounded-lg border border-[var(--color-border)] px-3 py-2.5 text-sm',
                      'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)]',
                      'outline-none transition-all',
                      'focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-light)]',
                      'disabled:opacity-60'
                    )}
                    disabled={isPending}
                  />
                </div>

                <div className="mb-4">
                  <label
                    htmlFor="language"
                    className="mb-1.5 block text-sm font-medium text-[var(--color-text-primary)]"
                  >
                    Langue préférée
                  </label>
                  <select
                    id="language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className={cn(
                      'w-full rounded-lg border border-[var(--color-border)] px-3 py-2.5 text-sm bg-white',
                      'text-[var(--color-text-primary)]',
                      'outline-none transition-all',
                      'focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-light)]',
                      'disabled:opacity-60'
                    )}
                    disabled={isPending}
                  >
                    <option value="fr">Français (FR)</option>
                    <option value="en">English (EN)</option>
                    <option value="nl">Nederlands (NL)</option>
                  </select>
                </div>
              </>
            )}

            {/* Email */}
            <div className="mb-4">
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-[var(--color-text-primary)]"
              >
                Adresse email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="votre@email.com"
                required
                autoComplete="email"
                className={cn(
                  'w-full rounded-lg border border-[var(--color-border)] px-3 py-2.5 text-sm',
                  'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)]',
                  'outline-none transition-all',
                  'focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-light)]',
                  'disabled:opacity-60'
                )}
                disabled={isPending}
              />
            </div>

            {/* Password */}
            <div className="mb-6">
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-[var(--color-text-primary)]"
              >
                Mot de passe
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  className={cn(
                    'w-full rounded-lg border border-[var(--color-border)] px-3 py-2.5 pr-10 text-sm',
                    'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)]',
                    'outline-none transition-all',
                    'focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-light)]',
                    'disabled:opacity-60'
                  )}
                  disabled={isPending}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isPending || !email || !password || (isSignUp && !fullName)}
              className={cn(
                'flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white',
                'bg-[var(--color-accent)] transition-all hover:bg-[#6B5A93] active:scale-[0.99]',
                'disabled:cursor-not-allowed disabled:opacity-60'
              )}
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {isSignUp ? 'Inscription en cours...' : 'Connexion en cours...'}
                </>
              ) : (
                isSignUp ? 'S\'inscrire' : 'Se connecter'
              )}
            </button>
          </form>

          {/* Toggle signup/login */}
          <div className="border-t border-slate-100 bg-slate-50/50 px-8 py-4 text-center">
            <button
              type="button"
              onClick={() => {
                setIsSignUp(!isSignUp)
                setError(null)
                setSuccess(null)
              }}
              className="text-xs font-semibold text-[var(--color-accent)] hover:underline"
              disabled={isPending}
            >
              {isSignUp ? 'Déjà un compte ? Se connecter' : "Pas encore de compte ? S'inscrire"}
            </button>
          </div>
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-[var(--color-text-secondary)]">
          © 2025 VO Event Max. Tous droits réservés.
        </p>
      </div>
    </div>
  )
}
