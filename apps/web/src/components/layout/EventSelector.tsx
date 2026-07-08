'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown, Check, Calendar } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Event {
  id: string
  name: string
  date: string
  location: string
}

// Mock events — replace with API data
const MOCK_EVENTS: Event[] = [
  { id: '1', name: 'LivaNova — Barcelona Summit', date: '2025-09-15', location: 'Barcelone' },
  { id: '2', name: 'Medtronic — Paris Congress', date: '2025-10-22', location: 'Paris' },
  { id: '3', name: 'Abbott — Geneva Forum', date: '2025-11-08', location: 'Genève' },
]

interface EventSelectorProps {
  currentEventId: string
  onSwitch?: (eventId: string) => void
}

export function EventSelector({ currentEventId, onSwitch }: EventSelectorProps) {
  const [open, setOpen] = useState(false)
  const currentEvent = MOCK_EVENTS.find((e) => e.id === currentEventId) ?? MOCK_EVENTS[0]

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-3 py-2',
          'text-sm font-medium text-[var(--color-text-primary)] transition-all',
          'hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-light)]',
          open && 'border-[var(--color-accent)] bg-[var(--color-accent-light)]'
        )}
      >
        <Calendar className="h-4 w-4 text-[var(--color-accent)]" />
        <span className="max-w-[200px] truncate">{currentEvent.name}</span>
        <ChevronDown
          className={cn(
            'h-4 w-4 text-[var(--color-text-secondary)] transition-transform',
            open && 'rotate-180'
          )}
        />
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />

          {/* Dropdown */}
          <div
            className="absolute left-0 top-full z-20 mt-1.5 w-[280px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white"
            style={{ boxShadow: 'var(--shadow-dropdown)' }}
          >
            <div className="border-b border-[var(--color-border)] px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
                Événements
              </p>
            </div>
            <ul className="p-1">
              {MOCK_EVENTS.map((event) => (
                <li key={event.id}>
                  <button
                    onClick={() => {
                      onSwitch?.(event.id)
                      setOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors',
                      'hover:bg-[var(--color-bg-subtle)]',
                      event.id === currentEventId && 'bg-[var(--color-accent-light)]'
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                        {event.name}
                      </p>
                      <p className="text-xs text-[var(--color-text-secondary)]">
                        {event.location} — {event.date}
                      </p>
                    </div>
                    {event.id === currentEventId && (
                      <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-accent)]" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
