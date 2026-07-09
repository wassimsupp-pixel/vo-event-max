'use client'

import { useTranslations } from 'next-intl'
import { usePathname } from 'next/navigation'
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
  BarChart3,
  Settings,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  key: string
  href: string | null
  icon: React.ElementType
  disabled?: boolean
  badge?: string
}

function getNavItems(eventId: string, locale: string, userRole: string): NavItem[] {
  const base = `/${locale}/events/${eventId}`
  const items = [
    { key: 'dashboard', href: `${base}/dashboard`, icon: LayoutDashboard },
    { key: 'masterList', href: `${base}/master-list`, icon: ListChecks },
    { key: 'sources', href: `${base}/sources`, icon: Database },
    { key: 'participants', href: `/${locale}/participants`, icon: Users },
    { key: 'flights', href: `${base}/flights`, icon: Plane },
    { key: 'hotels', href: `${base}/hotels`, icon: Hotel },
    { key: 'activities', href: `${base}/activities`, icon: Sparkles },
    { key: 'transfers', href: `${base}/transfers`, icon: Bus },
    { key: 'communications', href: `${base}/communications`, icon: Mail },
    { key: 'exceptions', href: `${base}/exceptions`, icon: AlertTriangle, badge: '18' },
    { key: 'reports', href: `${base}/reports`, icon: BarChart3 },
    { key: 'settings', href: `/${locale}/settings`, icon: Settings },
  ]

  if (userRole.toLowerCase() === 'client') {
    // Hide sources, exceptions, settings, reports, and communications
    return items.filter(item => !['sources', 'exceptions', 'settings', 'reports', 'communications'].includes(item.key))
  }
  return items
}

interface SidebarProps {
  eventId: string
  locale: string
  userName?: string
  userRole?: string
  userInitials?: string
}

export function Sidebar({
  eventId,
  locale,
  userName = 'Marie Dubois',
  userRole = 'Event Manager',
  userInitials = 'MD',
}: SidebarProps) {
  const t = useTranslations('nav')
  const pathname = usePathname()
  const navItems = getNavItems(eventId, locale, userRole)

  return (
    <aside
      className="fixed left-0 top-0 z-40 flex h-screen w-[240px] flex-col bg-[var(--color-surface)]"
      style={{ boxShadow: 'var(--shadow-sidebar)' }}
    >
      {/* Logo */}
      <div className="flex h-[60px] flex-shrink-0 items-center gap-2.5 border-b border-[var(--color-border)] px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent)]">
          <Zap className="h-4 w-4 text-white" />
        </div>
        <div>
          <span className="text-base font-bold text-[var(--color-accent)]">VO</span>
          <span className="text-base font-bold text-[var(--color-text-primary)]"> Event Max</span>
        </div>
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
      <div className="flex-shrink-0 border-t border-[var(--color-border)] p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-accent)] text-xs font-bold text-white">
            {userInitials}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
              {userName}
            </p>
            <p className="truncate text-xs text-[var(--color-text-secondary)]">{userRole}</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
