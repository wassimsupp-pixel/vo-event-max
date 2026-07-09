'use client'

import React from 'react'
import { useParams } from 'next/navigation'
import { AppLayout } from '@/components/layout/AppLayout'
import { Mail, Send, FileText, Search, Sparkles, ShieldAlert } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export default function CommunicationsPage() {
  const { locale, eventId } = useParams() as { locale: string; eventId: string }

  const templates = [
    { name: 'Confirmation d\'inscription', trigger: 'Automatique', status: 'Actif', lastSent: 'Il y a 2h' },
    { name: 'Relance billet d\'avion manquant', trigger: 'Manuel', status: 'Actif', lastSent: 'Il y a 1j' },
    { name: 'Détails pratiques hôtel & navettes', trigger: '7 jours avant', status: 'Brouillon', lastSent: '-' },
  ]

  return (
    <AppLayout eventId={eventId} locale={locale}>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center border-b pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)] flex items-center gap-2">
              <Mail className="h-6 w-6 text-[var(--color-accent)]" />
              Communications & Campagnes
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Gérez les modèles de courriels d&apos;invitation, les notifications de logistique et le suivi des envois.
            </p>
          </div>
        </div>

        {/* AI Agent Teaser */}
        <div className="rounded-[var(--radius-card)] bg-gradient-to-r from-[var(--color-accent-light)] to-[var(--color-cta-light)] p-6 border border-[var(--color-accent)]/20 shadow-sm flex items-start gap-4">
          <div className="h-10 w-10 rounded-full bg-white flex items-center justify-center shadow-sm flex-shrink-0 text-amber-500">
            <Sparkles className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-bold text-[var(--color-text-primary)]">Email Agent IA (Phase 2/3)</h4>
              <Badge className="bg-[var(--color-accent)] text-white text-[10px]">Bientôt disponible</Badge>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1.5 leading-relaxed max-w-2xl">
              Cette section accueillera l&apos;Email Agent intelligent. Il analysera en temps réel les emails reçus pour en extraire automatiquement les demandes spéciales (ex: nuits d&apos;hôtel supplémentaires) et rédigera les réponses en un clic après validation humaine.
            </p>
          </div>
        </div>

        {/* Templates */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Modèles de courriels</h3>
            <div className="rounded-[var(--radius-card)] border bg-white overflow-hidden shadow-sm">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 font-semibold text-[var(--color-text-secondary)] text-left">
                  <tr>
                    <th className="px-6 py-3">Nom du modèle</th>
                    <th className="px-6 py-3">Déclencheur</th>
                    <th className="px-6 py-3">Statut</th>
                    <th className="px-6 py-3">Dernier envoi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-[var(--color-text-primary)]">
                  {templates.map((tpl, i) => (
                    <tr key={i} className="hover:bg-slate-50/50">
                      <td className="px-6 py-4 font-medium flex items-center gap-2">
                        <FileText className="h-4 w-4 text-slate-400" />
                        {tpl.name}
                      </td>
                      <td className="px-6 py-4 text-xs font-mono">{tpl.trigger}</td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          tpl.status === 'Actif' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
                        }`}>
                          {tpl.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs text-[var(--color-text-secondary)]">{tpl.lastSent}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Actions rapides</h3>
            <Card className="p-4 flex flex-col gap-3">
              <button className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--color-border)] py-2 text-xs font-semibold text-[var(--color-text-primary)] hover:bg-slate-50 transition-colors">
                <Search className="h-3.5 w-3.5" />
                Rechercher un envoi
              </button>
              <button className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-[var(--color-accent)] py-2 text-xs font-semibold text-white hover:bg-[var(--color-accent)]/90 transition-colors shadow-sm">
                <Send className="h-3.5 w-3.5" />
                Envoyer une campagne
              </button>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
