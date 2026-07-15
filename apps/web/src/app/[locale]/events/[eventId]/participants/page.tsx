'use client'

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'

/**
 * Event-scoped "Participants" entry point. The event's participant list is the
 * Master List, so this keeps the selected event in context (no jump to the
 * global cross-event page) and lands the user there.
 */
export default function EventParticipantsPage() {
  const { locale, eventId } = useParams() as { locale: string; eventId: string }
  const router = useRouter()

  useEffect(() => {
    router.replace(`/${locale}/events/${eventId}/master-list`)
  }, [locale, eventId, router])

  return null
}
