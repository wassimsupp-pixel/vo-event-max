"""
models/schemas.py — Pydantic v2 request/response models for VO Event Max API.

Organized by domain:
  - Events
  - Files / Column Mapping
  - Participants
  - Consolidation Runs
  - Exceptions
  - Exports
  - Change Log

i18n-ready error message constants are defined at the bottom of this file.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class ORMBase(BaseModel):
    """Base model with ORM mode enabled for use with Supabase dict responses."""
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

class OrganizationResponse(ORMBase):
    id: UUID
    name: str
    slug: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    """Request body for creating a new project."""
    name: str = Field(..., min_length=1, max_length=255)
    client_name: str = Field(..., min_length=1, max_length=255)


class ProjectResponse(ORMBase):
    id: UUID
    org_id: UUID
    name: str
    client_name: str
    created_by: UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    """Request body for creating a new event."""
    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    event_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: Optional[date], info) -> Optional[date]:
        start = info.data.get("start_date")
        if v is not None and start is not None and v < start:
            raise ValueError("end_date must be on or after start_date.")
        return v


class EventUpdate(BaseModel):
    """Request body for partial event update (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    event_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None


class EventResponse(ORMBase):
    id: UUID
    project_id: UUID
    name: str
    event_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Files & Column Mapping
# ---------------------------------------------------------------------------

class ColumnMappingSuggestion(BaseModel):
    suggested_field: Optional[str] = None
    confidence: float
    alternatives: list[str] = []


class MappingSuggestionsResponse(BaseModel):
    suggestions: dict[str, ColumnMappingSuggestion]
    canonical_fields: list[str]


class FileUploadResponse(ORMBase):
    """Returned after a file is successfully uploaded and parsed."""
    file_id: UUID
    original_filename: str
    source_type: str
    row_count: int
    column_count: int
    columns: list[str]
    sample_rows: list[dict[str, Any]]   # First 5 rows as list of dicts
    import_status: str
    mapping_suggestions: dict[str, ColumnMappingSuggestion]
    canonical_fields: list[str]


class FileListItem(ORMBase):
    id: UUID
    original_filename: str
    source_type: str
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    import_status: str
    imported_at: datetime
    error_message: Optional[str] = None


class FilePreviewResponse(ORMBase):
    """Returned by GET /files/{file_id}/preview."""
    file_id: UUID
    columns: list[str]
    row_count: int
    sample_rows: list[dict[str, Any]]   # 10 rows
    mapping_suggestions: dict[str, ColumnMappingSuggestion]
    canonical_fields: list[str]
    # The full auto-built mapping already stored on the file (every column,
    # including catch-all custom fields) so the review confirms the COMPLETE
    # mapping and never drops columns. Plus the per-column report.
    column_mapping: Optional[dict[str, str]] = None
    mapping_report: Optional[dict[str, Any]] = None


class ColumnMappingRequest(BaseModel):
    """
    Request body for POST /files/{file_id}/map-columns.

    ``confirmed`` MUST be True — this gate enforces human review of the mapping
    before it is persisted and processing begins.
    """
    mapping: dict[str, str] = Field(
        ...,
        description="Map of source column name → canonical target field name.",
        examples=[{"Nom": "last_name", "Prénom": "first_name", "E-mail": "email"}],
    )
    confirmed: bool = Field(
        ...,
        description="Must be true. Confirms that a human has reviewed the column mapping.",
    )

    @field_validator("confirmed")
    @classmethod
    def must_be_confirmed(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                ERR_MAPPING_NOT_CONFIRMED
            )
        return v


class ColumnMappingResponse(BaseModel):
    """Returned after a column mapping is saved."""
    file_id: UUID
    import_status: str
    mapping: dict[str, str]
    message: str


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------

class ParticipantResponse(ORMBase):
    """Full participant record. dietary_requirements omitted for non-admin/pm."""
    id: UUID
    event_id: UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    nationality: Optional[str] = None
    # dietary_requirements is conditionally included (see router)
    dietary_requirements: Optional[str] = None
    completeness_status: str
    has_flight: bool
    has_hotel: bool
    has_transfer: bool
    has_activities: bool
    verification_note: Optional[str] = None
    locked_fields: dict[str, Any]
    registration_source_id: Optional[UUID] = None
    fcm_source_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ParticipantListItem(ORMBase):
    """Lightweight participant for list views."""
    id: UUID
    event_id: UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    company: Optional[str] = None
    completeness_status: str
    has_flight: bool
    has_hotel: bool
    has_transfer: bool
    has_activities: bool


class ParticipantLookupItem(ORMBase):
    """Minimal participant record for dropdowns/selectors."""
    id: UUID
    first_name: str
    last_name: str
    completeness_status: str


class ParticipantUpdate(BaseModel):
    """
    Request body for PATCH /participants/{id}.

    Each call updates a single field. The reason is required and written to the
    change_log BEFORE the update is applied (non-repudiation).
    """
    field: str = Field(..., description="Name of the field to update.")
    value: Any = Field(..., description="New value for the field.")
    lock: bool = Field(
        False,
        description="If true, add this field to locked_fields so re-imports cannot overwrite it.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Human-readable reason for the change (written to change_log).",
    )


class ParticipantListResponse(BaseModel):
    """Paginated participant list."""
    items: list[ParticipantListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Consolidation Runs
# ---------------------------------------------------------------------------

class ConsolidationRunRequest(BaseModel):
    """Request body to trigger a new consolidation run."""
    # No body required — event_id comes from the path parameter.
    pass


class ConsolidationStats(BaseModel):
    """Statistics summary for a completed consolidation run.

    Mirrors the runtime `stats` dict built incrementally in
    consolidation_service.py's run_consolidation — several keys are only
    added conditionally during a run (e.g. mappings_repaired is 0 unless
    repair_stored_mappings actually changed something), so everything here
    defaults to 0 rather than being required. Kept in sync manually since
    that dict has no schema of its own (2026-07-21/22 audit finding: this
    model previously covered only 8 of the ~18 real keys).
    """
    total_source_records: int = 0
    matched_certain: int = 0
    matched_probable: int = 0
    to_verify: int = 0
    not_found: int = 0
    participants_created: int = 0
    participants_updated: int = 0
    exceptions_count: int = 0
    mappings_repaired: int = 0
    skipped_noise_rows: int = 0
    stale_records_purged: int = 0
    junk_participants_purged: int = 0
    links_sanitized: int = 0
    names_backfilled: int = 0
    phantoms_merged: int = 0
    exact_duplicates_merged: int = 0
    ai_auto_merged: int = 0
    match_candidates: int = 0

    model_config = ConfigDict(extra="allow")


class ConsolidationRunResponse(ORMBase):
    id: UUID
    event_id: UUID
    triggered_by: UUID
    status: str
    stats: Optional[ConsolidationStats] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class ConsolidationRunListItem(ORMBase):
    id: UUID
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    stats: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ExceptionResponse(ORMBase):
    id: UUID
    run_id: UUID
    event_id: UUID
    participant_id: Optional[UUID] = None
    source_record_id: Optional[UUID] = None
    exception_type: str
    severity: str
    message: str
    context_data: Optional[dict[str, Any]] = None
    resolved: bool
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime


class ExceptionResolveRequest(BaseModel):
    """Request body to mark an exception as resolved."""
    resolved: bool = True
    note: Optional[str] = None


class ExceptionResolutionRequest(BaseModel):
    """Request body to mark an exception as resolved with a chosen value."""
    resolution: str


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    """Request body for POST /events/{event_id}/exports."""
    run_id: Optional[UUID] = Field(None, description="UUID of the consolidation run to export. If not provided, exports the latest completed run.")


class ExportResponse(ORMBase):
    id: UUID
    run_id: UUID
    event_id: UUID
    filename: str
    created_at: datetime


class ExportDownloadResponse(BaseModel):
    """Response containing a time-limited signed download URL."""
    export_id: UUID
    signed_url: str
    expires_at: datetime
    filename: str


# ---------------------------------------------------------------------------
# Change Log
# ---------------------------------------------------------------------------

class ChangeLogEntry(ORMBase):
    id: UUID
    event_id: UUID
    user_id: UUID
    entity_type: str
    entity_id: UUID
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    change_reason: Optional[str] = None
    changed_at: datetime


# ---------------------------------------------------------------------------
# Generic responses
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    """Simple success/info message."""
    message: str


class ErrorResponse(BaseModel):
    """Standard error response shape."""
    detail: str
    code: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 2 — Flights, Hotels, Transfers, Activities
# ---------------------------------------------------------------------------

class FlightResponse(ORMBase):
    id: UUID
    event_id: UUID
    participant_id: Optional[UUID] = None
    pnr_code: Optional[str] = None
    airline: Optional[str] = None
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    baggage_info: Optional[str] = None
    status: str
    created_at: datetime
    participant_name: Optional[str] = None  # joined helper


class FlightUpdate(BaseModel):
    pnr_code: Optional[str] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    departure_airport: Optional[str] = None
    arrival_airport: Optional[str] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
    baggage_info: Optional[str] = None
    status: Optional[str] = None


class HotelResponse(ORMBase):
    id: UUID
    event_id: UUID
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    contact_info: Optional[str] = None
    created_at: datetime


class HotelCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    contact_info: Optional[str] = None


class HotelUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    contact_info: Optional[str] = None


class HotelNightResponse(ORMBase):
    id: UUID
    hotel_id: UUID
    participant_id: UUID
    night_date: date
    room_type: str
    status: str
    created_at: datetime
    participant_name: Optional[str] = None  # joined helper
    hotel_name: Optional[str] = None        # joined helper


class HotelNightCreate(BaseModel):
    hotel_id: UUID
    participant_id: UUID
    night_date: date
    room_type: Optional[str] = "single"
    status: Optional[str] = "confirmed"


class HotelNightUpdate(BaseModel):
    hotel_id: Optional[UUID] = None
    room_type: Optional[str] = None
    status: Optional[str] = None


class TransferResponse(ORMBase):
    id: UUID
    event_id: UUID
    participant_id: UUID
    transfer_type: str
    flight_id: Optional[UUID] = None
    pickup_location: str
    dropoff_location: str
    pickup_time: datetime
    vehicle_type: Optional[str] = None
    status: str
    created_at: datetime
    participant_name: Optional[str] = None
    flight_number: Optional[str] = None


class TransferCreate(BaseModel):
    participant_id: UUID
    transfer_type: str
    flight_id: Optional[UUID] = None
    pickup_location: str
    dropoff_location: str
    pickup_time: datetime
    vehicle_type: Optional[str] = None
    status: Optional[str] = "scheduled"


class TransferUpdate(BaseModel):
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    pickup_time: Optional[datetime] = None
    vehicle_type: Optional[str] = None
    status: Optional[str] = None


class ActivityResponse(ORMBase):
    id: UUID
    event_id: UUID
    name: str
    description: Optional[str] = None
    date_time: Optional[datetime] = None
    location: Optional[str] = None
    capacity: Optional[int] = None
    created_at: datetime
    registrations_count: Optional[int] = 0


class ActivityCreate(BaseModel):
    name: str
    description: Optional[str] = None
    date_time: Optional[datetime] = None
    location: Optional[str] = None
    capacity: Optional[int] = None


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    date_time: Optional[datetime] = None
    location: Optional[str] = None
    capacity: Optional[int] = None


class ParticipantActivityResponse(ORMBase):
    id: UUID
    participant_id: UUID
    activity_id: UUID
    status: str
    created_at: datetime
    participant_name: Optional[str] = None
    dietary_requirements: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 3 — Reporting & Global Participant History
# ---------------------------------------------------------------------------

class ReportSummaryResponse(BaseModel):
    total_registered: int
    missing_flight: int
    missing_hotel: int
    missing_transfer: int


class HotelNightsReportItem(BaseModel):
    night_date: date
    count: int


class GlobalParticipantHistoryItem(BaseModel):
    event_name: str
    event_date: Optional[date] = None
    dietary_requirements: Optional[str] = None


class GlobalParticipantHistoryResponse(BaseModel):
    email: str
    full_name: str
    history: list[GlobalParticipantHistoryItem]


# ---------------------------------------------------------------------------
# Phase 3 — AI Email Agent
# ---------------------------------------------------------------------------

class EmailProposalAnalyzeRequest(BaseModel):
    sender: str
    subject: str
    body: str

class EmailProposalResponse(ORMBase):
    id: UUID
    event_id: UUID
    sender: str
    subject: str
    body: str
    received_at: datetime
    participant_id: Optional[UUID] = None
    status: str
    proposed_changes: dict[str, Any]
    ai_explanation: Optional[str] = None
    created_at: datetime
    participant_name: Optional[str] = None


# ---------------------------------------------------------------------------
# i18n-ready error message constants
# ---------------------------------------------------------------------------
# These constants are the canonical English error messages.
# The frontend is responsible for translating them using their code (key name).

ERR_MAPPING_NOT_CONFIRMED = (
    "Column mapping must be explicitly confirmed (confirmed=true) before it can be saved. "
    "This ensures a human has reviewed the mapping."
)
ERR_UNSUPPORTED_FILE_FORMAT = (
    "Unsupported file format. Only .xlsx, .xls, and .csv files are accepted."
)
ERR_FILE_TOO_LARGE = "File exceeds the maximum allowed size of 50 MB."
ERR_EVENT_NOT_FOUND = "Event not found or access denied."
ERR_PARTICIPANT_NOT_FOUND = "Participant not found."
ERR_EXPORT_NOT_FOUND = "Export not found."
ERR_RUN_NOT_FOUND = "Consolidation run not found."
ERR_FILE_NOT_FOUND = "File not found."
ERR_INSUFFICIENT_ROLE = "You do not have permission to perform this action."
ERR_LOCKED_FIELD = "This field is locked and cannot be modified via re-import."
