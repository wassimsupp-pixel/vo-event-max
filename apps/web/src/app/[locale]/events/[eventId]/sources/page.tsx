'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { DataSourceCard } from '@/components/ui/DataSourceCard'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Upload, CheckCircle2, AlertTriangle, ArrowRight, Table as TableIcon } from 'lucide-react'

const SOURCE_TYPES = [
  { key: 'registration', name: 'Export Inscriptions (Client)', icon: '📋', subtitle: 'Fichier des participants inscrits' },
  { key: 'fcm', name: 'Export Vols (FCM Broker)', icon: '✈️', subtitle: 'Détails des vols FCM Travel' },
  { key: 'hotel', name: 'Liste Hôtels', icon: '🏨', subtitle: 'Confirmations de réservations hôtelières' },
  { key: 'transfer', name: 'Liste Transferts', icon: '🚐', subtitle: 'Planning des navettes & transferts' },
  { key: 'activity', name: 'Liste Activités', icon: '🎯', subtitle: 'Planning et inscriptions aux activités' }
]

export default function SourcesPage() {
  const params = useParams()
  const router = useRouter()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')

  const [uploadingType, setUploadingType] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isMappingMode, setIsMappingMode] = useState(false)
  const [uploadResponse, setUploadResponse] = useState<any>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})

  // Mocked state for file list
  const [importedFiles, setImportedFiles] = useState<any[]>([
    { id: 'f1', original_filename: 'inscriptions_livanova_v3.xlsx', source_type: 'registration', row_count: 324, imported_at: '2026-07-08T12:00:00Z', import_status: 'processed' },
    { id: 'f2', original_filename: 'fcm_vols_barcelona.csv', source_type: 'fcm', row_count: 297, imported_at: '2026-07-08T14:30:00Z', import_status: 'processed' }
  ])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0])
    }
  }

  const handleUpload = () => {
    if (!selectedFile || !uploadingType) return

    const mockColumns = ['ID_PARTICIPANT', 'FIRSTNAME', 'LASTNAME', 'EMAIL_ADR', 'COMPANY_NAME', 'PHONE_NUM', 'DIETARY_REQ', 'NATIONALITY_CODE']
    const mockSampleRows = [
      { ID_PARTICIPANT: '1', FIRSTNAME: 'Sophie', LASTNAME: 'Martin', EMAIL_ADR: 'sophie@livanova.com', COMPANY_NAME: 'LivaNova', PHONE_NUM: '+32490123456', DIETARY_REQ: 'None', NATIONALITY_CODE: 'BE' },
      { ID_PARTICIPANT: '2', FIRSTNAME: 'Thomas', LASTNAME: 'Bernard', EMAIL_ADR: 'thomas@livanova.com', COMPANY_NAME: 'LivaNova', PHONE_NUM: '+32490123457', DIETARY_REQ: 'Vegetarian', NATIONALITY_CODE: 'FR' }
    ]

    setUploadResponse({
      file_id: 'mock-file-id-' + Math.random().toString(36).substr(2, 9),
      columns: mockColumns,
      sample_rows: mockSampleRows,
      row_count: 100
    })

    // Pre-fill initial mapping guess
    const initialMapping: Record<string, string> = {}
    mockColumns.forEach(col => {
      const lower = col.toLowerCase()
      if (lower.includes('id')) initialMapping[col] = 'id'
      else if (lower.includes('first')) initialMapping[col] = 'first_name'
      else if (lower.includes('last')) initialMapping[col] = 'last_name'
      else if (lower.includes('email') || lower.includes('adr')) initialMapping[col] = 'email'
      else if (lower.includes('comp') || lower.includes('soc')) initialMapping[col] = 'company'
      else if (lower.includes('tel') || lower.includes('phone')) initialMapping[col] = 'phone'
      else if (lower.includes('diet') || lower.includes('regime')) initialMapping[col] = 'dietary_requirements'
      else if (lower.includes('nat') || lower.includes('pays')) initialMapping[col] = 'nationality'
    })
    setMapping(initialMapping)
    setIsMappingMode(true)
  }

  const handleConfirmMapping = () => {
    const newFile = {
      id: uploadResponse.file_id,
      original_filename: selectedFile?.name || 'uploaded_file.xlsx',
      source_type: uploadingType || 'other',
      row_count: uploadResponse.row_count,
      imported_at: new Date().toISOString(),
      import_status: 'processed'
    }

    setImportedFiles(prev => [newFile, ...prev])
    setIsMappingMode(false)
    setUploadingType(null)
    setSelectedFile(null)
    setUploadResponse(null)

    router.refresh()
  }

  return (
    <AppLayout
      eventId={eventId}
      locale={locale}
      pageTitle={t('sources')}
      pageSubtitle="Gérez les fichiers Excel/CSV importés et configurez le mapping des colonnes"
    >
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">{t('sources')}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Importez et configurez vos fichiers sources</p>
        </div>

        {isMappingMode && uploadResponse ? (
          <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)] space-y-6">
            <div className="flex items-center justify-between border-b pb-4">
              <div>
                <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
                  Mapping des colonnes — {selectedFile?.name}
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                  Associez les colonnes de votre fichier aux champs de la Master List. Confirmation humaine requise.
                </p>
              </div>
              <Badge variant="outline" className="border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent-light)]">
                {uploadResponse.row_count} lignes détectées
              </Badge>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Mapping Form */}
              <div className="space-y-4">
                <h4 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
                  Champs Cibles Masterfile
                </h4>
                <div className="space-y-3">
                  {[
                    { field: 'id', label: 'Identifiant Participant (ID)', required: false },
                    { field: 'first_name', label: 'Prénom', required: true },
                    { field: 'last_name', label: 'Nom', required: true },
                    { field: 'email', label: 'Email', required: true },
                    { field: 'company', label: 'Société / Compagnie', required: false },
                    { field: 'phone', label: 'Téléphone', required: false },
                    { field: 'dietary_requirements', label: 'Régime Alimentaire', required: false },
                    { field: 'nationality', label: 'Nationalité', required: false }
                  ].map(({ field, label, required }) => (
                    <div key={field} className="grid grid-cols-12 items-center gap-3">
                      <label className="col-span-5 text-sm font-medium text-[var(--color-text-primary)]">
                        {label} {required && <span className="text-[var(--color-danger)]">*</span>}
                      </label>
                      <div className="col-span-7">
                        <select
                          className="w-full text-xs rounded-md border border-[var(--color-border)] bg-white p-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                          value={Object.keys(mapping).find(k => mapping[k] === field) || ''}
                          onChange={(e) => {
                            const val = e.target.value
                            const next = { ...mapping }
                            // Remove previous binding
                            Object.keys(next).forEach(k => {
                              if (next[k] === field) delete next[k]
                            })
                            if (val) next[val] = field
                            setMapping(next)
                          }}
                        >
                          <option value="">-- Ignorer --</option>
                          {uploadResponse.columns.map((col: string) => (
                            <option key={col} value={col}>{col}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Data Preview */}
              <div className="space-y-4">
                <h4 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider flex items-center gap-1.5">
                  <TableIcon className="h-3.5 w-3.5" /> Aperçu des premières lignes
                </h4>
                <div className="overflow-x-auto rounded-md border border-[var(--color-border)] max-h-[300px]">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-[var(--color-text-secondary)]">
                      <tr>
                        {uploadResponse.columns.map((col: string) => (
                          <th key={col} className="p-2.5 font-medium border-b border-r">{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y text-[var(--color-text-primary)]">
                      {uploadResponse.sample_rows.map((row: any, rIdx: number) => (
                        <tr key={rIdx}>
                          {uploadResponse.columns.map((col: string) => (
                            <td key={col} className="p-2.5 border-r truncate max-w-[120px]">{row[col]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4 border-t">
              <Button variant="outline" onClick={() => setIsMappingMode(false)}>
                Annuler
              </Button>
              <Button
                className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white"
                onClick={handleConfirmMapping}
              >
                Confirmer le mapping & Lancer l'analyse <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Import options */}
            <div className="col-span-12 lg:col-span-2 space-y-6">
              <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)]">
                <h3 className="text-base font-semibold text-[var(--color-text-primary)] mb-4">
                  Importer une nouvelle source de données
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {SOURCE_TYPES.map((src) => (
                    <div
                      key={src.key}
                      className="group cursor-pointer rounded-lg border border-[var(--color-border)] p-4 bg-white hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-light)]/10 transition-all flex items-start gap-3.5"
                      onClick={() => setUploadingType(src.key)}
                    >
                      <span className="text-2xl p-1 bg-slate-50 group-hover:bg-white rounded-md transition-colors">{src.icon}</span>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-accent)] transition-colors">
                          {src.name}
                        </h4>
                        <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{src.subtitle}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              {/* Upload Overlay Modal if type selected */}
              {uploadingType && !isMappingMode && (
                <Card className="p-6 border-[var(--color-accent)] bg-[var(--color-accent-light)]/5 shadow-[var(--shadow-card)] space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                      Importer : {SOURCE_TYPES.find(s => s.key === uploadingType)?.name}
                    </h3>
                    <Button variant="ghost" size="sm" onClick={() => setUploadingType(null)}>Fermer</Button>
                  </div>
                  <div className="flex flex-col items-center justify-center border-2 border-dashed border-[var(--color-border-strong)] rounded-lg p-6 bg-white hover:border-[var(--color-accent)] transition-colors relative">
                    <input
                      type="file"
                      id="source-file-upload"
                      className="absolute inset-0 opacity-0 cursor-pointer"
                      accept=".xlsx,.xls,.csv"
                      onChange={handleFileChange}
                    />
                    <Upload className="h-8 w-8 text-[var(--color-text-secondary)] mb-2" />
                    <p className="text-xs text-[var(--color-text-primary)] font-medium">
                      {selectedFile ? selectedFile.name : 'Sélectionnez ou glissez-déposez votre fichier Excel / CSV'}
                    </p>
                    <p className="text-[10px] text-[var(--color-text-secondary)] mt-1">Formats acceptés : .xlsx, .xls, .csv (Max 50Mo)</p>
                  </div>
                  <div className="flex justify-end gap-2.5">
                    <Button variant="outline" onClick={() => { setUploadingType(null); setSelectedFile(null); }}>
                      Annuler
                    </Button>
                    <Button
                      className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white"
                      disabled={!selectedFile}
                      onClick={handleUpload}
                    >
                      Analyser le fichier
                    </Button>
                  </div>
                </Card>
              )}

              {/* File registry list */}
              <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)] space-y-4">
                <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
                  Fichiers sources importés
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-[var(--color-text-secondary)] font-medium text-xs uppercase tracking-wider">
                        <th className="pb-3">Fichier</th>
                        <th className="pb-3">Type de source</th>
                        <th className="pb-3">Nombre de lignes</th>
                        <th className="pb-3">Date d'import</th>
                        <th className="pb-3">Statut</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y text-[var(--color-text-primary)]">
                      {importedFiles.map((file) => (
                        <tr key={file.id} className="hover:bg-slate-50/50">
                          <td className="py-3.5 font-medium">{file.original_filename}</td>
                          <td className="py-3.5 text-xs text-[var(--color-text-secondary)]">
                            {SOURCE_TYPES.find(s => s.key === file.source_type)?.name || file.source_type}
                          </td>
                          <td className="py-3.5 text-xs font-semibold">{file.row_count} lignes</td>
                          <td className="py-3.5 text-xs text-[var(--color-text-secondary)]">
                            {new Date(file.imported_at).toLocaleString('fr-FR')}
                          </td>
                          <td className="py-3.5">
                            <Badge className="bg-[var(--color-success-light)] text-[var(--color-success)] border-0 flex items-center gap-1 w-fit">
                              <CheckCircle2 className="h-3 w-3" /> Traité
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>

            {/* Sidebar info */}
            <div className="col-span-12 lg:col-span-1 space-y-6">
              <Card className="p-5 border-[var(--color-border)] shadow-[var(--shadow-card)] space-y-4">
                <h4 className="text-sm font-semibold text-[var(--color-text-primary)]">Charte de Qualité</h4>
                <div className="space-y-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
                  <p>
                    Pour chaque fichier importé, vous devez mapper ses colonnes avec les champs standards de la plateforme.
                  </p>
                  <div className="flex gap-2.5 items-start">
                    <CheckCircle2 className="h-4 w-4 text-[var(--color-success)] shrink-0 mt-0.5" />
                    <span>L'outil essaie de deviner automatiquement les correspondances d'en-têtes.</span>
                  </div>
                  <div className="flex gap-2.5 items-start">
                    <AlertTriangle className="h-4 w-4 text-[var(--color-warning)] shrink-0 mt-0.5" />
                    <span><strong>Validation Humaine Obligatoire :</strong> Vous devez confirmer et valider chaque mapping avant qu'il ne soit traité par le moteur de consolidation.</span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
