/**
 * API client for VO Event Max backend.
 * All endpoints target NEXT_PUBLIC_API_URL (Railway deployment).
 */

const BASE_URL = 'https://web-production-f0ba2.up.railway.app'

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
  status: ParticipantStatus
  confidence: ConfidenceLevel
  has_flight: boolean
  has_hotel: boolean
  has_transfer: boolean
  has_activity: boolean
  locked_fields: string[]
  sources: string[]
  match_score?: number
  created_at: string
  updated_at: string
}

export interface ParticipantListParams {
  page?: number
  per_page?: number
  search?: string
  status?: ParticipantStatus
  confidence?: ConfidenceLevel
}

export interface PaginatedParticipants {
  data: Participant[]
  total: number
  page: number
  per_page: number
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

export interface FileUploadResponse {
  file_id: string
  filename: string
  row_count: number
  columns: string[]
  uploaded_at: string
}

export interface FilePreviewResponse {
  columns: string[]
  rows: Record<string, string>[]
  total_rows: number
}

export interface UploadedFile {
  id: string
  event_id: string
  filename: string
  source_type: string
  row_count: number
  status: 'imported' | 'pending' | 'error' | 'mapped'
  uploaded_at: string
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
  type: 'conflict' | 'duplicate' | 'not_found' | 'to_verify'
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
}

import { createClient } from './supabase'

const supabase = createClient()

// ─── HTTP helpers ──────────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession()
  const authHeaders: Record<string, string> = {}
  if (session?.access_token) {
    authHeaders['Authorization'] = `Bearer ${session.access_token}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ message: res.statusText }))
    throw new Error(error.message ?? `HTTP ${res.status}`)
  }

  return res.json()
}

function qs(params: Record<string, string | number | undefined>): string {
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
      return request<FileUploadResponse>(`/api/events/${eventId}/files`, {
        method: 'POST',
        body: form,
        headers: {}, // let browser set Content-Type with boundary
      })
    },

    async preview(fileId: string): Promise<FilePreviewResponse> {
      return request<FilePreviewResponse>(`/api/files/${fileId}/preview`)
    },

    async mapColumns(fileId: string, mapping: Record<string, string>): Promise<void> {
      await request(`/api/files/${fileId}/mapping`, {
        method: 'POST',
        body: JSON.stringify({ mapping }),
      })
    },

    async list(eventId: string): Promise<UploadedFile[]> {
      return request<UploadedFile[]>(`/api/events/${eventId}/files`)
    },
  },

  consolidation: {
    async run(eventId: string): Promise<ConsolidationRun> {
      return request<ConsolidationRun>(`/api/events/${eventId}/consolidation`, {
        method: 'POST',
      })
    },

    async list(eventId: string): Promise<ConsolidationRun[]> {
      return request<ConsolidationRun[]>(`/api/events/${eventId}/consolidation`)
    },

    async get(eventId: string, runId: string): Promise<ConsolidationRunDetail> {
      return request<ConsolidationRunDetail>(`/api/events/${eventId}/consolidation/${runId}`)
    },
  },

  participants: {
    async list(eventId: string, params?: ParticipantListParams): Promise<PaginatedParticipants> {
      const query = qs({
        page: params?.page,
        per_page: params?.per_page,
        search: params?.search,
        status: params?.status,
        confidence: params?.confidence,
      })
      return request<PaginatedParticipants>(`/api/events/${eventId}/participants${query}`)
    },

    async get(participantId: string): Promise<Participant> {
      return request<Participant>(`/api/participants/${participantId}`)
    },

    async update(participantId: string, update: ParticipantUpdate): Promise<Participant> {
      return request<Participant>(`/api/participants/${participantId}`, {
        method: 'PATCH',
        body: JSON.stringify(update),
      })
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
  },
  exports: {
    async create(eventId: string, runId: string): Promise<Export> {
      return request<Export>(`/api/events/${eventId}/exports`, {
        method: 'POST',
        body: JSON.stringify({ run_id: runId }),
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
      return request<Exception[]>(`/api/events/${eventId}/exceptions`)
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
  },

  globalParticipants: {
    async getHistory(email: string): Promise<any[]> {
      return request<any[]>(`/api/global-participants/history?email=${encodeURIComponent(email)}`)
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
  },
}
