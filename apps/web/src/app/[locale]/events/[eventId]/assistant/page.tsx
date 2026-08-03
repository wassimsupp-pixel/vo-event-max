'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { MessageSquare, Send, Loader2, Info, Database, AlertCircle } from 'lucide-react'
import { api, type ChatAnswer } from '@/lib/api'

interface Turn {
  id: number
  question: string
  answer?: ChatAnswer
  failed?: boolean
}

/** Renders an answer's supporting rows. The assistant only ever returns data it
 *  actually read, so this is a plain table over whatever columns came back —
 *  no client-side derivation, nothing computed here that could drift from the
 *  figures stated in the answer text. */
function AnswerTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null
  const columns = Object.keys(rows[0]).filter((c) => c !== 'id')
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-left text-xs">
        <thead className="bg-[var(--color-bg-subtle)]">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
                {c.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border)]">
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} className="px-3 py-2 text-[var(--color-text-primary)]">
                  {row[c] === true ? 'oui' : row[c] === false ? 'non' : String(row[c] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AssistantPage() {
  const params = useParams()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [asking, setAsking] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [capabilities, setCapabilities] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement | null>(null)
  // A plain counter, not Date.now(): the React compiler treats clock reads as
  // impure, and two questions fired inside the same millisecond would collide
  // on the same React key anyway.
  const nextTurnId = useRef(0)

  useEffect(() => {
    let cancelled = false
    api.chat
      .suggestions(eventId)
      .then((s) => {
        if (cancelled) return
        setSuggestions(s.questions)
        setCapabilities(s.capabilities)
      })
      .catch(() => { /* chips are a convenience — the input still works */ })
    return () => { cancelled = true }
  }, [eventId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns, asking])

  const send = async (question: string) => {
    const q = question.trim()
    if (!q || asking) return
    nextTurnId.current += 1
    const id = nextTurnId.current
    setTurns((prev) => [...prev, { id, question: q }])
    setInput('')
    setAsking(true)
    try {
      const answer = await api.chat.ask(eventId, q)
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, answer } : t)))
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erreur inconnue.'
      setTurns((prev) =>
        prev.map((t) =>
          t.id === id
            ? { ...t, failed: true, answer: { answer: msg, rows: [], references: [], intent: null, answered: false } }
            : t
        )
      )
    } finally {
      setAsking(false)
    }
  }

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle="Assistant"
      pageSubtitle="Posez vos questions sur cet événement — réponses issues uniquement de vos données"
    >
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Assistant</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            Connecté uniquement aux données de cet événement : master list, fichiers importés,
            exceptions et communications.
          </p>
        </div>

        {turns.length === 0 && (
          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Info className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-accent)]" />
              <div className="space-y-3">
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Ce que je peux consulter
                </p>
                <ul className="list-inside list-disc space-y-1 text-sm text-[var(--color-text-secondary)]">
                  {capabilities.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  Si une information n&apos;existe pas dans vos données, je vous le dis — je ne la
                  devine jamais.
                </p>
              </div>
            </div>
          </Card>
        )}

        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                disabled={asking}
                className="rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="space-y-4">
          {turns.map((turn) => (
            <div key={turn.id} className="space-y-3">
              <div className="flex justify-end">
                <div className="max-w-2xl rounded-2xl rounded-br-sm bg-[var(--color-accent)] px-4 py-2.5 text-sm text-white">
                  {turn.question}
                </div>
              </div>

              {turn.answer ? (
                <Card
                  className={
                    'p-4 ' +
                    (turn.answer.answered
                      ? ''
                      : 'border-[var(--color-warning)] bg-[var(--color-warning-light)]')
                  }
                >
                  <div className="flex items-start gap-3">
                    {turn.answer.answered ? (
                      <MessageSquare className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-accent)]" />
                    ) : (
                      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-warning)]" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-[var(--color-text-primary)]">{turn.answer.answer}</p>
                      <AnswerTable rows={turn.answer.rows} />
                      {turn.answer.references.length > 0 && (
                        <div className="mt-3 flex flex-wrap items-center gap-1.5">
                          <Database className="h-3 w-3 text-[var(--color-text-secondary)]" />
                          <span className="text-[11px] text-[var(--color-text-secondary)]">
                            Sources : {turn.answer.references.join(' · ')}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              ) : (
                <Card className="p-4">
                  <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Lecture des données de l&apos;événement…
                  </div>
                </Card>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
          className="sticky bottom-4 flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ex. : quels participants ont un vol mais aucun transfert ?"
            disabled={asking}
            maxLength={500}
            className="flex-1 rounded-lg border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-accent)] disabled:opacity-60"
          />
          <Button type="submit" disabled={asking || !input.trim()} className="gap-2">
            {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Envoyer
          </Button>
        </form>
      </div>
    </AppLayout>
  )
}
