'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/button'
import { Send, Loader2, Sparkles, ChevronDown, RotateCcw } from 'lucide-react'
import { api, type ChatAnswer } from '@/lib/api'

interface Turn {
  id: number
  question: string
  answer?: ChatAnswer
}

/** Rows are shown collapsed past this many; the full list always lives on the
 *  page named in the answer's sources. */
const PREVIEW_ROWS = 5

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  const [expanded, setExpanded] = useState(false)
  if (!rows.length) return null
  const columns = Object.keys(rows[0]).filter((c) => c !== 'id')
  const visible = expanded ? rows : rows.slice(0, PREVIEW_ROWS)
  const hidden = rows.length - visible.length

  const render = (v: unknown) =>
    v === true ? 'oui' : v === false ? 'non' : String(v ?? '—')

  return (
    <div className="mt-3">
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border)]">
              {columns.map((c) => (
                <th key={c} className="px-3 py-2 font-medium text-[var(--color-text-secondary)]">
                  {c.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
                {columns.map((c) => (
                  <td key={c} className="px-3 py-2 text-[var(--color-text-primary)]">
                    {render(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
        >
          <ChevronDown className="h-3 w-3" />
          Afficher les {hidden} autres
        </button>
      )}
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
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const nextTurnId = useRef(0)

  useEffect(() => {
    let cancelled = false
    api.chat
      .suggestions(eventId)
      .then((s) => { if (!cancelled) setSuggestions(s.questions.slice(0, 4)) })
      .catch(() => { /* chips are a convenience — the input still works */ })
    return () => { cancelled = true }
  }, [eventId])

  useEffect(() => {
    if (turns.length) bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns, asking])

  const send = async (question: string) => {
    const q = question.trim()
    if (!q || asking) return
    nextTurnId.current += 1
    const id = nextTurnId.current
    const history = turns.map((t) => ({ question: t.question }))
    setTurns((prev) => [...prev, { id, question: q }])
    setInput('')
    setAsking(true)
    try {
      const answer = await api.chat.ask(eventId, q, history)
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, answer } : t)))
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur inconnue.'
      setTurns((prev) =>
        prev.map((t) =>
          t.id === id
            ? { ...t, answer: { answer: message, rows: [], references: [], intent: null, answered: false } }
            : t
        )
      )
    } finally {
      setAsking(false)
      inputRef.current?.focus()
    }
  }

  const isEmpty = turns.length === 0

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle="Assistant"
      pageSubtitle="Posez vos questions sur cet événement"
    >
      <div className="mx-auto flex min-h-[calc(100vh-13rem)] max-w-3xl flex-col">
        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-accent)]/10">
              <Sparkles className="h-6 w-6 text-[var(--color-accent)]" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
                Que voulez-vous savoir sur cet événement ?
              </h1>
              <p className="mt-1.5 text-sm text-[var(--color-text-secondary)]">
                Je réponds à partir de vos données uniquement, et je vous dis quand
                une information n&apos;existe pas.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-[var(--color-border)] px-3.5 py-1.5 text-xs text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex-1 space-y-6 py-2">
            {turns.map((turn) => (
              <div key={turn.id} className="space-y-3">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[var(--color-accent)] px-4 py-2.5 text-sm text-white">
                    {turn.question}
                  </div>
                </div>

                {turn.answer ? (
                  <div className="max-w-[95%]">
                    <p
                      className={
                        'text-sm leading-relaxed ' +
                        (turn.answer.answered
                          ? 'text-[var(--color-text-primary)]'
                          : 'text-[var(--color-text-secondary)]')
                      }
                    >
                      {turn.answer.answer}
                    </p>
                    <ResultTable rows={turn.answer.rows} />
                    {turn.answer.references.length > 0 && (
                      <p className="mt-2 text-[11px] text-[var(--color-text-secondary)]">
                        {turn.answer.references.join(' · ')}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Lecture de vos données…
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        <div className="sticky bottom-0 bg-[var(--color-bg)] pb-4 pt-3">
          <form
            onSubmit={(e) => { e.preventDefault(); send(input) }}
            className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white p-1.5 shadow-sm focus-within:border-[var(--color-accent)]"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Posez une question…"
              disabled={asking}
              maxLength={500}
              autoFocus
              className="flex-1 bg-transparent px-3 py-1.5 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-secondary)] disabled:opacity-60"
            />
            {!isEmpty && !asking && (
              <button
                type="button"
                onClick={() => { setTurns([]); inputRef.current?.focus() }}
                title="Nouvelle conversation"
                className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-bg-subtle)]"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            )}
            <Button type="submit" disabled={asking || !input.trim()} className="h-9 w-9 shrink-0 rounded-lg p-0">
              {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
        </div>
      </div>
    </AppLayout>
  )
}
