'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AppLayout } from '@/components/layout/AppLayout'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Upload, CheckCircle2, AlertTriangle, ArrowRight, Table as TableIcon, Loader2, Trash2, Plus, X } from 'lucide-react'
import type { UploadedFile, FileUploadResponse } from '@/lib/api'
import { api } from '@/lib/api'

const SOURCE_TYPES = [
  { key: 'masterfile', name: 'Master File (infos mixtes)', icon: '🗂️', subtitle: 'Un seul fichier: participants + vols + hôtel + transferts + activités' },
  { key: 'registration', name: 'Export Inscriptions (Client)', icon: '📋', subtitle: 'Fichier des participants inscrits' },
  { key: 'fcm', name: 'Export Vols (FCM Broker)', icon: '✈️', subtitle: 'Détails des vols FCM Travel' },
  { key: 'hotel', name: 'Liste Hôtels', icon: '🏨', subtitle: 'Confirmations de réservations hôtelières' },
  { key: 'transfer', name: 'Liste Transferts', icon: '🚐', subtitle: 'Planning des navettes & transferts' },
  { key: 'activity', name: 'Liste Activités', icon: '🎯', subtitle: 'Planning et inscriptions aux activités' }
]

const MAPPING_FIELDS_BY_TYPE: Record<string, { field: string; label: string; required: boolean }[]> = {
  // Master File: a single file mixing every kind of info. All fields are offered
  // and none is strictly required — the user maps whatever the file contains.
  masterfile: [
    { field: 'first_name', label: 'Prénom (First Name)', required: false },
    { field: 'last_name', label: 'Nom (Last Name)', required: false },
    { field: 'traveler_name', label: 'Nom voyageur / complet', required: false },
    { field: 'email', label: 'Email', required: false },
    { field: 'company', label: 'Société / Compagnie', required: false },
    { field: 'phone', label: 'Téléphone', required: false },
    { field: 'nationality', label: 'Nationalité', required: false },
    { field: 'attendee_category', label: 'Catégorie participant', required: false },
    { field: 'job_title', label: 'Fonction / Poste', required: false },
    { field: 'region', label: 'Région', required: false },
    { field: 'country', label: 'Pays', required: false },
    { field: 'date_of_birth', label: 'Date de naissance', required: false },
    { field: 'passport_number', label: 'N° passeport', required: false },
    { field: 'passport_expiry', label: 'Expiration passeport', required: false },
    { field: 'dietary_requirements', label: 'Régime Alimentaire', required: false },
    { field: 'food_allergy_info', label: 'Allergies / Restrictions', required: false },
    { field: 'airline', label: 'Compagnie Aérienne', required: false },
    { field: 'flight_number', label: 'Numéro de Vol', required: false },
    { field: 'departure_airport', label: 'Aéroport Départ', required: false },
    { field: 'arrival_airport', label: 'Aéroport Arrivée', required: false },
    { field: 'departure_time', label: 'Date/Heure Départ', required: false },
    { field: 'arrival_time', label: 'Date/Heure Arrivée', required: false },
    { field: 'pnr_code', label: 'Code PNR', required: false },
    { field: 'hotel_name', label: 'Nom de l\'Hôtel', required: false },
    { field: 'check_in_date', label: 'Date Check-in', required: false },
    { field: 'check_out_date', label: 'Date Check-out', required: false },
    { field: 'room_type', label: 'Type de Chambre', required: false },
    { field: 'pickup_location', label: 'Transfert — Lieu de prise en charge', required: false },
    { field: 'dropoff_location', label: 'Transfert — Destination', required: false },
    { field: 'pickup_time', label: 'Transfert — Heure', required: false },
    { field: 'activity_name', label: 'Nom de l\'Activité', required: false },
  ],
  registration: [
    { field: 'first_name', label: 'Prénom (First Name)', required: true },
    { field: 'last_name', label: 'Nom (Last Name)', required: true },
    { field: 'email', label: 'Email', required: true },
    { field: 'company', label: 'Société / Compagnie', required: false },
    { field: 'phone', label: 'Téléphone', required: false },
    { field: 'dietary_requirements', label: 'Régime Alimentaire', required: false },
    { field: 'nationality', label: 'Nationalité', required: false }
  ],
  // Non-registration files identify the traveller by a single name (Traveller)
  // or email and are matched to existing participants — so identity fields are
  // OPTIONAL here (only the domain fields are truly required).
  fcm: [
    { field: 'traveler_name', label: 'Nom voyageur (billet)', required: false },
    { field: 'first_name', label: 'Prénom (First Name)', required: false },
    { field: 'last_name', label: 'Nom (Last Name)', required: false },
    { field: 'email', label: 'Email', required: false },
    { field: 'flight_number', label: 'Numéro de Vol', required: true },
    { field: 'pnr_code', label: 'Code PNR', required: false },
    { field: 'airline', label: 'Compagnie Aérienne', required: false },
    { field: 'departure_airport', label: 'Aéroport Départ', required: true },
    { field: 'arrival_airport', label: 'Aéroport Arrivée', required: true },
    { field: 'departure_time', label: 'Date/Heure Départ', required: true },
    { field: 'arrival_time', label: 'Date/Heure Arrivée', required: true },
    { field: 'baggage_info', label: 'Infos Bagages', required: false }
  ],
  hotel: [
    { field: 'traveler_name', label: 'Nom voyageur / complet', required: false },
    { field: 'first_name', label: 'Prénom (First Name)', required: false },
    { field: 'last_name', label: 'Nom (Last Name)', required: false },
    { field: 'email', label: 'Email', required: false },
    { field: 'hotel_name', label: 'Nom de l\'Hôtel', required: true },
    { field: 'check_in_date', label: 'Date Check-in', required: true },
    { field: 'check_out_date', label: 'Date Check-out', required: true },
    { field: 'room_type', label: 'Type de Chambre', required: false }
  ],
  transfer: [
    { field: 'traveler_name', label: 'Nom voyageur / complet', required: false },
    { field: 'first_name', label: 'Prénom (First Name)', required: false },
    { field: 'last_name', label: 'Nom (Last Name)', required: false },
    { field: 'email', label: 'Email', required: false },
    { field: 'transfer_type', label: 'Type de Transfert (arrival/departure)', required: false },
    { field: 'pickup_location', label: 'Lieu de Prise en charge', required: true },
    { field: 'dropoff_location', label: 'Destination', required: true },
    { field: 'pickup_time', label: 'Heure de Prise en charge', required: true },
    { field: 'vehicle_type', label: 'Type de Véhicule', required: false }
  ],
  activity: [
    { field: 'traveler_name', label: 'Nom voyageur / complet', required: false },
    { field: 'first_name', label: 'Prénom (First Name)', required: false },
    { field: 'last_name', label: 'Nom (Last Name)', required: false },
    { field: 'email', label: 'Email', required: false },
    { field: 'activity_name', label: 'Nom de l\'Activité', required: true }
  ]
}
const ALL_MAPPING_FIELDS = [
  { field: 'first_name', label: 'Prénom (First Name)' },
  { field: 'last_name', label: 'Nom (Last Name)' },
  { field: 'email', label: 'Email' },
  { field: 'company', label: 'Société / Compagnie' },
  { field: 'phone', label: 'Téléphone' },
  { field: 'dietary_requirements', label: 'Régime Alimentaire' },
  { field: 'nationality', label: 'Nationalité' },
  { field: 'flight_number', label: 'Numéro de Vol' },
  { field: 'pnr_code', label: 'Code PNR' },
  { field: 'airline', label: 'Compagnie Aérienne' },
  { field: 'departure_airport', label: 'Aéroport Départ' },
  { field: 'arrival_airport', label: 'Aéroport Arrivée' },
  { field: 'departure_time', label: 'Date/Heure Départ' },
  { field: 'arrival_time', label: 'Date/Heure Arrivée' },
  { field: 'baggage_info', label: 'Infos Bagages' },
  { field: 'hotel_name', label: 'Nom de l\'Hôtel' },
  { field: 'check_in_date', label: 'Date Check-in' },
  { field: 'check_out_date', label: 'Date Check-out' },
  { field: 'room_type', label: 'Type de Chambre' },
  { field: 'transfer_type', label: 'Type de Transfert' },
  { field: 'pickup_location', label: 'Lieu de Prise en charge' },
  { field: 'dropoff_location', label: 'Destination' },
  { field: 'pickup_time', label: 'Heure de Prise en charge' },
  { field: 'vehicle_type', label: 'Type de Véhicule' },
  { field: 'activity_name', label: 'Nom de l\'Activité' }
]

const CANONICAL_FIELD_LABELS: Record<string, string> = {
  id: 'ID Participant',
  first_name: 'Prénom (First Name)',
  last_name: 'Nom (Last Name)',
  email: 'Email',
  company: 'Société / Compagnie',
  phone: 'Téléphone',
  nationality: 'Nationalité',
  dietary_requirements: 'Régime Alimentaire',
  departure_date: 'Date Départ Vol',
  return_date: 'Date Retour Vol',
  flight_number: 'Numéro de Vol',
  departure_airport: 'Aéroport Départ',
  arrival_airport: 'Aéroport Arrivée',
  departure_time: 'Date/Heure Départ Vol',
  arrival_time: 'Date/Heure Arrivée Vol',
  pnr_code: 'Code PNR',
  airline: 'Compagnie Aérienne',
  baggage_info: 'Infos Bagages',
  hotel_name: 'Nom de l\'Hôtel',
  check_in_date: 'Date Check-in',
  check_out_date: 'Date Check-out',
  room_type: 'Type de Chambre',
  transfer_type: 'Type de Transfert',
  pickup_location: 'Lieu de Prise en charge',
  dropoff_location: 'Destination',
  pickup_time: 'Heure de Prise en charge',
  vehicle_type: 'Type de Véhicule',
  activity_name: 'Nom de l\'Activité',
  // Master-file aligned fields
  attendee_category: 'Catégorie participant',
  job_title: 'Fonction / Poste (Job Title)',
  region: 'Région',
  function: 'Fonction',
  language: 'Langue',
  badge_name: 'Nom sur badge',
  country: 'Pays',
  date_of_birth: 'Date de naissance',
  passport_number: 'Numéro de passeport',
  passport_expiry: 'Expiration passeport',
  food_allergy_info: 'Allergies / Restrictions alimentaires',
  arrival_date: 'Date Arrivée Vol',
  departure_city: 'Ville de départ',
  departure_country: 'Pays de départ',
  arrival_city: 'Ville d\'arrivée',
  arrival_country: 'Pays d\'arrivée',
  traveler_name: 'Nom voyageur (billet)',
  flight_domestic_intl: 'Domestique / International',
  early_checkin: 'Check-in anticipé',
  late_checkout: 'Check-out tardif',
  fast_track: 'Fast Track',
  extra_meetings: 'Réunions supplémentaires',
  headphones_translation: 'Casque traduction',
}

export default function SourcesPage() {
  const params = useParams()
  const router = useRouter()
  const locale = params.locale as string
  const eventId = params.eventId as string

  const t = useTranslations('nav')

  const [uploadingType, setUploadingType] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isMappingMode, setIsMappingMode] = useState(false)
  const [uploadResponse, setUploadResponse] = useState<FileUploadResponse | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  // Columns the user chose to map to a custom (non-predefined) field
  const [customFields, setCustomFields] = useState<Record<string, boolean>>({})
  // Reusable user-defined target fields (persisted per event), available in every
  // column's dropdown so the user can add mapping fields freely.
  const [customFieldList, setCustomFieldList] = useState<string[]>([])
  const [newCustomField, setNewCustomField] = useState('')

  const customFieldsKey = `mapping_custom_fields_${eventId}`

  useEffect(() => {
    try {
      const saved = localStorage.getItem(customFieldsKey)
      if (saved) setCustomFieldList(JSON.parse(saved))
    } catch { /* ignore corrupt storage */ }
  }, [customFieldsKey])

  const persistCustomFields = (list: string[]) => {
    setCustomFieldList(list)
    try { localStorage.setItem(customFieldsKey, JSON.stringify(list)) } catch { /* ignore */ }
  }

  const addCustomField = () => {
    const name = newCustomField.trim()
    if (!name) return
    if (customFieldList.some(f => f.toLowerCase() === name.toLowerCase())) { setNewCustomField(''); return }
    persistCustomFields([...customFieldList, name])
    setNewCustomField('')
  }

  const removeCustomField = (name: string) => {
    persistCustomFields(customFieldList.filter(f => f !== name))
    // Unmap any column that used this custom field
    setMapping(prev => {
      const next = { ...prev }
      Object.keys(next).forEach(col => { if (next[col] === name) delete next[col] })
      return next
    })
  }

  // User-added source-column rows (name of a column in the file + its target).
  // Lets the user add as many columns to map as they want.
  const [extraColumns, setExtraColumns] = useState<{ id: string; name: string; target: string }[]>([])

  const addExtraColumn = () => {
    setExtraColumns(prev => [...prev, { id: `x_${Date.now()}_${prev.length}`, name: '', target: '' }])
  }
  const updateExtraColumn = (id: string, patch: Partial<{ name: string; target: string }>) => {
    setExtraColumns(prev => prev.map(c => (c.id === id ? { ...c, ...patch } : c)))
  }
  const removeExtraColumn = (id: string) => {
    setExtraColumns(prev => prev.filter(c => c.id !== id))
  }

  // Real file list state
  const [importedFiles, setImportedFiles] = useState<UploadedFile[]>([])
  const [filesLoading, setFilesLoading] = useState(true)

  // Upload states
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [deletingFileId, setDeletingFileId] = useState<string | null>(null)

  const loadFiles = useCallback(async () => {
    setFilesLoading(true)
    try {
      const files = await api.files.list(eventId)
      setImportedFiles(files)
    } catch (err) {
      console.error('Failed to load files:', err)
    } finally {
      setFilesLoading(false)
    }
  }, [eventId])

  useEffect(() => {
    loadFiles()
  }, [loadFiles])

  const handleDeleteFile = async (fileId: string) => {
    if (!confirm('Êtes-vous sûr de vouloir supprimer ce fichier ? cette action est irréversible.')) {
      return
    }
    setDeletingFileId(fileId)
    try {
      await api.files.delete(fileId)
      await loadFiles()
      router.refresh()
    } catch (err) {
      console.error('Failed to delete file:', err)
      alert('Erreur lors de la suppression du fichier.')
    } finally {
      setDeletingFileId(null)
    }
  }

  const getFieldLabel = (field: string) => {
    const fields = MAPPING_FIELDS_BY_TYPE[uploadingType || 'registration'] || []
    const found = fields.find(f => f.field === field)
    if (found) return found.label
    return CANONICAL_FIELD_LABELS[field] || field
  }

  const getSortedFieldsForColumn = (col: string) => {
    const suggestion = uploadResponse?.mapping_suggestions?.[col]
    const suggestedField = suggestion?.suggested_field || null
    const alternatives = suggestion?.alternatives || []
    // Offer every canonical field (the master file is rich and may be imported
    // under any source type); prioritise the current type's fields first.
    const typeFields = (MAPPING_FIELDS_BY_TYPE[uploadingType || 'registration'] || []).map(f => f.field)
    const allFields = Object.keys(CANONICAL_FIELD_LABELS)
    const currentTypeFields = [...typeFields, ...allFields.filter(f => !typeFields.includes(f))]

    const validSuggestedField = currentTypeFields.includes(suggestedField || '') ? suggestedField : null
    const validAlternatives = alternatives.filter(f => currentTypeFields.includes(f))

    const alternativesList = validAlternatives.filter(f => f !== validSuggestedField)
    const othersList = currentTypeFields.filter(f => f !== validSuggestedField && !alternativesList.includes(f))

    othersList.sort((a, b) => {
      const labelA = getFieldLabel(a)
      const labelB = getFieldLabel(b)
      return labelA.localeCompare(labelB)
    })

    return {
      suggestedField: validSuggestedField,
      alternatives: alternativesList,
      others: othersList,
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0])
      setUploadError(null)
    }
  }

  const handleUpload = async () => {
    if (!selectedFile || !uploadingType) return

    setUploading(true)
    setUploadError(null)
    try {
      // 'masterfile' is a UI convenience (mixed-info file). It is stored as
      // 'registration' — a valid DB source type that already creates participants;
      // the domain extractor pulls flight/hotel/transfer/activity from every row.
      const apiSourceType = uploadingType === 'masterfile' ? 'registration' : uploadingType
      const response = await api.files.upload(eventId, selectedFile, apiSourceType)
      setUploadResponse(response)

      // Pre-fill initial mapping guess from backend suggestions (confidence >= 0.5)
      const initialMapping: Record<string, string> = {}
      if (response.mapping_suggestions) {
        Object.entries(response.mapping_suggestions).forEach(([col, sug]) => {
          if (sug.suggested_field && sug.confidence >= 0.5) {
            initialMapping[col] = sug.suggested_field
          }
        })
      }
      setMapping(initialMapping)
      setExtraColumns([])
      setIsMappingMode(true)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Erreur lors de l\'upload du fichier')
    } finally {
      setUploading(false)
    }
  }

  const handleConfirmMapping = async () => {
    if (!uploadResponse) return

    try {
      // Merge auto-detected mappings with the columns the user added manually.
      const finalMapping: Record<string, string> = { ...mapping }
      extraColumns.forEach(c => {
        const name = c.name.trim()
        if (name && c.target) finalMapping[name] = c.target
      })
      await api.files.mapColumns(uploadResponse.file_id, finalMapping)
      await loadFiles()
      setIsMappingMode(false)
      setUploadingType(null)
      setSelectedFile(null)
      setUploadResponse(null)
      setExtraColumns([])
      setUploadError(null)
      router.refresh()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Erreur lors de la confirmation du mapping')
    }
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

        {/* Prominent call-to-action for the import step (§8) */}
        {!isMappingMode && (
          <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--color-accent)]/30 bg-[var(--color-accent-light)] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <Upload className="h-5 w-5 flex-shrink-0 text-[var(--color-accent)]" />
              <div>
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Importez vos fichiers sources ({new Set(importedFiles.map((f) => f.source_type)).size}/{SOURCE_TYPES.length})
                </p>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  Ajoutez les exports (inscriptions, vols, hôtels, transferts, activités), puis lancez la consolidation.
                </p>
              </div>
            </div>
            <button
              onClick={() => document.getElementById('import-zone')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              className="inline-flex items-center gap-2 self-start rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[var(--color-accent)]/90 sm:self-auto"
            >
              <Upload className="h-4 w-4" /> Importer un fichier
            </button>
          </div>
        )}

        {isMappingMode && uploadResponse ? (
          <Card className="p-6 border-[var(--color-border)] shadow-[var(--shadow-card)] space-y-6">
            {uploadResponse.import_status === 'mapped' && (
              <div className="flex items-start gap-3 rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success-light)] px-4 py-3">
                <CheckCircle2 className="h-5 w-5 shrink-0 text-[var(--color-success)] mt-0.5" />
                <div className="text-sm">
                  <p className="font-semibold text-[var(--color-text-primary)]">
                    Analyse & mapping automatiques terminés — consolidation lancée.
                  </p>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    Les informations de cette personne sont fusionnées avec les autres fichiers.
                    Vous pouvez ajuster le mapping ci-dessous si besoin, ou{' '}
                    <button
                      onClick={() => router.push(`/${locale}/events/${eventId}/master-list`)}
                      className="font-semibold text-[var(--color-accent)] underline"
                    >
                      aller à la master list
                    </button>.
                  </p>
                </div>
              </div>
            )}
            <div className="flex items-center justify-between border-b pb-4">
              <div>
                <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
                  Mapping des colonnes — {selectedFile?.name}
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                  Le mapping a été détecté automatiquement. Vérifiez ou ajustez si nécessaire — c&apos;est optionnel.
                </p>
              </div>
              <Badge variant="outline" className="border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent-light)]">
                {uploadResponse.row_count} lignes détectées
              </Badge>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Mapping Form */}
              <div className="space-y-4">
                <h4 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
                  Mapping des colonnes
                </h4>

                {/* Reusable custom target fields — add mapping fields as you want */}
                <div className="rounded-md border border-dashed border-[var(--color-accent)]/40 bg-[var(--color-accent-light)]/20 p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newCustomField}
                      onChange={(e) => setNewCustomField(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomField() } }}
                      placeholder="Ajouter un champ personnalisé (ex. Numéro de commande, VIP, Taille t-shirt…)"
                      className="flex-1 text-xs rounded-md border border-[var(--color-border)] bg-white p-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                    />
                    <Button
                      type="button"
                      size="sm"
                      className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white shrink-0"
                      onClick={addCustomField}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" /> Ajouter
                    </Button>
                  </div>
                  {customFieldList.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {customFieldList.map(name => (
                        <span key={name} className="inline-flex items-center gap-1 rounded-full bg-white border border-[var(--color-accent)]/30 px-2 py-0.5 text-[11px] font-medium text-[var(--color-accent)]">
                          {name}
                          <button type="button" onClick={() => removeCustomField(name)} className="hover:text-[var(--color-danger)]" title="Supprimer ce champ">
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="text-[10px] text-[var(--color-text-secondary)]">
                    Les champs ajoutés apparaissent dans la liste déroulante de chaque colonne et sont mémorisés pour cet événement.
                  </p>
                </div>

                <div className="space-y-3 max-h-[350px] overflow-y-auto pr-2 border rounded-md p-4 bg-slate-50">
                  {uploadResponse.columns.map((col: string) => {
                    const colOptions = getSortedFieldsForColumn(col)
                    const currentSuggestion = uploadResponse?.mapping_suggestions?.[col]
                    return (
                      <div key={col} className="grid grid-cols-12 items-center gap-3">
                        <div className="col-span-5 flex flex-col min-w-0">
                          <span className="text-sm font-medium text-[var(--color-text-primary)] truncate" title={col}>
                            {col}
                          </span>
                          {currentSuggestion?.suggested_field && (
                            <span className={`inline-flex items-center text-[10px] font-medium mt-0.5 ${
                              currentSuggestion.confidence >= 0.7 ? 'text-emerald-600' : 'text-amber-600'
                            }`}>
                              Suggéré — {Math.round(currentSuggestion.confidence * 100)}%
                            </span>
                          )}
                        </div>
                        <div className="col-span-7 space-y-1.5">
                          <select
                            className="w-full text-xs rounded-md border border-[var(--color-border)] bg-white p-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                            value={customFields[col] ? '__custom__' : (mapping[col] || '')}
                            onChange={(e) => {
                              const val = e.target.value
                              if (val === '__custom__') {
                                setCustomFields(prev => ({ ...prev, [col]: true }))
                                setMapping(prev => { const next = { ...prev }; delete next[col]; return next })
                                return
                              }
                              setCustomFields(prev => ({ ...prev, [col]: false }))
                              setMapping(prev => {
                                const next = { ...prev }
                                if (val) next[col] = val
                                else delete next[col]
                                return next
                              })
                            }}
                          >
                            <option value="">-- Ignorer --</option>
                            {customFieldList.length > 0 && (
                              <optgroup label="⭐ Mes champs ajoutés">
                                {customFieldList.map(name => (
                                  <option key={name} value={name}>
                                    {name}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            {colOptions.suggestedField && (
                              <optgroup label="Suggéré">
                                <option value={colOptions.suggestedField}>
                                  {getFieldLabel(colOptions.suggestedField)}
                                </option>
                              </optgroup>
                            )}
                            {colOptions.alternatives.length > 0 && (
                              <optgroup label="Alternatives">
                                {colOptions.alternatives.map(field => (
                                  <option key={field} value={field}>
                                    {getFieldLabel(field)}
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            <optgroup label="Tous les champs">
                              {colOptions.others.map(field => (
                                <option key={field} value={field}>
                                  {getFieldLabel(field)}
                                </option>
                              ))}
                            </optgroup>
                            <option value="__custom__">➕ Champ personnalisé ponctuel…</option>
                          </select>
                          {customFields[col] && (
                            <input
                              type="text"
                              autoFocus
                              placeholder="Nom du champ personnalisé (ex. Numéro de commande)"
                              value={mapping[col] || ''}
                              onChange={(e) => {
                                const v = e.target.value
                                setMapping(prev => {
                                  const next = { ...prev }
                                  if (v.trim()) next[col] = v
                                  else delete next[col]
                                  return next
                                })
                              }}
                              className="w-full text-xs rounded-md border border-[var(--color-accent)] bg-white p-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                            />
                          )}
                        </div>
                      </div>
                    )
                  })}

                  {/* Columns the user adds manually (name from the file + target) */}
                  {extraColumns.map((c) => (
                    <div key={c.id} className="grid grid-cols-12 items-center gap-3">
                      <div className="col-span-5 flex items-center gap-1.5 min-w-0">
                        <input
                          type="text"
                          list="file-columns-list"
                          value={c.name}
                          onChange={(e) => updateExtraColumn(c.id, { name: e.target.value })}
                          placeholder="Nom de la colonne (ex. Traveller, Airline…)"
                          className="w-full text-sm rounded-md border border-[var(--color-accent)]/50 bg-white p-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                        />
                        <button type="button" onClick={() => removeExtraColumn(c.id)} className="shrink-0 text-[var(--color-text-secondary)] hover:text-[var(--color-danger)]" title="Retirer cette colonne">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="col-span-7">
                        <select
                          className="w-full text-xs rounded-md border border-[var(--color-border)] bg-white p-2 text-[var(--color-text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
                          value={c.target}
                          onChange={(e) => updateExtraColumn(c.id, { target: e.target.value })}
                        >
                          <option value="">-- Choisir le champ cible --</option>
                          {customFieldList.length > 0 && (
                            <optgroup label="⭐ Mes champs ajoutés">
                              {customFieldList.map(name => (
                                <option key={name} value={name}>{name}</option>
                              ))}
                            </optgroup>
                          )}
                          <optgroup label="Tous les champs">
                            {Object.keys(CANONICAL_FIELD_LABELS).map(field => (
                              <option key={field} value={field}>{CANONICAL_FIELD_LABELS[field]}</option>
                            ))}
                          </optgroup>
                        </select>
                      </div>
                    </div>
                  ))}

                  {/* Datalist of the file's real columns, for quick autocomplete */}
                  <datalist id="file-columns-list">
                    {(uploadResponse.columns || []).map((col: string) => (
                      <option key={col} value={col} />
                    ))}
                  </datalist>

                  <button
                    type="button"
                    onClick={addExtraColumn}
                    className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-accent)] hover:underline pt-1"
                  >
                    <Plus className="h-3.5 w-3.5" /> Ajouter une colonne à mapper
                  </button>
                </div>
              </div>

              {/* Required fields indicator / preview */}
              <div className="space-y-4">
                <h4 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
                  Champs Cibles Masterfile
                </h4>
                <div className="p-4 bg-slate-50 rounded-lg border space-y-3">
                  <p className="text-xs text-[var(--color-text-secondary)]">
                    Pour importer ce fichier en tant que <strong>{SOURCE_TYPES.find(s => s.key === uploadingType)?.name}</strong>, les correspondances ci-dessous sont appliquées :
                  </p>
                  <ul className="text-xs space-y-2 mt-2 max-h-[300px] overflow-y-auto pr-2">
                    {(MAPPING_FIELDS_BY_TYPE[uploadingType || 'registration'] || []).map(({ field, label, required }) => {
                      const isMapped = Object.values(mapping).includes(field)
                      return (
                        <li key={field} className="flex items-center justify-between border-b pb-1.5 border-slate-100 last:border-b-0 last:pb-0">
                          <span className={`${required ? 'font-semibold' : ''} text-[var(--color-text-primary)]`}>
                            {label} {required && <span className="text-[var(--color-danger)]">*</span>}
                          </span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            isMapped
                              ? 'bg-emerald-100 text-emerald-800'
                              : required
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-slate-100 text-slate-600'
                          }`}>
                            {isMapped ? 'Mappé' : required ? 'Requis' : 'Optionnel'}
                          </span>
                        </li>
                      )
                    })}
                    {/* User-added custom fields shown as real target columns */}
                    {customFieldList.map((name) => {
                      const isMapped = Object.values(mapping).includes(name)
                      return (
                        <li key={`custom-${name}`} className="flex items-center justify-between border-b pb-1.5 border-slate-100 last:border-b-0 last:pb-0">
                          <span className="text-[var(--color-text-primary)] inline-flex items-center gap-1">
                            <span className="text-[9px] font-bold text-[var(--color-accent)] bg-[var(--color-accent-light)]/50 rounded px-1 py-0.5">PERSO</span>
                            {name}
                          </span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            isMapped ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
                          }`}>
                            {isMapped ? 'Mappé' : 'Optionnel'}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              </div>
            </div>

            {uploadError && (
              <div className="flex items-center gap-2 rounded-md border border-[var(--color-danger)] bg-red-50 p-3 text-sm text-[var(--color-danger)]">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-4 border-t">
              <Button variant="outline" onClick={() => setIsMappingMode(false)}>
                Annuler
              </Button>
              <Button
                className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white"
                onClick={handleConfirmMapping}
              >
                Confirmer le mapping & Lancer l&apos;analyse <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Import options */}
            <div id="import-zone" className="col-span-12 lg:col-span-2 space-y-6 scroll-mt-24">
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
                    <Button variant="ghost" size="sm" onClick={() => { setUploadingType(null); setSelectedFile(null); setUploadError(null) }}>Fermer</Button>
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

                  {uploadError && (
                    <div className="flex items-center gap-2 rounded-md border border-[var(--color-danger)] bg-red-50 p-3 text-sm text-[var(--color-danger)]">
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                      <span>{uploadError}</span>
                    </div>
                  )}

                  <div className="flex justify-end gap-2.5">
                    <Button variant="outline" onClick={() => { setUploadingType(null); setSelectedFile(null); setUploadError(null) }}>
                      Annuler
                    </Button>
                    <Button
                      className="bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white flex items-center gap-2"
                      disabled={!selectedFile || uploading}
                      onClick={handleUpload}
                    >
                      {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
                      {uploading ? 'Analyse en cours...' : 'Analyser le fichier'}
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
                  {filesLoading ? (
                    <div className="flex items-center justify-center py-10 text-sm text-[var(--color-text-secondary)]">
                      <Loader2 className="h-5 w-5 animate-spin mr-2" />
                      Chargement des fichiers...
                    </div>
                  ) : importedFiles.length === 0 ? (
                    <div className="py-10 text-center text-sm text-[var(--color-text-secondary)]">
                      Aucun fichier importé pour cet événement.
                    </div>
                  ) : (
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b text-[var(--color-text-secondary)] font-medium text-xs uppercase tracking-wider">
                          <th className="pb-3">Fichier</th>
                          <th className="pb-3">Type de source</th>
                          <th className="pb-3">Nombre de lignes</th>
                          <th className="pb-3">Date d&apos;import</th>
                          <th className="pb-3">Statut</th>
                          <th className="pb-3 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y text-[var(--color-text-primary)]">
                        {importedFiles.map((file) => (
                          <tr key={file.id} className="hover:bg-slate-50/50">
                            <td className="py-3.5 font-medium">{file.filename}</td>
                            <td className="py-3.5 text-xs text-[var(--color-text-secondary)]">
                              {SOURCE_TYPES.find(s => s.key === file.source_type)?.name || file.source_type}
                            </td>
                            <td className="py-3.5 text-xs font-semibold">{file.row_count} lignes</td>
                            <td className="py-3.5 text-xs text-[var(--color-text-secondary)]">
                              {new Date(file.uploaded_at).toLocaleString('fr-FR')}
                            </td>
                            <td className="py-3.5">
                              {file.status === 'error' ? (
                                <Badge className="bg-red-100 text-[var(--color-danger)] border-0 flex items-center gap-1 w-fit">
                                  <AlertTriangle className="h-3 w-3" /> Erreur
                                </Badge>
                              ) : file.status === 'pending' ? (
                                <Badge className="bg-yellow-50 text-yellow-700 border-0 flex items-center gap-1 w-fit">
                                  <Loader2 className="h-3 w-3 animate-spin" /> En attente
                                </Badge>
                              ) : (
                                <Badge className="bg-[var(--color-success-light)] text-[var(--color-success)] border-0 flex items-center gap-1 w-fit">
                                  <CheckCircle2 className="h-3 w-3" /> Traité
                                </Badge>
                              )}
                            </td>
                            <td className="py-3.5 text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-[var(--color-danger)] hover:text-[var(--color-danger)] hover:bg-red-50"
                                onClick={() => handleDeleteFile(file.id)}
                                disabled={deletingFileId === file.id}
                              >
                                {deletingFileId === file.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Trash2 className="h-4 w-4" />
                                )}
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
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
                    <span>L&apos;outil essaie de deviner automatiquement les correspondances d&apos;en-têtes.</span>
                  </div>
                  <div className="flex gap-2.5 items-start">
                    <AlertTriangle className="h-4 w-4 text-[var(--color-warning)] shrink-0 mt-0.5" />
                    <span><strong>Validation Humaine Obligatoire :</strong> Vous devez confirmer et valider chaque mapping avant qu&apos;il ne soit traité par le moteur de consolidation.</span>
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
