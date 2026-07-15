'use client'

import React, { useEffect, useState, useTransition } from 'react'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import {
  Mail,
  Send,
  FileText,
  Search,
  Sparkles,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  XCircle,
  Plus,
  AlertTriangle,
  User,
  ArrowRight,
  RefreshCw,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api, type EmailProposal, type MailProvider, type MailStatus } from '@/lib/api'

export default function CommunicationsPage() {
  const { locale, eventId } = useParams() as { locale: string; eventId: string }
  const t = useTranslations('communications')
  const [proposals, setProposals] = useState<EmailProposal[]>([])
  const [selectedProposal, setSelectedProposal] = useState<EmailProposal | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Simulation form states
  const [simSender, setSimSender] = useState('sophie.martin@livanoba.com')
  const [simSubject, setSimSubject] = useState('Demande spéciale régime alimentaire')
  const [simBody, setSimBody] = useState('Bonjour,\n\nPourriez-vous modifier mon régime alimentaire en "Végétarien" s\'il vous plaît ?\n\nMerci,\nSophie')
  const [simulating, setSimulating] = useState(false)
  const [simSuccess, setSimSuccess] = useState(false)

  // Action states
  const [isPending, startTransition] = useTransition()
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  // Confirmation tracking table (§13)
  const [comms, setComms] = useState<any[]>([])

  // Bulk personalized campaign
  const [campaignMode, setCampaignMode] = useState<'template' | 'ai'>('template')
  const [campaignSubject, setCampaignSubject] = useState('Information — {event_name}')
  const [campaignBody, setCampaignBody] = useState('Bonjour {first_name},\n\n\n\nCordialement,\nL’équipe organisation')
  const [campaignInstructions, setCampaignInstructions] = useState('')
  const [campaignPreview, setCampaignPreview] = useState<any | null>(null)
  const [campaignResult, setCampaignResult] = useState<any | null>(null)
  const [campaignBusy, setCampaignBusy] = useState<'preview' | 'send' | null>(null)
  const [campaignError, setCampaignError] = useState<string | null>(null)

  // Mailbox connection states
  const [mailStatus, setMailStatus] = useState<MailStatus | null>(null)
  const [mailSyncing, setMailSyncing] = useState<MailProvider | null>(null)
  const [mailBanner, setMailBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadProposals = async () => {
    try {
      setLoading(true)
      const data = await api.emailAgent.list(eventId)
      setProposals(data)
    } catch {
      setError(t('errorLoad'))
    } finally {
      setLoading(false)
    }
  }

  const loadMailStatus = async () => {
    try {
      setMailStatus(await api.mail.status(eventId))
    } catch {
      // status is best-effort; leave whatever we had
    }
  }

  const loadComms = async () => {
    try {
      setComms(await api.communications.list(eventId))
    } catch {
      /* best-effort */
    }
  }

  const campaignPayload = () => ({
    mode: campaignMode,
    subject: campaignSubject,
    body: campaignBody,
    instructions: campaignInstructions,
  })

  const handlePreviewCampaign = async () => {
    setCampaignBusy('preview')
    setCampaignError(null)
    setCampaignResult(null)
    try {
      setCampaignPreview(await api.campaigns.preview(eventId, campaignPayload()))
    } catch (err) {
      setCampaignError(err instanceof Error ? err.message : 'Erreur lors de la prévisualisation.')
    } finally {
      setCampaignBusy(null)
    }
  }

  const handleSendCampaign = async () => {
    const n = campaignPreview?.recipient_count
    const msg = n
      ? `Envoyer un e-mail personnalisé à ${n} participant(s) ? Cette action est irréversible.`
      : 'Envoyer un e-mail personnalisé à tous les participants ? Cette action est irréversible.'
    if (!window.confirm(msg)) return
    setCampaignBusy('send')
    setCampaignError(null)
    try {
      const res = await api.campaigns.send(eventId, { ...campaignPayload(), send: true })
      setCampaignResult(res)
      await loadComms()
    } catch (err) {
      setCampaignError(err instanceof Error ? err.message : 'Erreur lors de l’envoi.')
    } finally {
      setCampaignBusy(null)
    }
  }

  useEffect(() => {
    if (!eventId) return
    loadProposals()
    loadMailStatus()
    loadComms()

    // Handle the OAuth callback redirect flags, then clean them from the URL.
    const sp = new URLSearchParams(window.location.search)
    if (sp.get('mail_connected')) {
      setMailBanner({ type: 'success', text: t('connectSuccess') })
      window.history.replaceState({}, '', window.location.pathname)
    } else if (sp.get('mail_error')) {
      setMailBanner({ type: 'error', text: t('connectError') })
      window.history.replaceState({}, '', window.location.pathname)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId])

  const handleConnectMailbox = async (provider: MailProvider) => {
    setMailBanner(null)
    try {
      const { authorization_url } = await api.mail.authorize(eventId, provider, locale)
      window.location.assign(authorization_url)
    } catch {
      setMailBanner({ type: 'error', text: t('connectError') })
    }
  }

  const handleSyncMailbox = async (provider: MailProvider) => {
    setMailSyncing(provider)
    setMailBanner(null)
    try {
      const res = await api.mail.sync(eventId, provider)
      setMailBanner({ type: 'success', text: t('syncSuccess', { count: res.synced }) })
      await loadProposals()
    } catch {
      setMailBanner({ type: 'error', text: t('syncError') })
    } finally {
      setMailSyncing(null)
    }
  }

  const handleDisconnectMailbox = async (provider: MailProvider) => {
    try {
      await api.mail.disconnect(eventId, provider)
      await loadMailStatus()
    } catch {
      // ignore — disconnect is best-effort
    }
  }

  const handleSimulateEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    setSimulating(true)
    setError(null)
    setSimSuccess(false)
    try {
      const newProposal = await api.emailAgent.analyze(eventId, simSender, simSubject, simBody)
      setProposals(prev => [newProposal, ...prev])
      setSelectedProposal(newProposal)
      setSimSuccess(true)
      setTimeout(() => setSimSuccess(false), 3000)
    } catch {
      setError(t('errorLoad'))
    } finally {
      setSimulating(false)
    }
  }

  const handleApply = (proposalId: string) => {
    setActionError(null)
    setActionSuccess(null)
    startTransition(async () => {
      try {
        await api.emailAgent.apply(proposalId)
        setActionSuccess(t('successApply'))
        setTimeout(() => setActionSuccess(null), 3000)
        // Reload
        const updated = await api.emailAgent.list(eventId)
        setProposals(updated)
        const found = updated.find(p => p.id === proposalId)
        if (found) setSelectedProposal(found)
      } catch (err) {
        setActionError(err instanceof Error ? err.message : t('errorApply'))
      }
    })
  }

  const handleReject = (proposalId: string) => {
    setActionError(null)
    setActionSuccess(null)
    startTransition(async () => {
      try {
        await api.emailAgent.reject(proposalId)
        setActionSuccess(t('successReject'))
        setTimeout(() => setActionSuccess(null), 3000)
        // Reload
        const updated = await api.emailAgent.list(eventId)
        setProposals(updated)
        const found = updated.find(p => p.id === proposalId)
        if (found) setSelectedProposal(found)
      } catch (err) {
        setActionError(err instanceof Error ? err.message : t('errorReject'))
      }
    })
  }

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Mail className="h-6 w-6 text-[var(--color-accent)]" />
              {t('title')}
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('subtitle')}
            </p>
          </div>
        </div>

        {/* Action success/error banner */}
        {actionSuccess && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-success-light)] border border-[var(--color-success)]/20 text-[var(--color-success)] text-sm font-medium">
            <CheckCircle2 className="h-5 w-5 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
        )}
        {actionError && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-sm font-medium">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {/* Bulk personalized email campaign */}
        <Card className="p-5 border-[var(--color-border)] shadow-sm bg-white space-y-4">
          <div className="flex items-center gap-2 border-b pb-3">
            <Send className="h-4.5 w-4.5 text-[var(--color-accent)]" />
            <h3 className="text-sm font-bold text-[var(--color-text-primary)]">Campagne e-mail — envoi personnalisé à tous les participants</h3>
          </div>

          {!mailStatus?.providers?.some((p) => p.connected) && (
            <div className="flex items-center gap-2 rounded-lg bg-[var(--color-warning-light)] px-3 py-2 text-xs text-[var(--color-text-primary)]">
              <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--color-warning)]" />
              <span>Aucune boîte mail connectée : tu peux générer les e-mails (statut « prêt ») mais pas les envoyer. Connecte Gmail/Outlook ci-dessous pour l’envoi réel.</span>
            </div>
          )}

          <div className="inline-flex rounded-lg bg-slate-100 p-1 text-xs">
            <button
              onClick={() => setCampaignMode('template')}
              className={`rounded px-3 py-1 font-medium transition-colors ${campaignMode === 'template' ? 'bg-white shadow-sm text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'}`}
            >
              Écrire un modèle
            </button>
            <button
              onClick={() => setCampaignMode('ai')}
              className={`rounded px-3 py-1 font-medium transition-colors ${campaignMode === 'ai' ? 'bg-white shadow-sm text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'}`}
            >
              Générer par IA
            </button>
          </div>

          {campaignMode === 'template' ? (
            <div className="space-y-3">
              <input
                type="text"
                value={campaignSubject}
                onChange={(e) => setCampaignSubject(e.target.value)}
                placeholder="Objet (variables autorisées, ex. {event_name})"
                className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              />
              <textarea
                value={campaignBody}
                onChange={(e) => setCampaignBody(e.target.value)}
                rows={7}
                placeholder="Message… utilise des variables comme {first_name}"
                className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white px-3 py-2 whitespace-pre-wrap focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              />
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] font-semibold text-[var(--color-text-secondary)]">Variables :</span>
                {['first_name', 'last_name', 'full_name', 'email', 'company', 'region', 'country', 'attendee_category', 'job_title', 'event_name'].map((ph) => (
                  <button
                    key={ph}
                    onClick={() => setCampaignBody((b) => `${b}{${ph}}`)}
                    className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent-light)]"
                  >
                    {`{${ph}}`}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <textarea
                value={campaignInstructions}
                onChange={(e) => setCampaignInstructions(e.target.value)}
                rows={4}
                placeholder="Décris le message à générer, ex. : Invite chaque participant au dîner de gala, ton chaleureux, mentionne sa région."
                className="w-full text-sm rounded-md border border-[var(--color-border)] bg-white px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              />
              <p className="text-[10px] text-[var(--color-text-secondary)]">L’IA (Gemini) rédige un e-mail adapté à chaque participant à partir de ses données — sans rien inventer.</p>
            </div>
          )}

          {campaignError && (
            <div className="flex items-center gap-2 rounded-lg bg-[var(--color-danger-light)] px-3 py-2 text-xs text-[var(--color-danger)]">
              <AlertTriangle className="h-4 w-4 shrink-0" /><span>{campaignError}</span>
            </div>
          )}

          {campaignResult && (
            <div className="flex items-center gap-2 rounded-lg bg-[var(--color-success-light)] px-3 py-2 text-xs font-medium text-[var(--color-success)]">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>
                {campaignResult.generated} e-mail(s) générés{campaignResult.delivered ? `, ${campaignResult.sent} envoyés via ${campaignResult.provider}` : ' (stockés, non envoyés)'}
                {campaignResult.errors ? `, ${campaignResult.errors} échec(s)` : ''}
                {campaignResult.skipped_no_email ? `, ${campaignResult.skipped_no_email} sans email ignorés` : ''}.
              </span>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={handlePreviewCampaign} disabled={campaignBusy !== null} className="flex items-center gap-2">
              {campaignBusy === 'preview' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Prévisualiser
            </Button>
            <Button onClick={handleSendCampaign} disabled={campaignBusy !== null} className="bg-[var(--color-accent)] text-white flex items-center gap-2">
              {campaignBusy === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Envoyer à tous les participants
            </Button>
            {campaignPreview && (
              <span className="text-xs text-[var(--color-text-secondary)]">
                {campaignPreview.recipient_count} destinataire(s){campaignPreview.without_email ? ` · ${campaignPreview.without_email} sans email` : ''}
              </span>
            )}
          </div>

          {campaignPreview?.samples?.length > 0 && (
            <div className="space-y-2 border-t pt-3">
              <p className="text-[11px] font-semibold text-[var(--color-text-secondary)]">Aperçu personnalisé ({campaignPreview.samples.length} exemples)</p>
              {campaignPreview.samples.map((s: any, i: number) => (
                <div key={i} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <div className="text-[11px] font-semibold text-[var(--color-text-primary)]">{s.name} &lt;{s.to}&gt;</div>
                  <div className="text-[11px] text-[var(--color-accent)] mt-0.5">{s.subject}</div>
                  <div className="text-xs text-[var(--color-text-secondary)] mt-1 whitespace-pre-wrap">{s.body}</div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="grid grid-cols-12 gap-6">
          {/* Left: Email Simulation Form & Inbox */}
          <div className="col-span-12 lg:col-span-4 space-y-6">
            {/* Mailbox connection (OAuth) */}
            <Card className="p-5 border-[var(--color-border)] shadow-sm bg-white space-y-4">
              <div>
                <h3 className="text-sm font-bold text-[var(--color-text-primary)] flex items-center gap-1.5">
                  <Mail className="h-4 w-4 text-[var(--color-accent)]" /> {t('mailConnectionTitle')}
                </h3>
                <p className="text-[11px] text-[var(--color-text-secondary)] mt-1">{t('mailConnectionSubtitle')}</p>
              </div>

              {mailBanner && (
                <div
                  className={`flex items-center gap-2 p-2.5 rounded-lg text-xs font-medium ${
                    mailBanner.type === 'success'
                      ? 'bg-[var(--color-success-light)] text-[var(--color-success)]'
                      : 'bg-[var(--color-danger-light)] text-[var(--color-danger)]'
                  }`}
                >
                  {mailBanner.type === 'success'
                    ? <CheckCircle2 className="h-4 w-4 shrink-0" />
                    : <AlertTriangle className="h-4 w-4 shrink-0" />}
                  <span>{mailBanner.text}</span>
                </div>
              )}

              <div className="space-y-2.5">
                {(mailStatus?.providers ?? []).map((p) => (
                  <div
                    key={p.provider}
                    className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 p-2.5"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-semibold capitalize text-[var(--color-text-primary)]">{p.provider}</span>
                      <Badge
                        className={`text-[9px] border-0 ${
                          !p.configured
                            ? 'bg-slate-100 text-slate-500'
                            : p.connected
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-amber-50 text-amber-700'
                        }`}
                      >
                        {!p.configured
                          ? t('providerNotConfigured')
                          : p.connected
                          ? t('providerConnected')
                          : t('providerNotConnected')}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {!p.configured ? (
                        <span className="text-[10px] text-[var(--color-text-secondary)]" title={t('notConfiguredHint')}>
                          &mdash;
                        </span>
                      ) : p.connected ? (
                        <>
                          <Button
                            size="sm"
                            onClick={() => handleSyncMailbox(p.provider)}
                            disabled={mailSyncing === p.provider}
                            className="bg-[var(--color-accent)] text-white text-[11px] h-7 px-2"
                          >
                            {mailSyncing === p.provider
                              ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                              : <RefreshCw className="h-3 w-3 mr-1" />}
                            {mailSyncing === p.provider ? t('syncingLabel') : t('syncButton')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDisconnectMailbox(p.provider)}
                            className="text-[11px] h-7 px-2 border-[var(--color-border)]"
                          >
                            {t('disconnectButton')}
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => handleConnectMailbox(p.provider)}
                          className="bg-[var(--color-accent)] text-white text-[11px] h-7 px-2.5"
                        >
                          {t('connectButton')}
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
                {mailStatus && mailStatus.providers.every((p) => !p.configured) && (
                  <p className="text-[10px] text-[var(--color-text-secondary)] italic">{t('notConfiguredHint')}</p>
                )}
              </div>
            </Card>

            {/* Simulation Block */}
            <Card className="p-5 border-[var(--color-border)] shadow-sm bg-white space-y-4">
              <h3 className="text-sm font-bold text-[var(--color-text-primary)] flex items-center gap-1.5">
                <Sparkles className="h-4.5 w-4.5 text-amber-500" /> {t('simulateTitle')}
              </h3>
              <form onSubmit={handleSimulateEmail} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-semibold mb-1 text-[var(--color-text-secondary)]">{t('senderLabel')}</label>
                  <input
                    type="email"
                    value={simSender}
                    onChange={(e) => setSimSender(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1 text-[var(--color-text-secondary)]">{t('subjectLabel')}</label>
                  <input
                    type="text"
                    value={simSubject}
                    onChange={(e) => setSimSubject(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1 text-[var(--color-text-secondary)]">{t('messageLabel')}</label>
                  <textarea
                    value={simBody}
                    onChange={(e) => setSimBody(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-[var(--color-accent)] h-24"
                    required
                  />
                </div>
                <Button type="submit" disabled={simulating} className="w-full bg-[var(--color-accent)] text-white text-xs py-2">
                  {simulating ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
                  {t('sendButton')}
                </Button>
              </form>
            </Card>

            {/* Inbox proposals */}
            <Card className="p-5 border-[var(--color-border)] shadow-sm bg-white space-y-4">
              <h3 className="text-sm font-bold text-[var(--color-text-primary)]">{t('inboxTitle')}</h3>
              {loading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
                </div>
              ) : proposals.length === 0 ? (
                <p className="text-xs text-[var(--color-text-secondary)] text-center py-10">{t('noEmails')}</p>
              ) : (
                <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1">
                  {proposals.map((prop) => (
                    <div
                      key={prop.id}
                      onClick={() => { setSelectedProposal(prop); setActionError(null); setActionSuccess(null); }}
                      className={`p-3 rounded-lg border border-slate-100 cursor-pointer transition-all ${
                        selectedProposal?.id === prop.id
                          ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)]/20'
                          : 'hover:bg-slate-50 bg-white'
                      }`}
                    >
                      <div className="flex justify-between items-start gap-1">
                        <span className="text-xs font-bold text-[var(--color-text-primary)] truncate max-w-[150px]">{prop.sender}</span>
                        <Badge
                          className={`text-[9px] border-0 capitalize ${
                            prop.status === 'applied'
                              ? 'bg-emerald-50 text-emerald-700'
                              : prop.status === 'rejected'
                              ? 'bg-rose-50 text-rose-700'
                              : 'bg-amber-50 text-amber-700'
                          }`}
                        >
                          {prop.status}
                        </Badge>
                      </div>
                      <div className="text-[11px] font-semibold text-[var(--color-text-primary)] mt-1 truncate">{prop.subject}</div>
                      <div className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">{new Date(prop.received_at).toLocaleDateString(locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US')}</div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Right: AI Split Screen Panel Details */}
          <div className="col-span-12 lg:col-span-8">
            {selectedProposal ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Email text view */}
                <Card className="p-5 border-[var(--color-border)] shadow-sm bg-white space-y-4">
                  <div className="border-b pb-3.5">
                    <h3 className="text-sm font-bold text-[var(--color-text-primary)] truncate">{selectedProposal.subject}</h3>
                    <p className="text-[11px] text-[var(--color-text-secondary)] mt-1">{t('senderPrefix', { sender: selectedProposal.sender })}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">{t('receivedPrefix', { date: new Date(selectedProposal.received_at).toLocaleString(locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US') })}</p>
                  </div>
                  <div className="bg-slate-50 border rounded-lg p-3 text-xs font-mono text-[var(--color-text-primary)] whitespace-pre-wrap min-h-[220px]">
                    {selectedProposal.body}
                  </div>
                </Card>

                {/* AI Proposed Changes */}
                <Card className="p-5 border-[var(--color-accent)] shadow-sm bg-white flex flex-col justify-between">
                  <div className="space-y-5">
                    <div className="border-b pb-3.5 flex items-center gap-1.5">
                      <Sparkles className="h-4.5 w-4.5 text-amber-500" />
                      <div>
                        <h3 className="text-sm font-bold text-[var(--color-text-primary)]">{t('aiExtractionTitle')}</h3>
                        <p className="text-[10px] text-[var(--color-text-secondary)]">{t('aiExtractionSubtitle')}</p>
                      </div>
                    </div>

                    {/* Participant identification status */}
                    <div className="flex items-center gap-2 p-2.5 rounded bg-slate-50 border border-slate-100 text-xs">
                      <User className="h-4 w-4 text-[var(--color-accent)] shrink-0" />
                      <div>
                        {selectedProposal.participant_name ? (
                          <span>{t('participantIdentified', { name: selectedProposal.participant_name })}</span>
                        ) : (
                          <span className="text-amber-700">{t('participantNotFound')}</span>
                        )}
                      </div>
                    </div>

                    {/* Proposed changes listing */}
                    <div className="space-y-3">
                      <h4 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">{t('proposedChanges')}</h4>
                      {Object.keys(selectedProposal.proposed_changes).length === 0 ? (
                        <p className="text-xs text-[var(--color-text-secondary)] italic">{t('noProposedChanges')}</p>
                      ) : (
                        Object.entries(selectedProposal.proposed_changes).map(([field, val]) => (
                          <div key={field} className="flex items-center gap-2 bg-slate-50 border rounded px-3 py-2 text-xs">
                            <span className="font-semibold capitalize text-slate-600 w-24 truncate">{field.replace('_', ' ')}</span>
                            <ArrowRight className="h-3 w-3 text-slate-400 shrink-0" />
                            <span className="font-bold text-[var(--color-success)] truncate">{val}</span>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Explanation */}
                    {selectedProposal.ai_explanation && (
                      <div className="space-y-1.5 p-3 rounded-lg border border-slate-100 bg-amber-50/20 text-xs">
                        <h4 className="font-semibold text-amber-800">{t('aiExplanationTitle')}</h4>
                        <p className="text-amber-900 leading-relaxed">{selectedProposal.ai_explanation}</p>
                      </div>
                    )}
                  </div>

                  {/* Actions buttons */}
                  {selectedProposal.status === 'pending' && (
                    <div className="flex gap-2.5 pt-5 mt-5 border-t">
                      <Button
                        variant="outline"
                        onClick={() => handleReject(selectedProposal.id)}
                        disabled={isPending || !selectedProposal.participant_id}
                        className="flex-1 text-xs py-2 border-[var(--color-border)] hover:bg-rose-50 hover:text-rose-700 transition-colors"
                      >
                        {t('rejectButton')}
                      </Button>
                      <Button
                        onClick={() => handleApply(selectedProposal.id)}
                        disabled={isPending || !selectedProposal.participant_id}
                        className="flex-1 bg-[var(--color-success)] hover:bg-emerald-600 text-white text-xs py-2"
                      >
                        {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />}
                        {t('applyButton')}
                      </Button>
                    </div>
                  )}
                </Card>
              </div>
            ) : (
              <Card className="h-full border border-dashed border-[var(--color-border-strong)] flex flex-col items-center justify-center p-8 text-center bg-slate-50/50 min-h-[300px]">
                <Mail className="h-10 w-10 text-[var(--color-text-secondary)] mb-2" />
                <h4 className="font-semibold text-sm text-[var(--color-text-primary)]">{t('noSelectedEmail')}</h4>
                <p className="text-xs text-[var(--color-text-secondary)] mt-1.5 max-w-sm leading-relaxed">
                  {t('noSelectedEmailDesc')}
                </p>
              </Card>
            )}
          </div>
        </div>

        {/* Confirmation tracking table (§13) */}
        <Card className="p-5 border-[var(--color-border)] shadow-sm bg-white space-y-4">
          <div className="flex items-center gap-2 border-b pb-3">
            <FileText className="h-4.5 w-4.5 text-[var(--color-accent)]" />
            <h3 className="text-sm font-bold text-[var(--color-text-primary)]">Suivi des confirmations</h3>
          </div>
          {comms.length === 0 ? (
            <p className="text-xs text-[var(--color-text-secondary)] py-4 text-center">
              Aucune confirmation générée. Générez-en une depuis la fiche d’un participant.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse min-w-[600px]">
                <thead>
                  <tr className="border-b bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] text-xs">
                    <th className="p-3">Participant</th>
                    <th className="p-3">Type</th>
                    <th className="p-3">Statut</th>
                    <th className="p-3">Générée le</th>
                    <th className="p-3">Envoyée le</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {comms.map((c) => {
                    const statusStyle =
                      c.status === 'sent' ? 'bg-emerald-50 text-emerald-700'
                        : c.status === 'ready' ? 'bg-amber-50 text-amber-700'
                        : c.status === 'outdated' ? 'bg-rose-50 text-rose-700'
                        : 'bg-slate-100 text-slate-600'
                    const fmt = (d: string | null) => d ? new Date(d).toLocaleString(locale === 'fr' ? 'fr-FR' : locale === 'nl' ? 'nl-NL' : 'en-US', { dateStyle: 'short', timeStyle: 'short' }) : '—'
                    return (
                      <tr key={c.id} className="text-xs">
                        <td className="p-3 font-semibold text-[var(--color-text-primary)]">{c.participant_name || '—'}</td>
                        <td className="p-3 capitalize text-[var(--color-text-secondary)]">{c.type}</td>
                        <td className="p-3"><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${statusStyle}`}>{c.status}</span></td>
                        <td className="p-3 text-[var(--color-text-secondary)]">{fmt(c.generated_at || c.created_at)}</td>
                        <td className="p-3 text-[var(--color-text-secondary)]">{fmt(c.sent_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </AppLayout>
  )
}

