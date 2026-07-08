'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Zap, Eye, EyeOff, Loader2, AlertCircle } from 'lucide-react'
import { createClient } from '@/lib/supabase'
import { cn } from '@/lib/utils'

export default function LoginPage() {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    startTransition(async () => {
      try {
        const supabase = createClient()
        const { error } = await supabase.auth.signInWithPassword({ email, password })

        if (error) {
          setError(error.message === 'Invalid login credentials'
            ? 'Email ou mot de passe incorrect.'
            : error.message
          )
          return
        }

        router.push('/fr/events')
        router.refresh()
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
          <div className="px-8 pb-6 pt-8 text-center">
            <div className="mb-4 flex items-center justify-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-accent)]">
                <Zap className="h-5 w-5 text-white" />
              </div>
              <div>
                <span className="text-xl font-bold text-[var(--color-accent)]">VO</span>
                <span className="text-xl font-bold text-[var(--color-text-primary)]"> Event Max</span>
              </div>
            </div>
            <h1 className="text-xl font-bold text-[var(--color-text-primary)]">
              Connexion
            </h1>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
              Plateforme de gestion événementielle
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="px-8 pb-8">
            {/* Error message */}
            {error && (
              <div className="mb-4 flex items-start gap-2 rounded-lg bg-[var(--color-danger-light)] p-3">
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-danger)]" />
                <p className="text-sm text-[var(--color-danger)]">{error}</p>
              </div>
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
              <div className="mt-1.5 text-right">
                <a
                  href="#"
                  className="text-xs text-[var(--color-accent)] hover:underline"
                >
                  Mot de passe oublié ?
                </a>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isPending || !email || !password}
              className={cn(
                'flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white',
                'bg-[var(--color-accent)] transition-all hover:bg-[#6B5A93] active:scale-[0.99]',
                'disabled:cursor-not-allowed disabled:opacity-60'
              )}
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Connexion en cours...
                </>
              ) : (
                'Se connecter'
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-[var(--color-text-secondary)]">
          © 2025 VO Event Max. Tous droits réservés.
        </p>
      </div>
    </div>
  )
}
