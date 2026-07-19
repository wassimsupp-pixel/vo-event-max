/**
 * API client for VO Event Max backend.
 * All endpoints target NEXT_PUBLIC_API_URL (Railway deployment).
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://vo-event-max-api-production.up.railway.app'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ParticipantStatus = 'complete' | 'incomplete' | 'conflict'
export type ConfidenceLevel = 'certain' | 'probable' | 'to_verify' | 'not_found'

export interface Participant {
  id: string
  event_id: string
  first_name: string
  last_name: string
  email: string
  company?: string
  phone?: string
  nationality?: string
  dietary_requirements?: string
  completeness_status: ParticipantStatus
  confidence: ConfidenceLevel
  has_flight: boolean
  has_hotel: boolean
  has_transfer: boolean
  has_activities: boolean
  locked_fields: string[]
  sources: string[]
  match_score?: number
  created_at: string
  updated_at: string
}

export interface ProjectMember {
  id: string
  user_id: string
  access_level: 'viewer' | 'editor'
  event_ids: string[] | null
  email?: string
  full_name?: string
  user_role?: string
  created_at?: string
}

export interface ParticipantLookupItem {
  id: string
  first_name: string
  last_name: string
  completeness_status: string
}

export interface ParticipantListParams {
  page?: number
  page_size?: number
  search?: string
  status?: ParticipantStatus
  confidence?: ConfidenceLevel
  has_flight?: boolean
  has_hotel?: boolean
  has_transfer?: boolean
}

export interface PaginatedParticipants {
  items: Participant[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ParticipantUpdate {
  first_name?: string
  last_name?: string
  email?: string
  company?: string
  phone?: string
  [key: string]: string | undefined
}

export interface ColumnMappingSuggestion {
  suggested_field: string | null
  confidence: number
  alternatives: string[]
}

export interface FileUploadResponse {
  file_id: string
  filename: string
  row_count: number
  columns: string[]
  uploaded_at: string
  import_status?: string
  mapping_suggestions: Record<string, ColumnMappingSuggestion>
  canonical_fields: string[]
}

export interface MappingReportEntry {
  field: string | null
  confidence: number
  source: 'heuristic' | 'ai' | 'custom'
  needs_split: boolean
}

export interface FilePreviewResponse {
  columns: string[]
  rows: Record<string, string>[]
  total_rows: number
  mapping_suggestions: Record<string, ColumnMappingSuggestion>
  canonical_fields: string[]
  column_mapping?: Record<string, string> | null
  mapping_report?: Record<string, MappingReportEntry> | null
}

export interface UploadedFile {
  id: string
  event_id: string
  filename: string
  source_type: string
  row_count: number
  status: 'imported' | 'pending' | 'error' | 'mapped' | 'review'
  uploaded_at: string
}

export interface EventMergeEvent {
  id: string
  name: string
  start_date?: string | null
  location_city?: string | null
  participant_count: number
}

export interface EventMergeSuggestion {
  canonical_event_id: string
  events: EventMergeEvent[]
  ai_confirmed?: boolean | null
  min_similarity: number
}

export interface MatchCandidateParty {
  nom?: string
  email?: string | null
  telephone?: string | null
  societe?: string | null
  nationalite?: string | null
}

export interface MatchCandidate {
  id: string
  event_id: string
  participant_a_id?: string | null
  participant_b_id?: string | null
  name_a?: string | null
  name_b?: string | null
  details_a?: MatchCandidateParty | null
  details_b?: MatchCandidateParty | null
  deterministic_score?: number | null
  ai_recommendation?: 'fusionner' | 'separer' | 'incertain' | null
  ai_justification?: string | null
  ai_confidence?: number | null
  human_decision?: string | null
  status: string
  created_at?: string | null
}

export interface ConsolidationRun {
  id: string
  event_id: string
  status: 'pending' | 'running' | 'done' | 'error'
  started_at: string
  finished_at?: string
  stats?: {
    total: number
    matched: number
    conflicts: number
    duplicates: number
    not_found: number
  }
}

export interface ConsolidationRunDetail extends ConsolidationRun {
  steps: Array<{
    name: string
    status: 'done' | 'active' | 'pending' | 'error'
    count?: number
    duration_ms?: number
  }>
}

export interface Export {
  id: string
  event_id: string
  run_id: string
  format: string
  status: 'pending' | 'ready' | 'error'
  created_at: string
}

export interface Exception {
  id: string
  event_id: string
  type: 'conflict' | 'duplicate' | 'not_found' | 'to_verify' | 'coverage' | 'missing_field'
  exception_type?: string
  severity: 'critical' | 'warning' | 'info'
  participant_id?: string
  participant_name?: string
  message: string
  field?: string
  value_a?: string
  value_b?: string
  source_a?: string
  source_b?: string
  resolved: boolean
  created_at: string
  context_data?: Record<string, unknown>
}

export interface EmailProposal {
  id: string
  event_id: string
  sender: string
  subject: string
  body: string
  received_at: string
  participant_id?: string
  status: 'pending' | 'applied' | 'rejected'
  proposed_changes: Record<string, string>
  ai_explanation?: string
  created_at: string
  participant_name?: string
}

export type MailProvider = 'gmail' | 'outlook'

export interface MailProviderStatus {
  provider: MailProvider
  configured: boolean
  connected: boolean
}

export interface MailStatus {
  providers: MailProviderStatus[]
}

import { createClient } from './supabase'

const supabase = createClient()


function mapParticipant(p: any): Participant {
  if (!p) return p
  
  let lockedFieldsArray: string[] = []
  if (p.locked_fields) {
    if (Array.isArray(p.locked_fields)) {
      lockedFieldsArray = p.locked_fields
    } else if (typeof p.locked_fields === 'object') {
      lockedFieldsArray = Object.keys(p.locked_fields).filter(k => p.locked_fields[k] === true)
    }
  }

  let sourcesArray: string[] = []
  if (p.sources) {
    sourcesArray = p.sources
  } else {
    if (p.registration_source_id) sourcesArray.push('registration')
    if (p.fcm_source_id) sourcesArray.push('fcm')
  }

  return {
    ...p,
    completeness_status: p.completeness_status || p.status || 'incomplete',
    has_activities: p.has_activities !== undefined ? p.has_activities : (p.has_activity !== undefined ? p.has_activity : false),
    locked_fields: lockedFieldsArray,
    sources: sourcesArray,
    confidence: p.confidence || 'certain',
  }
}

function mapException(exc: any): Exception {
  if (!exc) return exc
  const ctx = exc.context_data || {}
  let value_a: string | undefined = undefined
  let value_b: string | undefined = undefined
  let source_a: string | undefined = undefined
  let source_b: string | undefined = undefined
  let participant_name: string | undefined = exc.participant_name

  if (exc.exception_type === 'conflict' || exc.exception_type === 'DATA_CONFLICT') {
    if (ctx.conflicts && ctx.conflicts.length > 0) {
      const c = ctx.conflicts[0]
      value_a = c.registration_value
      value_b = c.fcm_value
      source_a = "Fiche Inscription"
      source_b = "Import FCM (Vols)"
      if (!participant_name) {
        participant_name = c.participant_name
      }
    } else {
      value_a = ctx.value_a
      value_b = ctx.value_b
      source_a = ctx.source_a
      source_b = ctx.source_b
    }
  }

  if (!participant_name && ctx.participant_name) {
    participant_name = ctx.participant_name
  }

  // Every backend type falls into ONE of the filter categories so the chips
  // actually sort the page (coverage = aggregated "X participants without…").
  const EXC_CATEGORY: Record<string, Exception['type']> = {
    DATA_CONFLICT: 'conflict', NAME_DIVERGENCE: 'conflict', conflict: 'conflict',
    POSSIBLE_DUPLICATE: 'duplicate', DUPLICATE_EMAIL: 'duplicate', duplicate: 'duplicate',
    FLIGHT_NO_PARTICIPANT: 'not_found', not_found: 'not_found',
    PROBABLE_MATCH: 'to_verify', MISSING_REQUIRED_FIELD: 'to_verify', INVALID_FORMAT: 'to_verify',
    DATE_INCOHERENCE: 'to_verify', MISSING_CONTACT: 'to_verify', to_verify: 'to_verify',
    PARTICIPANT_NO_FLIGHT: 'coverage', PARTICIPANT_NO_HOTEL: 'coverage',
    PARTICIPANT_NO_TRANSFER: 'coverage', PARTICIPANT_NO_DIETARY: 'coverage',
  }
  const category: Exception['type'] = ctx.category === 'missing_field'
    ? 'missing_field'
    : ctx.aggregate
    ? 'coverage'
    : (EXC_CATEGORY[exc.exception_type as string] || EXC_CATEGORY[exc.type as string] || 'to_verify')

  return {
    ...exc,
    type: category,
    exception_type: exc.exception_type,
    participant_name,
    value_a,
    value_b,
    source_a,
    source_b,
  }
}


// ─── HTTP helpers ──────────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession()
  const isFormData = options.body instanceof FormData
  const headers = new Headers(options.headers)

  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }

  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const { headers: _, ...restOptions } = options
  const method = (options.method ?? 'GET').toUpperCase()

  // Per-endpoint timing to profile slow calls (dev only — see feedback P1.6).
  const startedAt = typeof performance !== 'undefined' ? performance.now() : Date.now()
  const res = await fetch(`${BASE_URL}${path}`, {
    headers,
    ...restOptions,
  })
  if (process.env.NODE_ENV !== 'production') {
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
    console.debug(`[api] ${method} ${path} → ${res.status} in ${Math.round(now - startedAt)}ms`)
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ message: res.statusText }))
    throw new Error(error.message ?? `HTTP ${res.status}`)
  }

  return res.json()
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const q = Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&')
  return q ? `?${q}` : ''
}

// ─── API client ───────────────────────────────────────────────────────────────

export const api = {
  files: {
    async upload(eventId: string, file: File, sourceType: string): Promise<FileUploadResponse> {
      const form = new FormData()
      form.append('file', file)
      form.append('source_type', sourceType)
      form.append('event_id', eventId)
      return request<FileUploadResponse>('/api/files/upload', {
        method: 'POST',
        body: form,
        headers: {}, // let browser set Content-Type with boundary
      })
    },

    async preview(fileId: string): Promise<FilePreviewResponse> {
      return request<FilePreviewResponse>(`/api/files/${fileId}/preview`)
    },

    async mapColumns(fileId: string, mapping: Record<string, string>): Promise<void> {
      await request(`/api/files/${fileId}/map-columns`, {
        method: 'POST',
        body: JSON.stringify({ mapping, confirmed: true }),
      })
    },

    async list(eventId: string): Promise<UploadedFile[]> {
      const files = await request<any[]>(`/api/events/${eventId}/files`)
      return files.map(file => ({
        id: file.id,
        event_id: file.event_id || eventId,
        filename: file.original_filename || '',
        source_type: file.source_type,
        row_count: file.row_count,
        status: file.import_status === 'processed' || file.import_status === 'mapped' ? 'mapped' : file.import_status,
        uploaded_at: file.imported_at,
      }))
    },

    async delete(fileId: string): Promise<void> {
      await request(`/api/files/${fileId}`, {
        method: 'DELETE',
      })
    },
  },

  consolidation: {
    async run(eventId: string): Promise<ConsolidationRun> {
      const run = await request<any>(`/api/events/${eventId}/consolidate`, {
        method: 'POST',
      })
      let status = run.status
      if (run.status === 'completed') status = 'done'
      else if (run.status === 'failed') status = 'error'

      return {
        id: run.id,
        event_id: run.event_id,
        status: status as any,
        started_at: run.started_at,
        finished_at: run.completed_at,
      }
    },

    async list(eventId: string): Promise<ConsolidationRun[]> {
      const list = await request<any[]>(`/api/events/${eventId}/runs`)
      return list.map(run => {
        let status = run.status
        if (run.status === 'completed') status = 'done'
        else if (run.status === 'failed') status = 'error'
        return {
          id: run.id,
          event_id: run.event_id,
          status: status as any,
          started_at: run.started_at,
          finished_at: run.completed_at,
        }
      })
    },

    async get(eventId: string, runId: string): Promise<ConsolidationRunDetail> {
      const resp = await request<{
        run: any
        exceptions: any[]
        exception_count: number
      }>(`/api/events/${eventId}/runs/${runId}`)
      
      const run = resp.run || {}
      let status = run.status
      if (run.status === 'completed') status = 'done'
      else if (run.status === 'failed') status = 'error'

      const backendStats = run.stats || {}
      const stats = {
        total: backendStats.total_source_records || 0,
        matched: (backendStats.matched_certain || 0) + (backendStats.matched_probable || 0),
        conflicts: backendStats.exceptions_count || 0,
        duplicates: 0,
        not_found: backendStats.not_found || 0,
      }

      return {
        id: run.id,
        event_id: run.event_id,
        status: status as any,
        started_at: run.started_at,
        finished_at: run.completed_at,
        stats,
        steps: [
          { name: 'Importation', status: 'done', count: resp.exception_count },
          { name: 'Analyse', status: 'done' },
          { name: 'Matching', status: run.status === 'running' ? 'active' : 'done' },
          { name: 'Consolidation', status: run.status === 'running' ? 'pending' : 'done' },
          { name: 'Validation', status: run.status === 'running' ? 'pending' : 'done' },
        ]
      }
    },
  },

  participants: {
    async list(eventId: string, params?: ParticipantListParams): Promise<PaginatedParticipants> {
      const query = qs({
        page: params?.page,
        page_size: params?.page_size,
        search: params?.search,
        status: params?.status,
        confidence: params?.confidence,
        has_flight: params?.has_flight,
        has_hotel: params?.has_hotel,
        has_transfer: params?.has_transfer,
      })
      const resp = await request<{
        items: any[]
        total: number
        page: number
        page_size: number
        total_pages: number
      }>(`/api/events/${eventId}/participants${query}`)
      
      return {
        items: (resp.items || []).map(mapParticipant),
        total: resp.total || 0,
        page: resp.page || 1,
        page_size: resp.page_size || 50,
        total_pages: resp.total_pages || 1
      }
    },

    async lookup(eventId: string): Promise<ParticipantLookupItem[]> {
      return request<ParticipantLookupItem[]>(`/api/events/${eventId}/participants/lookup`)
    },

    async get(participantId: string): Promise<Participant> {
      const p = await request<any>(`/api/participants/${participantId}`)
      return mapParticipant(p)
    },

    async getConsolidated(participantId: string): Promise<{
      flights: any[]
      transfers: any[]
      hotel_nights: any[]
      activities: any[]
      source_records: any[]
    }> {
      return request(`/api/participants/${participantId}/consolidated`)
    },

    async update(participantId: string, update: ParticipantUpdate): Promise<Participant> {
      const p = await request<any>(`/api/participants/${participantId}`, {
        method: 'PATCH',
        body: JSON.stringify(update),
      })
      return mapParticipant(p)
    },

    async lockField(participantId: string, field: string): Promise<void> {
      await request(`/api/participants/${participantId}/lock`, {
        method: 'POST',
        body: JSON.stringify({ field }),
      })
    },

    async unlockField(participantId: string, field: string): Promise<void> {
      await request(`/api/participants/${participantId}/lock`, {
        method: 'DELETE',
        body: JSON.stringify({ field }),
      })
    },
  },
  events: {
    async list(): Promise<any[]> {
      return request<any[]>('/api/events')
    },
    async create(name: string, projectId?: string): Promise<any> {
      const projId = projectId ?? '00000000-0000-0000-0000-000000000002'
      return request<any>('/api/events', {
        method: 'POST',
        body: JSON.stringify({
          project_id: projId,
          name,
        }),
      })
    },
    async delete(eventId: string): Promise<void> {
      await request(`/api/events/${eventId}`, { method: 'DELETE' })
    },
  },
  exports: {
    async create(eventId: string, runId?: string): Promise<Export> {
      return request<Export>(`/api/events/${eventId}/exports`, {
        method: 'POST',
        body: JSON.stringify({ run_id: runId || null }),
      })
    },

    async getDownloadUrl(exportId: string): Promise<{ signed_url: string; expires_at: string }> {
      return request<{ signed_url: string; expires_at: string }>(
        `/api/exports/${exportId}/download`
      )
    },
  },

  exceptions: {
    async list(eventId: string): Promise<Exception[]> {
      const list = await request<any[]>(`/api/events/${eventId}/exceptions`)
      return list.map(mapException)
    },

    async resolve(exceptionId: string, resolution: string): Promise<void> {
      await request(`/api/exceptions/${exceptionId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ resolution }),
      })
    },
  },

  flights: {
    async list(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/flights`)
    },
    async update(flightId: string, payload: any): Promise<any> {
      return request<any>(`/api/flights/${flightId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
    },
    async extract(eventId: string): Promise<any> {
      return request<any>(`/api/events/${eventId}/flights/extract`, {
        method: 'POST',
      })
    },
  },

  hotels: {
    async list(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/hotels`)
    },
    async create(eventId: string, payload: any): Promise<any> {
      return request<any>(`/api/events/${eventId}/hotels`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async update(hotelId: string, payload: any): Promise<any> {
      return request<any>(`/api/hotels/${hotelId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
    },
    async listRooming(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/hotels/rooming`)
    },
    async assignRooming(eventId: string, payload: any): Promise<any> {
      return request<any>(`/api/events/${eventId}/hotels/rooming`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async assignRoomingBulk(eventId: string, payload: any): Promise<any> {
      return request<any>(`/api/events/${eventId}/hotels/rooming/bulk`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async updateRooming(roomingId: string, payload: any): Promise<any> {
      return request<any>(`/api/hotels/rooming/${roomingId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
    },
    async deleteRooming(roomingId: string): Promise<any> {
      return request<any>(`/api/hotels/rooming/${roomingId}`, {
        method: 'DELETE',
      })
    },
  },

  transfers: {
    async list(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/transfers`)
    },
    async create(eventId: string, payload: any): Promise<any> {
      return request<any>(`/api/events/${eventId}/transfers`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async update(transferId: string, payload: any): Promise<any> {
      return request<any>(`/api/transfers/${transferId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
    },
    async delete(transferId: string): Promise<any> {
      return request<any>(`/api/transfers/${transferId}`, {
        method: 'DELETE',
      })
    },
    async group(eventId: string, params: { window_minutes?: number; pickup_location?: string; dropoff_location?: string; vehicle_type?: string }): Promise<any> {
      const query = qs(params)
      return request<any>(`/api/events/${eventId}/transfers/group${query}`, {
        method: 'POST',
      })
    },
  },

  activities: {
    async list(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/activities`)
    },
    async create(eventId: string, payload: any): Promise<any> {
      return request<any>(`/api/events/${eventId}/activities`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async update(activityId: string, payload: any): Promise<any> {
      return request<any>(`/api/activities/${activityId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
    },
    async delete(activityId: string): Promise<any> {
      return request<any>(`/api/activities/${activityId}`, {
        method: 'DELETE',
      })
    },
    async listParticipants(activityId: string): Promise<any[]> {
      return request<any[]>(`/api/activities/${activityId}/participants`)
    },
    async register(activityId: string, participantId: string): Promise<any> {
      return request<any>(`/api/activities/${activityId}/register?participant_id=${participantId}`, {
        method: 'POST',
      })
    },
    async unregister(activityId: string, participantId: string): Promise<any> {
      return request<any>(`/api/activities/${activityId}/unregister/${participantId}`, {
        method: 'DELETE',
      })
    },
  },

  reports: {
    async getSummary(eventId: string): Promise<any> {
      return request<any>(`/api/events/${eventId}/reports/summary`)
    },
    async getHotelNights(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/reports/hotel-nights`)
    },
    async getAnalysis(eventId: string, aiSummary = false): Promise<any> {
      return request<any>(`/api/events/${eventId}/reports/analysis${aiSummary ? '?ai_summary=true' : ''}`)
    },
  },

  masterList: {
    async get(eventId: string): Promise<{ items: any[]; total: number }> {
      return request<{ items: any[]; total: number }>(`/api/events/${eventId}/master-list`)
    },
  },

  posters: {
    async analyze(eventId: string, file: File): Promise<{ fields?: Record<string, any>; error?: string }> {
      const form = new FormData()
      form.append('file', file)
      return request(`/api/events/${eventId}/posters/analyze`, { method: 'POST', body: form, headers: {} })
    },
  },

  campaigns: {
    async preview(eventId: string, payload: { mode: string; subject: string; body: string; instructions: string }): Promise<{
      recipient_count: number; without_email: number; samples: { to: string; name: string; subject: string; body: string }[]
    }> {
      return request(`/api/events/${eventId}/campaigns/preview`, { method: 'POST', body: JSON.stringify(payload) })
    },
    async send(eventId: string, payload: { mode: string; subject: string; body: string; instructions: string; send: boolean }): Promise<{
      generated: number; sent: number; skipped_no_email: number; errors: number; provider: string | null; delivered: boolean
    }> {
      return request(`/api/events/${eventId}/campaigns/send`, { method: 'POST', body: JSON.stringify(payload) })
    },
  },

  globalParticipants: {
    async getHistory(email: string): Promise<any[]> {
      return request<any[]>(`/api/global-participants/history?email=${encodeURIComponent(email)}`)
    },
  },

  emailAgent: {
    async list(eventId: string): Promise<EmailProposal[]> {
      return request<EmailProposal[]>(`/api/events/${eventId}/email-agent`)
    },
    async analyze(eventId: string, sender: string, subject: string, body: string): Promise<EmailProposal> {
      return request<EmailProposal>(`/api/events/${eventId}/email-agent/analyze`, {
        method: 'POST',
        body: JSON.stringify({ sender, subject, body }),
      })
    },
    async apply(proposalId: string): Promise<void> {
      await request(`/api/email-agent/${proposalId}/apply`, {
        method: 'POST',
      })
    },
    async reject(proposalId: string): Promise<void> {
      await request(`/api/email-agent/${proposalId}/reject`, {
        method: 'POST',
      })
    },
  },

  communications: {
    async generateConfirmation(eventId: string, participantId: string): Promise<{
      communication: any | null
      persisted: boolean
      subject: string
      body: string
      facts: Record<string, any>
      missing: string[]
      source: string
    }> {
      return request(`/api/events/${eventId}/participants/${participantId}/confirmation/generate`, { method: 'POST' })
    },
    async list(eventId: string): Promise<any[]> {
      return request<any[]>(`/api/events/${eventId}/communications`)
    },
    async update(id: string, payload: { subject?: string; body?: string; status?: string }): Promise<any> {
      return request(`/api/communications/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
    },
    async send(id: string): Promise<any> {
      return request(`/api/communications/${id}/send`, { method: 'POST' })
    },
  },

  projects: {
    async list(): Promise<any[]> {
      return request<any[]>('/api/projects')
    },
    async create(payload: { name: string; client_name: string }): Promise<any> {
      return request<any>('/api/projects', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async delete(projectId: string): Promise<void> {
      await request(`/api/projects/${projectId}`, { method: 'DELETE' })
    },
  },

  sharing: {
    async listMembers(projectId: string): Promise<ProjectMember[]> {
      return request<ProjectMember[]>(`/api/projects/${projectId}/members`)
    },
    async addMember(
      projectId: string,
      payload: { email: string; access_level: 'viewer' | 'editor'; event_ids?: string[] | null }
    ): Promise<ProjectMember> {
      return request<ProjectMember>(`/api/projects/${projectId}/members`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async updateMember(
      projectId: string,
      memberId: string,
      patch: { access_level?: 'viewer' | 'editor'; event_ids?: string[] }
    ): Promise<ProjectMember> {
      return request<ProjectMember>(`/api/projects/${projectId}/members/${memberId}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
    },
    async removeMember(projectId: string, memberId: string): Promise<void> {
      await request(`/api/projects/${projectId}/members/${memberId}`, { method: 'DELETE' })
    },
  },

  mail: {
    async status(eventId: string): Promise<MailStatus> {
      return request<MailStatus>(`/api/events/${eventId}/mail/status`)
    },
    async authorize(eventId: string, provider: MailProvider, locale: string): Promise<{ authorization_url: string }> {
      return request<{ authorization_url: string }>(
        `/api/events/${eventId}/mail/authorize${qs({ provider, locale })}`
      )
    },
    async sync(eventId: string, provider: MailProvider): Promise<{ synced: number; provider: string }> {
      return request<{ synced: number; provider: string }>(
        `/api/events/${eventId}/mail/sync${qs({ provider })}`,
        { method: 'POST' }
      )
    },
    async disconnect(eventId: string, provider: MailProvider): Promise<void> {
      await request(`/api/events/${eventId}/mail/disconnect${qs({ provider })}`, { method: 'POST' })
    },
  },

  eventGrouping: {
    async suggestions(): Promise<EventMergeSuggestion[]> {
      return request<EventMergeSuggestion[]>(`/api/org/event-merge-suggestions`)
    },
    async merge(canonicalEventId: string, mergeEventIds: string[]): Promise<{ merged: number; message: string }> {
      return request<{ merged: number; message: string }>(`/api/events/merge`, {
        method: 'POST',
        body: JSON.stringify({ canonical_event_id: canonicalEventId, merge_event_ids: mergeEventIds }),
      })
    },
  },

  matching: {
    async candidates(eventId: string, includeResolved = false): Promise<MatchCandidate[]> {
      return request<MatchCandidate[]>(
        `/api/events/${eventId}/match-candidates${qs({ include_resolved: includeResolved })}`
      )
    },
    async resolve(candidateId: string, decision: 'fusionner' | 'separer'): Promise<{ status: string; message: string }> {
      return request<{ status: string; message: string }>(`/api/match-candidates/${candidateId}`, {
        method: 'PUT',
        body: JSON.stringify({ decision }),
      })
    },
  },
}
