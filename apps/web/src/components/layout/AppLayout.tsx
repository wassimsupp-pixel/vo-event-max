import { Sidebar } from '@/components/layout/Sidebar'
import { EventSelector } from '@/components/layout/EventSelector'
import { Bell, HelpCircle } from 'lucide-react'

interface AppLayoutProps {
  children: React.ReactNode
  eventId: string
  locale: string
  pageTitle?: string
  pageSubtitle?: string
  headerExtra?: React.ReactNode
  userRole?: string
}

export function AppLayout({
  children,
  eventId,
  locale,
  pageTitle,
  pageSubtitle,
  headerExtra,
  userRole = 'Event Manager',
}: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-[var(--color-bg-subtle)]">
      {/* Sidebar */}
      <Sidebar eventId={eventId} locale={locale} userRole={userRole} />

      {/* Main content area */}
      <div className="ml-[240px] flex min-h-screen flex-col">
        {/* Top header bar */}
        <header className="sticky top-0 z-30 flex h-[60px] flex-shrink-0 items-center gap-4 border-b border-[var(--color-border)] bg-white px-6">
          {/* Event selector */}
          <EventSelector currentEventId={eventId} />

          {/* Page title in header (optional) */}
          {pageTitle && (
            <div className="hidden border-l border-[var(--color-border)] pl-4 sm:block">
              <h1 className="text-sm font-semibold text-[var(--color-text-primary)]">
                {pageTitle}
              </h1>
              {pageSubtitle && (
                <p className="text-xs text-[var(--color-text-secondary)]">{pageSubtitle}</p>
              )}
            </div>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Header actions */}
          {headerExtra}

          {/* Notification bell */}
          <button className="relative flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-secondary)] transition-colors hover:bg-gray-100 hover:text-[var(--color-text-primary)]">
            <Bell className="h-4 w-4" />
            <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-[var(--color-danger)]" />
          </button>

          {/* Help */}
          <button className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-secondary)] transition-colors hover:bg-gray-100 hover:text-[var(--color-text-primary)]">
            <HelpCircle className="h-4 w-4" />
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  )
}
