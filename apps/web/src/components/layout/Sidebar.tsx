'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  LayoutDashboard,
  ListChecks,
  Database,
  Users,
  Plane,
  Hotel,
  Sparkles,
  Bus,
  Mail,
  AlertTriangle,
  GitMerge,
  BarChart3,
  Settings,
  Zap,
  LogOut,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase'
import { EventMaxLogo } from '@/components/ui/EventMaxLogo'

interface NavItem {
  key: string
  href: string | null
  icon: React.ElementType
  disabled?: boolean
  badge?: string
}

function getNavItems(eventId: string, locale: string, userRole: string, exceptionCount: number): NavItem[] {
  const base = `/${locale}/events/${eventId}`
  const items = [
    { key: 'dashboard', href: `${base}/dashboard`, icon: LayoutDashboard },
    { key: 'masterList', href: `${base}/master-list`, icon: ListChecks },
    { key: 'sources', href: `${base}/sources`, icon: Database },
    { key: 'participants', href: `${base}/participants`, icon: Users },
    { key: 'flights', href: `${base}/flights`, icon: Plane },
    { key: 'hotels', href: `${base}/hotels`, icon: Hotel },
    { key: 'activities', href: `${base}/activities`, icon: Sparkles },
    { key: 'transfers', href: `${base}/transfers`, icon: Bus },
    { key: 'communications', href: `${base}/communications`, icon: Mail },
    { key: 'exceptions', href: `${base}/exceptions`, icon: AlertTriangle, badge: exceptionCount > 0 ? String(exceptionCount) : undefined },
    { key: 'matchReview', href: `${base}/match-review`, icon: GitMerge },
    { key: 'reports', href: `${base}/reports`, icon: BarChart3 },
    { key: 'settings', href: `/${locale}/settings`, icon: Settings },
  ]

  if (userRole.toLowerCase() === 'client') {
    // Hide sources, exceptions, settings, reports, and communications
    return items.filter(item => !['sources', 'exceptions', 'matchReview', 'settings', 'reports', 'communications'].includes(item.key))
  }
  return items
}

interface SidebarProps {
  eventId: string
  locale: string
}

export function Sidebar({ eventId, locale }: SidebarProps) {
  const t = useTranslations('nav')
  const tBrand = useTranslations('branding')
  const pathname = usePathname()
  const router = useRouter()

  const [userName, setUserName] = useState('Marie Dubois')
  const [userRole, setUserRole] = useState('Event Manager')
  const [userInitials, setUserInitials] = useState('MD')
  const [exceptionCount, setExceptionCount] = useState<number>(0)
  const [showUserMenu, setShowUserMenu] = useState(false)

  // 1. Fetch user profile
  useEffect(() => {
    async function getUser() {
      const supabase = createClient()
      const { data: { user } } = await supabase.auth.getUser()
      if (user) {
        const name = user.user_metadata?.full_name || user.email?.split('@')[0] || 'Utilisateur VO'
        setUserName(name)
        const parts = name.trim().split(/\s+/)
        const initials = parts.map((p: string) => p[0]).join('').toUpperCase().substring(0, 2)
        setUserInitials(initials || 'VO')

        try {
          const { data: profile } = await supabase.from('users').select('role').eq('id', user.id).single()
          if (profile) {
            setUserRole(profile.role === 'admin' ? 'Administrateur' : profile.role === 'pm' ? 'Chef de projet' : 'Utilisateur')
          }
        } catch {
          // ignore
        }
      }
    }
    getUser()
  }, [])

  // 2. Fetch exceptions count in real-time
  useEffect(() => {
    async function loadExceptionCount() {
      if (!eventId || eventId === 'global') {
        setExceptionCount(0)
        return
      }
      try {
        const supabase = createClient()
        const startedAt = typeof performance !== 'undefined' ? performance.now() : Date.now()
        const { count, error } = await supabase
          .from('exceptions')
          .select('*', { count: 'exact', head: true })
          .eq('event_id', eventId)
          .eq('resolved', false)

        if (process.env.NODE_ENV !== 'production') {
          const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
          console.debug(`[sidebar] exception count query → ${Math.round(now - startedAt)}ms`)
        }

        if (error) {
          console.warn('Failed to fetch exception count:', error)
          return
        }
        if (count !== null) {
          setExceptionCount(count)
        }
      } catch (err) {
        console.error('Exception count query error:', err)
      }
    }
    loadExceptionCount()

    // Poll to keep the badge synced. 30s (was 5s) to cut idle DB load on every
    // page; can be replaced by a Supabase Realtime subscription later (P1.6).
    const timer = setInterval(loadExceptionCount, 30_000)
    return () => clearInterval(timer)
  }, [eventId])

  const navItems = getNavItems(eventId, locale, userRole, exceptionCount)

  return (
    <aside
      className="fixed left-0 top-0 z-40 flex h-screen w-[240px] flex-col bg-[var(--color-surface)]"
      style={{ boxShadow: 'var(--shadow-sidebar)' }}
    >
      {/* Logo — Event MAX (primary brand) */}
      <div className="flex items-center border-b border-[var(--color-border)] px-6 py-6 select-none text-[var(--color-text-primary)]">
        <EventMaxLogo className="h-9 w-auto" />
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {navItems.map((item) => {
            const isActive = item.href ? pathname.startsWith(item.href) : false
            const Icon = item.icon

            if (item.disabled) {
              return (
                <li key={item.key}>
                  <div
                    className="group flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 opacity-40"
                    title="Phase 2"
                  >
                    <Icon className="h-4 w-4 text-[var(--color-text-secondary)]" />
                    <span className="text-sm text-[var(--color-text-secondary)]">
                      {t(item.key as any)}
                    </span>
                    <span className="ml-auto rounded-sm bg-gray-100 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wider text-gray-400">
                      P2
                    </span>
                  </div>
                </li>
              )
            }

            return (
              <li key={item.key}>
                <Link
                  href={item.href!}
                  className={cn(
                    'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-[var(--color-accent-light)] font-semibold text-[var(--color-accent)]'
                      : 'font-medium text-[var(--color-text-secondary)] hover:bg-gray-50 hover:text-[var(--color-text-primary)]'
                  )}
                >
                  <Icon
                    className={cn(
                      'h-4 w-4 flex-shrink-0 transition-colors',
                      isActive
                        ? 'text-[var(--color-accent)]'
                        : 'text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)]'
                    )}
                  />
                  <span className="flex-1">
                    {t(item.key as any)}
                  </span>
                  {item.badge && (
                    <span className="flex-shrink-0 rounded-full bg-[var(--color-danger)] px-1.5 py-0.5 text-[10px] font-bold text-white">
                      {item.badge}
                    </span>
                  )}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* User section */}
      <div className="flex-shrink-0 border-t border-[var(--color-border)] p-4 relative">
        {showUserMenu && (
          <div className="absolute bottom-[60px] left-4 right-4 bg-white border border-[var(--color-border)] rounded-lg shadow-lg p-1.5 z-50">
            <button
              onClick={async () => {
                const supabase = createClient()
                await supabase.auth.signOut()
                router.push(`/${locale}/login`)
              }}
              className="w-full text-left px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 rounded-md transition-colors flex items-center gap-2"
            >
              <LogOut className="h-4 w-4" />
              {t('logout')}
            </button>
          </div>
        )}
        <div
          className="flex items-center gap-3 cursor-pointer p-1.5 -m-1.5 rounded-lg hover:bg-slate-50 transition-colors"
          onClick={() => setShowUserMenu(!showUserMenu)}
        >
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-accent)] text-xs font-bold text-white">
            {userInitials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
              {userName}
            </p>
            <p className="truncate text-xs text-[var(--color-text-secondary)]">{userRole}</p>
          </div>
        </div>
      </div>

      {/* Powered by VO Communication Group (white-label attribution) */}
      <div className="flex-shrink-0 border-t border-[var(--color-border)] px-4 py-3 flex items-center gap-2.5 select-none">
        <div className="h-[34px] w-[46px] flex-shrink-0 text-[var(--color-text-secondary)]" aria-hidden>
          <svg className="h-full w-full" viewBox="0 0 60 40">
            <text x="0" y="27" fontFamily="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" fontWeight="900" fontSize="30" letterSpacing="-1.5" fill="currentColor">VO</text>
            <line x1="1" y1="34" x2="44" y2="34" stroke="currentColor" strokeWidth="4" />
          </svg>
        </div>
        <div className="min-w-0 leading-tight">
          <span className="block text-[10px] text-[var(--color-text-secondary)]">{tBrand('poweredBy')}</span>
          <span className="block truncate text-[11px] font-semibold text-[var(--color-text-primary)]">
            VO Communication Group
          </span>
        </div>
      </div>
    </aside>
  )
}
